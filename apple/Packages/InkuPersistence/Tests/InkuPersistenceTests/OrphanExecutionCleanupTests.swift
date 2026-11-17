import Foundation
import GRDB
import Testing
@testable import InkuPersistence

struct OrphanExecutionCleanupTests {
    private func directory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("inku-cleanup-\(UUID().uuidString)")
    }
    private func work(_ id: String) -> (SavedWork, LineageNode) {
        let nodeID = "node-" + id
        return (SavedWork(id: id, at: 1, input: "test", score: "{}", svg: "<svg/>", lineageNodeID: nodeID),
                LineageNode(id: nodeID, historyID: id, at: 1))
    }

    @Test func linkedAndTrashedWorksAreKeptAndAcknowledgementsAreDeleted() async throws {
        let folder = directory(); defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("db.sqlite"))
        let bytes = Data("{}".utf8)
        _ = try await db.compareAndSwapExecution(id: "saved", expectedRevision: nil, snapshot: bytes)
        let (saved, node) = work("saved_1"); try await db.save(saved, node: node)
        _ = try await db.setTrashed(ids: [saved.id], trashed: true)
        #expect(try await db.discardUnsavedExecution(id: "saved") == .kept(.linked))
        _ = try await db.compareAndSwapExecution(id: "referenced", expectedRevision: nil, snapshot: Data(#"{"savedWorkID":"saved_1"}"#.utf8))
        #expect(try await db.discardUnsavedExecution(id: "referenced") == .kept(.linked))
        _ = try await db.compareAndSwapExecution(id: "orphan", expectedRevision: nil, snapshot: bytes)
        _ = try await db.commitEffect(id: "orphan", expectedRevision: 0, effectID: "prepare", snapshot: bytes, acknowledgement: bytes)
        #expect(try await db.discardUnsavedExecution(id: "orphan", expectedRevision: 0) == .kept(.revisionMoved))
        #expect(try await db.discardUnsavedExecution(id: "orphan") == .discarded)
        #expect(try await db.acknowledgement(executionID: "orphan", effectID: "prepare") == nil)
        #expect(try await db.discardUnsavedExecution(id: "orphan") == .absent)
    }

    @Test func backupMismatchAndGracePeriodKeepExecution() async throws {
        let folder = directory(); defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("db.sqlite"), backup = folder.appendingPathComponent("backup.sqlite")
        let db = try InkuDatabase(url: file), bytes = Data("{}".utf8)
        _ = try await db.compareAndSwapExecution(id: "old", expectedRevision: nil, snapshot: bytes)
        _ = try await db.commitEffect(id: "old", expectedRevision: 0, effectID: "earlier", snapshot: bytes, acknowledgement: bytes)
        let raw = try DatabaseQueue(path: file.path)
        try await raw.write { try $0.execute(sql: "UPDATE execution_snapshots SET updated_at = 1 WHERE id = 'old'") }
        try await db.backup(to: backup)
        #expect(try await db.discardUnsavedExecution(id: "old", olderThan: 1, backupURL: backup) == .kept(.tooRecent))
        try await raw.write { try $0.execute(sql: "INSERT INTO effect_acknowledgements (execution_id, effect_id, revision, snapshot_sha256, acknowledgement, save_payload_sha256) SELECT execution_id, 'later', revision, snapshot_sha256, acknowledgement, save_payload_sha256 FROM effect_acknowledgements WHERE execution_id = 'old' AND effect_id = 'earlier'") }
        #expect(try await db.discardUnsavedExecution(id: "old", olderThan: 2, backupURL: backup) == .kept(.tooRecent))
        #expect(try await db.loadExecution(id: "old") != nil)
    }

    @Test func casAndEffectAdvanceUpdatedAt() async throws {
        let folder = directory(); defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("db.sqlite"), db = try InkuDatabase(url: file), bytes = Data("{}".utf8)
        _ = try await db.compareAndSwapExecution(id: "e", expectedRevision: nil, snapshot: bytes)
        let raw = try DatabaseQueue(path: file.path)
        try await raw.write { try $0.execute(sql: "UPDATE execution_snapshots SET updated_at = 1 WHERE id = 'e'") }
        _ = try await db.compareAndSwapExecution(id: "e", expectedRevision: 0, snapshot: bytes)
        #expect(try await raw.read { try Int64.fetchOne($0, sql: "SELECT updated_at FROM execution_snapshots WHERE id = 'e'") } ?? 0 > 1)
        try await raw.write { try $0.execute(sql: "UPDATE execution_snapshots SET updated_at = 1 WHERE id = 'e'") }
        _ = try await db.commitEffect(id: "e", expectedRevision: 1, effectID: "effect", snapshot: bytes, acknowledgement: bytes)
        #expect(try await raw.read { try Int64.fetchOne($0, sql: "SELECT updated_at FROM execution_snapshots WHERE id = 'e'") } ?? 0 > 1)
    }

    @Test func activeExecutionsAreKept() async throws {
        let folder = directory(); defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("db.sqlite")), bytes = Data("{}".utf8)
        _ = try await db.compareAndSwapExecution(id: "running", expectedRevision: nil, snapshot: bytes)
        await db.beginExecutionUse("running")
        #expect(try await db.discardUnsavedExecution(id: "running") == .kept(.busy))
        let (saved, node) = work("running_0")
        _ = try await db.commitEffect(id: "running", expectedRevision: 0, effectID: "save-render:0", snapshot: bytes, acknowledgement: bytes, work: saved, node: node)
        _ = try await db.permanentlyDelete(ids: [saved.id], requireTrashed: false)
        #expect(try await db.loadExecution(id: "running") != nil)
        await db.endExecutionUse("running")
    }

    @Test func migrationV11DatesExistingExecutions() async throws {
        let folder = directory(); defer { try? FileManager.default.removeItem(at: folder) }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let file = folder.appendingPathComponent("db.sqlite")
        let resources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Sources/InkuPersistence/Resources")
        let raw = try DatabaseQueue(path: file.path)
        try await raw.write { db in
            for name in ["schema-v1", "migration-v2", "migration-v3", "migration-v4", "migration-v5", "migration-v6", "migration-v7", "migration-v8", "migration-v9-prepare", "migration-v9", "migration-v10"] {
                try db.execute(sql: String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8))
            }
            try db.execute(sql: "INSERT INTO schema_migrations(identifier) VALUES ('swift-v9-vacuum-complete')")
            try db.execute(sql: "INSERT INTO execution_snapshots(id, revision, snapshot) VALUES ('old', 0, ?)", arguments: [Data("{}".utf8)])
        }
        try raw.close()
        let started = Int64(Date().timeIntervalSince1970 * 1000) - 100
        let db = try InkuDatabase(url: file)
        #expect(try await db.loadExecution(id: "old") != nil)
        let reader = try DatabaseQueue(path: file.path)
        #expect((try await reader.read { try Int64.fetchOne($0, sql: "SELECT updated_at FROM execution_snapshots WHERE id = 'old'") } ?? 0) >= started)
    }

    @Test func deletingWorksKeepsOtherWorksAndAdvancedExecutions() async throws {
        let folder = directory(); defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("db.sqlite")), bytes = Data("{}".utf8)
        _ = try await db.compareAndSwapExecution(id: "e", expectedRevision: nil, snapshot: bytes)
        let (first, firstNode) = work("e_1"), (second, secondNode) = work("e_2")
        _ = try await db.commitEffect(id: "e", expectedRevision: 0, effectID: "save-render:1", snapshot: bytes, acknowledgement: bytes, work: first, node: firstNode)
        _ = try await db.commitEffect(id: "e", expectedRevision: 1, effectID: "save-render:2", snapshot: bytes, acknowledgement: bytes, work: second, node: secondNode)
        _ = try await db.permanentlyDelete(ids: [first.id], requireTrashed: false)
        #expect(try await db.loadExecution(id: "e") != nil)
        _ = try await db.compareAndSwapExecution(id: "e", expectedRevision: 2, snapshot: bytes)
        _ = try await db.permanentlyDelete(ids: [second.id], requireTrashed: false)
        #expect(try await db.loadExecution(id: "e")?.revision == 3)
        _ = try await db.compareAndSwapExecution(id: "last", expectedRevision: nil, snapshot: bytes)
        let (last, lastNode) = work("last_0")
        _ = try await db.commitEffect(id: "last", expectedRevision: 0, effectID: "save-render:0", snapshot: bytes, acknowledgement: bytes, work: last, node: lastNode)
        _ = try await db.permanentlyDelete(ids: [last.id], requireTrashed: false)
        #expect(try await db.loadExecution(id: "last") == nil)
        #expect(try await db.acknowledgement(executionID: "last", effectID: "save-render:0") == nil)
    }
}
