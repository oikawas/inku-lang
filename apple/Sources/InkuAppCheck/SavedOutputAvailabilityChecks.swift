import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runSavedOutputAvailabilityChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-saved-output-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("works.sqlite")
    let provider = SavedOutputAvailabilityProvider()
    let app = AppModel(databaseURL: databaseURL, transport: provider)
    await app.initialize()
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false)
    try await app.updateHostSettings(HostSettings(providers: [service],
        models: ModelSelection(stage1Model: "check:saved-output", stage2Model: "check:saved-output")))
    app.inputMode = "description"; app.descriptionText = "a red circle"; app.language = "en"; app.seedText = "42"
    await app.generate()
    guard app.errorText == nil, let parent = app.selectedWork, !app.sourceLocked,
          app.promptAvailability == .recorded, !app.promptJSON.isEmpty, await provider.calls == 1,
          let separator = parent.id.lastIndex(of: "_") else {
        throw CheckFailure.message("Saved-output parent fixture did not retain its actual prompt journal: \(app.errorText ?? app.status)")
    }
    let executionID = String(parent.id[..<separator])
    let parentContext = try await app.savedConfiguration(workID: parent.id)
    app.ddlText = "place one blue circle at center."
    await app.commitDDL()
    guard app.errorText == nil, let child = app.selectedWork, child.id != parent.id, app.sourceLocked,
          child.id.hasPrefix(executionID + "_"), await provider.calls == 1 else {
        throw CheckFailure.message("Saved-output fixture did not make a later DDL save on the same execution: \(app.errorText ?? app.status)")
    }

    let database = try InkuDatabase(url: databaseURL)
    let reopened = AppModel(databaseURL: databaseURL, transport: provider)
    await reopened.initialize()
    guard reopened.errorText == nil else { throw CheckFailure.message("Saved-output reopen failed: \(reopened.errorText ?? reopened.status)") }
    let rows = try await database.list()
    guard rows.count == 2, let execution = try await database.loadExecution(id: executionID) else {
        throw CheckFailure.message("Saved-output fixture is missing its two saved revisions or durable execution")
    }
    let calls = await provider.calls

    // Failure: selecting an older saved parent called an unavailable prompt journal "not sent".
    await reopened.selectWork(parent)
    guard reopened.errorText == nil, reopened.selectedWork == parent,
          reopened.visibleDDL == parent.ddl, reopened.scoreJSON == parent.score, reopened.currentSVG == parent.svg,
          reopened.authoringAuthority == parentContext.authority, reopened.authoringRevision == parentContext.revision,
          !reopened.sourceLocked, reopened.promptAvailability == .unavailable, reopened.promptJSON.isEmpty,
          reopened.diagnosticsJSON.isEmpty, reopened.eventsJSON.isEmpty,
          await provider.calls == calls, try await database.list() == rows,
          try await database.loadExecution(id: executionID) == execution,
          try await database.work(id: parent.id) == parent, try await database.work(id: child.id) == child else {
        throw CheckFailure.message("Saved parent adopted a later output, misreported prompt availability, changed authority/history or called a provider")
    }
    print("Saved output availability passed: real core parent -> same-execution DDL child -> old parent selection; missing prompt is unavailable, saved DDL/Score/SVG/authority retained, no provider call or history/execution write. Isolated mock only.")
}

private actor SavedOutputAvailabilityProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        let input = try ExactJSON(data: action)
        guard input["tag"].string == "generate_normalized_ddl" else { throw HostError("saved_output_unexpected_provider_action") }
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": input["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
    }
}
