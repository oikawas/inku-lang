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
    // Drawing takes only registered models.
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                    models: ["first", "changed"].map { ProviderModelSettings(id: $0) })
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
    try await retryFailuresCheck(directory: directory.appendingPathComponent("retry", isDirectory: true), provider: provider)
    print("Batch passed: original line numbers; failed-only retry; explicit exhausted-round resume keeps pinned models; crash-ambiguous rows wait for a choice; skip sends no request; retrying failures draws only the failed row with its pinned model and leaves a waiting row waiting. Offline mock only.")
}

/// Failure: "retry failed works" drew rows that had not failed, used the current conditions, or left a
/// succeeded row in the failure list (Web BatchState.retryFailed).
@MainActor private func retryFailuresCheck(directory: URL, provider: ProviderSettings) async throws {
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let transport = BatchRetryProvider()
    let app = AppModel(databaseURL: directory.appendingPathComponent("works.sqlite"), transport: transport)
    await app.initialize()
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:first", stage2Model: "check:first")))
    app.inputMode = "description"; app.display.preferences.batchRetries = 0
    let batch = AutomationModel()
    await batch.connect(app: app)
    batch.batchText = "alpha red circle\nbeta blue square\ngamma green dot"
    await batch.startBatch(app: app)
    guard batch.rows.map(\.state) == [.succeeded, .failed, .failed] else {
        throw CheckFailure.message("Retry fixture did not start with one success and two failures: \(batch.rows.map(\.state))")
    }
    // The third row becomes one the batch never reached.
    let journalURL = directory.appendingPathComponent("batch-journal.json")
    var object = try JSONSerialization.jsonObject(with: Data(contentsOf: journalURL)) as! [String: Any]
    var rows = object["rows"] as! [[String: Any]]
    rows[2]["state"] = "waiting"; rows[2]["error"] = nil; object["rows"] = rows
    try JSONSerialization.data(withJSONObject: object).write(to: journalURL, options: .atomic)
    let reopened = AutomationModel()
    await reopened.connect(app: app)
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:changed", stage2Model: "check:changed")))
    await transport.succeedFromNowOn()
    guard reopened.canRetryFailures else { throw CheckFailure.message("A stopped batch with a failed row offered no retry") }
    await reopened.retryFailures(app: app)
    let sent = await transport.drawn
    guard sent.map(\.input) == ["alpha", "beta", "gamma", "beta"], sent.last?.model == "check:first",
          reopened.rows.map(\.state) == [.succeeded, .succeeded, .waiting], !reopened.canRetryFailures,
          !reopened.running, !app.isBusy else {
        throw CheckFailure.message("Retrying failures drew \(sent) and left \(reopened.rows.map(\.state))")
    }
}

/// Fails every row until told otherwise, except the first row; answers the composition reading as refused so
/// the core falls back to its default reading.
private actor BatchRetryProvider: ProviderTransport {
    private(set) var drawn: [(input: String, model: String)] = []
    private var succeedAll = false
    func succeedFromNowOn() { succeedAll = true }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let value = try ExactJSON(data: action)
        guard value["tag"].string == "generate_normalized_ddl" else {
            return ExactJSON.object(["tag": .string("provider_failed"), "identity": value["identity"],
                "failure": .string("provider_rejected"), "elapsed_ms": .string("1")]).data
        }
        let message = value["payload"]["prompt"]["message"].string ?? ""
        let input = ["alpha", "beta", "gamma"].first { message.contains($0) } ?? "?"
        drawn.append((input, models.stage1Model))
        guard succeedAll || input == "alpha" else { throw HostError("forced_offline_batch_failure") }
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": value["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
    }
}

private actor BatchFailureProvider: ProviderTransport {
    private(set) var models: [String] = []
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        self.models.append(models.stage1Model)
        throw HostError("forced_offline_batch_failure")
    }
}
