import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runRefinementChecks() async throws {
    let began = Date()
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-refinement-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    let provider = RefinementProvider()
    let app = AppModel(databaseURL: databaseURL, transport: provider)
    await app.initialize()
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false)
    let settings = HostSettings(providers: [service], models: ModelSelection(stage1Model: "check:original", stage2Model: "check:original"))
    try await app.updateHostSettings(settings)
    app.inputMode = "description"; app.descriptionText = "a red circle"; app.seedText = "0"; app.wild = true
    var parentRequest = try app.requestForCurrentInput()
    var parentConfiguration = try ExactJSON(data: parentRequest.configuration)
    var parentOptions = try ExactJSON(data: parentRequest.renderOptions)
    parentConfiguration["compiler"]["composition_seed"] = .null
    parentOptions["composition_seed"] = .null
    parentRequest.configuration = parentConfiguration.data; parentRequest.renderOptions = parentOptions.data
    _ = await app.runAutomation(request: parentRequest)
    guard app.errorText == nil, let parent = app.selectedWork, parent.compositionSeed == nil, parent.renderSeed == "0" else {
        throw CheckFailure.message("Refinement zero-seed parent failed: \(app.errorText ?? app.status)")
    }
    let database = try InkuDatabase(url: databaseURL)
    let context = try await app.savedConfiguration(workID: parent.id)
    let document = try ExactJSON(data: context.document!)
    guard document["macro_locks"].array?.count == 7 else { throw CheckFailure.message("Refinement requires complete pinned macro locks") }
    let initialRows = try await database.list().count
    let initialCalls = await provider.calls

    // Failure: word touch used a random seed, reinterpreted words and resolved today's colors.
    let words = "\u{001c}\u{3000}春風e\u{0301}\u{200b}\u{00a0}\u{001f}"
    let canonicalWords = "春風e\u{0301}\u{200b}"
    var touched: SavedWork?
    let touchSucceeded = await app.performComparison(status: "touch check") { token in
        let plans = try await app.makeDrawingAdjustmentPlans(work: parent, kind: "touch_change", count: 1,
            words: words, wildOverride: false, modelReference: "unknown:unused")
        guard plans.count == 1, plans[0].stage1Model == parent.stage1Model, plans[0].stage2Model == parent.stage2Model else {
            throw CheckFailure.message("Touch did not retain the parent's model facts")
        }
        let candidate = try await app.prepareDrawingAdjustmentCandidate(plan: plans[0], token: token)
        let repeated = try await app.makeDrawingAdjustmentPlans(work: parent, kind: "touch_change", count: 1, words: canonicalWords)
        let same = try await app.prepareDrawingAdjustmentCandidate(plan: repeated[0], token: token)
        guard candidate.work.renderSeed == "14859340650796947346", candidate.work.seedText == canonicalWords,
              candidate.work.compositionSeed == "0", candidate.work.score == parent.score, candidate.work.ddl == parent.ddl,
              candidate.work.renderColorMap == parent.renderColorMap, candidate.work.renderWild == parent.renderWild,
              same.work.svg == candidate.work.svg, same.work.renderSeed == candidate.work.renderSeed,
              app.selectedWork == parent, app.currentSVG == parent.svg, app.visibleDDL == parent.ddl,
              try await database.list().count == initialRows, await provider.calls == initialCalls else {
            throw CheckFailure.message("Word touch changed source/colors/placement, called a provider or leaked an unsaved candidate")
        }
        let saved = try await app.adoptDrawingAdjustmentCandidate(candidate: candidate, token: token)
        let twice = try await app.adoptDrawingAdjustmentCandidate(candidate: candidate, token: token)
        guard saved.id == twice.id, try await database.list().count == initialRows + 1,
              let edge = try await database.edge(childNodeID: saved.lineageNodeID!), edge.parentNodeID == parent.lineageNodeID,
              edge.derivationKind == "touch_change" else { throw CheckFailure.message("Touch adoption was not explicit and idempotent") }
        let metadata = try ExactJSON(data: Data(edge.metadataJSON.utf8))
        guard metadata["render_seed_from"] == .number("0"), metadata["render_seed_to"] == .number("14859340650796947346"),
              metadata["seed_text"].string == canonicalWords else { throw CheckFailure.message("Touch lost exact Server seed provenance") }
        touched = saved
    }
    guard touchSucceeded, let touched else { throw CheckFailure.message("Touch operation failed: \(app.errorText ?? app.status)") }
    do {
        _ = try await app.makeDrawingAdjustmentPlans(work: parent, kind: "touch_change", count: 4, words: words)
        throw CheckFailure.message("Touch admitted four candidates")
    } catch let error as HostError where error.code == "invalid_adjustment_count" { }
    do {
        _ = try await app.makeDrawingAdjustmentPlans(work: parent, kind: "touch_change", count: 1, words: "\u{001c}\u{001f}")
        throw CheckFailure.message("Touch admitted empty core-trimmed words")
    } catch CoreFailure.emptySeedText { }

    // Failure: variation claimed a Stage 2 operation and mutated a Score although current Stage 1.5 is a no-op.
    let variationSucceeded = await app.performComparison(status: "variation check") { token in
        let plans = try await app.makeDrawingAdjustmentPlans(work: parent, kind: "variation", count: 4, amplitude: "large",
            modelReference: "unknown:unused")
        guard plans.count == 4, plans.allSatisfy({ $0.stage1Model == parent.stage1Model && $0.stage2Model == parent.stage2Model }) else {
            throw CheckFailure.message("Variation changed actual parent model facts")
        }
        let candidate = try await app.prepareDrawingAdjustmentCandidate(plan: plans[0], token: token)
        guard candidate.work.score == parent.score, candidate.work.svg == parent.svg, candidate.work.ddl == parent.ddl,
              candidate.work.renderColorMap == parent.renderColorMap, candidate.work.renderSeed == parent.renderSeed,
              candidate.work.compositionSeed == parent.compositionSeed, candidate.work.variationAmplitude == "large",
              candidate.work.variationSeed.flatMap(UInt64.init).map({ (1...((UInt64(1) << 31) - 1)).contains($0) }) == true,
              await provider.calls == initialCalls, try await database.list().count == initialRows + 1,
              app.selectedWork == touched else { throw CheckFailure.message("Current variation was not an unsaved, exact, provider-free replay") }
    }
    guard variationSucceeded else { throw CheckFailure.message("Variation failed: \(app.errorText ?? app.status)") }

    // Failure: there was no frozen four-layout round, and retained drawing borrowed next-work colors or model facts.
    var layouts: [PreparedCandidate] = []
    let layoutSucceeded = await app.performComparison(status: "layout check") { token in
        let plans = try await app.makeDrawingAdjustmentPlans(work: parent, kind: "layout_change", count: 4, modelReference: "check:layout")
        guard plans.count == 4, plans.allSatisfy({ $0.stage1Model == "check:original" && $0.stage2Model == "check:layout" }) else {
            throw CheckFailure.message("Layout plans did not capture Stage 1 facts and local Stage 2 selection")
        }
        app.catalogID = app.catalogs.first(where: { $0.id != parent.catalogID })!.id; app.seedText = "999"; app.wild = false
        for plan in plans { layouts.append(try await app.prepareDrawingAdjustmentCandidate(plan: plan, token: token)) }
        guard Set(layouts.compactMap { $0.work.compositionSeed }).count == 4,
              layouts.allSatisfy({ $0.work.renderSeed == "0" && $0.work.ddl == parent.ddl
                  && $0.work.renderColorMap == parent.renderColorMap && $0.work.renderWild == parent.renderWild
                  && $0.work.stage1Model == "check:original" && $0.work.stage2Model == "check:layout" }),
              await provider.calls == initialCalls, try await database.list().count == initialRows + 1,
              app.selectedWork == touched else { throw CheckFailure.message("Four layout previews mixed current UI state, called a provider or entered history") }
        let saved = try await app.adoptDrawingAdjustmentCandidate(candidate: layouts[0], token: token)
        let savedContext = try await app.savedConfiguration(workID: saved.id)
        guard try ExactJSON(data: savedContext.document!)["macro_locks"] == document["macro_locks"],
              let edge = try await database.edge(childNodeID: saved.lineageNodeID!), edge.derivationKind == "layout_change",
              try ExactJSON(data: Data(edge.metadataJSON.utf8))["composition_seed"] == .number(saved.compositionSeed!) else {
            throw CheckFailure.message("Layout adoption lost retained locks or exact composition metadata")
        }
    }
    guard layoutSucceeded else { throw CheckFailure.message("Layout failed: \(app.errorText ?? app.status)") }

    // Failure: a Stage 2 picker was incorrectly used for reading; promotion/reopening then left a preview writer attached.
    app.selectNextDrawingModel("check:reading")
    var reread: SavedWork?
    let readingSucceeded = await app.performComparison(status: "reading check") { token in
        let plans = try await app.makeDrawingAdjustmentPlans(work: parent, kind: "reinterpretation", count: 1, modelReference: "check:ignored-stage2")
        guard plans[0].stage1Model == "check:reading", plans[0].stage2Model == "check:reading" else {
            throw CheckFailure.message("Reading failed to capture current next Stage 1 for both stages")
        }
        let candidate = try await app.prepareDrawingAdjustmentCandidate(plan: plans[0], token: token)
        guard candidate.work.stage1Model == "check:reading", candidate.work.stage2Model == "check:reading",
              candidate.work.interpretationSeed?.isEmpty == false, candidate.authority == "description_authoritative",
              try await database.list().count == initialRows + 2 else { throw CheckFailure.message("Reading leaked a candidate or lost its actual captured model/authority") }
        let saved = try await app.adoptDrawingAdjustmentCandidate(candidate: candidate, token: token)
        guard let edge = try await database.edge(childNodeID: saved.lineageNodeID!), edge.derivationKind == "reinterpretation",
              try ExactJSON(data: Data(edge.metadataJSON.utf8))["interpretation_seed"].string == saved.interpretationSeed,
              try ExactJSON(data: await app.savedConfiguration(workID: saved.id).document!)["macro_locks"] == document["macro_locks"] else {
            throw CheckFailure.message("Reading lost its saved interpretation provenance or parent macro locks")
        }
        reread = saved
    }
    guard readingSucceeded, let reread else { throw CheckFailure.message("Reading failed: \(app.errorText ?? app.status)") }
    await app.selectWork(reread)
    app.ddlText = "place one green circle at center."
    await app.commitDDL()
    guard app.errorText == nil, let held = app.selectedWork, held.id != reread.id, held.ddl == app.ddlText, app.sourceLocked,
          try await database.list().count == initialRows + 4, try await database.work(id: reread.id) == reread,
          try await database.edge(childNodeID: held.lineageNodeID!)?.parentNodeID == reread.lineageNodeID else {
        throw CheckFailure.message("Reopened adopted reading failed to commit a locked DDL child: \(app.errorText ?? app.status)")
    }
    let callsBeforeLocked = await provider.calls
    do {
        _ = try await app.makeDrawingAdjustmentPlans(work: held, kind: "reinterpretation", count: 1)
        throw CheckFailure.message("DDL authority admitted reading")
    } catch let error as HostError where error.code == "description_source_locked" { }
    let heldSucceeded = await app.performComparison(status: "held layout check") { token in
        let plans = try await app.makeDrawingAdjustmentPlans(work: held, kind: "layout_change", count: 1, modelReference: "check:layout")
        let candidate = try await app.prepareDrawingAdjustmentCandidate(plan: plans[0], token: token)
        guard candidate.authority == "ddl_authoritative", candidate.work.ddl == held.ddl,
              await provider.calls == callsBeforeLocked else { throw CheckFailure.message("Held layout reread or discarded the committed DDL") }
        _ = try await app.makeDrawingAdjustmentPlans(work: held, kind: "variation", count: 1)
        _ = try await app.makeDrawingAdjustmentPlans(work: held, kind: "touch_change", count: 1, words: words)
    }
    guard heldSucceeded else { throw CheckFailure.message("Held non-reading adjustment failed: \(app.errorText ?? app.status)") }

    // Failure: saved edit child edges dropped Server's operation metadata; old Codable requests must remain decodable.
    let descriptionEdit = try await app.makeSavedWorkEditRequest(work: parent, mode: .description, description: parent.effectiveSourceText)
    guard try ExactJSON(data: descriptionEdit.derivationMetadata!)["edited_from_history_id"].string == parent.id else {
        throw CheckFailure.message("Description edit did not carry Server parent metadata")
    }
    var oldRequest = try JSONSerialization.jsonObject(with: JSONEncoder().encode(descriptionEdit)) as! [String: Any]
    oldRequest.removeValue(forKey: "derivationMetadata"); oldRequest.removeValue(forKey: "interpretationSeed")
    let legacyRequest = try JSONDecoder().decode(GenerationRequest.self, from: JSONSerialization.data(withJSONObject: oldRequest))
    guard legacyRequest.derivationMetadata == nil, legacyRequest.interpretationSeed == nil else { throw CheckFailure.message("Optional metadata extension broke an old pinned request") }
    let sketchEdit = try await app.makeSavedWorkEditRequest(work: parent, mode: .sketch, description: parent.effectiveSourceText, sketchMode: "off")
    guard let sketchChild = await app.runSavedWorkEdit(request: sketchEdit),
          let sketchEdge = try await database.edge(childNodeID: sketchChild.lineageNodeID!) else {
        throw CheckFailure.message("Sketch edit metadata child failed: \(app.errorText ?? app.status)")
    }
    let sketchMetadata = try ExactJSON(data: Data(sketchEdge.metadataJSON.utf8))
    guard sketchMetadata["edited_from_history_id"].string == parent.id,
          sketchMetadata["from_sketch_state"].string == parent.sketchState, sketchMetadata["to_sketch_mode"].string == "off" else {
        throw CheckFailure.message("Saved sketch edge lost exact Server operation metadata")
    }

    // Failure: stopping an adjustment admitted a late response or released the busy gate before it drained.
    let beforeCancel = try await database.list().count
    let displayed = app.selectedWork
    let svg = app.currentSVG; let ddl = app.visibleDDL
    await provider.blockNextCall()
    let pending = Task { @MainActor in
        await app.performComparison(status: "cancel check") { token in
            let plans = try await app.makeDrawingAdjustmentPlans(work: parent, kind: "reinterpretation", count: 1)
            _ = try await app.prepareDrawingAdjustmentCandidate(plan: plans[0], token: token)
            throw CheckFailure.message("Stopped adjustment accepted a late candidate")
        }
    }
    try await provider.started.wait()
    let stopping = Task { @MainActor in await app.cancel() }
    try await provider.cancelled.wait()
    guard app.isBusy, app.selectedWork == displayed else {
        await provider.releaseLateAnswer()
        throw CheckFailure.message("Adjustment stop cleared busy before the provider drained")
    }
    await provider.releaseLateAnswer()
    guard !(await pending.value) else { throw CheckFailure.message("Stopped adjustment reported success") }
    await stopping.value
    guard !app.isBusy, app.selectedWork == displayed, app.currentSVG == svg, app.visibleDDL == ddl,
          try await database.list().count == beforeCancel, try await database.work(id: parent.id) == parent,
          try await app.savedConfiguration(workID: parent.id).configuration == context.configuration else {
        throw CheckFailure.message("Late adjustment saved/adopted a child or mutated its parent")
    }
    print(String(format: "Refinement passed in %.3fs: exact word-touch/provider0/zero placement; four frozen layout previews; no-op variation; Stage1 reading; explicit idempotent adoption/reopened DDL fork; held-source guard; Server edit metadata; cancellation drain. Mock transport + isolated SQLite + real Rust only.", Date().timeIntervalSince(began)))
}

private actor RefinementSignal {
    private var fired = false
    private var waiter: CheckedContinuation<Void, Error>?
    private var deadline: Task<Void, Never>?
    func fire() { fired = true; deadline?.cancel(); deadline = nil; waiter?.resume(); waiter = nil }
    func wait() async throws {
        if fired { return }
        try await withCheckedThrowingContinuation { continuation in
            waiter = continuation
            deadline = Task {
                do { try await Task.sleep(for: .seconds(5)) } catch { return }
                self.timeout()
            }
        }
    }
    private func timeout() { waiter?.resume(throwing: CheckFailure.message("Refinement cancellation boundary timed out")); waiter = nil; deadline = nil }
}

private actor RefinementProvider: ProviderTransport {
    nonisolated let started = RefinementSignal()
    nonisolated let cancelled = RefinementSignal()
    private(set) var calls = 0
    private var blockNext = false
    private var action: ExactJSON?
    private var continuation: CheckedContinuation<Data, Never>?
    func blockNextCall() { blockNext = true }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        let input = try ExactJSON(data: action)
        if blockNext {
            blockNext = false; self.action = input
            return await withTaskCancellationHandler {
                await withCheckedContinuation { continuation in
                    self.continuation = continuation
                    Task { await started.fire() }
                }
            } onCancel: { Task { await self.cancelled.fire() } }
        }
        return response(input)
    }
    func releaseLateAnswer() {
        guard let continuation, let action else { return }
        self.continuation = nil; self.action = nil
        continuation.resume(returning: response(action))
    }
    private func response(_ action: ExactJSON) -> Data {
        ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": action["identity"],
            "response": .string(#"{"normalized_ddl":"place one red circle at center."}"#), "elapsed_ms": .string("1")]).data
    }
}
