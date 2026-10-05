import Foundation
import InkuHost
import InkuPersistence
import InkuUI

// Concrete failures: initial sample DDL became the primary input; model-picker
// cancellation/DDL selection changed the shared model; an unchanged DDL could
// not be rendered with new conditions; layout changes lost checked work IDs.
@MainActor
func runAppParityContractChecks(fixtureDirectory: URL? = nil) async throws {
    let folder = fixtureDirectory ?? FileManager.default.temporaryDirectory.appendingPathComponent("inku-app-parity-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { if fixtureDirectory == nil { try? FileManager.default.removeItem(at: folder) } }
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    guard !FileManager.default.fileExists(atPath: databaseURL.path) else { throw CheckFailure.message("Parity fixture already exists") }
    let model = AppModel(databaseURL: databaseURL, transport: NoParityProviderCalls())
    await model.initialize()
    guard model.errorText == nil, model.inputMode == "description", model.ddlText.isEmpty,
          model.descriptionText.isEmpty, !model.canGenerateDescription else {
        throw CheckFailure.message("A fresh workspace did not start with an empty description")
    }
    let provider = ProviderSettings(id: "fixture", baseURL: URL(string: "http://localhost:1/v1")!,
        requiresAPIKey: false, label: "Offline parity fixture", models: [
            ProviderModelSettings(id: "alpha", label: "LLM A", purposes: ["llm"]),
            ProviderModelSettings(id: "beta", label: "LLM B", purposes: ["llm"]),
        ])
    try await model.updateHostSettings(HostSettings(providers: [provider], models: .init(stage1Model: "fixture:alpha", stage2Model: "fixture:alpha")))
    try await model.selectSharedDrawingModel("fixture:alpha")
    try await model.selectDdlDrawingModel("fixture:beta")
    let settings = await model.hostSettings()
    guard settings.models.stage1Model == "fixture:alpha", settings.models.stage2Model == "fixture:beta",
          model.nextDrawingModelReference == "fixture:alpha" else {
        throw CheckFailure.message("The DDL picker changed the shared next-drawing selection")
    }
    model.seedText = "42"
    model.catalogMode = "fixed"
    let source = "place one green square at center."
    guard await model.drawNewDDL(source), let parent = model.selectedWork else {
        throw CheckFailure.message("Direct DDL fixture failed: \(model.errorText ?? model.status)")
    }
    let editor = DdlEditingSession(work: parent)
    guard editor.draft == source, editor.canSubmit(to: model), await editor.commit(to: model, wildOverride: true),
          let child = model.selectedWork, child.id != parent.id, child.ddl == source, child.renderWild == true else {
        throw CheckFailure.message("Unchanged DDL could not be redrawn with new conditions: \(model.errorText ?? model.status)")
    }
    let database = try InkuDatabase(url: databaseURL)
    let storedParent = try await database.work(id: parent.id)
    guard storedParent == parent, try await database.list().count == 2 else {
        throw CheckFailure.message("The unchanged-DDL edit altered its parent or saved twice")
    }
    model.library.selectedIDs = [parent.id]
    model.library.layout = .list
    await model.library.setPage(0)
    model.library.layout = .grid
    await model.library.setPage(0)
    guard model.library.selectedIDs == [parent.id], model.library.page == 0 else {
        throw CheckFailure.message("A layout change lost the checked work or page")
    }
    await model.selectWork(parent)
    await model.loadWorkActionState(parent)
    guard model.workActionState(for: parent) == .userDDL else { throw CheckFailure.message("DDL provenance did not control its available actions") }
    if fixtureDirectory != nil {
        try JSONEncoder().encode(parent).write(to: folder.appendingPathComponent("native-work.json"), options: .atomic)
        try Data(parent.score.utf8).write(to: folder.appendingPathComponent("native-score.json"), options: .atomic)
        try Data(parent.svg.utf8).write(to: folder.appendingPathComponent("native.svg"), options: .atomic)
        let context = try await model.savedConfiguration(workID: parent.id)
        try context.renderOptions.write(to: folder.appendingPathComponent("native-render-options.json"), options: .atomic)
        model.display.preferences.uiMode = "full"
    }
    print("App parity contract passed: empty description; shared/DDL models separated; unchanged-DDL condition edit saves one immutable-parent child; layout retains checked ID; user-authored DDL availability. Two deterministic works, zero provider calls.")
}

private struct NoParityProviderCalls: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("unexpected_provider_call_in_deterministic_parity_check")
    }
}
