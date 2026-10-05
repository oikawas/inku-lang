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
    func nextBackupURL() throws -> URL {
        let folder = directory.appendingPathComponent("automatic-backups", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder.appendingPathComponent("inku-auto-\(Int64(Date().timeIntervalSince1970 * 1000))-\(UUID().uuidString).sqlite")
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
        for file in files where file.lastPathComponent.hasPrefix("inku-auto-") && file.pathExtension == "sqlite" {
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
    func completed(url: URL, retention: Int) throws {
        var record = try manifest()
        record.lastSuccess = Date()
        record.files.append(url.lastPathComponent)
        let excess = max(0, record.files.count - min(30, max(1, retention)))
        let removed = Array(record.files.prefix(excess))
        record.files.removeFirst(excess)
        // Record the verified replacement before deleting any previous owned backup.
        try JSONEncoder().encode(record).write(to: manifestURL, options: .atomic)
        for name in removed where name.hasPrefix("inku-auto-") && name.hasSuffix(".sqlite") && !name.contains("/") {
            let old = url.deletingLastPathComponent().appendingPathComponent(name)
            try FileManager.default.removeItem(at: old)
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
    public private(set) var backupInfoLoaded = false
    public private(set) var backupInfoError: String?
    public private(set) var backupError: String?
    @ObservationIgnored private var store: LocalMaintenanceStore?
    public init() {}

    public func connect(app: AppModel) {
        guard store == nil, let directory = app.localDataDirectory() else { return }
        store = LocalMaintenanceStore(directory: directory)
        backupDirectory = directory.appendingPathComponent("automatic-backups", isDirectory: true)
    }
    public func nextBackupDate(preferences: DisplayPreferences) -> Date? {
        guard preferences.automaticBackup, backupInfoLoaded else { return nil }
        return backupLastSuccess.map { $0.addingTimeInterval(TimeInterval(min(168, max(1, preferences.backupIntervalHours)) * 3600)) } ?? Date()
    }
    public func refreshBackupInfo(app: AppModel) async {
        connect(app: app)
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
        await refreshBackupInfo(app: app)
        guard let store, app.display.preferences.automaticBackup, !app.isBusy, !automationRunning else { return }
        do {
            let preferences = app.display.preferences
            let manifest = try await store.manifest()
            let interval = TimeInterval(min(168, max(1, preferences.backupIntervalHours)) * 3600)
            guard manifest.lastSuccess.map({ Date().timeIntervalSince($0) >= interval }) ?? true else { return }
            try Task.checkCancellation()
            let url = try await store.nextBackupURL()
            guard await app.backup(to: url) else {
                backupError = app.errorText ?? "自動バックアップを保存できませんでした。"
                backupStatus = "自動バックアップを保存できませんでした。"
                return
            }
            try await store.completed(url: url, retention: preferences.backupGenerations)
            backupStatus = "自動バックアップを保存しました。"
            backupError = nil
            await refreshBackupInfo(app: app)
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
