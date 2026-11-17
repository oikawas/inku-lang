import Foundation
import CryptoKit
import GRDB
import InkuCore
import Testing
@testable import InkuPersistence

struct SaijikiV4MigrationTests {
    @Test func rehearsalOnExplicitCopy() async throws {
        guard let path = ProcessInfo.processInfo.environment["INKU_SAIJIKI_V4_REHEARSAL_COPY"] else { return }
        guard path.hasPrefix("/private/tmp/") else { throw PersistenceError.invalidFileURL }
        let url = URL(fileURLWithPath: path).standardizedFileURL
        let database = try InkuDatabase(url: url)
        _ = database
        let files = try FileManager.default.contentsOfDirectory(at: url.deletingLastPathComponent(), includingPropertiesForKeys: nil)
        let reportURL = try #require(files.first { $0.lastPathComponent.hasPrefix(".inku-saijiki-v4-v10-") })
        let report = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: reportURL)) as? [String: Any])
        let seconds = try #require(report["seconds"] as? Double)
        print("V4 rehearsal report: \(reportURL.path), seconds=\(seconds)")
        guard seconds <= 60 else { throw PersistenceError.invalidRecord("v10 rehearsal exceeded 60 seconds") }
        let approximated = try #require(report["approximated_words"] as? [[String: Any]])
        let ids = approximated.prefix(2).compactMap { $0["id"] as? String }
        let reader = try DatabaseQueue(path: url.path)
        let samples: [Data] = try await reader.read { db in
            var selected = ids
            if let lockID = try String.fetchOne(db, sql: """
                SELECT json_extract(CAST(acknowledgement AS TEXT), '$.work_id')
                FROM effect_acknowledgements WHERE json_array_length(CAST(acknowledgement AS TEXT), '$.performance.document.macro_locks') > 0
                  AND json_extract(CAST(acknowledgement AS TEXT), '$.performance.document.saijiki') = 'inku.saijiki.v4' LIMIT 1
                """) { selected.append(lockID) }
            return try selected.compactMap { id in
                try Data.fetchOne(db, sql: "SELECT acknowledgement FROM effect_acknowledgements WHERE json_extract(CAST(acknowledgement AS TEXT), '$.work_id') = ?", arguments: [id])
            }
        }
        #expect(samples.count >= 3)
        for data in samples {
            let ack = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
            let performance = try #require(ack["performance"] as? [String: Any])
            let configuration = try #require(performance["configuration"] as? [String: Any])
            let input = try JSONSerialization.data(withJSONObject: ["document": try #require(performance["document"]),
                "definitions": try #require(configuration["definitions"]), "compiler": try #require(configuration["compiler"])])
            let result = try #require(JSONSerialization.jsonObject(with: InkuCore.compile(input)) as? [String: Any])
            #expect(result["score"] is [String: Any])
            #expect(result["outcome"] as? String != "stopped")
        }
        try reader.close()
    }

    @Test func migratesV9WithoutChangingDigestsAndReportsRefusals() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-v10-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let url = folder.appendingPathComponent("works.sqlite")
        let resources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Sources/InkuPersistence/Resources")
        let source = "青い小さめの線を引く。"
        let snapshot = Data("historical".utf8)
        let snapshotDigest = Data(SHA256.hash(data: snapshot))
        let payloadDigest = Data(SHA256.hash(data: Data("{}".utf8)))
        @Sendable func ack(_ id: String, _ edition: String, _ documentSource: String, _ locks: [[String: String]] = []) throws -> Data {
            let definition = try JSONSerialization.jsonObject(with: Data(#"{"schema":"inku.macro-definition.v1","namespace":"Saved","heading":"Mark","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"line"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"continuity":{"expr":"semantic_ref","category":"continuity","id":"dash_dot"}}}]}"#.utf8))
            return try JSONSerialization.data(withJSONObject: ["work_id": id, "performance": ["document": ["source": documentSource,
                "language": "ja", "macro_locks": locks, "saijiki": edition], "configuration": ["definitions": id == "good" ? [definition] : []], "presentation": "keep"]], options: [.sortedKeys])
        }
        let goodAck = try ack("good", "inku.saijiki.v3", source)
        let old = try DatabaseQueue(path: url.path)
        try await old.write { db in
            for name in ["schema-v1", "migration-v2", "migration-v3", "migration-v4", "migration-v5", "migration-v6", "migration-v7", "migration-v8", "migration-v9-prepare", "migration-v9"] {
                try db.execute(sql: String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8))
            }
            for id in ["good", "already", "other", "mismatch", "refused"] {
                let edition = id == "already" ? "inku.saijiki.v4" : (id == "other" ? "inku.saijiki.v2" : "inku.saijiki.v3")
                let locks = id == "refused" ? [["qualified_name": "missing.word", "version": "1.0.0", "digest": "sha256:" + String(repeating: "0", count: 64)]] : []
                let acknowledgement = try ack(id, edition, id == "mismatch" ? "different" : source, locks)
                try db.execute(sql: "INSERT INTO history (id, at, input, ddl, score, svg) VALUES (?, 1, 'fixture', ?, '{}', '<svg/>')", arguments: [id, source])
                try db.execute(sql: "INSERT INTO execution_snapshots (id, revision, snapshot) VALUES (?, 1, ?)", arguments: [id, snapshot])
                try db.execute(sql: "INSERT INTO effect_acknowledgements (execution_id, effect_id, revision, snapshot_sha256, acknowledgement, save_payload_sha256) VALUES (?, 'save', 1, ?, ?, ?)", arguments: [id, snapshotDigest, acknowledgement, payloadDigest])
            }
            try db.execute(sql: "INSERT INTO schema_migrations(identifier) VALUES ('swift-v9-vacuum-complete')")
        }
        try old.close()
        let migrated = try InkuDatabase(url: url)
        #expect(try await migrated.work(id: "good")?.ddl?.contains("小さな") == true)
        let reader = try DatabaseQueue(path: url.path)
        let values = try await reader.read { db in
            let row = try Row.fetchOne(db, sql: "SELECT snapshot_sha256, save_payload_sha256, acknowledgement FROM effect_acknowledgements WHERE execution_id='good'")!
            return (row["snapshot_sha256"] as Data, row["save_payload_sha256"] as Data, row["acknowledgement"] as Data)
        }
        #expect(values.0 == snapshotDigest)
        #expect(values.1 == payloadDigest)
        #expect(values.2 != goodAck)
        await #expect(throws: PersistenceError.effectConflict) {
            try await migrated.commitEffect(id: "good", expectedRevision: 0, effectID: "save", snapshot: snapshot, acknowledgement: goodAck)
        }
        for id in ["already", "other", "mismatch", "refused"] { #expect(try await migrated.work(id: id)?.ddl == source) }
        try reader.close()
        let files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        let reportURL = try #require(files.first { $0.lastPathComponent.hasPrefix(".inku-saijiki-v4-v10-") })
        let report = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: reportURL)) as? [String: Any])
        #expect(report["changed"] as? Int == 1)
        #expect(report["already"] as? Int == 1)
        #expect((report["refused"] as? [[String: String]])?.count == 3)
        #expect((report["approximated_words"] as? [[String: Any]])?.count == 1)
        let refs = try #require((report["approximated_refs"] as? [[String: Any]])?.first)
        #expect(refs["id"] as? String == "good")
        #expect(refs["qualified_name"] as? String == "Saved.Mark")
        #expect(refs["version"] as? String == "1.0.0")
        #expect(refs["paths"] as? [String] == ["$.body[0].fields.continuity"])
        #expect(files.contains { $0.lastPathComponent.hasPrefix(".inku-before-v10-") })
    }
}
