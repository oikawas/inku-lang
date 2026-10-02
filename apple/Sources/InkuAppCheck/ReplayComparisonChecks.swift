import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runReplayComparisonChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-replay-comparison-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("works.sqlite")
    let provider = ReplayComparisonProvider()
    let app = AppModel(databaseURL: databaseURL, transport: provider)
    await app.initialize()
    app.seedText = "42"; app.wild = true
    await app.generate()
    guard app.errorText == nil, let original = app.selectedWork, let originalNodeID = original.lineageNodeID,
          let separator = original.id.lastIndex(of: "_") else {
        throw CheckFailure.message("Replay comparison source generation failed: \(app.errorText ?? app.status)")
    }
    let database = try InkuDatabase(url: databaseURL)
    let executionID = String(original.id[..<separator])
    let effectID = "save-render:" + String(original.id[original.id.index(after: separator)...])
    guard let acknowledgement = try await database.acknowledgement(executionID: executionID, effectID: effectID) else {
        throw CheckFailure.message("Replay comparison source has no saved performance")
    }
    let context = try ExactJSON(data: acknowledgement).requiredObject("performance")
    var legacy = original
    legacy.renderSeed = nil; legacy.seedText = " \u{3000}\u{00a0}"; legacy.compositionSeed = nil
    legacy.renderEngineVersion = nil
    legacy = try await saveReplayComparisonFixture(legacy, parentNodeID: originalNodeID, context: context, database: database)
    var wordSeeded = original
    // The saved words override this deliberately disagreeing recorded number, as on Server.
    wordSeeded.renderSeed = "7"; wordSeeded.seedText = "\u{001c}\u{3000}春風e\u{0301}\u{200b}\u{00a0}\u{001f}"
    wordSeeded.compositionSeed = nil; wordSeeded.renderEngineVersion = "archived-check-engine"
    wordSeeded = try await saveReplayComparisonFixture(wordSeeded, parentNodeID: originalNodeID, context: context, database: database)
    let rows = try await database.list()
    let lineage = try await database.lineage(focusNodeID: originalNodeID)
    let execution = try await database.loadExecution(id: executionID)
    let status = app.status
    let svg = app.currentSVG; let ddl = app.visibleDDL; let score = app.scoreJSON
    let authority = app.authoringAuthority; let revision = app.authoringRevision
    let displayedWorks = app.works
    app.catalogID = app.catalogs.first(where: { $0.id != original.catalogID })!.id
    app.canvasID = app.canvases.first(where: { $0.id != original.renderCanvasAspectID })!.id
    app.seedText = "999"; app.wild = false

    // Failure: ordinary Replay saved and selected a new child rather than only comparing SVGs.
    var savedSnapshot: ReplayComparisonSnapshot?
    var completedToken: UUID?
    let completed = await app.performComparison(status: "replay check", restoreDisplayStatus: true) { token in
        completedToken = token
        savedSnapshot = try await app.prepareReplayComparison(work: original, token: token)
    }
    guard completed, let savedSnapshot, savedSnapshot.workID == original.id,
          savedSnapshot.originalSVG == original.svg, savedSnapshot.replayedSVG == original.svg,
          savedSnapshot.recordedVersion == original.renderEngineVersion,
          savedSnapshot.currentVersion == original.renderEngineVersion, savedSnapshot.provisionalSeed == nil,
          app.selectedWork == original, app.displayedWork == original, app.previewWork == nil,
          app.currentSVG == svg, app.visibleDDL == ddl, app.scoreJSON == score,
          app.authoringAuthority == authority, app.authoringRevision == revision,
          app.status == status, app.works == displayedWorks,
          try await database.list() == rows, try await database.lineage(focusNodeID: originalNodeID) == lineage,
          try await database.loadExecution(id: executionID) == execution, await provider.calls == 0 else {
        throw CheckFailure.message("Ordinary replay changed display/history/lineage, used current options or lost its engine facts")
    }
    do {
        _ = try await app.prepareReplayComparison(work: original, token: completedToken!)
        throw CheckFailure.message("Replay comparison admitted a completed token")
    } catch is CancellationError { }

    // Failure: an old seedless work randomized replay or borrowed an invented composition seed.
    let expectedLegacy = try expectedReplayComparisonSVG(work: legacy, context: context, seed: "0")
    let expectedWords = try expectedReplayComparisonSVG(work: wordSeeded, context: context, seed: "14859340650796947346")
    let staleNumericWords = try expectedReplayComparisonSVG(work: wordSeeded, context: context, seed: "7")
    guard expectedWords != staleNumericWords else { throw CheckFailure.message("Saved-word fixture does not distinguish Server seed precedence") }
    var legacySnapshot: ReplayComparisonSnapshot?
    var wordSnapshot: ReplayComparisonSnapshot?
    let boundaryCompleted = await app.performComparison(status: "legacy replay check", restoreDisplayStatus: true) { token in
        legacySnapshot = try await app.prepareReplayComparison(work: legacy, token: token)
        wordSnapshot = try await app.prepareReplayComparison(work: wordSeeded, token: token)
        var changedParent = original
        changedParent.svg += "<!-- stale parent -->"
        do {
            _ = try await app.prepareReplayComparison(work: changedParent, token: token)
            throw CheckFailure.message("Replay comparison admitted a changed parent snapshot")
        } catch let error as HostError where error.code == "saved_work_changed_or_unavailable" { }
    }
    guard boundaryCompleted, let legacySnapshot, let wordSnapshot,
          legacySnapshot.workID == legacy.id, legacySnapshot.originalSVG == legacy.svg,
          legacySnapshot.replayedSVG == expectedLegacy, legacySnapshot.recordedVersion == nil,
          legacySnapshot.currentVersion == savedSnapshot.currentVersion, legacySnapshot.provisionalSeed == "0",
          wordSnapshot.workID == wordSeeded.id, wordSnapshot.originalSVG == wordSeeded.svg,
          wordSnapshot.replayedSVG == expectedWords, wordSnapshot.recordedVersion == "archived-check-engine",
          wordSnapshot.currentVersion == savedSnapshot.currentVersion, wordSnapshot.provisionalSeed == nil,
          try await database.work(id: legacy.id) == legacy, try await database.work(id: wordSeeded.id) == wordSeeded,
          legacy.compositionSeed == nil, wordSeeded.compositionSeed == nil,
          app.selectedWork == original, app.currentSVG == svg, app.visibleDDL == ddl, app.scoreJSON == score,
          app.status == status, try await database.list() == rows,
          try await database.lineage(focusNodeID: originalNodeID) == lineage, await provider.calls == 0 else {
        throw CheckFailure.message("Old-work replay lost raw seed absence, exact word seed, versions or read-only state")
    }

    // Failure: a suspended comparison callback accepted a snapshot after Stop.
    let pause = ReplayComparisonPause()
    var acceptedLateSnapshot = false
    let pending = Task { @MainActor in
        await app.performComparison(status: "stopped replay check", restoreDisplayStatus: true) { token in
            await withTaskCancellationHandler {
                await pause.wait()
            } onCancel: {
                Task { await pause.markCancelled() }
            }
            _ = try await app.prepareReplayComparison(work: original, token: token)
            acceptedLateSnapshot = true
        }
    }
    await pause.waitUntilEntered()
    let stopping = Task { @MainActor in await app.cancel() }
    await pause.waitUntilCancelled()
    let busyUntilDrained = app.isBusy && app.selectedWork == original
    await pause.release()
    await stopping.value
    let stoppedResult = await pending.value
    guard busyUntilDrained, !stoppedResult, !acceptedLateSnapshot, !app.isBusy,
          app.status == "停止しました", app.selectedWork == original, app.currentSVG == svg,
          app.visibleDDL == ddl, app.scoreJSON == score, app.works == displayedWorks,
          try await database.list() == rows, try await database.lineage(focusNodeID: originalNodeID) == lineage,
          try await database.work(id: original.id) == original, await provider.calls == 0 else {
        throw CheckFailure.message("Stopped replay accepted a late snapshot or changed persisted/displayed state")
    }
    print("Replay comparison passed: saved SVG/current SVG and versions captured; no history, lineage or display mutation; old seedless work uses provisional 0 with raw missing composition; saved Unicode words override a numeric seed exactly; stale parent/token and stopped callback refused. Provider calls: 0.")
}

private func saveReplayComparisonFixture(_ source: SavedWork, parentNodeID: String, context: ExactJSON,
                                         database: InkuDatabase) async throws -> SavedWork {
    let executionID = UUID().uuidString
    var work = source
    work.id = executionID + "_0"; work.at += 1; work.lineageNodeID = UUID().uuidString
    let node = LineageNode(id: work.lineageNodeID!, historyID: work.id, at: work.at,
                           descriptionHash: work.descriptionHash, renderHash: work.renderHash, rootNodeID: parentNodeID)
    let edge = LineageEdge(id: UUID().uuidString, parentNodeID: parentNodeID, childNodeID: node.id,
                           derivationKind: "replay-check-fixture", at: work.at)
    let snapshot = Data("{}".utf8)
    let execution = try await database.compareAndSwapExecution(id: executionID, expectedRevision: nil, snapshot: snapshot)
    let acknowledgement = ExactJSON.object(["tag": .string("saved_work_committed"), "work_id": .string(work.id),
                                            "performance": context]).data
    _ = try await database.commitEffect(id: executionID, expectedRevision: execution.revision, effectID: "save-render:0",
        snapshot: snapshot, acknowledgement: acknowledgement, work: work, node: node, edge: edge)
    return work
}

private func expectedReplayComparisonSVG(work: SavedWork, context: ExactJSON, seed: String) throws -> String {
    var options = context["options"]
    options["render_seed"] = .number(seed); options["composition_seed"] = .null
    options["svg_profile"] = .string("display")
    let request = ExactJSON.object(["request": .object(["score": try ExactJSON(data: Data(work.score.utf8)), "options": options]),
        "hard_policy": context["hard_policy"], "operational_budget": context["operational_budget"], "clip": context["clip"]])
    let rendered = try ExactJSON(data: InkuCore.renderSaved(request.data))
    if let error = rendered["error"].string { throw CheckFailure.message("Replay fixture render failed: \(error)") }
    return try rendered.requiredString("svg")
}

private actor ReplayComparisonProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw HostError("replay_comparison_must_not_call_provider")
    }
}

private actor ReplayComparisonPause {
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
