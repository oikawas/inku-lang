import XCTest
@testable import InkuUI

@MainActor final class RetainedBackupTests: XCTestCase {
    func testOldManifestWithoutDeletionJournalIsReadable() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-backup-legacy-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try Data(#"{"files":[]}"#.utf8).write(to: root.appendingPathComponent("automatic-backups.json"))
        let maintenance = LocalMaintenance(directory: root)
        await maintenance.refreshBackupInfo()
        XCTAssertNil(maintenance.backupInfoError)
        XCTAssertTrue(maintenance.backupInfoLoaded)
        XCTAssertTrue(maintenance.backupGenerations.isEmpty)
    }

    func testPruningKeepsUnremovedBackupTrackedForRetry() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-backup-prune-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        var preferences = DisplayPreferences(); preferences.automaticBackup = true; preferences.backupSchedule.maxGenerations = 1
        let initial = LocalMaintenance(directory: root)
        await initial.checkAutomaticBackup(preferences: preferences) { url in
            try Data("first".utf8).write(to: url); return true
        }
        let name = try XCTUnwrap(initial.backupGenerations.first?.name)
        let old = root.appendingPathComponent("automatic-backups").appendingPathComponent(name)
        try FileManager.default.removeItem(at: old)
        try FileManager.default.createDirectory(at: old, withIntermediateDirectories: false)

        let later = LocalMaintenance(directory: root, now: { Date().addingTimeInterval(40 * 86400) })
        await later.checkAutomaticBackup(preferences: preferences) { url in
            try Data("second".utf8).write(to: url); return true
        }
        XCTAssertNotNil(later.backupError)
        let manifest = try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("automatic-backups.json"))) as? [String: Any]
        XCTAssertTrue((manifest?["files"] as? [String] ?? []).contains(name))

        try FileManager.default.removeItem(at: old)
        try Data("first".utf8).write(to: old)
        let recovered = LocalMaintenance(directory: root)
        await recovered.refreshBackupInfo()
        XCTAssertNil(recovered.backupInfoError)
        XCTAssertFalse(FileManager.default.fileExists(atPath: old.path))
        let retry = LocalMaintenance(directory: root, now: { Date().addingTimeInterval(80 * 86400) })
        await retry.checkAutomaticBackup(preferences: preferences) { url in
            try Data("third".utf8).write(to: url); return true
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: old.path))
        XCTAssertEqual(retry.backupGenerations.count, 1)
    }

    func testRestoreRetainsSafetyBackupAcrossAutomaticPruning() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-backup-restore-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"))
        await app.initialize()
        XCTAssertNil(app.errorText)
        let maintenance = LocalMaintenance(directory: root)
        var preferences = DisplayPreferences(); preferences.automaticBackup = true; preferences.backupSchedule.maxGenerations = 1
        await maintenance.checkAutomaticBackup(preferences: preferences) { url in await app.backup(to: url) }
        let original = try XCTUnwrap(maintenance.backupGenerations.first?.name)
        await maintenance.restoreRetainedBackup(name: original, app: app)
        XCTAssertEqual(app.restorationRevision, 1)
        XCTAssertEqual(maintenance.backupGenerations.filter(\.isManual).count, 1)
        let manual = try XCTUnwrap(maintenance.backupGenerations.first(where: \.isManual)?.name)
        let later = LocalMaintenance(directory: root, now: { Date().addingTimeInterval(40 * 86400) })
        await later.checkAutomaticBackup(preferences: preferences) { url in await app.backup(to: url) }
        XCTAssertEqual(later.backupGenerations.filter(\.isManual).map(\.name), [manual])
        XCTAssertEqual(later.backupGenerations.filter { !$0.isManual }.count, 1)
    }
    func testOnlyTrackedRegularBackupCanBeDeleted() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-backup-delete-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let maintenance = LocalMaintenance(directory: root)
        var preferences = DisplayPreferences(); preferences.automaticBackup = true
        await maintenance.checkAutomaticBackup(preferences: preferences) { url in
            try Data("test data".utf8).write(to: url); return true
        }
        let name = try XCTUnwrap(maintenance.backupGenerations.first?.name)
        let outside = root.appendingPathComponent("outside.sqlite")
        try Data("keep".utf8).write(to: outside)
        await maintenance.deleteRetainedBackup(name: "../outside.sqlite")
        XCTAssertTrue(FileManager.default.fileExists(atPath: outside.path))
        XCTAssertEqual(maintenance.backupGenerations.count, 1)
        let retained = root.appendingPathComponent("automatic-backups").appendingPathComponent(name)
        try FileManager.default.removeItem(at: retained)
        try FileManager.default.createSymbolicLink(at: retained, withDestinationURL: outside)
        await maintenance.deleteRetainedBackup(name: name)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outside.path))
        XCTAssertNotNil(maintenance.backupError)
        try FileManager.default.removeItem(at: retained)
        try Data("test data".utf8).write(to: retained)
        await maintenance.deleteRetainedBackup(name: name)
        XCTAssertTrue(maintenance.backupGenerations.isEmpty)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outside.path))
    }
}
