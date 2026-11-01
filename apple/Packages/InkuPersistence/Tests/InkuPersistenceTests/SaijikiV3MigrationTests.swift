import Foundation
import GRDB
import InkuCore
import Testing
@testable import InkuPersistence

struct SaijikiV3MigrationTests {
    /// Only an explicitly named disposable SQLite backup may be passed here.
    @Test func migrateExplicitRehearsalCopy() async throws {
        guard let path = ProcessInfo.processInfo.environment["INKU_V7_REHEARSAL_DB"], !path.isEmpty else { return }
        let url = URL(fileURLWithPath: path).resolvingSymlinksInPath()
        let temporaryRoots = [FileManager.default.temporaryDirectory, URL(fileURLWithPath: "/private/tmp", isDirectory: true)]
            .map { $0.resolvingSymlinksInPath().path + "/" }
        guard temporaryRoots.contains(where: { url.path.hasPrefix($0) }) else {
            throw PersistenceError.invalidRecord("rehearsal_requires_temporary_copy")
        }
        _ = try InkuDatabase(url: url)
    }

    @Test func compileExplicitRehearsalSamples() async throws {
        guard let path = ProcessInfo.processInfo.environment["INKU_V7_REHEARSAL_DB"],
              let oldPath = ProcessInfo.processInfo.environment["INKU_V7_REHEARSAL_BEFORE"] else { return }
        let dbURL = URL(fileURLWithPath: path).resolvingSymlinksInPath()
        let oldURL = URL(fileURLWithPath: oldPath).resolvingSymlinksInPath()
        let root = URL(fileURLWithPath: "/private/tmp", isDirectory: true).resolvingSymlinksInPath().path + "/"
        guard dbURL.path.hasPrefix(root), oldURL.path.hasPrefix(root) else { throw PersistenceError.invalidRecord("rehearsal_requires_temporary_copy") }
        var config = Configuration(); config.readonly = true
        let old = try DatabaseQueue(path: oldURL.path, configuration: config)
        let ids = try await old.read { db -> [String] in
            let many = try String.fetchAll(db, sql: """
                SELECT id FROM history WHERE ddl IS NOT NULL
                ORDER BY (length(ddl)-length(replace(ddl,'細筆',''))) +
                         (length(ddl)-length(replace(ddl,'太筆',''))) +
                         (length(ddl)-length(replace(ddl,'クレヨン',''))) DESC LIMIT 2
                """)
            let rare = try String.fetchOne(db, sql: """
                SELECT json_extract(CAST(acknowledgement AS TEXT), '$.work_id') AS work_id
                FROM effect_acknowledgements
                GROUP BY json_extract(CAST(acknowledgement AS TEXT), '$.performance.document.macro_locks')
                ORDER BY count(*) ASC LIMIT 1
                """)
            return many + (rare.map { [$0] } ?? [])
        }
        try old.close()
        #expect(ids.count == 3)
        let current = try DatabaseQueue(path: dbURL.path, configuration: config)
        for id in ids {
            let request = try #require(try await current.read { db in
                try String.fetchOne(db, sql: """
                    SELECT json_object('document', json(json_extract(CAST(acknowledgement AS TEXT), '$.performance.document')),
                        'definitions', json(json_extract(CAST(acknowledgement AS TEXT), '$.performance.configuration.definitions')),
                        'compiler', json(json_extract(CAST(acknowledgement AS TEXT), '$.performance.configuration.compiler')))
                    FROM effect_acknowledgements WHERE json_extract(CAST(acknowledgement AS TEXT), '$.work_id') = ?
                    """, arguments: [id])
            })
            let result = try #require(JSONSerialization.jsonObject(with: InkuCore.compile(Data(request.utf8))) as? [String: Any])
            #expect(result["error"] == nil || result["error"] is NSNull)
            #expect(result["score"] is [String: Any])
        }
        try current.close()
    }

    @Test func migratesOneUnitAndLeavesRefusalsAndLogsIntact() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-v7-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("works.sqlite")
        let resources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Sources/InkuPersistence/Resources")
        let old = try DatabaseQueue(path: file.path)
        @Sendable func bytes(_ object: Any) throws -> Data { try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) }
        let source = "青い細筆の線を引く。"
        try await old.write { db in
            for name in ["schema-v1", "migration-v2", "migration-v3", "migration-v4", "migration-v5", "migration-v6"] {
                try db.execute(sql: String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8))
            }
            for id in ["good", "already", "mismatch", "refused"] {
                let locks: [[String: String]] = id == "refused" ? [["qualified_name": "missing.word", "version": "1.0.0", "digest": "sha256:" + String(repeating: "0", count: 64)]] : []
                let doc: [String: Any] = ["source": source, "language": "ja", "macro_locks": locks,
                                           "saijiki": id == "already" ? "inku.saijiki.v3" : "inku.saijiki.v2"]
                let ack = try bytes(["work_id": id, "performance": ["document": doc, "configuration": ["definitions": []], "presentation": "keep"]])
                let payload = try bytes(["work": ["ddl": id == "mismatch" ? "different" : source], "other": "keep"])
                try db.execute(sql: "INSERT INTO history (id, at, input, ddl, score, svg) VALUES (?, 1, 'fixture', ?, '{}', '<svg/>')", arguments: [id, source])
                try db.execute(sql: "INSERT INTO execution_snapshots (id, revision, snapshot) VALUES (?, 0, ?)", arguments: [id, Data("historical".utf8)])
                try db.execute(sql: "INSERT INTO effect_acknowledgements (execution_id, effect_id, revision, snapshot, acknowledgement, save_payload) VALUES (?, 'save', 0, ?, ?, ?)", arguments: [id, Data("historical".utf8), ack, payload])
            }
        }
        try old.close()
        let migrated = try InkuDatabase(url: file)
        #expect(try await migrated.work(id: "good")?.ddl?.contains("ガッシュ") == true)
        #expect(try await migrated.work(id: "already")?.ddl == source)
        #expect(try await migrated.work(id: "mismatch")?.ddl == source)
        #expect(try await migrated.work(id: "refused")?.ddl == source)
        let reader = try DatabaseQueue(path: file.path)
        let fields = try await reader.read { db in
            (try Int.fetchOne(db, sql: "PRAGMA user_version"),
             try Data.fetchOne(db, sql: "SELECT snapshot FROM execution_snapshots WHERE id='good'"),
             try Data.fetchOne(db, sql: "SELECT snapshot FROM effect_acknowledgements WHERE execution_id='good'"),
             try String.fetchOne(db, sql: "SELECT json_extract(CAST(acknowledgement AS TEXT), '$.performance.document.saijiki') FROM effect_acknowledgements WHERE execution_id='good'"))
        }
        #expect(fields.0 == 7)
        #expect(fields.1 == Data("historical".utf8))
        #expect(fields.2 == Data("historical".utf8))
        #expect(fields.3 == "inku.saijiki.v3")
        try reader.close()
        let files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        let reportURL = try #require(files.first { $0.lastPathComponent.hasPrefix(".inku-saijiki-v3-v7-") })
        let report = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: reportURL)) as? [String: Any])
        #expect(report["changed"] as? Int == 1)
        #expect(report["already"] as? Int == 1)
        #expect((report["refused"] as? [[String: String]])?.count == 2)
        let backupURL = try #require(files.first { $0.lastPathComponent.hasPrefix(".inku-before-v7-") })
        let backup = try DatabaseQueue(path: backupURL.path)
        #expect(try await backup.read { try Int.fetchOne($0, sql: "PRAGMA user_version") } == 6)
        try backup.close()
    }
}
