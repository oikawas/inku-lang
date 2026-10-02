import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runCompositionProgressChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-composition-progress-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let stage1 = CompositionProgressPause(); let first = CompositionProgressPause()
    let retry = CompositionProgressPause(); let stopped = CompositionProgressPause()
    let provider = CompositionProgressProvider(stage1: stage1, composition: [first, retry, stopped])
    let databaseURL = folder.appendingPathComponent("works.sqlite")
    let app = AppModel(databaseURL: databaseURL, transport: provider)
    await app.initialize()
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false)
    try await app.updateHostSettings(HostSettings(providers: [service],
        models: ModelSelection(stage1Model: "check:pinned", stage2Model: "check:pinned")))
    app.inputMode = "description"; app.descriptionText = compositionProgressDescription; app.seedText = "0"
    let defaultRequest = try app.requestForCurrentInput()
    guard try ExactJSON(data: defaultRequest.configuration)["composition"]["read"].bool == true else {
        throw CheckFailure.message("New work did not inherit Server's composition-reading default")
    }

    // Failure: the new composition effect was shown as a generic response, with no separate stage/model clock.
    let generation = Task { @MainActor in await app.generate() }
    await stage1.waitUntilEntered()
    let interpreting = try await waitForCompositionProgress(app, stage: .interpretation, attempt: 1)
    await stage1.release()
    await first.waitUntilEntered()
    let composing = try await waitForCompositionProgress(app, stage: .composition, attempt: 1)
    let firstFacts = composing.executionID == interpreting.executionID && composing.stageTitleKey == "構図の読み"
        && composing.stageBeganAt == composing.attemptBeganAt && composing.stageBeganAt > interpreting.stageBeganAt
        && composing.stageElapsed(at: composing.stageBeganAt) == 0
        && composing.modelReference == "check:pinned" && composing.modelReference == interpreting.modelReference
        && app.status == "構図の応答を受信中"
        && InkuLocalization.string(composing.stageTitleKey, language: "en") == "Composition reading"
        && InkuLocalization.message(app.status, language: "en") == "Receiving the composition reply"
    app.selectNextDrawingModel("check:later")
    await first.release()
    await retry.waitUntilEntered()
    let retried = try await waitForCompositionProgress(app, stage: .composition, attempt: 2)
    let retryFacts = retried.stageBeganAt == composing.stageBeganAt && retried.attemptBeganAt > composing.attemptBeganAt
        && retried.maxAttempts == composing.maxAttempts && retried.modelReference == "check:pinned"
        && retried.attemptElapsed(at: retried.attemptBeganAt) == 0
        && retried.stageElapsed(at: retried.attemptBeganAt) > 0
    await retry.release()
    await generation.value
    guard firstFacts, retryFacts, app.errorText == nil, let work = app.selectedWork,
          work.ddl?.contains("[composition]") == true, let finished = app.providerProgress,
          finished.stage == .composition, finished.outcome == .succeeded, !finished.clockRunning,
          let endedAt = finished.stageEndedAt,
          finished.stageElapsed(at: endedAt) == finished.stageElapsed(at: endedAt.addingTimeInterval(60)),
          finished.tokensIn == nil, finished.tokensOut == nil,
          await provider.models == ["check:pinned", "check:pinned", "check:pinned"] else {
        throw CheckFailure.message("Composition progress lost native stage/model/retry/time facts or did not complete: \(app.errorText ?? app.status)")
    }
    let prompts = try ExactJSON(data: Data(app.promptJSON.utf8))
    guard let entries = prompts.array, entries.count == 1,
          entries[0]["action"].string == "generate_normalized_ddl",
          !app.promptJSON.contains("inku.composition-reading-prompt.v1") else {
        throw CheckFailure.message("Composition prompt leaked into the Stage 1/2 prompt presentation")
    }
    let context = try await app.savedConfiguration(workID: work.id)
    let database = try InkuDatabase(url: databaseURL)
    let rows = try await database.list()
    let svg = app.currentSVG; let ddl = app.visibleDDL

    // Failure: replaying an already composed saved Score called the reader again or carried its old status.
    let replayed = await app.performComparison(status: "composition replay check", restoreDisplayStatus: true) { token in
        guard app.providerProgress == nil else { throw CheckFailure.message("Replay retained composition progress") }
        await provider.sendLateCompositionBytes(attempt: 2)
        _ = try await app.prepareReplayComparison(work: work, token: token)
        guard app.providerProgress == nil else { throw CheckFailure.message("Old composition callback reached a new token") }
    }
    guard replayed, try await database.work(id: work.id) == work,
          try await app.savedConfiguration(workID: work.id).configuration == context.configuration,
          await provider.models.count == 3 else { throw CheckFailure.message("Saved-work replay changed its condition or called composition") }

    // Failure: comparison used Stage 2/current picker for composition or accepted bytes after Stop.
    var request = try app.requestForCurrentInput()
    request.models.stage1Model = "check:comparison-stage1"; request.models.stage2Model = "check:holes-only"
    let comparisonRequest = request
    let pending = Task { @MainActor in
        await app.performComparison(status: "composition comparison check") { token in
            _ = try await app.generateCandidate(request: comparisonRequest, token: token)
        }
    }
    await stopped.waitUntilEntered()
    let comparing = try await waitForCompositionProgress(app, stage: .composition, attempt: 1)
    let comparisonFacts = comparing.comparison && comparing.modelReference == "check:comparison-stage1"
        && comparing.modelReference != comparisonRequest.models.stage2Model
        && app.status == "比較候補の構図の応答を受信中" && app.selectedWork == work && app.currentSVG == svg
    let cancellation = Task { @MainActor in await app.cancel() }
    await stopped.waitUntilCancelled()
    let frozen = app.providerProgress
    await provider.sendLateCompositionBytes(attempt: 3)
    await Task.yield()
    let drainFacts = app.isBusy && app.providerProgress == frozen && frozen?.outcome == .cancelled
    await stopped.release()
    await cancellation.value
    let comparisonResult = await pending.value
    await provider.sendLateCompositionBytes(attempt: 3)
    await Task.yield()
    guard comparisonFacts, drainFacts, !comparisonResult, !app.isBusy, let frozen, let frozenAt = frozen.stageEndedAt,
          app.providerProgress == frozen, !frozen.clockRunning,
          frozen.stageElapsed(at: frozenAt) == frozen.stageElapsed(at: frozenAt.addingTimeInterval(60)),
          app.selectedWork == work, app.currentSVG == svg, app.visibleDDL == ddl, try await database.list() == rows,
          await provider.models == ["check:pinned", "check:pinned", "check:pinned", "check:comparison-stage1", "check:comparison-stage1"] else {
        throw CheckFailure.message("Composition comparison mixed models, admitted a late event or changed saved/displayed state")
    }
    app.newWork()
    guard app.providerProgress == nil else { throw CheckFailure.message("Next work retained composition progress") }
    print("Composition progress passed: Server default; real Rust interpretation→composition stage reset; one composition retry with pinned Stage1 model; JA/EN presentation; composition prompt absent; completion/Stop freeze and late-event refusal; saved Score replay/New keep provider-free/reset boundaries. Offline mock only.")
}

@MainActor
private func waitForCompositionProgress(_ app: AppModel, stage: ProviderProgressSnapshot.Stage, attempt: Int) async throws -> ProviderProgressSnapshot {
    for _ in 0..<200 {
        if let value = app.providerProgress, value.stage == stage, value.attempt == attempt,
           value.awaitingReply, (stage != .composition || value.receivedBytes == 17) { return value }
        try await Task.sleep(for: .milliseconds(10))
    }
    throw CheckFailure.message("Composition presentation did not receive stage/attempt facts")
}

private let compositionProgressDescription = "A red circle above black dots scattered at the bottom"

private actor CompositionProgressProvider: ProviderTransport {
    let stage1: CompositionProgressPause
    let composition: [CompositionProgressPause]
    private(set) var models: [String] = []
    private var stage1Calls = 0
    private var compositionCalls = 0
    private var byteCallbacks: [Int: @Sendable (Int) -> Void] = [:]
    init(stage1: CompositionProgressPause, composition: [CompositionProgressPause]) {
        self.stage1 = stage1; self.composition = composition
    }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        self.models.append(models.stage1Model)
        let response: ExactJSON
        let resultTag: String
        switch input["tag"].string {
        case "generate_normalized_ddl":
            stage1Calls += 1
            if stage1Calls == 1 { await stage1.wait() }
            response = compositionProgressPlan(); resultTag = "normalized_ddl_generated"
        case "read_composition":
            compositionCalls += 1
            let attempt = compositionCalls
            guard attempt <= composition.count else { throw HostError("unexpected_composition_progress_call") }
            let pause = composition[attempt - 1]
            byteCallbacks[attempt] = onBytes; onBytes(17)
            await withTaskCancellationHandler { await pause.wait() } onCancel: { Task { await pause.markCancelled() } }
            if attempt == 1 {
                return ExactJSON.object(["tag": .string("provider_failed"), "identity": input["identity"],
                    "failure": .string("transport_timeout"), "elapsed_ms": .string("1")]).data
            }
            response = .object(["thesis": .string("a lone circle above a floor of dots"),
                "roles": .array([.string("field"), .string("focal"), .string("scattered")]),
                "relations": .array([.object(["type": .string("above"), "layers": .array([.number("1"), .number("2")]),
                    "side": .string("unspecified"), "toward": .string("unspecified")])]),
                "tension": .object(["motion": .string("still"), "focus": .string("unspecified"), "vertical": .string("unspecified"),
                    "balance": .string("unspecified"), "symmetry": .string("unspecified"), "void": .string("unspecified")]),
                "stated_places": .array([.object(["layer": .number("2"), "words": .string("at the bottom"), "place": .string("bottom")])])])
            resultTag = "composition_read"
        default: throw HostError("unexpected_composition_progress_effect")
        }
        return ExactJSON.object(["tag": .string(resultTag), "identity": input["identity"],
            "response": .string(response.text), "elapsed_ms": .string("1")]).data
    }
    func sendLateCompositionBytes(attempt: Int) { byteCallbacks[attempt]?(999) }
}

private func compositionProgressPlan() -> ExactJSON {
    func layer(_ action: String, _ shape: String, _ count: Int, _ position: String, _ size: String, _ color: String) -> ExactJSON {
        var fields = Dictionary(uniqueKeysWithValues: ["angle", "bleeding", "continuity", "line_up_direction", "motion_amplitude",
            "motion_quality", "proportion", "thinness"].map { ($0, ExactJSON.string("unspecified")) })
        fields.merge(["action": .string(action), "shape": .string(shape), "count": .integer(count), "position": .string(position),
            "size": .string(size), "color": .string(color), "handling": .string("dense"), "tool": .string("pen"),
            "surface": .string(shape == "point" ? "empty" : "flat")], uniquingKeysWith: { _, value in value })
        return .object(fields)
    }
    return .object(["ground": .string("paper"), "background": .string("white"), "plugins": .array([]),
        "layers": .array([layer("fill", "square", 1, "unspecified", "large", "gray"),
            layer("place", "circle", 1, "center", "small", "red"), layer("scatter", "point", 12, "bottom", "very_small", "black")])])
}

private actor CompositionProgressPause {
    private var entered = false
    private var cancelled = false
    private var continuation: CheckedContinuation<Void, Never>?
    private var enteredWaiters: [CheckedContinuation<Void, Never>] = []
    private var cancelledWaiters: [CheckedContinuation<Void, Never>] = []
    func wait() async {
        await withCheckedContinuation { continuation in
            self.continuation = continuation; entered = true
            let waiters = enteredWaiters; enteredWaiters = []; waiters.forEach { $0.resume() }
        }
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
    func release() { continuation?.resume(); continuation = nil }
}
