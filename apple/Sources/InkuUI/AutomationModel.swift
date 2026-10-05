import Foundation
import InkuHost
import InkuPersistence
import Observation

public struct BatchRow: Codable, Sendable, Identifiable {
    public enum State: String, Codable, Sendable { case waiting, running, succeeded, failed, uncertain, skipped }
    public var id = UUID().uuidString
    public var line: Int
    public var input: String
    public var request: GenerationRequest
    public var state: State = .waiting
    public var attempts = 0
    public var workID: String?
    public var error: String?
}

public struct BatchDrawingConditions: Codable, Sendable {
    public var stage1Model: String
    public var stage2Model: String
    public var catalogID: String?
    public var canvasID: String?
    public var wild: Bool?
    public var inputMode: String
    public var sketchMode: String
    public var catalogMode: String

    init(request: GenerationRequest, catalogMode: String? = nil) {
        stage1Model = request.models.stage1Model; stage2Model = request.models.stage2Model
        let options = (try? JSONSerialization.jsonObject(with: request.renderOptions)) as? [String: Any]
        catalogID = options?["catalog_id"] as? String
        canvasID = options?["canvas_aspect_id"] as? String
        wild = options?["wild"] as? Bool
        switch request.authoring {
        case .directDDL:
            inputMode = "ddl"; sketchMode = "off"; self.catalogMode = catalogMode ?? "fixed"
        case .description(_, let auto, let sketch):
            inputMode = "description"; self.catalogMode = catalogMode ?? (auto ? "auto" : "fixed")
            switch sketch { case .off: sketchMode = "off"; case .on: sketchMode = "on"; case .supplied: sketchMode = "supplied" }
        }
    }
}

private struct BatchJournal: Codable, Sendable {
    var id = UUID().uuidString
    var created = Date()
    var rows: [BatchRow]
    var retries: Int
    var round = 0
    // Optional additions keep journals written by earlier clients readable.
    var originalText: String?
    var conditions: BatchDrawingConditions?
    var observedRowID: String?
}

private actor BatchJournalStore {
    let url: URL
    init(url: URL) { self.url = url }
    func load() throws -> BatchJournal? {
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        return try JSONDecoder().decode(BatchJournal.self, from: Data(contentsOf: url))
    }
    func save(_ journal: BatchJournal) throws {
        try JSONEncoder().encode(journal).write(to: url, options: .atomic)
    }
    func loadHistory() throws -> [String] {
        let historyURL = url.deletingLastPathComponent().appendingPathComponent("batch-prompt-history.json")
        guard FileManager.default.fileExists(atPath: historyURL.path) else { return [] }
        return try JSONDecoder().decode([String].self, from: Data(contentsOf: historyURL))
    }
    func saveHistory(_ prompts: [String]) throws {
        let historyURL = url.deletingLastPathComponent().appendingPathComponent("batch-prompt-history.json")
        try JSONEncoder().encode(prompts).write(to: historyURL, options: .atomic)
    }
}

private enum BatchPromptHistory {
    static func normalized(_ values: [String]) -> [String] {
        var seen = Set<String>()
        var result: [String] = []
        for value in values {
            let text = BatchInputLines.normalizedText(value.trimmingCharacters(in: .whitespacesAndNewlines))
            guard !text.isEmpty, text.utf16.count <= 20_000, seen.insert(text).inserted else { continue }
            result.append(text)
            if result.count == 50 { break }
        }
        return result
    }
}

private struct DemoPreferences: Codable {
    var seedPhrase = "日本の四季を感じさせる文章を40語以内で生成"
    var model = ""
    var interval = 30
    var duration = 3600
    var saveWorks = false
    var saveFiles = false
}

/// Requests are pinned before the first row. A restart never resends an ambiguous row.
@MainActor @Observable
public final class AutomationModel {
    public var workspaceInputMode = "description"
    public var batchText = ""
    public var batchSketchMode = "off"
    public var demoSeedPhrase = "日本の四季を感じさせる文章を40語以内で生成" { didSet { persistDemoPreferences() } }
    /// The saved choice survives while its provider is temporarily unusable; only the shown value falls back.
    public var demoModel: String {
        get { demoSavedModelAvailable ? demoSavedModel : demoStage1Model }
        set { demoSavedModel = newValue; demoSavedModelAvailable = true }
    }
    private var demoSavedModel = "" { didSet { persistDemoPreferences() } }
    private var demoSavedModelAvailable = true
    public var demoInterval = 30 { didSet { persistDemoPreferences() } }
    public var demoDuration = 3600 { didSet { persistDemoPreferences() } }
    public var demoSaveWorks = false { didSet { persistDemoPreferences() } }
    public var demoSaveFiles = false { didSet { persistDemoPreferences() } }
    public var demoStage1Model = ""
    public var demoStage2Model = ""
    public var demoSketchMode = "off"
    public private(set) var rows: [BatchRow] = []
    public private(set) var running = false
    public private(set) var stopping = false
    public private(set) var mode = "batch"
    public private(set) var status = ""
    public private(set) var errorText: String?
    public private(set) var demoCount = 0
    public private(set) var demoPrompt = ""
    public private(set) var demoWork: SavedWork?
    public private(set) var demoStartedAt: Date?
    public private(set) var demoEndedAt: Date?
    public private(set) var demoGeneratingPrompt = ""
    public private(set) var demoWaitUntil: Date?
    public private(set) var demoCurrentSaved = false
    public private(set) var savingDemo = false
    public private(set) var demoSaveStatus = ""
    public private(set) var demoCurrentMetrics: [ProviderAttemptMetric] = []
    public private(set) var demoTotalMetrics: [ProviderAttemptMetric] = []
    public private(set) var preparing = false
    public private(set) var batchPromptHistory: [String] = []
    public private(set) var historyErrorText: String?
    public private(set) var batchConditions: BatchDrawingConditions?
    public private(set) var observedWork: SavedWork?
    public private(set) var currentRetryRound = 0
    public private(set) var batchRowStartedAt: Date?
    private var observedRowID: String?
    @ObservationIgnored private var store: BatchJournalStore?
    @ObservationIgnored private var journal: BatchJournal?
    @ObservationIgnored private var token: UUID?
    @ObservationIgnored private var operation: Task<Void, Never>?
    @ObservationIgnored private var demoPreferencesURL: URL?
    @ObservationIgnored private var demoSaveOperation: Task<SavedWork?, Never>?
    @ObservationIgnored private var batchObservationToken = UUID()

    public init() {}
    public var isOccupied: Bool { running || preparing }
    public var nonEmptyBatchCount: Int { BatchInputLines.entries(in: batchText).count }
    public var completedCount: Int { rows.filter { $0.state == .succeeded || $0.state == .skipped }.count }
    public var successfulCount: Int { rows.filter { $0.state == .succeeded }.count }
    public var failedCount: Int { rows.filter { $0.state == .failed }.count }
    public var pendingCount: Int { rows.filter { [.waiting, .failed, .uncertain].contains($0.state) }.count }
    public var nextPendingLine: Int? { rows.first { [.waiting, .failed, .uncertain].contains($0.state) }?.line }
    public var activeRow: BatchRow? { rows.first { $0.state == .running } }
    public var observedRow: BatchRow? { rows.first { $0.id == observedRowID } }
    public var uncertainCount: Int { rows.filter { $0.state == .uncertain }.count }
    public var canResume: Bool { rows.contains { [.waiting, .failed, .uncertain].contains($0.state) } }
    public var canSaveDemoCurrent: Bool { demoWork != nil && !demoCurrentSaved && !savingDemo && !preparing }
    public func canStartDemo(app: AppModel) -> Bool {
        !isOccupied && !savingDemo && !app.isBusy && !demoSeedPhrase.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !demoModel.isEmpty && !demoStage1Model.isEmpty && !demoStage2Model.isEmpty
    }

    public func refreshDemoModels(app: AppModel) async {
        guard !isOccupied else { return }
        let settings = await app.hostSettings()
        demoStage1Model = SettingsModel.isBatchModelAvailable(settings.models.stage1Model, settings: settings) ? settings.models.stage1Model : ""
        demoStage2Model = SettingsModel.isBatchModelAvailable(settings.models.stage2Model, settings: settings) ? settings.models.stage2Model : ""
        demoSavedModelAvailable = SettingsModel.isBatchModelAvailable(demoSavedModel, settings: settings)
    }

    public func connect(app: AppModel) async {
        guard store == nil, let directory = app.localDataDirectory() else { return }
        let preferencesURL = directory.appendingPathComponent("demo-settings.json")
        do {
            if FileManager.default.fileExists(atPath: preferencesURL.path) {
                let saved = try TolerantPreferences.decode(DemoPreferences.self, from: Data(contentsOf: preferencesURL),
                                                           defaults: DemoPreferences())
                demoSeedPhrase = saved.seedPhrase; demoSavedModel = saved.model
                demoInterval = min(3600, max(1, saved.interval)); demoDuration = min(86400, max(60, saved.duration))
                demoSaveWorks = saved.saveWorks; demoSaveFiles = saved.saveFiles
            }
        } catch {
            TolerantPreferences.setAside(preferencesURL)
            errorText = "デモの設定を読み込めませんでした。"
        }
        demoPreferencesURL = preferencesURL
        await refreshDemoModels(app: app)
        let store = BatchJournalStore(url: directory.appendingPathComponent("batch-journal.json"))
        self.store = store
        do {
            if var saved = try await store.load() {
                var recovered = false
                for index in saved.rows.indices where saved.rows[index].state == .running {
                    saved.rows[index].state = .uncertain
                    saved.rows[index].error = "終了前に処理結果を確認できませんでした。履歴を確認し、再試行するか省略するか選んでください。"
                    recovered = true
                }
                journal = saved; rows = saved.rows
                batchConditions = saved.conditions ?? saved.rows.first.map { BatchDrawingConditions(request: $0.request) }
                currentRetryRound = saved.round
                observedRowID = saved.observedRowID ?? saved.rows.last { $0.state == .succeeded }?.id
                if let workID = observedRow?.workID { observedWork = try? await app.auxiliaryDatabase().work(id: workID) }
                if recovered { try await store.save(saved) }
                if canResume { status = "前回のバッチを再開できます。生成条件は開始時のままです。" }
            }
        } catch { errorText = "バッチの記録を読み込めませんでした: \(error.localizedDescription)" }
        do { batchPromptHistory = BatchPromptHistory.normalized(try await store.loadHistory()) }
        catch { historyErrorText = "バッチ記述履歴を読み込めませんでした。" }
    }

    public func restoreBatchInput(_ text: String) {
        guard !isOccupied else { return }
        batchText = BatchInputLines.normalizedText(text)
    }

    /// The external batch journal stays authoritative; only in-memory artwork observations expire.
    public func invalidateWorkObservationsAfterRestore() {
        batchObservationToken = UUID()
        observedRowID = nil
        observedWork = nil
        demoWork = nil
        demoPrompt = ""
        demoCurrentSaved = false
        demoCurrentMetrics = []
        demoSaveStatus = ""
    }

    @discardableResult
    public func observeBatchRow(id: String, app: AppModel) async -> SavedWork? {
        guard !app.isBrowsingLocked, let row = rows.first(where: { $0.id == id && $0.state == .succeeded }),
              let workID = row.workID else { return nil }
        let observationToken = UUID()
        batchObservationToken = observationToken
        let selectedWorkID = app.selectedWorkID
        do {
            guard let work = try await app.auxiliaryDatabase().work(id: workID) else { throw HostError("saved_work_missing") }
            guard batchObservationToken == observationToken, app.selectedWorkID == selectedWorkID,
                  !Task.isCancelled, !app.isBrowsingLocked,
                  rows.contains(where: { $0.id == id && $0.workID == workID && $0.state == .succeeded }) else { return nil }
            // Browsing during a run pins a view snapshot without changing the live
            // latest-result observation or the authoritative batch journal.
            if !isOccupied {
                observedRowID = id
                observedWork = work
                journal?.observedRowID = id
                await persist()
            }
            guard batchObservationToken == observationToken, app.selectedWorkID == selectedWorkID,
                  !Task.isCancelled, !app.isBrowsingLocked,
                  rows.contains(where: { $0.id == id && $0.workID == workID && $0.state == .succeeded }) else { return nil }
            return work
        } catch {
            guard batchObservationToken == observationToken, app.selectedWorkID == selectedWorkID,
                  !Task.isCancelled, !app.isBrowsingLocked,
                  rows.contains(where: { $0.id == id && $0.workID == workID && $0.state == .succeeded }) else { return nil }
            errorText = error.localizedDescription
            return nil
        }
    }

    public func resolveUncertain(id: String, retry: Bool) async {
        guard !isOccupied, let index = rows.firstIndex(where: { $0.id == id && $0.state == .uncertain }) else { return }
        rows[index].state = retry ? .waiting : .skipped
        rows[index].error = nil
        await persist()
    }

    public func startBatch(app: AppModel) async {
        guard !running, !preparing, !app.isBusy else { return }
        preparing = true
        batchObservationToken = UUID()
        defer { preparing = false }
        do {
            let originalText = batchText
            let catalogMode = app.catalogMode == "auto" ? "auto" : "fixed"
            let sketchMode = batchSketchMode
            let entries = BatchInputLines.paintableEntries(in: originalText)
            guard !entries.isEmpty else { throw HostError("empty_batch") }
            guard entries.count <= 1000 else { throw HostError("batch_exceeds_1000_rows") }
            let retries = min(5, max(0, app.display.preferences.batchRetries))
            let batchRunID = UUID().uuidString
            var captured = try entries.map { line, input in
                var request = try app.requestForBatchDescription(input, sketchMode: sketchMode)
                var provenance = request.provenance ?? GenerationProvenance()
                provenance.batchRunID = batchRunID; provenance.batchLineNumber = line
                request.provenance = provenance
                return BatchRow(line: line, input: input, request: request)
            }
            let pinned = try await app.pinPersonalPlanRequests(captured.map(\.request))
            guard pinned.count == captured.count else { throw HostError("personal_plan_batch_pin_incomplete") }
            for index in captured.indices { captured[index].request = pinned[index] }
            guard let store else { throw HostError("batch_journal_unavailable") }
            let conditions = BatchDrawingConditions(request: captured[0].request, catalogMode: catalogMode)
            let capturedJournal = BatchJournal(id: batchRunID, rows: captured, retries: retries,
                originalText: originalText, conditions: conditions)
            try await store.save(capturedJournal)
            rows = captured; journal = capturedJournal; batchConditions = conditions
            observedRowID = nil; observedWork = nil; currentRetryRound = 0
            let history = BatchPromptHistory.normalized([originalText] + batchPromptHistory)
            do {
                try await store.saveHistory(history)
                batchPromptHistory = history; historyErrorText = nil
            } catch { historyErrorText = "バッチ記述履歴を保存できませんでした。" }
            preparing = false
            await runBatch(app: app)
        } catch { errorText = error.localizedDescription }
    }

    public func resumeBatch(app: AppModel) async {
        guard !running, !preparing, !app.isBusy, canResume, uncertainCount == 0 else { return }
        preparing = true
        batchObservationToken = UUID()
        defer { preparing = false }
        if let originalText = journal?.originalText {
            batchText = BatchInputLines.normalizedText(originalText)
        } else if let lastLine = rows.map(\.line).max(), (1...1_000_000).contains(lastLine) {
            var originalLines = Array(repeating: "", count: lastLine)
            for row in rows where row.line > 0 { originalLines[row.line - 1] = row.input }
            batchText = originalLines.joined(separator: "\n")
        }
        for index in rows.indices where rows[index].state == .failed { rows[index].state = .waiting }
        journal?.round = 0
        do { try await saveJournal() } catch { errorText = error.localizedDescription; return }
        preparing = false
        await runBatch(app: app)
    }

    private func runBatch(app: AppModel) async {
        guard let initial = journal else { return }
        let runToken = UUID()
        token = runToken; running = true; stopping = false; mode = "batch"; errorText = nil
        batchRowStartedAt = nil
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                var round = initial.round
                while round <= initial.retries {
                    self.currentRetryRound = round
                    let indices = self.rows.indices.filter { self.rows[$0].state == .waiting || (round > 0 && self.rows[$0].state == .failed) }
                    for index in indices {
                        try Task.checkCancellation()
                        guard self.token == runToken else { return }
                        self.rows[index].state = .running; self.rows[index].attempts += 1; self.rows[index].error = nil
                        self.status = "\(index + 1) / \(self.rows.count)（元の\(self.rows[index].line)行目）\(round > 0 ? "・再試行\(round)" : "")"
                        try await self.saveJournal()
                        self.batchRowStartedAt = Date()
                        let result = await app.runAutomation(request: self.rows[index].request, allowsBrowsing: true)
                        self.batchRowStartedAt = nil
                        if let result {
                            self.rows[index].state = .succeeded; self.rows[index].workID = result.id
                            self.observedRowID = self.rows[index].id; self.observedWork = result
                            self.journal?.observedRowID = self.rows[index].id
                        } else if Task.isCancelled || self.stopping {
                            self.rows[index].state = .uncertain
                            self.rows[index].error = "停止した処理の保存結果を履歴で確認してください。"
                        } else {
                            self.rows[index].state = .failed
                            self.rows[index].error = app.automationFailureMessage ?? app.errorText ?? "生成できませんでした。"
                        }
                        try await self.saveJournal()
                        try Task.checkCancellation()
                    }
                    if !self.rows.contains(where: { $0.state == .failed }) { break }
                    round += 1
                    self.journal?.round = round
                    try await self.saveJournal()
                }
                self.status = "バッチ完了: \(self.rows.filter { $0.state == .succeeded }.count)件成功・\(self.rows.filter { $0.state == .failed }.count)件失敗"
            } catch is CancellationError {
                if self.token == runToken { self.status = "停止しました。未処理の行は再開できます。" }
            } catch {
                if self.token == runToken { self.errorText = error.localizedDescription; self.status = "バッチを中断しました。" }
            }
        }
        operation = task
        await task.value
        finish(runToken)
    }

    public func startDemo(app: AppModel) async {
        guard !running, !preparing, !savingDemo, !app.isBusy else { return }
        preparing = true
        defer { preparing = false }
        do {
            guard !demoSeedPhrase.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw HostError("empty_demo_seed_phrase") }
            let draft = try app.requestForDemoDescription(demoSeedPhrase, sketchMode: demoSketchMode)
            let settings = HostSettings(providers: draft.providers, models: draft.models)
            guard SettingsModel.isBatchModelAvailable(demoModel, settings: settings) else { throw HostError("demo_model_not_available") }
            let provider = try app.auxiliaryProvider()
            let seedPhrase = demoSeedPhrase
            let reference = demoModel
            let language = app.instructionLanguage(for: seedPhrase)
            // Web demo state.svelte.ts normalizeSettings: 1...3600 seconds.
            let interval = min(3600, max(1, demoInterval))
            let duration = min(86400, max(60, demoDuration))
            let saveWorks = demoSaveWorks
            let saveFiles = demoSaveFiles
            let randomizeSeed = app.seedText.isEmpty
            guard let template = try await app.pinPersonalPlanRequests([draft]).first else { throw HostError("personal_plan_demo_pin_incomplete") }
            let runToken = UUID()
            token = runToken; running = true; stopping = false; mode = "demo"; errorText = nil; demoCount = 0
            preparing = false
            let startedAt = Date()
            let timeoutAt = startedAt.addingTimeInterval(Double(duration))
            demoStartedAt = startedAt; demoEndedAt = nil; demoWaitUntil = nil; demoTotalMetrics = []; demoSaveStatus = ""
            demoWork = nil; demoPrompt = ""; demoGeneratingPrompt = ""; demoCurrentMetrics = []; demoCurrentSaved = false
            let task = Task { @MainActor [weak self] in
                guard let self else { return }
                do {
                    // As on Server, the demo duration bounds starting the next iteration,
                    // not an in-flight instruction or drawing. Core owns each action's
                    // attempt/total timeout and retry budget.
                    while self.token == runToken && Date() < timeoutAt {
                      do {
                        if let saving = self.demoSaveOperation { _ = await saving.value }
                        try Task.checkCancellation()
                        guard Date() < timeoutAt else { break }
                        let iterationStartedAt = Date()
                        self.demoWaitUntil = nil
                        self.status = "次の記述を生成中"
                        var instruction: String?
                        let read = await app.performSerialized(status: self.status) { _ in
                            instruction = try await provider.demoInstruction(seedPhrase: seedPhrase, modelReference: reference,
                                language: language, settings: settings)
                        }
                        try Task.checkCancellation()
                        guard read, let instruction else { throw HostError(app.errorText ?? "demo_instruction_failed") }
                        self.demoGeneratingPrompt = instruction
                        var request = try app.makeDemoRequest(template: template, description: instruction, randomizeSeed: randomizeSeed)
                        request.saveHistory = saveWorks
                        self.status = "デモの作品を生成中"
                        guard let work = await app.runAutomation(request: request) else {
                            try Task.checkCancellation(); throw HostError(app.errorText ?? "demo_generation_failed")
                        }
                        try Task.checkCancellation()
                        guard self.token == runToken else { return }
                        self.demoWork = work; self.demoPrompt = instruction; self.demoCount += 1; self.demoCurrentSaved = saveWorks
                        self.demoCurrentMetrics = app.providerMetrics
                        self.demoTotalMetrics += self.demoCurrentMetrics
                        self.demoSaveStatus = ""
                        // Web leaves artifact files to the drawing it already counted; a failed file save is
                        // reported without shortening the interval to the one-second failure retry.
                        if saveFiles, !(await app.saveDemoFiles(work)) { self.errorText = app.errorText ?? "demo_file_save_failed" }
                        let now = Date()
                        let intervalRemaining = Double(interval) - now.timeIntervalSince(iterationStartedAt)
                        let timeoutRemaining = timeoutAt.timeIntervalSince(now)
                        let wait = max(0, min(intervalRemaining, timeoutRemaining))
                        self.status = "\(self.demoCount)作品を表示しました。"
                        // The interval countdown describes an upcoming work only when
                        // that interval finishes before the demo's duration expires.
                        self.demoWaitUntil = wait > 0 && intervalRemaining <= timeoutRemaining ? now.addingTimeInterval(wait) : nil
                        if wait > 0 { try await Task.sleep(for: .seconds(wait)) }
                      } catch is CancellationError { throw CancellationError() }
                      catch {
                        try Task.checkCancellation()
                        guard self.token == runToken else { return }
                        self.errorText = error.localizedDescription
                        self.status = "デモの生成に失敗しました。次の生成を準備します。"
                        self.demoWaitUntil = nil
                        let retryDelay = min(1, max(0, timeoutAt.timeIntervalSinceNow))
                        if retryDelay > 0 { try await Task.sleep(for: .seconds(retryDelay)) }
                      }
                    }
                    if self.token == runToken && Date() >= timeoutAt {
                        self.status = "デモの実行時間を満了しました。"
                    }
                } catch is CancellationError {
                    if self.token == runToken { self.status = "デモを停止しました。" }
                } catch {
                    if self.token == runToken { self.errorText = error.localizedDescription; self.status = "デモを中断しました。" }
                }
            }
            operation = task
            await task.value
            finish(runToken)
        } catch { errorText = error.localizedDescription }
    }

    public func saveDemoCurrent(app: AppModel) async {
        guard canSaveDemoCurrent, !app.isBusy, let work = demoWork, demoSaveOperation == nil else { return }
        savingDemo = true
        defer { savingDemo = false; demoSaveOperation = nil }
        let saving = Task { @MainActor in await app.saveDemoCandidate(work) }
        demoSaveOperation = saving
        if let saved = await saving.value {
            if demoWork?.id == work.id { demoWork = saved; demoCurrentSaved = true }
            demoSaveStatus = "現在の作品を保存しました。"
        } else { errorText = app.errorText ?? "現在の作品を保存できませんでした。" }
    }

    private func persistDemoPreferences() {
        guard let demoPreferencesURL else { return }
        do {
            let saved = DemoPreferences(seedPhrase: demoSeedPhrase, model: demoSavedModel, interval: demoInterval,
                duration: demoDuration, saveWorks: demoSaveWorks, saveFiles: demoSaveFiles)
            try JSONEncoder().encode(saved).write(to: demoPreferencesURL, options: .atomic)
        } catch { errorText = "デモの設定を保存できませんでした。" }
    }

    public func stop(app: AppModel) async {
        guard running, !stopping else { return }
        stopping = true
        let task = operation
        task?.cancel()
        await app.cancel()
        await task?.value
    }

    private func finish(_ runToken: UUID) {
        guard token == runToken else { return }
        if mode == "demo" { demoEndedAt = Date(); demoWaitUntil = nil }
        batchRowStartedAt = nil; operation = nil; token = nil
        running = false; stopping = false
    }
    private func saveJournal() async throws {
        guard var journal, let store else { throw HostError("batch_journal_unavailable") }
        journal.rows = rows; self.journal = journal
        try await store.save(journal)
    }
    private func persist() async {
        do { try await saveJournal() } catch { errorText = error.localizedDescription }
    }
}
