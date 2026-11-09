import Foundation
import InkuHost
import InkuPersistence
import Observation

/// Web `RefinementCompositionFormView` and `generateCompositionFormCandidates` (refinement-coordinator.svelte.ts):
/// the saved work's description is read again in words with composition on, with the chosen form decided
/// (`authoring.composition.form`). One or four candidates of that form are drawn unsaved, as the model comparison's
/// are, and the chosen ones are saved from their executions (`AppModel.saveComparisonCandidate`), not drawn again.
@MainActor @Observable
public final class CompositionFormModel {
    public var selectedForm = "one_corner"
    public private(set) var original: SavedWork?
    /// The form the work was composed with (`description_ddl.composition.answer.form`); nil when none was recorded.
    public private(set) var currentForm: String?
    /// Web `compositionFormSwitch`: the work was not drawn in words with composition, so this switches it on.
    public private(set) var switchesComposition = false
    public private(set) var sourceIsLocked = false
    public private(set) var contextAvailable = false
    public private(set) var candidates: [ComparisonCandidate] = []
    public private(set) var previewID: String?
    public private(set) var failures: [String] = []
    public private(set) var laneLabels: [String] = []
    public private(set) var laneStates: [ComparisonLaneState] = []
    public private(set) var running = false
    public private(set) var saving = false
    public private(set) var stopping = false
    public private(set) var status = ""
    public var errorText: String?
    @ObservationIgnored private var initialized = false
    @ObservationIgnored private var runID: UUID?
    @ObservationIgnored private var failureOrder: [Int: String] = [:]
    @ObservationIgnored private var completionWaiters: [CheckedContinuation<Void, Never>] = []
    private let requestedWork: SavedWork?

    public init(work: SavedWork? = nil) { requestedWork = work }

    public var selectedCount: Int { candidates.filter { $0.selected && $0.savedWork == nil }.count }
    public var hasUnsaved: Bool { candidates.contains { $0.savedWork == nil } }
    /// Web: the 1 and 4 buttons wait while drawing and while unsaved candidates are shown.
    public var canGenerate: Bool { contextAvailable && !sourceIsLocked && !running && !hasUnsaved }

    public func initialize(app: AppModel) async {
        guard !initialized else { return }
        initialized = true
        guard !app.isPreview, let work = requestedWork ?? app.selectedWork else {
            errorText = "構図の形を変える保存作品を選択してください。"
            return
        }
        original = work
        do {
            let context = try await app.savedConfiguration(workID: work.id)
            sourceIsLocked = context.authority == "ddl_authoritative"
            let record = context.descriptionDDL.flatMap { try? ExactJSON(data: $0) }
            let form = record?["composition"]["answer"]["form"].string
            currentForm = form.flatMap { CompositionForm.all.contains($0) ? $0 : nil }
            // CanvasPanel.svelte:916: the switch notice shows when the work has no composition record.
            switchesComposition = record?["composition"].object == nil
            selectedForm = currentForm ?? "one_corner"
            contextAvailable = true
        } catch {
            errorText = "この作品には推敲用の保存設定がありません: \(error.localizedDescription)"
        }
    }

    public func discardCandidates() {
        guard !running else { return }
        candidates.removeAll { $0.savedWork == nil }
        previewID = nil; failures = []; errorText = nil
    }

    public func selectCandidate(_ id: String, selected: Bool) {
        guard !running, let index = candidates.firstIndex(where: { $0.id == id }), candidates[index].savedWork == nil else { return }
        candidates[index].selected = selected
    }

    public func preview(_ id: String?) { if !running { previewID = id } }

    /// `count` is 1 or 4 candidates of the selected form.
    public func generate(app: AppModel, count: Int) async {
        guard canGenerate, [1, 4].contains(count), !app.isBusy, let work = original else { return }
        let fanoutLimit: Int
        do { fanoutLimit = try RefinementFanout.validatedLimit(app.display.preferences.refinementFanoutLimit) }
        catch { errorText = error.localizedDescription; return }
        let form = selectedForm
        let labels = (1...count).map(String.init)
        let run = UUID()
        runID = run
        running = true; saving = false; stopping = false; app.runStops.track(self)
        errorText = nil; failures = []; failureOrder = [:]; candidates = []; previewID = nil
        laneLabels = labels
        laneStates = labels.map { _ in .waiting }
        let succeeded = await app.performComparison(status: "候補を生成中", restoreDisplayStatus: true) { token in
            var requests: [GenerationRequest] = []
            for _ in labels {
                requests.append(try await app.makeRefinementRequest(work: work, kind: CompositionForm.derivationKind, compositionForm: form))
            }
            let pinned = try await app.pinPersonalPlanRequests(requests)
            try await RefinementFanout.run(count: labels.count, limit: fanoutLimit, onStart: { index in
                self.laneStates[index] = .running
                self.status = "候補 \(index + 1)/\(labels.count)"
            }) { index in
                try Task.checkCancellation()
                guard self.runID == run, !self.stopping else { throw CancellationError() }
                do {
                    let candidate = try await app.generateCandidate(request: pinned[index], token: token)
                    try Task.checkCancellation()
                    guard self.runID == run, !self.stopping else { throw CancellationError() }
                    self.candidates.append(ComparisonCandidate(prepared: candidate, label: labels[index], order: index))
                    self.candidates.sort { $0.order < $1.order }
                } catch {
                    try Task.checkCancellation()
                    guard self.runID == run, !self.stopping else { throw CancellationError() }
                    self.failureOrder[index] = "\(labels[index]): \(error.localizedDescription)"
                    self.failures = self.failureOrder.sorted { $0.key < $1.key }.map(\.value)
                }
                self.laneStates[index] = .done
            }
        }
        if runID == run {
            status = succeeded ? "\(candidates.count)件の候補を用意しました。保存する候補を選択してください。" : "候補を作れませんでした。"
            if !succeeded { errorText = app.errorText }
        } else { status = "停止しました。保存されていない候補を破棄しました。" }
        finish()
    }

    @discardableResult public func saveSelected(app: AppModel) async -> Bool {
        guard !running, !app.isBusy, selectedCount > 0 else { return false }
        let selection = candidates.filter { $0.selected && $0.savedWork == nil }
        let run = UUID()
        runID = run; running = true; saving = true; stopping = false; errorText = nil; app.runStops.track(self)
        var savedCount = 0
        var expired = false
        let succeeded = await app.performComparison(status: "選択した候補を保存中") { token in
            for candidate in selection {
                try Task.checkCancellation()
                guard self.runID == run, !self.stopping else { throw CancellationError() }
                self.status = "保存中: \(candidate.label)"
                let saved: SavedWork
                do { saved = try await app.saveComparisonCandidate(executionID: candidate.id, token: token) }
                catch let error as HostError where error.code == "candidate_not_found" { expired = true; throw error }
                if let index = self.candidates.firstIndex(where: { $0.id == candidate.id }) {
                    self.candidates[index].savedWork = saved
                    self.candidates[index].selected = false
                }
                savedCount += 1
            }
        }
        if stopping { status = "保存を停止しました。保存済み \(savedCount)件は履歴と系譜に残ります。" }
        else if succeeded { status = "選択した\(savedCount)件を保存しました。" }
        else {
            status = "保存済み \(savedCount)件"
            // Web compositionFormExpired: the candidate's execution is gone.
            errorText = expired ? app.display.webCopy("compositionFormExpired", "候補が見つかりません。もう一度候補を作ってください。") : app.errorText
        }
        let committedAll = succeeded && !stopping && savedCount == selection.count
        if committedAll { candidates.removeAll { $0.savedWork == nil } }
        finish()
        return committedAll
    }

    public func stop(app: AppModel) async {
        guard running, !stopping else { return }
        stopping = true
        status = "停止中"
        if !saving { runID = nil; candidates = []; failures = [] }
        await app.cancel()
        if running { await withCheckedContinuation { completionWaiters.append($0) } }
    }

    private func finish() {
        running = false; saving = false; stopping = false; laneLabels = []; laneStates = []
        let waiters = completionWaiters; completionWaiters = []
        waiters.forEach { $0.resume() }
    }
}

extension CompositionFormModel: StoppableRun { var isStoppableRunActive: Bool { running } }
