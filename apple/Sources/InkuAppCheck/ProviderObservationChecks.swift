import Darwin
import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runProviderObservationChecks() async throws {
    let oldMode = ProcessInfo.processInfo.environment["INKU_DEVELOPER_MODE"]
    setenv("INKU_DEVELOPER_MODE", "1", 1)
    defer {
        if let oldMode { setenv("INKU_DEVELOPER_MODE", oldMode, 1) }
        else { unsetenv("INKU_DEVELOPER_MODE") }
    }
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-provider-observation-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("works.sqlite")
    let provider = ObservationCheckProvider()
    let app = AppModel(databaseURL: databaseURL, transport: provider)
    await app.initialize()
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false)
    try await app.updateHostSettings(HostSettings(providers: [service], models: ModelSelection(stage1Model: "check:pinned", stage2Model: "check:holes")))
    app.inputMode = "description"; app.descriptionText = "A red circle above black dots scattered at the bottom"
    app.language = "en"; app.seedText = "42"
    guard app.display.preferences.captureProviderIO != true else { throw CheckFailure.message("Provider raw capture did not default off") }
    app.display.preferences.captureProviderIO = true
    let request = try app.requestForCurrentInput()

    // Failure: native composition was mixed into Stage 1, usage stayed nil, and no durable IO could be reopened.
    await app.generate()
    guard app.errorText == nil, let work = app.selectedWork, let progress = app.providerProgress,
          progress.stage == .composition, progress.tokensIn == 13, progress.tokensOut == 0,
          progress.providerElapsedMS != nil, progress.outcome == .succeeded, !progress.clockRunning else {
        throw CheckFailure.message("Observed composition did not reach native actual usage/time: \(app.errorText ?? app.status)")
    }
    let metrics = app.providerMetrics
    guard metrics.count == 2, metrics.map(\.stage) == [.stage1, .composition],
          metrics.map(\.requestedModelReference) == ["check:pinned", "check:pinned"],
          metrics[0].usage == ProviderUsage(inputTokens: 11, outputTokens: 7, totalTokens: 18),
          metrics[1].usage == ProviderUsage(inputTokens: 13, outputTokens: 0, totalTokens: 13),
          metrics.allSatisfy({ ($0.elapsedMS ?? 0) > 0 && $0.sent && $0.outcome == .completed && $0.responseModel == "check-response" }),
          metrics[0].identity != metrics[1].identity else {
        throw CheckFailure.message("Stage 1/composition observations lost separate elapsed, explicit zero usage, pinned model or identity")
    }
    let publicJSON = String(decoding: try JSONEncoder().encode(metrics), as: UTF8.self)
    guard !publicJSON.contains("requestBody"), !publicJSON.contains("responseBody"), !publicJSON.contains("data:") else {
        throw CheckFailure.message("Normal provider metrics contain raw IO")
    }
    let database = try InkuDatabase(url: databaseURL)
    let restoredHost = PipelineHost(database: database, transport: provider, credentials: ObservationEmptyCredentials())
    let reopened = try await restoredHost.savedProviderMetrics(workID: work.id)
    let raw = try await restoredHost.savedProviderObservations(workID: work.id)
    let httpStarts = await provider.httpStarts
    guard reopened == metrics, raw.count == 2, raw.map(\.metric) == metrics,
          raw[1].raw?.responseBody?.contains("data:") == true,
          raw.allSatisfy({ $0.raw?.requestBody != nil && $0.raw?.captureComplete == true }), httpStarts == 2 else {
        throw CheckFailure.message("SQLite/Host recreation lost save-frozen metric/raw records or reopened a provider call")
    }
    let reopenedApp = AppModel(databaseURL: databaseURL, transport: provider)
    await reopenedApp.initialize(); await reopenedApp.selectWork(work)
    guard reopenedApp.providerMetrics == metrics, await provider.httpStarts == httpStarts else {
        throw CheckFailure.message("Saved-work native selection discarded metrics or resent a provider request")
    }
    let compared = try await restoredHost.prepareReplayComparison(work: work)
    let replay = try await restoredHost.replay(workID: work.id)
    guard compared.providerMetrics == metrics, compared.originalSVG == work.svg,
          replay.score == work.score, replay.ddl == work.ddl,
          try await restoredHost.savedProviderMetrics(workID: replay.id) == metrics,
          try await restoredHost.savedProviderObservations(workID: replay.id) == raw,
          await provider.httpStarts == httpStarts else {
        throw CheckFailure.message("Saved Score comparison/replay changed source facts, lost observation provenance or called a provider")
    }

    // Older optional request and private snapshot fields must decode without inventing measurements.
    var oldRequest = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as! [String: Any]
    oldRequest.removeValue(forKey: "captureProviderIO")
    guard try JSONDecoder().decode(GenerationRequest.self, from: JSONSerialization.data(withJSONObject: oldRequest)).captureProviderIO == nil else {
        throw CheckFailure.message("Old request acquired a developer capture opt-in")
    }
    guard let separator = work.id.lastIndex(of: "_") else { throw CheckFailure.message("Observed work identity is invalid") }
    let executionID = String(work.id[..<separator])
    guard let record = try await database.loadExecution(id: executionID) else { throw CheckFailure.message("Observation snapshot is missing") }
    var legacy = try JSONSerialization.jsonObject(with: record.snapshot) as! [String: Any]
    legacy.removeValue(forKey: "providerObservations"); legacy.removeValue(forKey: "captureProviderIO")
    _ = try await database.compareAndSwapExecution(id: executionID, expectedRevision: record.revision,
        snapshot: JSONSerialization.data(withJSONObject: legacy))
    let legacyHost = PipelineHost(database: database, transport: provider, credentials: ObservationEmptyCredentials())
    let oldView = try await legacyHost.restore(executionID: executionID)
    guard oldView.providerMetrics.isEmpty, oldView.svg == work.svg,
          try await legacyHost.savedProviderMetrics(workID: work.id) == metrics,
          try await database.work(id: work.id) == work, await provider.httpStarts == httpStarts else {
        throw CheckFailure.message("Optional-absent restore invented observations or replaced save-frozen metrics/SVG")
    }
    app.newWork()
    guard app.providerProgress == nil, app.providerMetrics.isEmpty else { throw CheckFailure.message("Next work retained observed progress") }

    // Failure: an observation CAS failure before willSend allowed HTTP or entered a paid retry.
    let faultDatabase = try InkuDatabase(url: folder.appendingPathComponent("cas.sqlite"))
    let capture = ObservationExecutionCapture()
    let faultProvider = ObservationCheckProvider(conflictDatabase: faultDatabase, execution: capture)
    let faultHost = PipelineHost(database: faultDatabase, transport: faultProvider, credentials: ObservationEmptyCredentials())
    do {
        _ = try await faultHost.generate(request) { value in
            if case .changed(let view) = value { capture.record(view.executionID) }
        }
        throw CheckFailure.message("Pre-send observation CAS failure was accepted")
    } catch ProviderObservationFailure.requestSaveFailed { }
    guard await faultProvider.httpStarts == 0, await faultProvider.calls == 1,
          let faultID = capture.id else { throw CheckFailure.message("Failed durable request reached HTTP or a retry") }
    let faultRestored = PipelineHost(database: faultDatabase, transport: faultProvider, credentials: ObservationEmptyCredentials())
    let stopped = try await faultRestored.restore(executionID: faultID)
    guard stopped.interruptedProvider, stopped.providerMetrics.isEmpty, await faultProvider.calls == 1 else {
        throw CheckFailure.message("Failed send claim was inferred as safe to resend on restore")
    }
    setenv("INKU_DEVELOPER_MODE", "0", 1)
    do {
        _ = try await faultHost.generate(request)
        throw CheckFailure.message("Raw capture outside developer mode was accepted")
    } catch let error as HostError {
        guard error.code == "developer_provider_observations_not_available" else { throw error }
    }
    guard await faultProvider.calls == 1 else { throw CheckFailure.message("Developer capture refusal reached provider transport") }
    print("Provider observations passed: real Rust Stage1/composition -> separate actual elapsed/usage including explicit zero -> SQLite -> Host/native reopen; raw isolated and save-frozen; old optional absent decode; saved Score replay/comparison no provider; pre-send CAS failure HTTP0/no retry/no restore resend; developer opt-in refusal. Offline mock and temporary DB only.")
}

private final class ObservationExecutionCapture: @unchecked Sendable {
    private let lock = NSLock()
    private var value: String?
    var id: String? { lock.withLock { value } }
    func record(_ id: String) { lock.withLock { value = id } }
}

private actor ObservationCheckProvider: ObservedProviderTransport {
    private(set) var httpStarts = 0
    private(set) var calls = 0
    let conflictDatabase: InkuDatabase?
    let execution: ObservationExecutionCapture?
    init(conflictDatabase: InkuDatabase? = nil, execution: ObservationExecutionCapture? = nil) {
        self.conflictDatabase = conflictDatabase; self.execution = execution
    }
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
        guard let stage = ProviderObservationStage(action: tag), let timeout = input["timeout_ms"].string.flatMap(UInt64.init) else {
            throw HostError("invalid_observation_check_action")
        }
        var metric = ProviderAttemptMetric(identity: try ProviderActionIdentity(action: action), action: tag, stage: stage,
            requestedModelReference: models.stage1Model, providerID: "check", model: "pinned", timeoutMS: timeout)
        var raw: ProviderRawObservation? = observation.captureRaw ? .init(requestBody: "{\"model\":\"pinned\",\"prompt\":\"bounded mock\"}") : nil
        if let conflictDatabase, let id = execution?.id,
           let current = try await conflictDatabase.loadExecution(id: id) {
            _ = try await conflictDatabase.compareAndSwapExecution(id: id, expectedRevision: current.revision, snapshot: current.snapshot)
        }
        try await willSend(.init(metric: metric, raw: raw))
        httpStarts += 1
        let began = Date()
        try await Task.sleep(for: .milliseconds(stage == .composition ? 35 : 20))
        let response = stage == .composition ? observationComposition() : observationPlan()
        let resultTag = stage == .composition ? "composition_read" : "normalized_ddl_generated"
        metric.elapsedMS = UInt64(max(0, Date().timeIntervalSince(began) * 1_000))
        metric.usage = stage == .composition ? ProviderUsage(inputTokens: 13, outputTokens: 0, totalTokens: 13)
            : ProviderUsage(inputTokens: 11, outputTokens: 7, totalTokens: 18)
        metric.responseModel = "check-response"; metric.httpStatus = 200; metric.outcome = .completed; metric.sent = true
        if raw != nil {
            raw?.responseBody = stage == .composition ? "data: \(response.text)\n\ndata: [DONE]\n\n" : response.text
            raw?.responseIncomplete = false; raw?.captureComplete = true
        }
        onBytes(raw?.responseBody?.utf8.count ?? response.data.count)
        try await didFinish(.init(metric: metric, raw: raw))
        return ExactJSON.object(["tag": .string(resultTag), "identity": input["identity"], "response": .string(response.text),
            "elapsed_ms": .string(String(metric.elapsedMS!))]).data
    }
}

private struct ObservationEmptyCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
    func setKey(_ key: String?, for credentialID: String) async throws { }
}

private func observationPlan() -> ExactJSON {
    func layer(_ action: String, _ shape: String, _ count: Int, _ position: String, _ size: String, _ color: String) -> ExactJSON {
        var fields = Dictionary(uniqueKeysWithValues: ["angle", "bleeding", "continuity", "line_up_direction", "motion_amplitude",
            "motion_quality", "proportion", "thinness"].map { ($0, ExactJSON.string("unspecified")) })
        fields.merge(["action": .string(action), "shape": .string(shape), "count": .integer(count), "position": .string(position),
            "size": .string(size), "color": .string(color), "handling": .string("dense"), "tool": .string("pen"),
            "surface": .string(shape == "point" ? "empty" : "flat")], uniquingKeysWith: { _, value in value })
        return .object(fields)
    }
    return .object(["ground": .string("paper"), "background": .string("white"), "plugins": .array([]), "layers": .array([
        layer("fill", "square", 1, "unspecified", "large", "gray"), layer("place", "circle", 1, "center", "small", "red"),
        layer("scatter", "point", 12, "bottom", "very_small", "black")])])
}

private func observationComposition() -> ExactJSON {
    .object(["thesis": .string("A red circle above black dots"), "roles": .array(["field", "focal", "scattered"].map(ExactJSON.string)),
        "relations": .array([.object(["type": .string("above"), "layers": .array([.integer(1), .integer(2)]),
            "side": .string("unspecified"), "toward": .string("unspecified")])]),
        "tension": .object(["motion": .string("still"), "focus": .string("unspecified"), "vertical": .string("unspecified"),
            "balance": .string("unspecified"), "symmetry": .string("unspecified"), "void": .string("unspecified")]),
        "stated_places": .array([.object(["layer": .integer(2), "words": .string("at the bottom"), "place": .string("bottom")])])])
}
