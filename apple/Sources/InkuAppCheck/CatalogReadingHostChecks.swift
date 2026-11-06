import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor func runCatalogReadingHostCheck() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-catalog-reading-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let provider = CatalogReadingProvider()
    let app = AppModel(databaseURL: folder.appendingPathComponent("bootstrap.sqlite"), transport: provider)
    await app.initialize()
    app.selectDrawRoute("stages"); app.sketchMode = "off"
    let service = ProviderSettings(id: "laws-check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false, models: [.init(id: "pinned")])
    let models = ModelSelection(stage1Model: "laws-check:pinned", stage2Model: "laws-check:pinned")
    try await app.updateHostSettings(HostSettings(providers: [service], models: models))
    app.selectNextDrawingModel("laws-check:pinned")
    app.inputMode = "description"; app.descriptionText = "赤い円がひとつ浮かび、下に黒い点が散らばる"
    app.language = "ja"; app.seedText = "7"; app.catalogMode = "auto"
    let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
    let host = PipelineHost(database: database, transport: provider, credentials: CatalogReadingCredentials())
    let request = try app.requestForCurrentInput()
    let result: PipelineView
    do { result = try await host.generate(request) } catch { throw CheckFailure.message("initial generate: \(error)") }
    guard result.phase == "completed", let id = result.savedWorkID, let ddl = result.visibleDDL else {
        throw CheckFailure.message("Catalog reading run did not save: \(result.phase) \(String(decoding: result.eventsJSON, as: UTF8.self))")
    }
    let saved = try await host.savedAuthoringContext(workID: id)
    guard let data = saved.catalogReading else { throw CheckFailure.message("No saved catalog reading") }
    let reading = try ExactJSON(data: data)
    let config = try ExactJSON(data: saved.configuration)
    guard reading["method"].string == "model", let chosen = reading["candidate_order"].array?.first?.string,
          reading["catalog_id"].string == chosen,
          config["compiler"]["host"]["resolved_catalog_id"].string == chosen else {
        throw CheckFailure.message("Choice was not resolved to saved catalog: \(reading.text)")
    }
    let presentation = try await host.savedWorkPresentation(workID: id)
    let prompts = try presentation.promptJSON.map { try ExactJSON(data: $0).array ?? [] } ?? []
    guard presentation.promptStages.contains("catalog_reading"), presentation.promptStages.contains("catalog"),
          prompts.contains(where: { $0["prompt"]["prompt_id"].string == "inku.description-color-reading-prompt.v1" }),
          prompts.contains(where: { $0["prompt"]["prompt_id"].string == "inku.description-catalog-choice-prompt.v1" }) else {
        throw CheckFailure.message("Saved prompts do not contain both catalog stages: \(presentation.promptStages)")
    }
    var childConfig = try ExactJSON(data: saved.configuration)
    childConfig["catalogs"] = .array([])
    childConfig["compiler"]["host"]["catalog_mode"] = .string(chosen == "default" ? "default" : "explicit")
    if var fields = childConfig.object { fields.removeValue(forKey: "catalog_seed"); childConfig = .object(fields) }
    let childRequest = GenerationRequest(authoring: .directDDL(ddl), configuration: childConfig.data, renderOptions: saved.renderOptions,
        clipPolicy: saved.clipPolicy, models: models, providers: [service], description: app.descriptionText, parentWorkID: id, derivationKind: "ddl_edit")
    let child: PipelineView
    do { child = try await host.generate(childRequest) } catch { throw CheckFailure.message("child generate: \(error)") }
    guard child.phase == "completed", let childID = child.savedWorkID,
          try await host.savedAuthoringContext(workID: childID).catalogReading == nil else { throw CheckFailure.message("Child inherited catalog reading") }
    await provider.emptyReading()
    let before = await provider.catalogActions
    let empty: PipelineView
    do { empty = try await host.generate(request) } catch { throw CheckFailure.message("empty generate: \(error)") }
    guard empty.phase == "completed", let emptyID = empty.savedWorkID,
          let emptyData = try await host.savedAuthoringContext(workID: emptyID).catalogReading,
          try ExactJSON(data: emptyData)["method"].string == "seed",
          await provider.catalogActions == before + 1 else { throw CheckFailure.message("Empty reading did not take seed path") }
    print("Catalog reading host passed: model reading and k01 choice saved; both prompt stages saved; direct child does not inherit; empty reading chooses by seed with one send. Real core, fake provider, temporary DB.")
}

private actor CatalogReadingCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}

private actor CatalogReadingProvider: ProviderTransport {
    private let rest = LawsColorsCheckProvider(refuseColors: false)
    private var isEmpty = false
    private(set) var catalogActions = 0
    func emptyReading() { isEmpty = true }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        guard input["tag"].string == "select_description_catalog" else {
            return try await rest.perform(action: action, models: models, providers: providers, credentials: credentials, onBytes: onBytes)
        }
        catalogActions += 1
        let id = input["payload"]["prompt"]["prompt_id"].string
        let answer: ExactJSON
        if id == "inku.description-color-reading-prompt.v1" {
            let none: ExactJSON = .object(["value": .string("none"), "quote": .string("")])
            let colors: [ExactJSON] = isEmpty ? [] : [.object(["word": .string("赤"), "lightness": .string("none"), "vividness": .string("none"), "quote": .string("赤")])]
            answer = .object(["note": .string(""), "brightness": none, "vividness": none, "warmth": none, "colors": .array(colors)])
        } else if id == "inku.description-catalog-choice-prompt.v1" {
            answer = .object(["catalog_id": .string("k01")])
        } else { throw HostError("unexpected_catalog_prompt") }
        return ExactJSON.object(["tag": .string("description_catalog_selected"), "identity": input["identity"],
            "response": .string(answer.text), "elapsed_ms": .string("10")]).data
    }
}
