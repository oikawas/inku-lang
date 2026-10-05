import Foundation
import InkuHost
import InkuUI

@MainActor func runAutomationChecks() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-batch-boundary-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let transport = BatchFailureProvider()
    let app = AppModel(databaseURL: directory.appendingPathComponent("works.sqlite"), transport: transport)
    await app.initialize()
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false)
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:first", stage2Model: "check:first")))
    app.inputMode = "description"; app.display.preferences.batchRetries = 1
    let batch = AutomationModel()
    await batch.connect(app: app)
    batch.batchText = "\n  one red circle  \n"
    await batch.startBatch(app: app)

    // Failure: an explicit resume after exhausting retries ran zero rows, or adopted new UI conditions.
    guard batch.rows.count == 1, batch.rows[0].line == 2, batch.rows[0].state == .failed,
          batch.rows[0].attempts == 2, batch.canResume else { throw CheckFailure.message("Initial failed-row retry bookkeeping changed") }
    let firstCallCount = await transport.models.count
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:changed", stage2Model: "check:changed")))
    await batch.resumeBatch(app: app)
    guard firstCallCount > 0, batch.rows[0].attempts == 4,
          await transport.models == Array(repeating: "check:first", count: firstCallCount * 2),
          !batch.running, !app.isBusy, app.works.isEmpty else {
        throw CheckFailure.message("Explicit resume did not retry the pinned request after exhausting its round")
    }

    // Failure: a crash after sending a request automatically sent the ambiguous row again.
    let journalURL = directory.appendingPathComponent("batch-journal.json")
    var object = try JSONSerialization.jsonObject(with: Data(contentsOf: journalURL)) as! [String: Any]
    var rows = object["rows"] as! [[String: Any]]
    rows[0]["state"] = "running"; object["rows"] = rows
    try JSONSerialization.data(withJSONObject: object).write(to: journalURL, options: .atomic)
    let recovered = AutomationModel()
    await recovered.connect(app: app)
    await recovered.resumeBatch(app: app)
    guard recovered.uncertainCount == 1, await transport.models.count == firstCallCount * 2 else { throw CheckFailure.message("Recovery resent an ambiguous request") }
    await recovered.resolveUncertain(id: recovered.rows[0].id, retry: false)
    guard recovered.rows[0].state == .skipped, !recovered.canResume,
          await transport.models.count == firstCallCount * 2 else { throw CheckFailure.message("Explicit skip invoked a model") }
    print("Batch passed: original line numbers; failed-only retry; explicit exhausted-round resume keeps pinned models; crash-ambiguous rows wait for a choice; skip sends no request. Offline mock only.")
}

private actor BatchFailureProvider: ProviderTransport {
    private(set) var models: [String] = []
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        self.models.append(models.stage1Model)
        throw HostError("forced_offline_batch_failure")
    }
}
