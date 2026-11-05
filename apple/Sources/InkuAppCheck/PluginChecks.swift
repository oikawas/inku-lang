import Foundation
import InkuHost
import InkuUI

/// Failure: disabling a bundled plugin changes a saved work's pinned definitions or export.
@MainActor
func runPluginChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plugin-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let model = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"))
    await model.initialize()
    model.inputMode = "ddl"
    model.language = "ja"
    model.ddlText = "｛若葉｝を置く"
    model.seedText = "42"
    await model.generate()
    guard model.errorText == nil, let saved = model.selectedWork else {
        throw CheckFailure.message("Plugin source did not save: \(model.errorText ?? model.status)")
    }
    let before = try await model.savedConfiguration(workID: saved.id)
    let definitions = try ExactJSON(data: before.configuration)["definitions"].array ?? []
    guard !definitions.isEmpty, !model.pluginWords.isEmpty else { throw CheckFailure.message("Plugin fixture has no definitions") }
    var settings = await model.hostSettings()
    settings.plugins = PluginPreferences(disabledPackageIDs: Set(model.pluginWords.compactMap(\.packageID)))
    try await model.updateHostSettings(settings)

    model.newWork()
    model.inputMode = "ddl"; model.ddlText = "中心に円を置く。"
    let next = try model.requestForCurrentInput()
    guard try ExactJSON(data: next.configuration)["definitions"].array?.isEmpty == true else {
        throw CheckFailure.message("Disabled plugin leaked into a fresh request")
    }
    let after = try await model.savedConfiguration(workID: saved.id)
    let sources = try await model.prepareExportSources(works: [saved], profile: "editable", requiresPluginDefinitions: true)
    guard before.configuration == after.configuration, before.document == after.document,
          sources.count == 1, sources[0].pluginDefinitions == definitions,
          sources[0].work == saved, !(try sources[0].svg(profile: "editable")).isEmpty else {
        throw CheckFailure.message("Plugin preferences altered a saved definition, document, or export context")
    }
    try await checkDescriptionForkPluginPreferences(folder: folder)
    print("Plugin selection passed: disabled definitions stay out of new requests; saved document, definitions, and editable/DDL export context remain pinned. Mock provider only.")
}

/// A description child must use current plugin preferences, while a DDL child retains its parent's definitions.
@MainActor
private func checkDescriptionForkPluginPreferences(folder: URL) async throws {
    let transport = PluginForkProvider()
    let model = AppModel(databaseURL: folder.appendingPathComponent("description-fork.sqlite"), transport: transport)
    await model.initialize()
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                    models: [ProviderModelSettings(id: "model")])
    try await model.updateHostSettings(HostSettings(providers: [provider],
        models: ModelSelection(stage1Model: "check:model", stage2Model: "check:model")))
    model.selectNextDrawingModel("check:model")
    model.inputMode = "description"; model.drawRoute = "stages"; model.sketchMode = "off"
    model.language = "ja"; model.catalogID = "default"; model.canvasID = "square"; model.seedText = "42"
    model.descriptionText = "若葉を中心に置く"
    await model.generate()
    guard model.errorText == nil, let parent = model.selectedWork, let ddl = parent.ddl else {
        throw CheckFailure.message("Plugin description parent: \(model.errorText ?? model.status)")
    }
    guard parent.drawRoute == "stages", parent.sketchRequested == "0", parent.compositionRequested == "1", parent.catalogMode == "fixed" else {
        throw CheckFailure.message("Description work did not record its drawing options")
    }
    let saved = try ExactJSON(data: (try await model.savedConfiguration(workID: parent.id)).configuration)
    guard saved["definitions"].array?.count == 7 else { throw CheckFailure.message("Plugin description parent must retain seven definitions") }
    var settings = await model.hostSettings()
    settings.plugins = PluginPreferences(disabledPackageIDs: Set(model.pluginWords.compactMap(\.packageID)))
    try await model.updateHostSettings(settings)
    await model.selectWork(parent)
    let a = try model.requestForCurrentInput(inputMode: "description", description: parent.effectiveSourceText,
                                              parentWorkID: parent.id, derivationKind: "description_edit")
    let b = try await model.makeSavedWorkEditRequest(work: parent, mode: .description, description: parent.effectiveSourceText)
    let c = try await model.makeRefinementRequest(work: parent, kind: "model_comparison")
    let d = try model.requestForCurrentInput(inputMode: "ddl", source: ddl, parentWorkID: parent.id, derivationKind: "ddl_edit")
    let configurations = try [a, b, c, d].map { try ExactJSON(data: $0.configuration) }
    let counts = configurations.map { $0["definitions"].array?.count ?? -1 }
    let summaries = configurations.map { $0["macro_summaries"].array?.count ?? -1 }
    FileHandle.standardError.write(Data("Plugin fork definitions (a,b,c,d): \(counts); summaries: \(summaries)\n".utf8))
    guard counts == [0, 0, 0, 7], summaries == [0, 0, 0, 7] else {
        throw CheckFailure.message("Plugin fork preferences: expected definitions and summaries [0, 0, 0, 7]")
    }
}

private actor PluginForkProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": input["identity"],
                                 "response": .string(#"{"normalized_ddl":"｛若葉｝を中心に置く。"}"#),
                                 "elapsed_ms": .string("1")]).data
    }
}
