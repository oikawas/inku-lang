import Foundation
import CryptoKit
import GRDB
import InkuCore
import Testing
@testable import InkuPersistence

struct SaijikiV3MigrationTests {
    @Test func recoversHistoricalDefinitionAndPreservesUnknownDigest() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-v7-missing-definition-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("works.sqlite")
        let package = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let root = package.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let table = root.appendingPathComponent("core/crates/inku-pipeline-uniffi/assets/nature-historical-definitions.json")
        let data = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: table)) as? [String: Any])
        let definitions = try #require(data["definitions"] as? [[String: Any]])
        let definition = definitions[14]
        let firstInput = try JSONSerialization.data(withJSONObject: ["definitions": [definition]])
        let first = try #require(JSONSerialization.jsonObject(with: InkuCore.migrateSaijikiV2(firstInput)) as? [String: Any])
        let entry = try #require((first["definitions"] as? [[String: Any]])?.first)
        let lock: [String: Any] = ["qualified_name": try #require(entry["qualified_name"] as? String),
            "version": try #require(entry["version"] as? String), "digest": try #require(entry["old_digest"] as? String)]
        let source = "｛若葉｝。"
        let document: [String: Any] = ["source": source, "language": "ja", "saijiki": "inku.saijiki.v2", "macro_locks": [lock]]
        let request = try JSONSerialization.data(withJSONObject: ["document": document, "definitions": []])
        let answer = try #require(JSONSerialization.jsonObject(with: InkuCore.migrateSaijikiV2(request)) as? [String: Any])
        #expect((answer["document"] as? [String: Any])?["error"] == nil)
        #expect((answer["definitions"] as? [Any])?.isEmpty == true)
        #expect(((answer["document"] as? [String: Any])?["recovered_definitions"] as? [Any])?.count == 1)
        let ack = try JSONSerialization.data(withJSONObject: ["work_id": "historical", "performance": ["document": document, "configuration": ["definitions": []]]])
        var unknownLock = lock; unknownLock["digest"] = "sha256:" + String(repeating: "0", count: 64)
        var unknownDocument = document; unknownDocument["macro_locks"] = [unknownLock]
        let unknownAck = try JSONSerialization.data(withJSONObject: ["work_id": "unknown", "performance": ["document": unknownDocument, "configuration": ["definitions": []]]])
        let payload = try JSONSerialization.data(withJSONObject: ["work": ["ddl": source]])
        let resources = package.appendingPathComponent("Sources/InkuPersistence/Resources")
        let old = try DatabaseQueue(path: file.path)
        try await old.write { db in
            for name in ["schema-v1", "migration-v2", "migration-v3", "migration-v4", "migration-v5", "migration-v6"] {
                try db.execute(sql: String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8))
            }
            try db.execute(sql: "INSERT INTO history (id, at, input, ddl, score, svg) VALUES ('historical', 1, 'fixture', ?, '{}', '<svg/>')", arguments: [source])
            try db.execute(sql: "INSERT INTO execution_snapshots (id, revision, snapshot) VALUES ('historical', 0, ?)", arguments: [Data("history".utf8)])
            try db.execute(sql: "INSERT INTO effect_acknowledgements (execution_id, effect_id, revision, snapshot, acknowledgement, save_payload) VALUES ('historical', 'save', 0, ?, ?, ?)", arguments: [Data("history".utf8), ack, payload])
            try db.execute(sql: "INSERT INTO history (id, at, input, ddl, score, svg) VALUES ('unknown', 1, 'fixture', ?, '{}', '<svg/>')", arguments: [source])
            try db.execute(sql: "INSERT INTO execution_snapshots (id, revision, snapshot) VALUES ('unknown', 0, ?)", arguments: [Data("history".utf8)])
            try db.execute(sql: "INSERT INTO effect_acknowledgements (execution_id, effect_id, revision, snapshot, acknowledgement, save_payload) VALUES ('unknown', 'save', 0, ?, ?, ?)", arguments: [Data("history".utf8), unknownAck, payload])
        }
        try old.close()
        let migrated = try InkuDatabase(url: file)
        #expect(try await migrated.work(id: "historical")?.ddl == source)
        #expect(try await migrated.work(id: "unknown")?.ddl == source)
        let reader = try DatabaseQueue(path: file.path)
        let savedAck = try #require(try await reader.read { try Data.fetchOne($0, sql: "SELECT acknowledgement FROM effect_acknowledgements WHERE execution_id='historical'") })
        let unchangedAck = try await reader.read { try Data.fetchOne($0, sql: "SELECT acknowledgement FROM effect_acknowledgements WHERE execution_id='unknown'") }
        #expect(unchangedAck == unknownAck)
        let parsed = try #require(JSONSerialization.jsonObject(with: savedAck) as? [String: Any])
        let performance = try #require(parsed["performance"] as? [String: Any])
        let migratedDocument = try #require(performance["document"] as? [String: Any])
        let configuration = try #require(performance["configuration"] as? [String: Any])
        let savedDefinitions = try #require(configuration["definitions"] as? [[String: Any]])
        #expect(savedDefinitions.count == 1)
        #expect(migratedDocument["saijiki"] as? String == "inku.saijiki.v3")
        let registry = try #require(JSONSerialization.jsonObject(with: InkuCore.canvasRegistry) as? [String: Any])
        let registryDigest = try #require(registry["digest"] as? String)
        let seed = "42"
        let paletteInput = try JSONSerialization.data(withJSONObject: ["color_map": [:], "catalog_id": "default", "render_seed": seed, "background": "white"])
        let palette = try #require(JSONSerialization.jsonObject(with: InkuCore.resolvePalette(paletteInput)) as? [String: Any])
        let budget: [String: Any] = ["maximum": ["logical_objects": 400, "primitive_marks": 400, "object_templates": 64, "maximum_per_template_primitive_marks": 240, "maximum_resolved_count": 2000, "template_nodes": 512, "anchor_instances": 400, "transform_instances": 400, "placement_instances": 400, "fill_instances": 400]]
        let compiler: [String: Any] = ["host": ["canvas_format_id": "square", "canvas_format_registry_id": "inku.canvas-format-registry.v1", "canvas_format_registry_digest": registryDigest, "resolved_catalog_id": "default", "catalog_mode": "default", "background": "white", "palette": palette], "composition_seed": seed, "macro_expansion_limits": ["max_invocations": "64", "max_depth": "16", "max_evaluation_steps": "8192", "max_nodes_per_invocation": "128", "max_total_nodes": "512"], "stage15_variation": NSNull(), "error_policy": "omit_and_continue", "hard_resource_policy": ["identity": "test.historical-v7", "budget": budget], "operational_resource_budget": budget]
        let compileInput = try JSONSerialization.data(withJSONObject: ["document": migratedDocument, "definitions": savedDefinitions, "compiler": compiler])
        let compiled = try #require(JSONSerialization.jsonObject(with: InkuCore.compile(compileInput)) as? [String: Any])
        #expect(compiled["score"] is [String: Any])
        #expect(compiled["outcome"] as? String != "stopped")
        try reader.close()
        let files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        let reportURL = try #require(files.first { $0.lastPathComponent.hasPrefix(".inku-saijiki-v3-v7-") })
        let report = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: reportURL)) as? [String: Any])
        #expect((report["refused"] as? [[String: String]])?.first?["id"] == "unknown")
        #expect((report["refused"] as? [[String: String]])?.first?["reason"] == "definition_not_supplied")
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
             try Data.fetchOne(db, sql: "SELECT snapshot_sha256 FROM effect_acknowledgements WHERE execution_id='good'"),
             try String.fetchOne(db, sql: "SELECT json_extract(CAST(acknowledgement AS TEXT), '$.performance.document.saijiki') FROM effect_acknowledgements WHERE execution_id='good'"))
        }
        #expect(fields.0 == InkuDatabase.currentSchemaVersion)
        #expect(fields.1 == Data("historical".utf8))
        #expect(fields.2 == Data(SHA256.hash(data: Data("historical".utf8))))
        #expect(fields.3 == "inku.saijiki.v3")
        try reader.close()
        let files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        let reportURL = try #require(files.first { $0.lastPathComponent.hasPrefix(".inku-saijiki-v3-v7-") })
        let report = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: reportURL)) as? [String: Any])
        #expect(report["changed"] as? Int == 1)
        #expect(report["already"] as? Int == 1)
        #expect((report["refused"] as? [[String: String]])?.count == 2)
        let backupURL = try #require(files.first { $0.lastPathComponent.hasPrefix(".inku-before-v9-") })
        let backup = try DatabaseQueue(path: backupURL.path)
        #expect(try await backup.read { try Int.fetchOne($0, sql: "PRAGMA user_version") } == 6)
        try backup.close()
    }
}
