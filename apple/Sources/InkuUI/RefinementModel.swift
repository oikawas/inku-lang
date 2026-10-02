import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import Observation

public enum RefinementKind: String, CaseIterable, Hashable, Sendable {
    case layout = "layout_change"
    case reading = "reinterpretation"
    case variation
    case touch = "touch_change"

    public var titleKey: String {
        switch self {
        case .layout: "配置を変える"
        case .reading: "読み取りを変える"
        case .variation: "変奏（いまは何も動かない）"
        case .touch: "言葉でタッチを変える"
        }
    }

    public var symbol: String {
        switch self {
        case .layout: "square.grid.2x2"
        case .reading: "text.book.closed"
        case .variation: "circle.dotted"
        case .touch: "paintbrush.pointed"
        }
    }
}

public struct RefinementCandidate: Identifiable, Sendable {
    public let prepared: PreparedCandidate
    public let kind: RefinementKind
    public let number: Int
    public var selected = false
    public var savedWork: SavedWork?
    public var id: String { prepared.id }
    public var work: SavedWork { savedWork ?? prepared.work }
}

public struct RefinementSlot: Identifiable, Sendable {
    public enum State: Equatable, Sendable { case waiting, running, ready, failed }
    public let id: Int
    public var state: State = .waiting
    public var error: String?
}

/// A dialog owns one immutable parent and private, explicitly adopted options.
@MainActor @Observable
public final class RefinementModel {
    public let work: SavedWork
    public var kind = RefinementKind.touch
    public var words = ""
    public var amplitude = "medium"
    public var inheritWild = true
    public var wildOverride: Bool
    public var modelReference = ""
    public private(set) var initialized = false
    public private(set) var initializing = false
    public private(set) var sourceIsLocked = false
    public private(set) var sourceIsDDLOrigin = false
    public private(set) var running = false
    public private(set) var saving = false
    public private(set) var stopping = false
    public private(set) var closed = false
    public private(set) var candidates: [RefinementCandidate] = []
    public private(set) var slots: [RefinementSlot] = []
    public private(set) var previewID: String?
    public private(set) var committedWorks: [SavedWork] = []
    public private(set) var capturedStage1Model: String?
    public private(set) var capturedStage2Model: String?
    public private(set) var status = "元の作品の条件を確認中"
    public private(set) var errorText: String?
    @ObservationIgnored private var operation: Task<Bool, Never>?
    @ObservationIgnored private var runID: UUID?
    @ObservationIgnored private var ownsAppOperation = false

    public init(work: SavedWork) {
        self.work = work
        wildOverride = work.renderWild ?? false
    }

    public var selectedCount: Int { candidates.filter { $0.selected && $0.savedWork == nil }.count }
    public var hasUnsaved: Bool { candidates.contains { $0.savedWork == nil } }
    public var completedCount: Int { slots.filter { $0.state == .ready || $0.state == .failed }.count }
    public var canSave: Bool { initialized && !running && !closed && selectedCount > 0 }
    private var hasTouchWords: Bool { (try? InkuCore.renderSeed(fromText: words)) != nil }

    public func canGenerate(count: Int) -> Bool {
        initialized && !running && !closed && !work.trashed && !hasUnsaved
            && [1, 4].contains(count) && !(kind == .reading && sourceIsLocked)
            && !(kind == .touch && (count != 1 || !hasTouchWords))
    }

    public func initialize(app: AppModel) async {
        guard !initialized, !initializing, !closed else { return }
        initializing = true
        defer { initializing = false }
        do {
            let context = try await app.savedConfiguration(workID: work.id)
            try Task.checkCancellation()
            guard !closed else { return }
            guard ["description_authoritative", "ddl_authoritative"].contains(context.authority) else {
                throw HostError("saved_authoring_context_unavailable")
            }
            sourceIsLocked = context.authority != "description_authoritative"
            sourceIsDDLOrigin = context.origin == "direct_ddl"
            if sourceIsLocked && kind == .reading { kind = .touch }
            if modelReference.isEmpty { modelReference = app.nextDrawingModelReference }
            initialized = true
            errorText = nil
            status = "変更条件を固定しました。候補を用意してください。"
        } catch is CancellationError { }
        catch { if !closed { errorText = error.localizedDescription } }
    }

    public func selectCandidate(_ id: String, selected: Bool) {
        guard !running, !closed, let index = candidates.firstIndex(where: { $0.id == id }),
              candidates[index].savedWork == nil else { return }
        candidates[index].selected = selected
    }

    public func preview(_ id: String?) {
        guard !running, !closed, id == nil || candidates.contains(where: { $0.id == id }) else { return }
        previewID = id
    }

    public func discardCandidates() {
        guard !running else { return }
        candidates = []; slots = []; previewID = nil
        errorText = nil
        status = "採用していない候補を破棄しました。"
    }

    public func generate(app: AppModel, count: Int) async {
        guard canGenerate(count: count), !app.isBusy, !app.isPreview, operation == nil,
              kind != .reading || app.hasNextDrawingModel else { return }
        let selectedKind = kind
        let selectedWords = words
        let selectedAmplitude = amplitude
        let selectedWild: Bool? = selectedKind == .touch || inheritWild ? nil : wildOverride
        let selectedModel: String? = selectedKind == .layout && !modelReference.isEmpty ? modelReference : nil
        let run = UUID()
        runID = run; running = true; saving = false; stopping = false
        candidates = []; previewID = nil; errorText = nil
        slots = (1...count).map { RefinementSlot(id: $0) }
        capturedStage1Model = selectedKind == .reading ? app.nextDrawingModelReference : work.stage1Model
        capturedStage2Model = [.touch, .variation].contains(selectedKind) ? work.stage2Model : selectedModel ?? app.nextDrawingModelReference
        status = "候補の準備中"
        let pending = Task { @MainActor [weak self] in
            guard let self else { return false }
            defer { self.finishOperation() }
            do {
                try Task.checkCancellation()
                guard self.runID == run, !self.closed, !app.isBusy else { throw CancellationError() }
                self.ownsAppOperation = true
                defer { self.ownsAppOperation = false }
                let succeeded = await app.performComparison(status: "調整候補を用意中", restoreDisplayStatus: true) { token in
                    try Task.checkCancellation()
                    let plans = try await app.makeDrawingAdjustmentPlans(work: self.work, kind: selectedKind.rawValue,
                        count: count, words: selectedWords, amplitude: selectedAmplitude,
                        wildOverride: selectedWild, modelReference: selectedModel)
                    try Task.checkCancellation()
                    guard self.runID == run, !self.closed, !self.stopping else { throw CancellationError() }
                    guard plans.count == count else { throw HostError("invalid_adjustment_plan_count") }
                    self.capturedStage1Model = plans.first?.stage1Model
                    self.capturedStage2Model = plans.first?.stage2Model
                    for (index, plan) in plans.enumerated() {
                        try Task.checkCancellation()
                        guard self.runID == run, !self.closed, !self.stopping else { throw CancellationError() }
                        self.slots[index].state = .running
                        do {
                            let candidate = try await app.prepareDrawingAdjustmentCandidate(plan: plan, token: token)
                            try Task.checkCancellation()
                            guard self.runID == run, !self.closed, !self.stopping else { throw CancellationError() }
                            self.candidates.append(RefinementCandidate(prepared: candidate, kind: selectedKind, number: index + 1))
                            self.slots[index].state = .ready
                        } catch {
                            try Task.checkCancellation()
                            guard self.runID == run, !self.closed, !self.stopping else { throw CancellationError() }
                            self.slots[index].state = .failed
                            self.slots[index].error = error.localizedDescription
                        }
                    }
                }
                try Task.checkCancellation()
                guard self.runID == run, !self.closed else { throw CancellationError() }
                if succeeded && !self.candidates.isEmpty { self.status = "候補を選んで採用してください。" }
                else {
                    if !succeeded { self.candidates = []; self.previewID = nil }
                    self.status = "候補を用意できませんでした。"
                    self.errorText = app.errorText ?? "候補を用意できませんでした。"
                }
                return succeeded
            } catch is CancellationError {
                self.candidates = []; self.slots = []; self.previewID = nil
                self.status = "候補の準備を停止しました。"
                return false
            } catch {
                self.errorText = error.localizedDescription
                return false
            }
        }
        operation = pending
        _ = await pending.value
    }

    /// True means every selected option committed and all remaining options were discarded.
    public func saveSelected(app: AppModel) async -> Bool {
        guard canSave, !app.isBusy, !app.isPreview, operation == nil else { return false }
        let selection = candidates.filter { $0.selected && $0.savedWork == nil }
        let run = UUID()
        runID = run; running = true; saving = true; stopping = false; errorText = nil
        status = "選択した候補を保存中"
        let pending = Task { @MainActor [weak self] in
            guard let self else { return false }
            defer { self.finishOperation() }
            do {
                try Task.checkCancellation()
                guard self.runID == run, !self.closed, !app.isBusy else { throw CancellationError() }
                self.ownsAppOperation = true
                defer { self.ownsAppOperation = false }
                let succeeded = await app.performComparison(status: "選択した調整候補を採用中") { token in
                    for candidate in selection {
                        try Task.checkCancellation()
                        guard self.runID == run, !self.closed, !self.stopping else { throw CancellationError() }
                        let saved = try await app.adoptDrawingAdjustmentCandidate(candidate: candidate.prepared, token: token)
                        // The transaction result survives cancellation after its commit.
                        if let index = self.candidates.firstIndex(where: { $0.id == candidate.id }) {
                            self.candidates[index].savedWork = saved
                            self.candidates[index].selected = false
                        }
                        if !self.committedWorks.contains(where: { $0.id == saved.id }) { self.committedWorks.append(saved) }
                        try Task.checkCancellation()
                    }
                }
                try Task.checkCancellation()
                guard succeeded, self.runID == run, !self.closed else {
                    self.errorText = app.errorText ?? "候補を保存できませんでした。未保存の候補を確認してください。"
                    return false
                }
                self.candidates = []; self.slots = []; self.previewID = nil
                self.status = "選択した候補を採用しました。"
                return true
            } catch is CancellationError {
                self.status = "保存を停止しました。保存済みの候補は履歴と系譜に残ります。"
                return false
            } catch {
                self.errorText = error.localizedDescription
                return false
            }
        }
        operation = pending
        return await pending.value
    }

    public func stop(app: AppModel) async {
        guard let operation else { return }
        stopping = true
        operation.cancel()
        if ownsAppOperation { await app.cancel() }
        _ = await operation.value
    }

    public func close(app: AppModel) async -> Bool {
        closed = true
        await stop(app: app)
        guard !running, !app.isBusy else { closed = false; return false }
        discardCandidates()
        return true
    }

    private func finishOperation() {
        operation = nil; runID = nil
        running = false; saving = false; stopping = false
    }
}
