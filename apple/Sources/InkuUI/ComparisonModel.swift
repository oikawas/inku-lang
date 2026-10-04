import Foundation
import InkuHost
import InkuPersistence
import Observation

public enum ComparisonKind: String, CaseIterable, Sendable {
    case catalog, model
}

public struct ComparisonCandidate: Identifiable, Sendable {
    public let prepared: PreparedCandidate
    public let label: String
    public var selected = false
    public var savedWork: SavedWork?
    public var id: String { prepared.id }
    public var work: SavedWork { savedWork ?? prepared.work }
}

/// Each comparison pins its original work; candidate preparation never adopts or saves it.
@MainActor @Observable
public final class ComparisonModel {
    public var kind = ComparisonKind.catalog
    public var selectedCatalogIDs: Set<String> = []
    public var modelReferencesText = ""
    public private(set) var selectedModelReferences: Set<String> = []
    public private(set) var modelProviders: [ProviderSettings] = []
    public private(set) var failedModelReferences: Set<String> = []
    public private(set) var original: SavedWork?
    public private(set) var sourceIsLocked = false
    public private(set) var contextAvailable = false
    public private(set) var candidates: [ComparisonCandidate] = []
    public private(set) var failures: [String] = []
    public private(set) var running = false
    public private(set) var saving = false
    public private(set) var stopping = false
    public private(set) var status = ""
    public var errorText: String?
    @ObservationIgnored private var initialized = false
    @ObservationIgnored private var runID: UUID?
    @ObservationIgnored private var completionWaiters: [CheckedContinuation<Void, Never>] = []
    private let requestedWork: SavedWork?

    public init(work: SavedWork? = nil, kind: ComparisonKind = .catalog) {
        requestedWork = work
        self.kind = kind
    }

    public var modelReferences: [String] {
        selectedModelReferences.sorted()
    }
    public var selectedCount: Int { candidates.filter { $0.selected && $0.savedWork == nil }.count }
    public var requestedCount: Int { kind == .catalog ? selectedCatalogIDs.count : modelReferences.count }
    public var canGenerate: Bool {
        contextAvailable && !running && requestedCount > 0
            && !hasUnsaved && (kind != .model || modelReferences.count <= 4)
            && !(kind == .model && sourceIsLocked)
    }
    public var hasUnsaved: Bool { candidates.contains { $0.savedWork == nil } }
    public var targetModelReference: String { original?.stage1Model ?? original?.stage2Model ?? "" }

    public func initialize(app: AppModel) async {
        guard !initialized else { return }
        initialized = true
        guard !app.isPreview, let work = requestedWork ?? app.selectedWork else {
            errorText = "比較の元になる保存作品を選択してください。"
            return
        }
        original = work
        do {
            let context = try await app.savedConfiguration(workID: work.id)
            sourceIsLocked = context.authority == "ddl_authoritative"
            contextAvailable = true
            let settings = await app.nextGenerationSettings()
            modelProviders = settings.providers.filter { !SettingsModel.batchModels(for: $0).isEmpty }
            selectedCatalogIDs = Set(app.catalogs.filter { $0.id != (work.renderColorCatalogID ?? work.catalogID) }.map(\.id))
            status = "元の作品の条件を固定しました。比較する配色またはモデルを選択してください。"
        } catch {
            errorText = "この作品には比較用の保存設定がありません: \(error.localizedDescription)"
        }
    }

    public func selectCatalog(_ id: String, selected: Bool) {
        guard !running, !hasUnsaved else { return }
        if !selected { selectedCatalogIDs.remove(id) }
        else { selectedCatalogIDs.insert(id) }
    }

    public func selectModel(_ reference: String, selected: Bool) {
        guard !running, !hasUnsaved, !sourceIsLocked else { return }
        if !selected { selectedModelReferences.remove(reference); return }
        guard selectedModelReferences.count < 4, reference != targetModelReference,
              modelProviders.contains(where: { provider in
                  SettingsModel.batchModels(for: provider).contains { provider.id + ":" + $0.id == reference && $0.isSelectable }
              }) else { return }
        selectedModelReferences.insert(reference)
    }

    public func discardCandidates() {
        guard !running else { return }
        candidates.removeAll { $0.savedWork == nil }
        failures = []; failedModelReferences = []
        errorText = nil
    }

    public func selectCandidate(_ id: String, selected: Bool) {
        guard !running, let index = candidates.firstIndex(where: { $0.id == id }), candidates[index].savedWork == nil else { return }
        candidates[index].selected = selected
    }

    public func generate(app: AppModel) async {
        guard canGenerate, !app.isBusy, let work = original else { return }
        let comparisonKind = kind
        let labels = comparisonKind == .catalog
            ? app.catalogs.filter { selectedCatalogIDs.contains($0.id) }.map { ($0.id, $0.name) }
            : modelReferences.map { ($0, $0) }
        guard !labels.isEmpty, labels.count == requestedCount else {
            errorText = "比較する候補を指定してください。"
            return
        }
        if comparisonKind == .model {
            let settings = await app.hostSettings()
            guard labels.count <= 4, labels.allSatisfy({ reference, _ in
                reference != targetModelReference && SettingsModel.isBatchModelAvailable(reference, settings: settings)
            }) else {
                errorText = "使用中のLLMモデルを4件まで選択してください。"
                return
            }
        }
        let run = UUID()
        runID = run
        running = true; saving = false; stopping = false
        errorText = nil; failures = []; failedModelReferences = []; candidates = []
        let succeeded = await app.performComparison(status: "比較候補を生成中") { token in
            var requests: [GenerationRequest] = []
            if comparisonKind == .model {
                for entry in labels {
                    requests.append(try await app.makeRefinementRequest(work: work, kind: "model_comparison", modelReference: entry.0))
                }
                requests = try await app.pinPersonalPlanRequests(requests)
            }
            for (index, entry) in labels.enumerated() {
                try Task.checkCancellation()
                guard self.runID == run, !self.stopping else { throw CancellationError() }
                self.status = "候補 \(index + 1)/\(labels.count): \(entry.1)"
                do {
                    let candidate: PreparedCandidate
                    if comparisonKind == .catalog {
                        candidate = try await app.previewCatalogCandidate(work: work, catalogID: entry.0, token: token)
                    } else {
                        candidate = try await app.generateCandidate(request: requests[index], token: token)
                    }
                    try Task.checkCancellation()
                    guard self.runID == run, !self.stopping else { throw CancellationError() }
                    self.candidates.append(ComparisonCandidate(prepared: candidate, label: entry.1))
                } catch {
                    try Task.checkCancellation()
                    guard self.runID == run, !self.stopping else { throw CancellationError() }
                    self.failures.append("\(entry.1): \(error.localizedDescription)")
                    if comparisonKind == .model { self.failedModelReferences.insert(entry.0) }
                }
            }
        }
        if runID == run {
            status = succeeded ? "\(candidates.count)件の候補を用意しました。保存する候補を選択してください。" : "比較を開始できませんでした。"
            if !succeeded { errorText = app.errorText }
        } else { status = "比較を停止しました。保存されていない候補を破棄しました。" }
        finish()
    }

    @discardableResult public func saveSelected(app: AppModel) async -> Bool {
        guard !running, !app.isBusy, selectedCount > 0 else { return false }
        let selection = candidates.filter { $0.selected && $0.savedWork == nil }
        let run = UUID()
        runID = run; running = true; saving = true; stopping = false; errorText = nil
        var savedCount = 0
        let succeeded = await app.performComparison(status: "選択した候補を保存中") { token in
            for candidate in selection {
                try Task.checkCancellation()
                guard self.runID == run, !self.stopping else { throw CancellationError() }
                self.status = "保存中: \(candidate.label)"
                let saved = try await app.saveComparisonCandidate(executionID: candidate.id, token: token)
                // A completed transaction stays visible even when cancellation arrives after its commit.
                if let index = self.candidates.firstIndex(where: { $0.id == candidate.id }) {
                    self.candidates[index].savedWork = saved
                    self.candidates[index].selected = false
                }
                savedCount += 1
            }
        }
        if stopping { status = "保存を停止しました。保存済み \(savedCount)件は履歴と系譜に残ります。" }
        else if succeeded { status = "選択した\(savedCount)件を保存しました。" }
        else { status = "保存済み \(savedCount)件"; errorText = app.errorText }
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
        running = false; saving = false; stopping = false
        let waiters = completionWaiters; completionWaiters = []
        waiters.forEach { $0.resume() }
    }
}
