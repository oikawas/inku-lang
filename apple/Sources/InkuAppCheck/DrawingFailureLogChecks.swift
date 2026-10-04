import CryptoKit
import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runDrawingFailureLogChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-drawing-failure-log-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    let provider = DrawingFailureLogProvider()
    let app = AppModel(databaseURL: databaseURL, transport: provider)
    await app.initialize()
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://127.0.0.1:1")!, requiresAPIKey: false)
    try await app.updateHostSettings(HostSettings(providers: [service], models: ModelSelection(stage1Model: "check:pinned", stage2Model: "check:pinned")))
    app.inputMode = "description"; app.descriptionText = "A red circle above black dots scattered at the bottom"
    app.seedText = "42"; app.sketchMode = "off"; app.catalogMode = "fixed"
    let maintenance = LocalMaintenance(); maintenance.connect(app: app)
    var terminal: DrawingLogRecord?
    app.onDrawingLog = { record in
        await maintenance.log(execution: record, enabled: true)
        if record.isTerminal { terminal = record }
    }

    // Failure: the failed performance was saved but could not be reopened or written to a result log.
    await app.generate()
    let logs = try await app.drawingLogs()
    guard let failed = logs.first, logs.count == 1, failed.phase == "failed",
          failed.failureReason == "transport_unavailable", failed.failureStage == "generate_normalized_ddl",
          failed.description == app.descriptionText, failed.providerMetrics.count == 4,
          failed.providerMetrics.allSatisfy({ $0.diagnostic?.errorCode == URLError.cannotConnectToHost.rawValue
              && $0.failure == "transport_unavailable" && $0.httpStatus == nil && !$0.sent }),
          failed.events.last?.tag == "failed", app.works.isEmpty else {
        throw CheckFailure.message("Failed execution lost its description, terminal state, safe diagnostics or event history")
    }
    let name = SHA256.hash(data: Data(failed.id.utf8)).map { String(format: "%02x", $0) }.joined() + ".json"
    let file = folder.appendingPathComponent("drawing-logs").appendingPathComponent(name)
    for _ in 0..<50 where terminal == nil { try await Task.sleep(for: .milliseconds(10)) }
    guard terminal?.id == failed.id, FileManager.default.fileExists(atPath: file.path) else {
        throw CheckFailure.message("Failed execution did not reach the file-log callback")
    }
    let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
    let fileLog = try decoder.decode(DrawingLogRecord.self, from: Data(contentsOf: file))
    let fileJSON = String(decoding: try Data(contentsOf: file), as: UTF8.self)
    guard fileLog.phase == "failed", fileLog.events == failed.events, fileLog.providerMetrics == failed.providerMetrics,
          !fileJSON.contains("requestBody"), !fileJSON.contains("responseBody"), !fileJSON.contains("raw"),
          !fileJSON.contains("credentialID"), !fileJSON.contains("Authorization"), maintenance.logStatus.isEmpty else {
        throw CheckFailure.message("File log lost terminal facts or included private provider IO/settings")
    }
    let starts = await provider.calls
    let reopened = AppModel(databaseURL: databaseURL, transport: provider)
    await reopened.initialize()
    guard try await reopened.drawingLogs() == logs, await provider.calls == starts else {
        throw CheckFailure.message("Reading failure logs after restart changed facts or called a provider")
    }
    // Reading and updating diagnostic files must not mutate the underlying execution or repeat its effects.
    let database = try InkuDatabase(url: databaseURL)
    let before = try await database.loadExecution(id: failed.id)
    await maintenance.log(execution: failed, enabled: true)
    guard try await database.loadExecution(id: failed.id) == before, await provider.calls == 4 else {
        throw CheckFailure.message("Reading/writing diagnostics changed SQLite execution or repeated a provider attempt")
    }
    print("Drawing failure log passed: one offline failed execution, 4 core attempts, safe diagnostics/events -> SQLite -> restart read without resend -> terminal file log without provider IO/credentials; no saved artwork. Temporary DB only.")
}

private actor DrawingFailureLogProvider: ObservedProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        throw HostError("observation_check_requires_observed_transport")
    }
    func performObserved(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                         observation: ProviderObservationOptions, willSend: @escaping ProviderObservationHandler,
                         didFinish: @escaping ProviderObservationHandler, onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        let input = try ExactJSON(data: action)
        let tag = try input.requiredString("tag")
        guard let stage = ProviderObservationStage(action: tag), let timeout = input["timeout_ms"].string.flatMap(UInt64.init),
              !observation.captureRaw else { throw HostError("invalid_failure_log_check_action") }
        var metric = ProviderAttemptMetric(identity: try ProviderActionIdentity(action: action), action: tag, stage: stage,
            requestedModelReference: models.stage1Model, providerID: "check", model: "pinned", timeoutMS: timeout)
        try await willSend(.init(metric: metric))
        metric.failure = "transport_unavailable"; metric.outcome = .failed; metric.elapsedMS = 1
        metric.diagnostic = .init(kind: .network, reason: "Could not connect to the provider host.", endpoint: "http://127.0.0.1:1",
                                  errorDomain: NSURLErrorDomain, errorCode: URLError.cannotConnectToHost.rawValue)
        try await didFinish(.init(metric: metric))
        return ExactJSON.object(["tag": .string("provider_failed"), "identity": input["identity"],
                                 "elapsed_ms": .string("1"), "failure": .string("transport_unavailable")]).data
    }
}
