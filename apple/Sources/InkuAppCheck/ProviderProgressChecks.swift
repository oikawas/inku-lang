import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runProviderProgressChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-provider-progress-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let first = ProviderProgressPause(); let retry = ProviderProgressPause(); let comparison = ProviderProgressPause()
    let provider = ProviderProgressProvider(pauses: [first, retry, comparison])
    let databaseURL = folder.appendingPathComponent("works.sqlite")
    let app = AppModel(databaseURL: databaseURL, transport: provider)
    await app.initialize()
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false)
    try await app.updateHostSettings(HostSettings(providers: [service],
        models: ModelSelection(stage1Model: "check:pinned", stage2Model: "check:pinned")))
    app.inputMode = "description"; app.descriptionText = "a red circle"; app.seedText = "0"

    // Failure: AppModel discarded the real core attempt and host clock, hiding a retry as one slow answer.
    let generation = Task { @MainActor in await app.generate() }
    await first.waitUntilEntered()
    let initial = try await waitForProviderProgress(app, attempt: 1, comparison: false)
    let initialFacts = initial.action == "generate_normalized_ddl" && initial.maxAttempts >= 2
        && initial.modelReference == "check:pinned" && initial.deadline > initial.attemptBeganAt
        && initial.stageBeganAt == initial.attemptBeganAt && initial.clockRunning
        && initial.tokensIn == nil && initial.tokensOut == nil
    app.selectNextDrawingModel("check:changed")
    await first.release()
    let second = try await waitForProviderProgress(app, attempt: 2, comparison: false)
    await retry.waitUntilEntered()
    let retryFacts = second.executionID == initial.executionID && second.action == initial.action
        && second.maxAttempts == initial.maxAttempts && second.modelReference == "check:pinned"
        && second.stageBeganAt == initial.stageBeganAt && second.attemptBeganAt > initial.attemptBeganAt
        && second.attemptElapsed(at: second.attemptBeganAt) == 0
        && second.stageElapsed(at: second.attemptBeganAt) > 0
    await retry.release()
    await generation.value
    guard initialFacts, retryFacts, app.errorText == nil, let original = app.selectedWork,
          let completed = app.providerProgress, completed.outcome == .succeeded, !completed.clockRunning,
          let completedAt = completed.stageEndedAt,
          completed.stageElapsed(at: completedAt) == completed.stageElapsed(at: completedAt.addingTimeInterval(60)),
          completed.attemptElapsed(at: completedAt) == completed.attemptElapsed(at: completedAt.addingTimeInterval(60)),
          completed.tokensIn == nil, completed.tokensOut == nil,
          await provider.models == ["check:pinned", "check:pinned"] else {
        throw CheckFailure.message("Provider progress lost retry/model/time facts, invented usage or kept a completed clock running")
    }
    let database = try InkuDatabase(url: databaseURL)
    let rows = try await database.list()
    let svg = app.currentSVG; let ddl = app.visibleDDL

    // Failure: a provider-free replay inherited the previous progress, or an old token updated the new operation.
    let replayed = await app.performComparison(status: "progress reset check", restoreDisplayStatus: true) { token in
        guard app.providerProgress == nil else { throw CheckFailure.message("Replay inherited an old provider card") }
        await provider.sendLateBytes(call: 2)
        _ = try await app.prepareReplayComparison(work: original, token: token)
        guard app.providerProgress == nil else { throw CheckFailure.message("An old provider token contaminated replay") }
    }
    guard replayed, app.providerProgress == nil else { throw CheckFailure.message("Provider-free operation did not clear progress") }

    // Failure: comparison callbacks discarded attempt facts or accepted late bytes while Stop was draining.
    let request = try app.requestForCurrentInput()
    let pending = Task { @MainActor in
        await app.performComparison(status: "comparison progress check") { token in
            _ = try await app.generateCandidate(request: request, token: token)
        }
    }
    await comparison.waitUntilEntered()
    let comparing = try await waitForProviderProgress(app, attempt: 1, comparison: true)
    guard comparing.executionID != completed.executionID, comparing.action == "generate_normalized_ddl",
          comparing.modelReference == request.models.stage1Model, comparing.awaitingReply,
          comparing.tokensIn == nil, comparing.tokensOut == nil,
          app.selectedWork == original, app.currentSVG == svg, app.visibleDDL == ddl else {
        await comparison.release(); _ = await pending.value
        throw CheckFailure.message("Comparison progress borrowed the old run or changed the displayed work")
    }
    let stopping = Task { @MainActor in await app.cancel() }
    await comparison.waitUntilCancelled()
    let cancelled = app.providerProgress
    await provider.sendLateBytes(call: 3)
    await Task.yield()
    let drainFacts = app.isBusy && app.providerProgress == cancelled && cancelled?.outcome == .cancelled
        && cancelled?.clockRunning == false && app.selectedWork == original
    await comparison.release()
    await stopping.value
    let stoppedResult = await pending.value
    await provider.sendLateBytes(call: 3)
    await Task.yield()
    guard drainFacts, !stoppedResult, !app.isBusy, let cancelled, let stoppedAt = cancelled.stageEndedAt,
          app.providerProgress == cancelled,
          cancelled.stageElapsed(at: stoppedAt) == cancelled.stageElapsed(at: stoppedAt.addingTimeInterval(60)),
          cancelled.attemptElapsed(at: stoppedAt) == cancelled.attemptElapsed(at: stoppedAt.addingTimeInterval(60)),
          app.selectedWork == original, app.currentSVG == svg, app.visibleDDL == ddl,
          try await database.list() == rows, await provider.models.count == 3 else {
        throw CheckFailure.message("Stopped comparison progress changed after its freeze or released busy before drain")
    }
    app.newWork()
    guard app.providerProgress == nil else { throw CheckFailure.message("New work retained old provider progress") }
    print("Provider progress passed: real Rust first attempt plus one retry; pinned requested model; shared stage/reset attempt clocks; missing usage stays nil; completion/Stop freeze; comparison callbacks, drain and old-token rejection; provider-free replay/New clear progress. Offline mock only.")
}

@MainActor
private func waitForProviderProgress(_ app: AppModel, attempt: Int, comparison: Bool) async throws -> ProviderProgressSnapshot {
    for _ in 0..<200 {
        if let value = app.providerProgress, value.attempt == attempt, value.comparison == comparison, value.awaitingReply { return value }
        try await Task.sleep(for: .milliseconds(10))
    }
    throw CheckFailure.message("Provider attempt \(attempt) never reached the presentation snapshot")
}

private actor ProviderProgressProvider: ProviderTransport {
    let pauses: [ProviderProgressPause]
    private(set) var models: [String] = []
    private var byteCallbacks: [Int: @Sendable (Int) -> Void] = [:]
    init(pauses: [ProviderProgressPause]) { self.pauses = pauses }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        self.models.append(models.stage1Model)
        let call = self.models.count
        guard call <= pauses.count else { throw HostError("unexpected_provider_progress_call") }
        byteCallbacks[call] = onBytes
        let input = try ExactJSON(data: action)
        let pause = pauses[call - 1]
        await withTaskCancellationHandler {
            await pause.wait()
        } onCancel: {
            Task { await pause.markCancelled() }
        }
        if call == 1 {
            return ExactJSON.object(["tag": .string("provider_failed"), "identity": input["identity"],
                "failure": .string("transport_timeout"), "elapsed_ms": .string("1")]).data
        }
        onBytes(17)
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": input["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
    }
    func sendLateBytes(call: Int) { byteCallbacks[call]?(999) }
}

private actor ProviderProgressPause {
    private var entered = false
    private var cancelled = false
    private var released = false
    private var continuation: CheckedContinuation<Void, Never>?
    private var enteredWaiters: [CheckedContinuation<Void, Never>] = []
    private var cancelledWaiters: [CheckedContinuation<Void, Never>] = []
    func wait() async {
        entered = true
        let waiters = enteredWaiters; enteredWaiters = []; waiters.forEach { $0.resume() }
        if !released { await withCheckedContinuation { continuation = $0 } }
    }
    func waitUntilEntered() async {
        if !entered { await withCheckedContinuation { enteredWaiters.append($0) } }
    }
    func markCancelled() {
        cancelled = true
        let waiters = cancelledWaiters; cancelledWaiters = []; waiters.forEach { $0.resume() }
    }
    func waitUntilCancelled() async {
        if !cancelled { await withCheckedContinuation { cancelledWaiters.append($0) } }
    }
    func release() { released = true; continuation?.resume(); continuation = nil }
}
