import Foundation
import InkuHost
import InkuPersistence
import Observation

enum ColorArrangementCursor { case next(SavedVariantOrdinal), exhausted }

enum RefinementResources {
    static func grounds() throws -> [GroundMaterial] {
        try SavedVariants.groundMaterials()
    }
}

public enum SavedScoreVariantKind: Sendable { case colorArrangement, ground }

public struct SavedScoreVariantCandidate: Identifiable, Sendable {
    public let prepared: PreparedCandidate
    public let plan: SavedScoreVariantPlan
    public let order: Int
    public var selected = false
    public var savedWork: SavedWork?
    public var id: String { prepared.id }
    public var work: SavedWork { savedWork ?? prepared.work }
}

/// One immutable saved target. A new color page lands atomically; selection and preview belong to that page.
@MainActor @Observable
public final class SavedScoreVariantModel {
    public let work: SavedWork
    public let kind: SavedScoreVariantKind
    public private(set) var candidates: [SavedScoreVariantCandidate] = []
    public private(set) var running = false
    public private(set) var saving = false
    public private(set) var stopping = false
    public private(set) var exhausted = false
    public private(set) var previewID: String?
    public private(set) var errorText: String?
    public private(set) var failures: [String] = []
    public private(set) var lanes: [ComparisonLaneState] = []
    @ObservationIgnored private var initialized = false
    @ObservationIgnored private var runID: UUID?
    @ObservationIgnored private var completionWaiters: [CheckedContinuation<Void, Never>] = []

    public init(work: SavedWork, kind: SavedScoreVariantKind) { self.work = work; self.kind = kind }
    public var hasUnsaved: Bool { candidates.contains { $0.savedWork == nil } }
    public var selectedCount: Int { candidates.filter { $0.selected && $0.savedWork == nil }.count }

    public func initialize(app: AppModel) async {
        guard !initialized else { return }
        initialized = true
        await generate(app: app)
    }

    public func generate(app: AppModel) async {
        guard !running, !app.isBusy, !exhausted else { return }
        let fanoutLimit: Int
        do { fanoutLimit = try RefinementFanout.validatedLimit(app.display.preferences.refinementFanoutLimit) }
        catch { errorText = error.localizedDescription; return }
        let run = UUID(); runID = run
        running = true; saving = false; stopping = false; errorText = nil; failures = []
        defer { finish() }
        var prepared: [SavedScoreVariantCandidate] = []
        let succeeded = await app.performComparison(status: kind == .ground ? "支持体の候補を用意中" : "配色の候補を用意中", restoreDisplayStatus: true) { token in
            let plans: [SavedScoreVariantPlan]
            if self.kind == .colorArrangement {
                if let page = try await app.nextColorArrangementPage(work: self.work) {
                    plans = page.plans; self.exhausted = page.nextCursor == nil
                } else { plans = []; self.exhausted = true }
            } else { plans = try await app.makeGroundVariantPlans(work: self.work) }
            self.lanes = plans.map { _ in .waiting }
            try await RefinementFanout.run(count: plans.count, limit: fanoutLimit, onStart: { index in self.lanes[index] = .running }) { index in
                try Task.checkCancellation()
                guard self.runID == run, !self.stopping else { throw CancellationError() }
                do {
                    let candidate = try await app.prepareSavedScoreVariant(plans[index], token: token)
                    try Task.checkCancellation()
                    guard self.runID == run, !self.stopping else { throw CancellationError() }
                    prepared.append(SavedScoreVariantCandidate(prepared: candidate, plan: plans[index], order: index))
                } catch {
                    try Task.checkCancellation()
                    guard self.runID == run, !self.stopping else { throw CancellationError() }
                    self.failures.append(app.failureMessage(error))
                }
                self.lanes[index] = .done
            }
        }
        if runID == run, !stopping {
            candidates = prepared.sorted { $0.order < $1.order }; previewID = nil
            if !succeeded { errorText = app.errorText }
        }
    }

    public func preview(_ id: String?) { if !running { previewID = id } }
    public func selectCandidate(_ id: String, selected: Bool) {
        guard !running, let index = candidates.firstIndex(where: { $0.id == id }), candidates[index].savedWork == nil else { return }
        candidates[index].selected = selected
    }
    public func discardCandidates() {
        guard !running else { return }
        candidates.removeAll { $0.savedWork == nil }; previewID = nil
    }

    @discardableResult public func saveSelected(app: AppModel) async -> Bool {
        guard !running, !app.isBusy, selectedCount > 0 else { return false }
        let selection = candidates.filter { $0.selected && $0.savedWork == nil }
        let run = UUID(); runID = run
        running = true; saving = true; stopping = false; errorText = nil
        defer { finish() }
        var savedCount = 0
        let succeeded = await app.performComparison(status: "選択した候補を保存中") { token in
            for candidate in selection {
                try Task.checkCancellation()
                guard self.runID == run, !self.stopping else { throw CancellationError() }
                let saved = try await app.saveComparisonCandidate(executionID: candidate.id, token: token)
                if let index = self.candidates.firstIndex(where: { $0.id == candidate.id }) {
                    self.candidates[index].savedWork = saved; self.candidates[index].selected = false
                }
                savedCount += 1
            }
        }
        if !succeeded { errorText = app.errorText }
        let complete = succeeded && !stopping && savedCount == selection.count
        if complete { discardUnsavedAfterSave() }
        return complete
    }

    private func discardUnsavedAfterSave() { candidates.removeAll { $0.savedWork == nil }; previewID = nil }

    public func stop(app: AppModel) async {
        guard running, !stopping else { return }
        stopping = true
        if !saving { runID = nil }
        await app.cancel()
        if running { await withCheckedContinuation { completionWaiters.append($0) } }
    }
    private func finish() {
        running = false; saving = false; stopping = false; lanes = []
        let waiters = completionWaiters; completionWaiters = []
        waiters.forEach { $0.resume() }
    }
}
