import Foundation
import InkuHost
import InkuPersistence
import InkuUI

// Compare the alias map to the Server's observed output, then use a seed that
// chooses the additional Deep Red candidate rather than the base red color.
@MainActor
func runPaletteAliasParityChecks(expectedMap: Data, fixtureDirectory: URL?, legacyDirectory: URL?) async throws {
    let folder = fixtureDirectory ?? FileManager.default.temporaryDirectory.appendingPathComponent("inku-palette-alias-\(UUID().uuidString)")
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    guard !FileManager.default.fileExists(atPath: databaseURL.path) else { throw CheckFailure.message("Palette alias fixture already exists") }
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { if fixtureDirectory == nil { try? FileManager.default.removeItem(at: folder) } }
    let app = AppModel(databaseURL: databaseURL, transport: PaletteAliasNoProvider())
    await app.initialize()
    let provider = ProviderSettings(id: "fixture", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
        label: "Offline palette alias fixture", models: [ProviderModelSettings(id: "alpha", label: "LLM A", purposes: ["llm"])])
    try await app.updateHostSettings(HostSettings(providers: [provider], models: .init(stage1Model: "fixture:alpha", stage2Model: "fixture:alpha")))
    app.seedText = "43"
    app.catalogMode = "fixed"
    let source = "place one red square at center."
    guard await app.drawNewDDL(source), let work = app.selectedWork else {
        throw CheckFailure.message("Named palette fixture did not draw: \(app.errorText ?? app.status)")
    }
    let context = try await app.savedConfiguration(workID: work.id)
    let options = try ExactJSON(data: context.renderOptions)
    let observedMap = try ExactJSON(data: expectedMap)
    guard options["resolved_color_map"] == observedMap,
          work.svg.contains("#7c2f26"), options["render_seed"].string == "43" else {
        throw CheckFailure.message("Server palette aliases or the additional Deep Red color did not reach the drawing")
    }
    if let legacyDirectory {
        let database = try InkuDatabase(url: legacyDirectory.appendingPathComponent("inku.sqlite"))
        let host = PipelineHost(database: database, transport: PaletteAliasNoProvider())
        let oldWorks = try await database.list()
        guard let old = oldWorks.first else { throw CheckFailure.message("Legacy palette fixture is empty") }
        let previous = try await host.savedAuthoringContext(workID: old.id)
        let previousMap = try ExactJSON(data: previous.renderOptions)["resolved_color_map"]
        guard previousMap.object?.count == 9, previousMap["palette:Deep Red"] == .null,
              try await host.exportSVG(workID: old.id, profile: "display") == old.svg,
              try await host.savedAuthoringContext(workID: old.id).renderOptions == previous.renderOptions,
              try await database.list() == oldWorks else {
            throw CheckFailure.message("Reading or replaying a saved palette extended its frozen map or changed history")
        }
    }
    if fixtureDirectory != nil {
        try Data(work.score.utf8).write(to: folder.appendingPathComponent("native-score.json"), options: .atomic)
        try Data(work.svg.utf8).write(to: folder.appendingPathComponent("native.svg"), options: .atomic)
        try context.renderOptions.write(to: folder.appendingPathComponent("native-render-options.json"), options: .atomic)
    }
    print("Palette alias parity passed: observed Server color map matches; red seed43 uses Deep Red; recorded legacy nine-color map, SVG and history stay unchanged. Provider0.")
}

private struct PaletteAliasNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("unexpected_provider_call_in_palette_alias_check")
    }
}
