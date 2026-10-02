import CryptoKit
import Foundation
import InkuPersistence
import Observation

private struct BackupManifest: Codable, Sendable {
    var lastSuccess: Date?
    var files: [String] = []
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
}

@MainActor @Observable
public final class LocalMaintenance {
    public private(set) var backupStatus = ""
    public private(set) var logStatus = ""
    @ObservationIgnored private var store: LocalMaintenanceStore?
    public init() {}

    public func connect(app: AppModel) {
        guard store == nil, let directory = app.localDataDirectory() else { return }
        store = LocalMaintenanceStore(directory: directory)
    }
    public func checkBackup(app: AppModel, automationRunning: Bool) async {
        guard let store, app.display.preferences.automaticBackup, !app.isBusy, !automationRunning else { return }
        do {
            let preferences = app.display.preferences
            let manifest = try await store.manifest()
            let interval = TimeInterval(min(168, max(1, preferences.backupIntervalHours)) * 3600)
            guard manifest.lastSuccess.map({ Date().timeIntervalSince($0) >= interval }) ?? true else { return }
            try Task.checkCancellation()
            let url = try await store.nextBackupURL()
            guard await app.backup(to: url) else { backupStatus = "自動バックアップを保存できませんでした。"; return }
            try await store.completed(url: url, retention: preferences.backupGenerations)
            backupStatus = "自動バックアップを保存しました。"
        } catch is CancellationError {} catch { backupStatus = "自動バックアップ: \(error.localizedDescription)" }
    }
    public func log(work: SavedWork?, enabled: Bool) async {
        guard let store, enabled, let work, work.lineageNodeID != nil else { return }
        do { try await store.log(work: work); logStatus = "" }
        catch { logStatus = "生成結果のログを保存できませんでした: \(error.localizedDescription)" }
    }
}
