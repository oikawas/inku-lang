import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// Web DdlViewer and DdlEditorDialog: the box keeps a draft of the displayed work's instructions, drawn only on
/// request; another work starts from its own; the editor's discard returns to the work's saved instructions.
@MainActor func runDdlBoxChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-ddl-box-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), transport: DdlBoxNoProvider())
    await app.initialize()
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                    models: [ProviderModelSettings(id: "m")])
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:m", stage2Model: "check:m")))
    guard await app.drawNewDDL("place one red circle at center."), let parent = app.displayedWork, let saved = parent.ddl else {
        throw CheckFailure.message("Parent failed: \(app.errorText ?? app.status)")
    }
    // Failure: typing in the box changed the work, or the draft was lost before drawing.
    let edited = "place one blue square at center."
    guard app.ddlBoxText(for: parent) == saved else { throw CheckFailure.message("Box did not start from the saved instructions") }
    app.setDdlBoxText(edited, for: parent)
    guard app.ddlBoxText(for: parent) == edited, app.displayedWork?.ddl == saved, app.works.count == 1 else {
        throw CheckFailure.message("Typing in the box drew or lost the draft")
    }
    // Failure: "Draw from instructions" drew the saved text instead of the draft (ContentView draw-ddl).
    guard await app.drawEditedDDL(work: parent, source: app.ddlBoxText(for: parent)), let child = app.displayedWork,
          child.id != parent.id, child.ddl == edited else {
        throw CheckFailure.message("Drawing from the box did not draw its draft: \(app.errorText ?? app.status)")
    }
    // Failure: a draft followed the author to another work.
    guard app.ddlBoxText(for: child) == edited, app.ddlBoxText(for: parent) == saved else {
        throw CheckFailure.message("The box draft belonged to the wrong work")
    }
    // Failure: the editor's discard returned to the box draft, or a new DDL offered a discard.
    guard DdlEditingSession(work: parent, draft: "draft text").discardTarget == saved,
          DdlEditingSession(work: parent, draft: "draft text").draft == "draft text",
          DdlEditingSession(model: app).discardTarget == nil else {
        throw CheckFailure.message("Editor discard target was wrong")
    }
    print("DDL box passed: the draft is kept per displayed work and never draws by itself; drawing from the box draws the draft once; another work starts from its own instructions; the editor opens on the draft and discards back to the saved instructions; a new DDL has no discard. Real core, no provider.")
}

private actor DdlBoxNoProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("ddl_box_check_sends_nothing")
    }
}
