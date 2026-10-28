import XCTest
@testable import InkuUI

@MainActor final class RetainedBackupTests: XCTestCase {
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
