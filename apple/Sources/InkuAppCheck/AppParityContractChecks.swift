import Foundation
import InkuHost
import InkuPersistence
import InkuUI
import SQLite3

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
    try await model.selectSharedDrawingModel("fixture:beta")
    let settings = await model.hostSettings()
    guard settings.models.stage1Model == "fixture:alpha", settings.models.stage2Model == "fixture:alpha",
          model.nextDrawingModelReference == "fixture:beta" else {
        throw CheckFailure.message("The next drawing model was not selected independently of saved defaults")
    }
    model.seedText = "42"
    model.catalogMode = "fixed"
    let source = "place one green square at center."
    guard await model.drawNewDDL(source), let parent = model.selectedWork, parent.stage2Model == "fixture:beta" else {
        throw CheckFailure.message("Direct DDL fixture failed: \(model.errorText ?? model.status)")
    }
    let editor = DdlEditingSession(work: parent)
    model.wild = true
    try await model.selectSharedDrawingModel("fixture:alpha")
    let permitted = editor.canSubmit(to: model)
    let committed = await editor.commit(to: model)
    guard editor.draft == parent.ddl, permitted, committed,
          let child = model.selectedWork, child.id != parent.id, child.ddl == parent.ddl, child.renderWild == parent.renderWild,
          child.stage2Model == "fixture:alpha" else {
        throw CheckFailure.message("Unchanged DDL redraw did not preserve its instructions and recorded wild or use the next model: \(model.errorText ?? model.status)")
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
    model.wild = true
    guard await model.drawNewDDL(source), let wildParent = model.selectedWork, wildParent.renderWild == true else {
        throw CheckFailure.message("New DDL did not use the tab's wild setting: \(model.errorText ?? model.status)")
    }
    model.wild = false
    let editedSource = "place one red circle at center."
    guard await model.drawEditedDDL(work: wildParent, source: editedSource),
          model.selectedWork?.renderWild == true else {
        throw CheckFailure.message("Edited DDL did not use its parent's recorded wild: \(model.errorText ?? model.status)")
    }
    // Model a legacy row with no recorded wild while its saved render options still have wild on.
    var sqlite: OpaquePointer?
    guard sqlite3_open(databaseURL.path, &sqlite) == SQLITE_OK, let sqlite else {
        if let sqlite { sqlite3_close(sqlite) }
        throw CheckFailure.message("Could not open the isolated legacy fixture")
    }
    let escapedID = wildParent.id.replacingOccurrences(of: "'", with: "''")
    let updateResult = sqlite3_exec(sqlite, "UPDATE history SET render_wild = NULL WHERE id = '\(escapedID)'", nil, nil, nil)
    let updatedRows = sqlite3_changes(sqlite)
    sqlite3_close(sqlite)
    guard updateResult == SQLITE_OK, updatedRows == 1,
          let legacy = try await database.work(id: wildParent.id), legacy.renderWild == nil else {
        throw CheckFailure.message("Could not make the missing-wild fixture")
    }
    model.wild = true
    guard await model.drawEditedDDL(work: legacy, source: editedSource), model.selectedWork?.renderWild == false else {
        throw CheckFailure.message("Edited DDL with no recorded wild did not default to off: \(model.errorText ?? model.status)")
    }
    if fixtureDirectory != nil {
        try JSONEncoder().encode(parent).write(to: folder.appendingPathComponent("native-work.json"), options: .atomic)
        try Data(parent.score.utf8).write(to: folder.appendingPathComponent("native-score.json"), options: .atomic)
        try Data(parent.svg.utf8).write(to: folder.appendingPathComponent("native.svg"), options: .atomic)
        let context = try await model.savedConfiguration(workID: parent.id)
        try context.renderOptions.write(to: folder.appendingPathComponent("native-render-options.json"), options: .atomic)
        model.display.preferences.uiMode = "full"
    }
    print("App parity contract passed: empty description; new DDL uses tab wild; edited DDL uses recorded wild or off; unchanged-DDL model edit saves one immutable-parent child; layout retains checked ID; user-authored DDL availability. Deterministic works, zero provider calls.")
}

private struct NoParityProviderCalls: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("unexpected_provider_call_in_deterministic_parity_check")
    }
}
