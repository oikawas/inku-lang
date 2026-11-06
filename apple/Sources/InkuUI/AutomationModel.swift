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
    /// Written before the row's pipeline starts sending or saving; absent in older journals.
    public var executionID: String?
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
        case .image(_, let auto):
            inputMode = "image"; sketchMode = "off"; self.catalogMode = catalogMode ?? (auto ? "auto" : "fixed")
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

private struct BatchRowProgress: Codable, Equatable, Sendable {
    var state: BatchRow.State
    var attempts: Int
    var workID: String?
    var executionID: String?
    var error: String?
    init(_ row: BatchRow) {
        state = row.state; attempts = row.attempts; workID = row.workID
        executionID = row.executionID; error = row.error
    }
    func apply(to row: inout BatchRow) {
        row.state = state; row.attempts = attempts; row.workID = workID
        row.executionID = executionID; row.error = error
    }
}

private struct BatchJournalV2: Codable, Sendable {
    struct Row: Codable, Sendable {
        let id: String
        let line: Int
        let input: String
        let requestChanges: [String: Data]
        let removedRequestKeys: [String]
    }
    let version: Int
    let id: String
    let created: Date
    let retries: Int
    let originalText: String?
    let conditions: BatchDrawingConditions?
    let baseRequest: GenerationRequest
    let rows: [Row]
}

private struct BatchJournalProgress: Codable, Equatable, Sendable {
    let round: Int
    let observedRowID: String?
}

private actor BatchJournalStore {
    let url: URL
    private var previous: BatchJournal?
    private var version2 = false
    init(url: URL) { self.url = url }
    private func folder(_ id: String) throws -> URL {
        guard UUID(uuidString: id) != nil else { throw HostError("batch_journal_invalid") }
        return url.deletingLastPathComponent().appendingPathComponent("batch-journal-v2-" + id, isDirectory: true)
    }
    private func rowURL(_ folder: URL, _ index: Int) -> URL { folder.appendingPathComponent("row-\(index).json") }
    private func object(_ request: GenerationRequest) throws -> [String: Any] {
        guard let value = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any] else {
            throw HostError("batch_journal_invalid")
        }
        return value
    }
    private func bytes(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed, .sortedKeys, .withoutEscapingSlashes])
    }
    private func write<T: Encodable>(_ value: T, to destination: URL) throws {
        try JSONEncoder().encode(value).write(to: destination, options: .atomic)
    }
    func load() throws -> BatchJournal? {
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let data = try Data(contentsOf: url)
        struct Marker: Decodable { let version: Int? }
        let marker = try JSONDecoder().decode(Marker.self, from: data)
        guard let version = marker.version else {
            let journal = try JSONDecoder().decode(BatchJournal.self, from: data)
            previous = journal; version2 = false
            return journal
        }
        guard version == 2 else { throw HostError("batch_journal_invalid") }
        let header = try JSONDecoder().decode(BatchJournalV2.self, from: data)
        let directory = try folder(header.id)
        let state = try JSONDecoder().decode(BatchJournalProgress.self, from: Data(contentsOf: directory.appendingPathComponent("state.json")))
        let base = try object(header.baseRequest)
        var rows: [BatchRow] = []
        for (index, item) in header.rows.enumerated() {
            var request = base
            for key in item.removedRequestKeys { request.removeValue(forKey: key) }
            for (key, value) in item.requestChanges {
                request[key] = try JSONSerialization.jsonObject(with: value, options: [.fragmentsAllowed])
            }
            let decoded = try JSONDecoder().decode(GenerationRequest.self, from: JSONSerialization.data(withJSONObject: request, options: [.sortedKeys]))
            var row = BatchRow(id: item.id, line: item.line, input: item.input, request: decoded)
            try JSONDecoder().decode(BatchRowProgress.self, from: Data(contentsOf: rowURL(directory, index))).apply(to: &row)
            rows.append(row)
        }
        let journal = BatchJournal(id: header.id, created: header.created, rows: rows, retries: header.retries,
                                   round: state.round, originalText: header.originalText, conditions: header.conditions,
                                   observedRowID: state.observedRowID)
        previous = journal; version2 = true
        return journal
    }
    func save(_ journal: BatchJournal) throws {
        let directory = try folder(journal.id)
        if !version2 || previous?.id != journal.id {
            guard let first = journal.rows.first else { throw HostError("batch_journal_invalid") }
            let obsolete = version2 && previous?.id != journal.id ? previous?.id : nil
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let base = try object(first.request)
            let baseBytes = try base.mapValues(bytes)
            var rows: [BatchJournalV2.Row] = []
            for (index, row) in journal.rows.enumerated() {
                let values = try object(row.request)
                let valueBytes = try values.mapValues(bytes)
                let changes = valueBytes.filter { baseBytes[$0.key] != $0.value }
                rows.append(.init(id: row.id, line: row.line, input: row.input, requestChanges: changes,
                                  removedRequestKeys: base.keys.filter { values[$0] == nil }.sorted()))
                try write(BatchRowProgress(row), to: rowURL(directory, index))
            }
            try write(BatchJournalProgress(round: journal.round, observedRowID: journal.observedRowID), to: directory.appendingPathComponent("state.json"))
            let header = BatchJournalV2(version: 2, id: journal.id, created: journal.created, retries: journal.retries,
                                        originalText: journal.originalText, conditions: journal.conditions,
                                        baseRequest: first.request, rows: rows)
            try write(header, to: url)
            version2 = true
            if let obsolete { try? FileManager.default.removeItem(at: folder(obsolete)) }
        } else if let previous {
            guard previous.rows.count == journal.rows.count else { throw HostError("batch_journal_invalid") }
            for index in journal.rows.indices {
                guard previous.rows[index].id == journal.rows[index].id else { throw HostError("batch_journal_invalid") }
                let progress = BatchRowProgress(journal.rows[index])
                if progress != BatchRowProgress(previous.rows[index]) { try write(progress, to: rowURL(directory, index)) }
            }
            let state = BatchJournalProgress(round: journal.round, observedRowID: journal.observedRowID)
            if state != BatchJournalProgress(round: previous.round, observedRowID: previous.observedRowID) {
                try write(state, to: directory.appendingPathComponent("state.json"))
            }
        }
        previous = journal
    }
    func clear() throws {
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
        if version2, let previous { try? FileManager.default.removeItem(at: folder(previous.id)) }
        previous = nil; version2 = false
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

public enum DemoIntervalPolicy {
    public static func acceptsUIEdit(_ value: Int) -> Bool { (1...999).contains(value) }
    public static func acceptsStoredValue(_ value: Int) -> Bool { (1...3600).contains(value) }
}

/// Requests are pinned before the first row. A restart never resends an ambiguous row.
@MainActor @Observable
public final class AutomationModel {
    let imageFolderBatch = ImageFolderBatch()
    public var workspaceInputMode = "description"
    public func selectInputTab(_ mode: String, app: AppModel) {
        workspaceInputMode = mode
        app.activeDrawTab = mode == "image" ? "image" : mode == "batch" ? "batch_text" : "describe"
        if mode == "description" || mode == "image" { app.inputMode = mode }
    }

    public func inputTabRunning(_ mode: String, app: AppModel) -> Bool {
        let batchRunning = (running && self.mode == "batch") || imageFolderBatch.running
        if mode == "batch" { return batchRunning }
        guard app.isBusy, !isOccupied, !imageFolderBatch.running else { return false }
        if mode == "image" { return app.activeSingleInputMode == "image" }
        return mode == "description" && app.activeSingleInputMode != "image"
    }
    public var batchText = "" { didSet { if batchText != oldValue { updateBatchLines() } } }
    public private(set) var nonEmptyBatchCount = 0
    public private(set) var paintableBatchCount = 0
    @ObservationIgnored private var batchLineCache: [String: Bool] = [:]
    @ObservationIgnored private var paintableBatchEntries: [(line: Int, text: String)] = []

    private func updateBatchLines() {
        let entries = BatchInputLines.entries(in: batchText)
        nonEmptyBatchCount = entries.count
        var next: [String: Bool] = [:]
        let paintable = BatchInputLines.paintableEntries(entries) { text in
            let result = next[text] ?? batchLineCache[text] ?? DescriptionLabels.hasDrawableText(text)
            next[text] = result
            return result
        }
        batchLineCache = next
        paintableBatchEntries = paintable
        paintableBatchCount = paintable.count
    }
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
    public private(set) var demoDrawing = false
    public private(set) var demoCurrentSaved = false
    public private(set) var savingDemo = false
    public private(set) var demoSaveStatus = ""
    public private(set) var demoCurrentMetrics: [ProviderAttemptMetric] = []
    public private(set) var demoTotalMetrics: [ProviderAttemptMetric] = []
    public private(set) var preparing = false
    public private(set) var resuming = false
    public private(set) var batchPromptHistory: [String] = []
    public private(set) var historyErrorText: String?
    public private(set) var batchConditions: BatchDrawingConditions?
    public private(set) var observedWork: SavedWork?
    public private(set) var currentRetryRound = 0
    public private(set) var batchStartedAt: Date?
    public private(set) var batchRowStartedAt: Date?
    private var observedRowID: String?
    @ObservationIgnored private var store: BatchJournalStore?
    @ObservationIgnored private var journal: BatchJournal?
    @ObservationIgnored private var token: UUID?
    @ObservationIgnored private var operation: Task<Void, Never>?
    @ObservationIgnored private var demoPreferencesURL: URL?
    @ObservationIgnored private var demoPreferencesTask: Task<Void, Never>?
    @ObservationIgnored private var demoSaveOperation: Task<SavedWork?, Never>?
    @ObservationIgnored private var batchObservationToken = UUID()

    public init() {}
    public var isOccupied: Bool { running || preparing || imageFolderBatch.running }
    public var completedCount: Int { rows.filter { $0.state == .succeeded || $0.state == .skipped }.count }
    public var successfulCount: Int { rows.filter { $0.state == .succeeded }.count }
    public var failedCount: Int { rows.filter { $0.state == .failed }.count }
    public var pendingCount: Int { rows.filter { [.waiting, .failed, .uncertain].contains($0.state) }.count }
    public var nextPendingLine: Int? { rows.first { [.waiting, .failed, .uncertain].contains($0.state) }?.line }
    public var activeRow: BatchRow? { rows.first { $0.state == .running } }
    public var observedRow: BatchRow? { rows.first { $0.id == observedRowID } }
    public var uncertainCount: Int { rows.filter { $0.state == .uncertain }.count }
    public var canResume: Bool { rows.contains { [.waiting, .failed, .uncertain].contains($0.state) } }
    @discardableResult public func newBatch(app: AppModel) async -> Bool {
        guard !isOccupied, !app.isBusy else { return false }
        do {
            try await store?.clear()
            rows = []; journal = nil; batchConditions = nil; observedRowID = nil; observedWork = nil
            batchText = ""; app.newWork(resetTab: "batch_text")
            return true
        } catch { errorText = error.localizedDescription; return false }
    }
    /// Web `canRetryFailures`: a stopped batch with failed rows can draw those rows alone again.
    public var canRetryFailures: Bool { !running && !preparing && failedCount > 0 }
    public var canSaveDemoCurrent: Bool { demoWork != nil && !demoCurrentSaved && !savingDemo && !preparing }
    @discardableResult public func setDemoIntervalFromUI(_ value: Int) -> Bool {
        guard DemoIntervalPolicy.acceptsUIEdit(value) else { return false }
        demoInterval = value
        return true
    }
    public func canStartDemo(app: AppModel) -> Bool {
        !isOccupied && !savingDemo && !app.isBusy && !demoSeedPhrase.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !demoModel.isEmpty && !demoStage1Model.isEmpty && !demoStage2Model.isEmpty
            && DemoIntervalPolicy.acceptsStoredValue(demoInterval)
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
                guard DemoIntervalPolicy.acceptsStoredValue(saved.interval) else { throw HostError("invalid_demo_interval") }
                demoInterval = saved.interval; demoDuration = min(86400, max(60, saved.duration))
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
        guard !isOccupied, !app.isBusy else { return }
        preparing = true
        batchObservationToken = UUID()
        defer { preparing = false }
        do {
            let originalText = batchText
            let catalogMode = app.catalogMode
            let sketchMode = app.sketchMode
            let entries = paintableBatchEntries
            guard !entries.isEmpty else { throw HostError("empty_batch") }
            guard entries.count <= 1000 else { throw HostError("batch_exceeds_1000_rows") }
            let retries = min(5, max(0, app.display.preferences.batchRetries))
            let batchRunID = UUID().uuidString
            var captured = try await app.makeBatchRows(entries, sketchMode: sketchMode, batchRunID: batchRunID)
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
        guard !running, !preparing, !app.isBusy, canResume else { return }
        let resumedAt = Date()
        preparing = true
        resuming = true
        batchObservationToken = UUID()
        defer { preparing = false; resuming = false }
        do {
            var resolved = rows
            for index in resolved.indices where resolved[index].state == .uncertain {
                if let id = resolved[index].executionID, let work = try await app.savedAutomationWork(executionID: id) {
                    resolved[index].state = .succeeded
                    resolved[index].workID = work.id
                } else {
                    resolved[index].state = .waiting
                    resolved[index].workID = nil
                }
                resolved[index].error = nil
            }
            guard var next = journal, let store else { throw HostError("batch_journal_unavailable") }
            next.rows = resolved
            try await store.save(next)
            journal = next
            rows = resolved
        } catch {
            errorText = "バッチの保存結果を確認できませんでした: \(error.localizedDescription)"
            return
        }
        // Pending rows continue with the conditions captured when this batch started.
        if let request = rows.first?.request {
            app.drawRoute = request.drawRoute ?? "stages"
            app.descriptionComposition = request.descriptionComposition ?? false
        }
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
        resuming = false
        preparing = false
        await runBatch(app: app, startedAt: resumedAt)
    }

    /// Web `retryFailed`: draws only the failed rows again with their original text, line numbers and the
    /// conditions pinned when the batch began. Waiting, uncertain, skipped and successful rows stay as they are.
    public func retryFailures(app: AppModel) async {
        guard canRetryFailures, !app.isBusy else { return }
        preparing = true
        batchObservationToken = UUID()
        defer { preparing = false }
        if let originalText = journal?.originalText { batchText = BatchInputLines.normalizedText(originalText) }
        let failed = Set(rows.filter { $0.state == .failed }.map(\.id))
        for index in rows.indices where failed.contains(rows[index].id) { rows[index].state = .waiting }
        journal?.round = 0
        do { try await saveJournal() } catch { errorText = error.localizedDescription; return }
        preparing = false
        await runBatch(app: app, only: failed)
    }

    private func runBatch(app: AppModel, only scope: Set<String>? = nil, startedAt: Date = Date()) async {
        guard let initial = journal else { return }
        let runToken = UUID()
        token = runToken; running = true; stopping = false; mode = "batch"; errorText = nil
        batchStartedAt = startedAt; batchRowStartedAt = nil
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                var round = initial.round
                while round <= initial.retries {
                    self.currentRetryRound = round
                    let indices = self.rows.indices.filter {
                        (scope?.contains(self.rows[$0].id) ?? true)
                            && (self.rows[$0].state == .waiting || (round > 0 && self.rows[$0].state == .failed))
                    }
                    for index in indices {
                        try Task.checkCancellation()
                        guard self.token == runToken else { return }
                        self.rows[index].state = .running; self.rows[index].attempts += 1; self.rows[index].error = nil
                        self.rows[index].executionID = nil
                        self.status = "\(index + 1) / \(self.rows.count)（元の\(self.rows[index].line)行目）\(round > 0 ? "・再試行\(round)" : "")"
                        try await self.saveJournal()
                        self.batchRowStartedAt = Date()
                        let rowID = self.rows[index].id
                        let result = await app.runAutomation(request: self.rows[index].request, allowsBrowsing: true) { executionID in
                            guard self.token == runToken, !self.stopping,
                                  let rowIndex = self.rows.firstIndex(where: { $0.id == rowID && $0.state == .running }) else { throw CancellationError() }
                            self.rows[rowIndex].executionID = executionID
                            try await self.saveJournal()
                        }
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
                    if !self.rows.contains(where: { $0.state == .failed && (scope?.contains($0.id) ?? true) }) { break }
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
            guard DemoIntervalPolicy.acceptsStoredValue(demoInterval) else { throw HostError("invalid_demo_interval") }
            let interval = demoInterval
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
                        var provenance = request.provenance ?? GenerationProvenance()
                        provenance.displayLabel = "[demo]"
                        request.provenance = provenance
                        request.saveHistory = saveWorks
                        self.status = "デモの作品を生成中"
                        self.demoDrawing = true
                        let drawing = await app.runAutomation(request: request)
                        self.demoDrawing = false
                        guard let work = drawing else {
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
        guard demoPreferencesURL != nil else { return }
        demoPreferencesTask?.cancel()
        demoPreferencesTask = Task { @MainActor [weak self] in
            do { try await Task.sleep(for: .milliseconds(500)) } catch { return }
            self?.flushDemoPreferences()
        }
    }

    public func flushDemoPreferences() {
        guard demoPreferencesTask != nil else { return }
        demoPreferencesTask?.cancel()
        demoPreferencesTask = nil
        guard let demoPreferencesURL else { return }
        do {
            guard DemoIntervalPolicy.acceptsStoredValue(demoInterval) else { throw HostError("invalid_demo_interval") }
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
        if mode == "demo" { demoEndedAt = Date(); demoWaitUntil = nil; demoDrawing = false }
        batchStartedAt = nil; batchRowStartedAt = nil; operation = nil; token = nil
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
