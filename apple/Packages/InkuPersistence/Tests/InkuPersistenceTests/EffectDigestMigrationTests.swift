import CryptoKit
import Foundation
import GRDB
import Testing
@testable import InkuPersistence

struct EffectDigestMigrationTests {
    private let snapshot = Data([0, 1, 255, 13])
    private let acknowledgement = Data([2, 255, 0])

    private func makeV8(at file: URL) async throws {
        let resources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Sources/InkuPersistence/Resources")
        let queue = try DatabaseQueue(path: file.path)
        try await queue.write { db in
            for name in ["schema-v1", "migration-v2", "migration-v3", "migration-v4", "migration-v5", "migration-v6", "migration-v7", "migration-v8"] {
                try db.execute(sql: String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8))
            }
            try db.execute(sql: "INSERT INTO history(id,at,input,score,svg) VALUES ('work',1,'test','{\"x\":1}','<svg/>')")
            try db.execute(sql: "INSERT INTO execution_snapshots(id,revision,snapshot) VALUES ('saved',1,?),('orphan',0,?)", arguments: [snapshot, Data([99])])
            try db.execute(sql: """
                INSERT INTO effect_acknowledgements(execution_id,effect_id,revision,snapshot,acknowledgement,save_payload)
                VALUES ('saved','effect',1,?,?,?)
                """, arguments: [snapshot, acknowledgement, Data("{}".utf8)])
        }
        try queue.close()
    }

    @Test func v8MigrationKeepsDataAndRetryAndPrunesOldBackup() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-v9-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("works.sqlite")
        let older = folder.appendingPathComponent(".inku-before-v7-\(UUID().uuidString).sqlite")
        try Data("old".utf8).write(to: older)
        try await makeV8(at: file)
        let db = try InkuDatabase(url: file)
        #expect(try await db.work(id: "work")?.svg == "<svg/>")
        #expect(try await db.work(id: "work")?.score == "{\"x\":1}")
        #expect(try await db.loadExecution(id: "orphan") == nil)
        #expect(try await db.loadExecution(id: "saved")?.snapshot == snapshot)
        #expect(try await db.acknowledgement(executionID: "saved", effectID: "effect") == acknowledgement)
        let retry = try await db.commitEffect(id: "saved", expectedRevision: 0, effectID: "effect", snapshot: snapshot, acknowledgement: acknowledgement)
        #expect(retry.wasAlreadyCommitted && retry.execution.revision == 1 && retry.execution.snapshot == snapshot && retry.acknowledgement == acknowledgement)
        await #expect(throws: PersistenceError.effectConflict) {
            try await db.commitEffect(id: "saved", expectedRevision: 0, effectID: "effect", snapshot: Data([3]), acknowledgement: acknowledgement)
        }
        let raw = try DatabaseQueue(path: file.path)
        try await raw.read { reader in
            let row = try #require(try Row.fetchOne(reader, sql: "SELECT snapshot_sha256,save_payload_sha256 FROM effect_acknowledgements"))
            #expect((row["snapshot_sha256"] as Data) == Data(SHA256.hash(data: snapshot)))
            #expect((row["save_payload_sha256"] as Data) == Data(SHA256.hash(data: Data("{}".utf8))))
            #expect(try Int.fetchOne(reader, sql: "PRAGMA user_version") == 9)
            #expect(try Int.fetchOne(reader, sql: "SELECT count(*) FROM sqlite_master WHERE type='index' AND name='lineage_edges_parent_node_id'") == 1)
            #expect(try Int.fetchOne(reader, sql: "SELECT count(*) FROM schema_migrations WHERE identifier='swift-v9-vacuum-complete'") == 1)
        }
        try raw.close()
        let files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        let backup = try #require(files.first { $0.lastPathComponent.hasPrefix(".inku-before-v9-") })
        #expect(!FileManager.default.fileExists(atPath: older.path))
        let backupDB = try DatabaseQueue(path: backup.path)
        #expect(try await backupDB.read { try Int.fetchOne($0, sql: "PRAGMA user_version") } == 8)
        #expect(try await backupDB.read { try String.fetchOne($0, sql: "PRAGMA journal_mode") } == "delete")
        try backupDB.close()
        let attributes = try FileManager.default.attributesOfItem(atPath: backup.path)
        #expect((attributes[.posixPermissions] as? NSNumber)?.intValue == 0o600)
    }

    @Test func restoreMigratesV8WithoutChangingBackup() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-v9-restore-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let backup = folder.appendingPathComponent("v8.sqlite")
        try await makeV8(at: backup)
        let before = try Data(contentsOf: backup)
        let db = try InkuDatabase(url: folder.appendingPathComponent("current.sqlite"))
        try await db.restore(from: backup)
        #expect(try Data(contentsOf: backup) == before)
        #expect(try await db.work(id: "work")?.score == "{\"x\":1}")
        #expect(try await db.loadExecution(id: "orphan") == nil)
        let retry = try await db.commitEffect(id: "saved", expectedRevision: 0, effectID: "effect", snapshot: snapshot, acknowledgement: acknowledgement)
        #expect(retry.wasAlreadyCommitted && retry.execution.snapshot == snapshot && retry.acknowledgement == acknowledgement)
    }
}
