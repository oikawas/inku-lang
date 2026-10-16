import CryptoKit
import Foundation
import InkuHost
import InkuPersistence
import Observation

private struct BackupManifest: Codable, Sendable {
    var lastSuccess: Date?
    var files: [String] = []
}

public struct LocalBackupGeneration: Identifiable, Sendable {
    public let name: String
    public let modifiedAt: Date?
    public let byteCount: Int64
    public var id: String { name }
}

private struct BackupSnapshot: Sendable {
    let lastSuccess: Date?
    let generations: [LocalBackupGeneration]
    let totalBytes: Int64
}

private actor LocalMaintenanceStore {
    private let directory: URL
    init(directory: URL) { self.directory = directory }
    private var manifestURL: URL { directory.appendingPathComponent("automatic-backups.json") }
    func manifest() throws -> BackupManifest {
        guard FileManager.default.fileExists(atPath: manifestURL.path) else { return BackupManifest() }
        return try JSONDecoder().decode(BackupManifest.self, from: Data(contentsOf: manifestURL))
    }
    func nextBackupURL(now: Date) throws -> URL {
        let folder = directory.appendingPathComponent("automatic-backups", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder.appendingPathComponent("inku-auto-\(Int64(now.timeIntervalSince1970 * 1000))-\(UUID().uuidString).sqlite")
    }
    func snapshot() throws -> BackupSnapshot {
        let record = try manifest()
        let folder = directory.appendingPathComponent("automatic-backups", isDirectory: true)
        guard FileManager.default.fileExists(atPath: folder.path) else {
            return BackupSnapshot(lastSuccess: record.lastSuccess, generations: [], totalBytes: 0)
        }
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey, .contentModificationDateKey]
        let files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: Array(keys), options: [.skipsHiddenFiles])
        var generations: [LocalBackupGeneration] = []
        var totalBytes: Int64 = 0
        let owned = Set(record.files)
        for file in files where owned.contains(file.lastPathComponent) && file.lastPathComponent.hasPrefix("inku-auto-") && file.pathExtension == "sqlite" {
            let metadata = try file.resourceValues(forKeys: keys)
            guard metadata.isRegularFile == true, metadata.isSymbolicLink != true else { continue }
            let bytes = Int64(max(0, metadata.fileSize ?? 0))
            let sum = totalBytes.addingReportingOverflow(bytes)
            guard !sum.overflow else { throw HostError("backup_size_out_of_range") }
            totalBytes = sum.partialValue
            generations.append(LocalBackupGeneration(name: file.lastPathComponent, modifiedAt: metadata.contentModificationDate, byteCount: bytes))
        }
        generations.sort { $0.name > $1.name }
        return BackupSnapshot(lastSuccess: record.lastSuccess, generations: generations, totalBytes: totalBytes)
    }
    func completed(url: URL, retention: Int, at: Date) throws {
        let metadata = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard (1...100).contains(retention), metadata.isRegularFile == true, metadata.isSymbolicLink != true,
              (metadata.fileSize ?? 0) > 0 else { throw HostError("backup_output_unavailable") }
        var record = try manifest()
        record.lastSuccess = at
        record.files.append(url.lastPathComponent)
        let excess = max(0, record.files.count - retention)
        let removed = Array(record.files.prefix(excess))
        record.files.removeFirst(excess)
        // Record the verified replacement before deleting any previous owned backup.
        try JSONEncoder().encode(record).write(to: manifestURL, options: .atomic)
        for name in removed where name.hasPrefix("inku-auto-") && name.hasSuffix(".sqlite") && !name.contains("/") {
            let old = url.deletingLastPathComponent().appendingPathComponent(name)
            if FileManager.default.fileExists(atPath: old.path) {
                let metadata = try old.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
                if metadata.isRegularFile == true, metadata.isSymbolicLink != true { try FileManager.default.removeItem(at: old) }
            }
        }
    }
    func log(work: SavedWork) throws {
        let folder = directory.appendingPathComponent("result-logs", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let name = SHA256.hash(data: Data(work.id.utf8)).map { String(format: "%02x", $0) }.joined()
        let file = folder.appendingPathComponent(name + ".json")
        guard !FileManager.default.fileExists(atPath: file.path) else { return }
        try JSONEncoder().encode(work).write(to: file, options: .atomic)
    }

    func log(execution: DrawingLogRecord) throws {
        let folder = directory.appendingPathComponent("drawing-logs", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true,
                                               attributes: [.posixPermissions: 0o700])
        let name = SHA256.hash(data: Data(execution.id.utf8)).map { String(format: "%02x", $0) }.joined()
        let file = folder.appendingPathComponent(name + ".json")
        let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
        if FileManager.default.fileExists(atPath: file.path),
           let previous = try? decoder.decode(DrawingLogRecord.self, from: Data(contentsOf: file)),
           previous.databaseRevision >= execution.databaseRevision { return }
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(execution).write(to: file, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
    }
}

@MainActor @Observable
public final class LocalMaintenance {
    public private(set) var backupStatus = ""
    public private(set) var logStatus = ""
    public private(set) var backupDirectory: URL?
    public private(set) var backupLastSuccess: Date?
    public private(set) var backupGenerations: [LocalBackupGeneration] = []
    public private(set) var backupTotalBytes: Int64 = 0
    /// The database file's size now, for Web `dbBackupEstimatedBytes` (size × generations kept).
    public private(set) var databaseBytes: Int64?
    public private(set) var backupInfoLoaded = false
    public private(set) var backupInfoError: String?
    public private(set) var backupError: String?
    @ObservationIgnored private var store: LocalMaintenanceStore?
    @ObservationIgnored private var checkingBackup = false
    @ObservationIgnored private var backupRunning = false
    @ObservationIgnored private var clock: @Sendable () -> Date
    @ObservationIgnored private var calendar: @Sendable () -> Calendar
    public init(directory: URL? = nil, now: @escaping @Sendable () -> Date = { Date() },
                calendar: @escaping @Sendable () -> Calendar = { .current }) {
        clock = now
        self.calendar = calendar
        if let directory {
            store = LocalMaintenanceStore(directory: directory)
            backupDirectory = directory.appendingPathComponent("automatic-backups", isDirectory: true)
        }
    }

    public func connect(app: AppModel) {
        guard store == nil, let directory = app.localDataDirectory() else { return }
        store = LocalMaintenanceStore(directory: directory)
        backupDirectory = directory.appendingPathComponent("automatic-backups", isDirectory: true)
    }
    public func nextBackupDate(preferences: DisplayPreferences) -> Date? {
        guard preferences.automaticBackup, backupInfoLoaded else { return nil }
        return try? preferences.nextAutomaticBackupDate(lastSuccess: backupLastSuccess, now: clock(), calendar: calendar())
    }
    public func refreshBackupInfo(app: AppModel) async {
        connect(app: app)
        await refreshBackupInfo()
        databaseBytes = app.databaseFileURL.flatMap {
            (try? FileManager.default.attributesOfItem(atPath: $0.path)[.size] as? NSNumber)?.int64Value
        }
    }
    public func refreshBackupInfo() async {
        guard let store else { backupInfoError = "バックアップの保存先を利用できません。"; return }
        do {
            let snapshot = try await store.snapshot()
            try Task.checkCancellation()
            backupLastSuccess = snapshot.lastSuccess
            backupGenerations = snapshot.generations
            backupTotalBytes = snapshot.totalBytes
            backupInfoLoaded = true
            backupInfoError = nil
        } catch is CancellationError { }
        catch { backupInfoError = "バックアップの状態を読み込めませんでした: \(error.localizedDescription)" }
    }
    public func checkBackup(app: AppModel, automationRunning: Bool) async {
        guard !checkingBackup else { return }
        checkingBackup = true
        defer { checkingBackup = false }
        await refreshBackupInfo(app: app)
        guard !app.isBusy, !automationRunning else { return }
        await checkAutomaticBackup(preferences: app.display.preferences) { url in
            guard !app.isBusy else { return false }
            return await app.backup(to: url)
        }
    }

    /// The database owner supplies a verified snapshot operation; the schedule and retention own only automatic files.
    public func checkAutomaticBackup(preferences: DisplayPreferences, create: @MainActor (URL) async throws -> Bool) async {
        guard !backupRunning, let store, preferences.automaticBackup else { return }
        backupRunning = true
        defer { backupRunning = false }
        do {
            let manifest = try await store.manifest()
            let now = clock()
            let due = try preferences.nextAutomaticBackupDate(lastSuccess: manifest.lastSuccess, now: now, calendar: calendar())
            guard due <= now else { return }
            try Task.checkCancellation()
            let url = try await store.nextBackupURL(now: now)
            guard try await create(url) else {
                backupError = "自動バックアップを保存できませんでした。"
                backupStatus = "自動バックアップを保存できませんでした。"
                return
            }
            try await store.completed(url: url, retention: preferences.automaticBackupRetention, at: clock())
            backupStatus = "自動バックアップを保存しました。"
            backupError = nil
            await refreshBackupInfo()
        } catch is CancellationError {} catch {
            backupError = error.localizedDescription
            backupStatus = "自動バックアップ: \(error.localizedDescription)"
        }
    }
    public func log(work: SavedWork?, enabled: Bool) async {
        guard let store, enabled, let work, work.lineageNodeID != nil else { return }
        do { try await store.log(work: work); logStatus = "" }
        catch { logStatus = "生成結果のログを保存できませんでした: \(error.localizedDescription)" }
    }

    public func log(execution: DrawingLogRecord, enabled: Bool) async {
        guard let store, enabled else { return }
        do { try await store.log(execution: execution); logStatus = "" }
        catch { logStatus = "描画ログのファイルを保存できませんでした。" }
    }
}
