import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runDdlEditorCancelChecks() async throws {
    // Failure: typing in the always-visible DDL editor changed authoring input before confirmation.
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-ddl-editor-cancel-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let url = folder.appendingPathComponent("works.sqlite")
    let transport = DdlEditorNoProvider()
    let model = AppModel(databaseURL: url, transport: transport)
    await model.initialize()
    model.inputMode = "ddl"; model.language = "en"; model.seedText = "42"
    model.ddlText = "place one red circle at center."
    await model.generate()
    guard model.errorText == nil, let work = model.selectedWork else {
        throw CheckFailure.message("DDL editor cancellation fixture did not save: \(model.errorText ?? model.status)")
    }
    let database = try InkuDatabase(url: url)
    let rows = try await database.list()
    let source = model.ddlText
    let svg = model.currentSVG
    let revision = model.authoringRevision
    let session = DdlEditingSession(model: model)
    session.draft = "place one blue square at center."
    session.insert("a thin line")
    guard model.ddlText == source, model.visibleDDL == work.ddl, model.currentSVG == svg,
          session.draft.contains("blue square"), session.draft.contains("a thin line") else {
        throw CheckFailure.message("Independent DDL typing or Saijiki insertion changed the displayed work")
    }
    session.cancel()
    guard model.ddlText == source, model.visibleDDL == work.ddl, model.currentSVG == svg,
          model.authoringRevision == revision, model.selectedWork == work,
          try await database.list() == rows, try await database.work(id: work.id) == work,
          await transport.calls == 0 else {
        throw CheckFailure.message("Cancelling DDL editing changed source, SVG, revision, history or sent a provider request")
    }
    print("DDL editor cancel passed: one saved core work; typing and explicit Saijiki insertion stay in the editor draft; cancellation leaves DDL/SVG/revision/history unchanged. No provider calls.")
}

private actor DdlEditorNoProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw CheckFailure.message("DDL editor cancellation must not call a provider")
    }
}
