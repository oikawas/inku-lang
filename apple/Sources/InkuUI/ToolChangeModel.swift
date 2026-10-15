import Foundation
import InkuHost
import InkuPersistence
import Observation

public struct ToolChangeCandidate: Identifiable, Sendable {
    public let prepared: PreparedCandidate
    public let plan: ToolVariantPlan
    public let number: Int
    public var selected = false
    public var savedWork: SavedWork?
    public var id: String { prepared.id }
    public var work: SavedWork { savedWork ?? prepared.work }
}

/// Owns one saved target; the Create draft never supplies an option or its saved description.
@MainActor @Observable
public final class ToolChangeModel {
    public let work: SavedWork
    public var mode = ToolChangeMode.uniform
    public private(set) var candidates: [ToolChangeCandidate] = []
    public private(set) var running = false
    public private(set) var saving = false
    public private(set) var stopping = false
    public private(set) var noChangeableSentences = false
    public private(set) var errorText: String?
    public private(set) var failures: [String] = []
    public private(set) var lanes: [ComparisonLaneState] = []
    public private(set) var previewID: String?
    @ObservationIgnored private var runID: UUID?
    @ObservationIgnored private var completionWaiters: [CheckedContinuation<Void, Never>] = []

    public init(work: SavedWork) { self.work = work }
    public var hasUnsaved: Bool { candidates.contains { $0.savedWork == nil } }
    public var selectedCount: Int { candidates.filter { $0.selected && $0.savedWork == nil }.count }

    public func generate(app: AppModel) async {
        guard !running, !app.isBusy else { return }
        let chosenMode = mode
        let run = UUID(); runID = run
        running = true; stopping = false; errorText = nil; failures = []
        candidates = []; lanes = []; noChangeableSentences = false; previewID = nil
        defer { finish() }
        let succeeded = await app.performComparison(status: "てざわりの候補を用意中", restoreDisplayStatus: true) { token in
            let plans = try await app.makeToolVariantPlans(work: self.work, mode: chosenMode)
            try Task.checkCancellation()
            guard self.runID == run else { throw CancellationError() }
            self.noChangeableSentences = plans.isEmpty
            self.lanes = plans.map { _ in .waiting }
            try await RefinementFanout.run(count: plans.count, onStart: { index in self.lanes[index] = .running }) { index in
                try Task.checkCancellation()
                guard self.runID == run, !self.stopping else { throw CancellationError() }
                do {
                    let prepared = try await app.prepareToolVariant(plans[index], token: token)
                    try Task.checkCancellation()
                    guard self.runID == run, !self.stopping else { throw CancellationError() }
                    self.candidates.append(ToolChangeCandidate(prepared: prepared, plan: plans[index], number: index + 1))
                    self.candidates.sort { $0.number < $1.number }
                } catch {
                    try Task.checkCancellation()
                    guard self.runID == run, !self.stopping else { throw CancellationError() }
                    self.failures.append(app.failureMessage(error))
                }
                self.lanes[index] = .done
            }
        }
        if !succeeded, !stopping { errorText = app.errorText }
    }

    public func selectCandidate(_ id: String, selected: Bool) {
        guard !running, let index = candidates.firstIndex(where: { $0.id == id }), candidates[index].savedWork == nil else { return }
        candidates[index].selected = selected
    }

    public func preview(_ id: String?) { if !running { previewID = id } }

    public func discardCandidates() {
        guard !running else { return }
        candidates.removeAll { $0.savedWork == nil }
        previewID = nil
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
                    self.candidates[index].savedWork = saved
                    self.candidates[index].selected = false
                }
                savedCount += 1
            }
        }
        if !succeeded { errorText = app.errorText }
        return succeeded && !stopping && savedCount == selection.count
    }

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
