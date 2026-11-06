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
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false,
                                   models: [.init(id: "saved-output")])
    try await app.updateHostSettings(HostSettings(providers: [service],
        models: ModelSelection(stage1Model: "check:saved-output", stage2Model: "check:saved-output")))
    app.selectNextDrawingModel("check:saved-output")
    app.selectDrawRoute("stages"); app.sketchMode = "off"
    app.inputMode = "description"; app.descriptionText = "a red circle"; app.language = "en"; app.seedText = "42"
    await app.generate()
    let parentOutput = await app.outputSnapshot()
    guard app.errorText == nil, let parent = app.selectedWork, !app.sourceLocked,
          parentOutput.promptAvailability == .recorded, !parentOutput.prompt.isEmpty, await provider.calls == 1,
          let separator = parent.id.lastIndex(of: "_") else {
        throw CheckFailure.message("Saved-output parent fixture did not retain its actual prompt journal: \(app.errorText ?? app.status)")
    }
    let executionID = String(parent.id[..<separator])
    let parentContext = try await app.savedConfiguration(workID: parent.id)
    let database = try InkuDatabase(url: databaseURL)
    // The current editor forks a new execution. Exercise the older same-execution
    // revision explicitly so this check still covers unavailable historical output.
    let host = PipelineHost(database: database, transport: provider)
    let later = try await host.perform(executionID: executionID,
        command: .commitUserDDL(expectedRevision: app.authoringRevision, source: "place one blue circle at center."),
        parentWorkID: parent.id, derivationKind: "ddl_edit")
    guard let childID = later.savedWorkID, let child = try await database.work(id: childID), child.id != parent.id,
          later.authority == "ddl_authoritative", child.id.hasPrefix(executionID + "_"), await provider.calls == 1 else {
        throw CheckFailure.message("Saved-output fixture did not make a later DDL save on the same execution: \(later.phase)")
    }
    let originalEffect = "save-render:" + String(parent.id[parent.id.index(after: separator)...])
    let acknowledgement = try await database.acknowledgement(executionID: executionID, effectID: originalEffect)
    guard let acknowledgement, let originalExecution = try await database.loadExecution(id: executionID),
          let root = parent.lineageNodeID else { throw CheckFailure.message("Saved-output parent context missing") }
    var legacyContext = try ExactJSON(data: acknowledgement)["performance"]
    legacyContext["presentation"] = .null
    var legacy = parent
    legacy.id = executionID + "_999999"; legacy.lineageNodeID = UUID().uuidString; legacy.at -= 1
    let node = LineageNode(id: legacy.lineageNodeID!, historyID: legacy.id, at: legacy.at,
                           descriptionHash: legacy.descriptionHash, renderHash: legacy.renderHash, rootNodeID: root)
    let edge = LineageEdge(id: UUID().uuidString, parentNodeID: root, childNodeID: node.id,
                           derivationKind: "saved-output-legacy-fixture", at: legacy.at)
    let legacyAck = ExactJSON.object(["tag": .string("saved_work_committed"), "work_id": .string(legacy.id),
                                      "performance": legacyContext]).data
    _ = try await database.commitEffect(id: executionID, expectedRevision: originalExecution.revision, effectID: "save-render:999999",
        snapshot: originalExecution.snapshot, acknowledgement: legacyAck, work: legacy, node: node, edge: edge)
    let reopened = AppModel(databaseURL: databaseURL, transport: provider)
    await reopened.initialize()
    guard reopened.errorText == nil else { throw CheckFailure.message("Saved-output reopen failed: \(reopened.errorText ?? reopened.status)") }
    let rows = try await database.list()
    guard rows.count == 3, let execution = try await database.loadExecution(id: executionID) else {
        throw CheckFailure.message("Saved-output fixture is missing its two saved revisions or durable execution")
    }
    let calls = await provider.calls

    // Failure: selecting an older saved parent called an unavailable prompt journal "not sent".
    await reopened.selectWork(legacy)
    let reopenedOutput = await reopened.outputSnapshot()
    guard reopened.errorText == nil, reopened.selectedWork == legacy,
          reopened.visibleDDL == legacy.ddl, reopenedOutput.score == legacy.score, reopened.currentSVG == legacy.svg,
          reopened.authoringAuthority == parentContext.authority, reopened.authoringRevision == parentContext.revision,
          !reopened.sourceLocked, reopenedOutput.promptAvailability == .unavailable, reopenedOutput.prompt.isEmpty,
          reopened.diagnosticsJSON.isEmpty, reopenedOutput.events.isEmpty,
          await provider.calls == calls, try await database.list() == rows,
          try await database.loadExecution(id: executionID) == execution,
          try await database.work(id: legacy.id) == legacy, try await database.work(id: child.id) == child else {
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
