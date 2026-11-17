import CryptoKit
import Foundation
import InkuPersistence
import SQLite3
import XCTest
@testable import InkuUI

@MainActor final class LogCleanupTests: XCTestCase {
    private func hash(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined() + ".json"
    }
    private func makeFile(_ url: URL, age: TimeInterval = 10 * 86400) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("fixture".utf8).write(to: url)
        try FileManager.default.setAttributes([.modificationDate: Date().addingTimeInterval(-age)], ofItemAtPath: url.path)
    }

    func testOldLogCleanupPreservesRecentInvalidLinksAndOtherFolders() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-log-cleanup-\(UUID())")
        defer { try? FileManager.default.removeItem(at: root) }
        let old = root.appendingPathComponent("result-logs/" + hash("old"))
        let recent = root.appendingPathComponent("drawing-logs/" + hash("recent"))
        let invalid = root.appendingPathComponent("drawing-logs/other.json")
        let outside = root.appendingPathComponent("other/" + hash("outside"))
        let link = root.appendingPathComponent("result-logs/" + hash("link"))
        let nested = root.appendingPathComponent("result-logs/sub/" + hash("nested"))
        try makeFile(old); try makeFile(recent, age: 10); try makeFile(invalid); try makeFile(outside); try makeFile(nested)
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: outside)
        let app = AppModel(databaseURL: root.appendingPathComponent("db.sqlite"))
        await app.initialize()
        let written = await app.backup(to: root.appendingPathComponent("backup.sqlite"))
        XCTAssertTrue(written)
        XCTAssertEqual(app.display.preferences.cleanupLastLogsDeleted, 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: old.path))
        for item in [recent, invalid, outside, nested, link] { XCTAssertTrue(FileManager.default.fileExists(atPath: item.path)) }
        let linkedRoot = root.appendingPathComponent("linked-root")
        try FileManager.default.createDirectory(at: linkedRoot, withIntermediateDirectories: true)
        try FileManager.default.createSymbolicLink(at: linkedRoot.appendingPathComponent("drawing-logs"), withDestinationURL: outside.deletingLastPathComponent())
        let linkedMaintenance = LocalMaintenance(directory: linkedRoot)
        let linkedCount = try await linkedMaintenance.removeOldLogs(olderThan: Date())
        XCTAssertEqual(linkedCount, 0)
        XCTAssertTrue(FileManager.default.fileExists(atPath: outside.path))
    }

    func testSafetyBackupAndBusyCleanupDoNotDeleteLogs() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-log-safety-\(UUID())")
        defer { try? FileManager.default.removeItem(at: root) }
        let app = AppModel(databaseURL: root.appendingPathComponent("db.sqlite"))
        await app.initialize()
        let old = root.appendingPathComponent("drawing-logs/" + hash("old"))
        try makeFile(old)
        app.display.preferences.cleanupAfterBackup = false
        let disabled = await app.backup(to: root.appendingPathComponent("disabled.sqlite"))
        XCTAssertTrue(disabled)
        XCTAssertTrue(FileManager.default.fileExists(atPath: old.path))
        app.display.preferences.cleanupAfterBackup = true
        let safety = root.appendingPathComponent("safety.sqlite")
        let saved = await app.backup(to: safety, cleanup: false)
        XCTAssertTrue(saved)
        XCTAssertTrue(FileManager.default.fileExists(atPath: old.path))
        _ = await app.performSerialized(status: "busy") { _ in
            await app.cleanupAfterBackup(url: safety, backupTime: Date())
        }
        XCTAssertTrue(app.display.preferences.cleanupLastSkipped == true)
        XCTAssertTrue(FileManager.default.fileExists(atPath: old.path))
    }

    func testDeletedWorkKeepsSharedDrawingLogAndDatabaseFailureKeepsFiles() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-log-deletion-\(UUID())")
        defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("db.sqlite"), app = AppModel(databaseURL: url)
        await app.initialize()
        let db = try app.auxiliaryDatabase()
        for id in ["run_1", "run_2"] {
            let work = SavedWork(id: id, at: 1, input: "test", score: "{}", svg: "<svg/>", lineageNodeID: "node-" + id)
            try await db.save(work, node: LineageNode(id: "node-" + id, historyID: id, at: 1))
        }
        _ = try await db.setTrashed(ids: ["run_1", "run_2"], trashed: true)
        let first = root.appendingPathComponent("result-logs/" + hash("run_1"))
        let second = root.appendingPathComponent("result-logs/" + hash("run_2"))
        let drawing = root.appendingPathComponent("drawing-logs/" + hash("run"))
        try makeFile(first); try makeFile(second); try makeFile(drawing)
        await app.library.permanentlyDelete(ids: ["run_1"])
        XCTAssertFalse(FileManager.default.fileExists(atPath: first.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: drawing.path))
        var connection: OpaquePointer?
        XCTAssertEqual(sqlite3_open(url.path, &connection), SQLITE_OK)
        defer { sqlite3_close(connection) }
        XCTAssertEqual(sqlite3_exec(connection, "CREATE TRIGGER fail_delete BEFORE DELETE ON history BEGIN SELECT RAISE(ABORT, 'test'); END", nil, nil, nil), SQLITE_OK)
        await app.library.emptyTrash()
        XCTAssertNotNil(app.library.errorText)
        XCTAssertTrue(FileManager.default.fileExists(atPath: second.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: drawing.path))
        XCTAssertEqual(sqlite3_exec(connection, "DROP TRIGGER fail_delete", nil, nil, nil), SQLITE_OK)
        await app.library.emptyTrash()
        XCTAssertFalse(FileManager.default.fileExists(atPath: second.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: drawing.path))
    }
}
