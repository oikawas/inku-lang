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

private struct BatchJournal: Codable, Sendable {
    var id = UUID().uuidString
    var created = Date()
    var rows: [BatchRow]
    var retries: Int
    var round = 0
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
}

/// Requests are pinned before the first row. A restart never resends an ambiguous row.
@MainActor @Observable
public final class AutomationModel {
    public var batchText = ""
    public var demoSeedPhrase = "日本の四季を感じさせる文章を40語以内で生成"
    public var demoModel = ""
    public var demoInterval = 30
    public var demoDuration = 3600
    public var demoSaveWorks = false
    public private(set) var rows: [BatchRow] = []
    public private(set) var running = false
    public private(set) var stopping = false
    public private(set) var mode = "batch"
    public private(set) var status = ""
    public private(set) var errorText: String?
    public private(set) var demoCount = 0
    public private(set) var demoPrompt = ""
    public private(set) var demoWork: SavedWork?
    @ObservationIgnored private var store: BatchJournalStore?
    @ObservationIgnored private var journal: BatchJournal?
    @ObservationIgnored private var token: UUID?
    @ObservationIgnored private var operation: Task<Void, Never>?
    @ObservationIgnored private var deadline: Task<Void, Never>?
    @ObservationIgnored private var demoExpired = false
    @ObservationIgnored private var preparing = false

    public init() {}
    public var completedCount: Int { rows.filter { $0.state == .succeeded || $0.state == .skipped }.count }
    public var uncertainCount: Int { rows.filter { $0.state == .uncertain }.count }
    public var canResume: Bool { rows.contains { [.waiting, .failed, .uncertain].contains($0.state) } }

    public func connect(app: AppModel) async {
        guard store == nil, let directory = app.localDataDirectory() else { return }
        let store = BatchJournalStore(url: directory.appendingPathComponent("batch-journal.json"))
        self.store = store
        do {
            if var saved = try await store.load() {
                for index in saved.rows.indices where saved.rows[index].state == .running {
                    saved.rows[index].state = .uncertain
                    saved.rows[index].error = "終了前に処理結果を確認できませんでした。履歴を確認し、再試行するか省略するか選んでください。"
                }
                journal = saved; rows = saved.rows
                try await store.save(saved)
                if canResume { status = "前回のバッチを再開できます。生成条件は開始時のままです。" }
            }
        } catch { errorText = "バッチの記録を読み込めませんでした: \(error.localizedDescription)" }
    }

    public func resolveUncertain(id: String, retry: Bool) async {
        guard !running, let index = rows.firstIndex(where: { $0.id == id && $0.state == .uncertain }) else { return }
        rows[index].state = retry ? .waiting : .skipped
        rows[index].error = nil
        await persist()
    }

    public func startBatch(app: AppModel) async {
        guard !running, !preparing, !app.isBusy else { return }
        preparing = true
        defer { preparing = false }
        do {
            let entries = batchText.components(separatedBy: .newlines).enumerated().compactMap { offset, input -> (Int, String)? in
                let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
                return text.isEmpty ? nil : (offset + 1, text)
            }
            guard !entries.isEmpty else { throw HostError("empty_batch") }
            guard entries.count <= 1000 else { throw HostError("batch_exceeds_1000_rows") }
            let retries = min(5, max(0, app.display.preferences.batchRetries))
            var captured = try entries.map { line, input in
                BatchRow(line: line, input: input,
                    request: try app.requestForCurrentInput(inputMode: app.inputMode, source: input,
                                                           description: app.inputMode == "description" ? input : "",
                                                           parentWorkID: nil, derivationKind: "new"))
            }
            let pinned = try await app.pinPersonalPlanRequests(captured.map(\.request))
            guard pinned.count == captured.count else { throw HostError("personal_plan_batch_pin_incomplete") }
            for index in captured.indices { captured[index].request = pinned[index] }
            rows = captured
            journal = BatchJournal(rows: captured, retries: retries)
            try await saveJournal()
            await runBatch(app: app)
        } catch { errorText = error.localizedDescription }
    }

    public func resumeBatch(app: AppModel) async {
        guard !running, !preparing, !app.isBusy, canResume, uncertainCount == 0 else { return }
        preparing = true
        defer { preparing = false }
        for index in rows.indices where rows[index].state == .failed { rows[index].state = .waiting }
        journal?.round = 0
        do { try await saveJournal() } catch { errorText = error.localizedDescription; return }
        await runBatch(app: app)
    }

    private func runBatch(app: AppModel) async {
        guard let initial = journal else { return }
        let runToken = UUID()
        token = runToken; running = true; stopping = false; mode = "batch"; errorText = nil
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                var round = initial.round
                while round <= initial.retries {
                    let indices = self.rows.indices.filter { self.rows[$0].state == .waiting || (round > 0 && self.rows[$0].state == .failed) }
                    for index in indices {
                        try Task.checkCancellation()
                        guard self.token == runToken else { return }
                        self.rows[index].state = .running; self.rows[index].attempts += 1; self.rows[index].error = nil
                        self.status = "\(index + 1) / \(self.rows.count)（元の\(self.rows[index].line)行目）\(round > 0 ? "・再試行\(round)" : "")"
                        try await self.saveJournal()
                        let result = await app.runAutomation(request: self.rows[index].request)
                        if let result {
                            self.rows[index].state = .succeeded; self.rows[index].workID = result.id
                        } else if Task.isCancelled || self.stopping {
                            self.rows[index].state = .uncertain
                            self.rows[index].error = "停止した処理の保存結果を履歴で確認してください。"
                        } else {
                            self.rows[index].state = .failed; self.rows[index].error = app.errorText ?? "生成できませんでした。"
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
        guard !running, !preparing, !app.isBusy, !demoSeedPhrase.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        preparing = true
        defer { preparing = false }
        do {
            let draft = try app.requestForCurrentInput(inputMode: "description", description: demoSeedPhrase, parentWorkID: nil)
            let settings = HostSettings(providers: draft.providers, models: draft.models)
            let provider = try app.auxiliaryProvider()
            let seedPhrase = demoSeedPhrase
            let reference = demoModel.isEmpty ? nil : demoModel
            let language = app.language
            let interval = min(3600, max(1, demoInterval))
            let duration = min(86400, max(60, demoDuration))
            let saveWorks = demoSaveWorks
            let randomizeSeed = app.seedText.isEmpty
            guard let template = try await app.pinPersonalPlanRequests([draft]).first else { throw HostError("personal_plan_demo_pin_incomplete") }
            let runToken = UUID()
            token = runToken; running = true; stopping = false; mode = "demo"; errorText = nil; demoCount = 0; demoExpired = false
            let task = Task { @MainActor [weak self] in
                guard let self else { return }
                do {
                    while self.token == runToken {
                        try Task.checkCancellation()
                        self.status = "次の記述を生成中"
                        var instruction: String?
                        let read = await app.performSerialized(status: self.status) { _ in
                            instruction = try await provider.demoInstruction(seedPhrase: seedPhrase, modelReference: reference,
                                language: language, settings: settings)
                        }
                        try Task.checkCancellation()
                        guard read, let instruction else { throw HostError(app.errorText ?? "demo_instruction_failed") }
                        self.demoPrompt = instruction
                        var request = try app.makeDemoRequest(template: template, description: instruction, randomizeSeed: randomizeSeed)
                        request.saveHistory = saveWorks
                        self.status = "デモの作品を生成中"
                        guard let work = await app.runAutomation(request: request) else {
                            try Task.checkCancellation(); throw HostError(app.errorText ?? "demo_generation_failed")
                        }
                        try Task.checkCancellation()
                        guard self.token == runToken else { return }
                        self.demoWork = work; self.demoCount += 1
                        self.status = "\(self.demoCount)作品を表示しました。次の生成まで\(interval)秒"
                        try await Task.sleep(for: .seconds(interval))
                    }
                } catch is CancellationError {
                    if self.token == runToken { self.status = self.demoExpired ? "デモの実行時間を満了しました。" : "デモを停止しました。" }
                } catch {
                    if self.token == runToken { self.errorText = error.localizedDescription; self.status = "デモを中断しました。" }
                }
            }
            operation = task
            deadline = Task { @MainActor [weak self] in
                do { try await Task.sleep(for: .seconds(duration)) } catch { return }
                guard let self, self.token == runToken else { return }
                self.demoExpired = true
                await self.stop(app: app)
            }
            await task.value
            finish(runToken)
        } catch { errorText = error.localizedDescription }
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
        deadline?.cancel(); deadline = nil; operation = nil; token = nil
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
