import Foundation
import GRDB
import InkuCore
import Testing
@testable import InkuPersistence

struct PluginNamesMigrationTests {
    @Test func migratesCopiesAndPreservesRefusedWorks() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plugin-v6-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("works.sqlite")
        let tests = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let package = tests.deletingLastPathComponent().deletingLastPathComponent()
        let resources = package.appendingPathComponent("Sources/InkuPersistence/Resources")
        let root = package.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let fixture = root.appendingPathComponent("core/crates/inku-ddl/tests/fixtures/nature-leaves-2.1-v1.json")
        let fixtureObject = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as? [String: Any])
        let entries = try #require(fixtureObject["entries"] as? [[String: Any]])
        let definition = try #require(entries.first?["definition"] as? [String: Any])
        func json(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) }
        let definitionText = String(decoding: try json(definition), as: UTF8.self)
        let request = try json(["maximum_entries": 64, "canonical": [["source_id": "fixture", "definition_json": definitionText, "summary": ""]], "legacy": [], "bundled_packages": [], "language": "ja"])
        let catalog = try #require(JSONSerialization.jsonObject(with: InkuCore.resolveMacroCatalog(request)) as? [String: Any])
        let catalogLocks = try #require(catalog["locks"] as? [[String: Any]])
        var lock = try #require(catalogLocks.first)
        let digest = try #require(lock["digest"] as? String)
        lock["digest"] = digest.hasPrefix("sha256:") ? digest : "sha256:" + digest
        lock["aliases"] = ["Nature.若葉"]
        var badLock = lock; badLock["digest"] = "sha256:" + String(repeating: "0", count: 64)
        let source = "Nature.若葉。"
        func records(id: String, lock: [String: Any]) throws -> (Data, Data, Data) {
            let document: [String: Any] = ["source": source, "language": "ja", "macro_locks": [lock]]
            let config: [String: Any] = ["definitions": [definition]]
            let inner = try json(["document": document, "config": config, "untouched": "inner"])
            let outer = try json(["schema": "inku.swift-pipeline-execution.v1", "snapshot": inner.base64EncodedString(), "untouched": "outer"])
            let ack = try json(["work_id": id, "performance": ["configuration": config, "document": document, "score": ["keep": 9]]])
            let payload = try json(["work": ["ddl": source, "score": "{\"exact\":1}", "svg": "<svg/>"], "untouched": "payload"])
            return (outer, ack, payload)
        }
        let good = try records(id: "good_1", lock: lock), bad = try records(id: "bad_1", lock: badLock)
        let old = try DatabaseQueue(path: file.path)
        try await old.write { db in
            for name in ["schema-v1", "migration-v2", "migration-v3", "migration-v4", "migration-v5"] {
                try db.execute(sql: String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8))
            }
            for (id, execution, data) in [("good_1", "good", good), ("bad_1", "bad", bad)] {
                try db.execute(sql: "INSERT INTO history (id, at, input, ddl, score, svg, instruction_lang_resolved) VALUES (?, 1, 'fixture', ?, '{\"exact\":1}', '<svg/>', 'ja')", arguments: [id, source])
                try db.execute(sql: "INSERT INTO execution_snapshots (id, revision, snapshot) VALUES (?, 0, ?)", arguments: [execution, data.0])
                try db.execute(sql: "INSERT INTO effect_acknowledgements (execution_id, effect_id, revision, snapshot, acknowledgement, save_payload) VALUES (?, 'save-render:1', 0, ?, ?, ?)", arguments: [execution, data.0, data.1, data.2])
            }
        }
        try old.close()
        let database = try InkuDatabase(url: file)
        let goodWork = try await database.work(id: "good_1"), badWork = try await database.work(id: "bad_1")
        #expect(goodWork?.ddl == "｛若葉｝。")
        #expect(goodWork?.score == "{\"exact\":1}" && goodWork?.svg == "<svg/>")
        #expect(badWork?.ddl == source)
        let registry = try #require(try JSONSerialization.jsonObject(with: InkuCore.canvasRegistry) as? [String: Any])
        let registryDigest = try #require(registry["digest"] as? String)
        let seed = "18446744073709551615"
        let palette = try #require(try JSONSerialization.jsonObject(with: InkuCore.resolvePalette(try json(["color_map": [:], "catalog_id": "default", "render_seed": seed, "background": "white"]))) as? [String: Any])
        let budget: [String: Any] = ["maximum": ["logical_objects": 400, "primitive_marks": 400, "object_templates": 64, "maximum_per_template_primitive_marks": 240,
            "maximum_resolved_count": 2000, "template_nodes": 512, "anchor_instances": 400, "transform_instances": 400, "placement_instances": 400, "fill_instances": 400]]
        let compiler: [String: Any] = ["host": ["canvas_format_id": "square", "canvas_format_registry_id": "inku.canvas-format-registry.v1",
            "canvas_format_registry_digest": registryDigest, "resolved_catalog_id": "default", "catalog_mode": "default", "background": "white", "palette": palette],
            "composition_seed": seed, "macro_expansion_limits": ["max_invocations": "64", "max_depth": "16", "max_evaluation_steps": "8192", "max_nodes_per_invocation": "128", "max_total_nodes": "512"],
            "stage15_variation": NSNull(), "error_policy": "omit_and_continue", "hard_resource_policy": ["identity": "test.plugin-v6", "budget": budget], "operational_resource_budget": budget]
        func compiled(_ ddl: String) throws -> [String: Any] {
            let request = try json(["document": ["source": ddl, "language": "ja", "macro_locks": [lock], "saijiki": "inku.saijiki.v2"], "definitions": [definition], "compiler": compiler])
            return try #require(try JSONSerialization.jsonObject(with: InkuCore.compile(request)) as? [String: Any])
        }
        let before = try compiled(source), after = try compiled(try #require(goodWork?.ddl))
        let beforeScore = try #require(before["score"] as? [String: Any]), afterScore = try #require(after["score"] as? [String: Any])
        #expect(!(beforeScore["instructions"] as? [Any] ?? []).isEmpty)
        #expect(try json(beforeScore) == json(afterScore))
        let reader = try DatabaseQueue(path: file.path)
        try await reader.read { db in
            #expect(try Int.fetchOne(db, sql: "PRAGMA user_version") == 6)
            let ack = try #require(try Data.fetchOne(db, sql: "SELECT acknowledgement FROM effect_acknowledgements WHERE execution_id = 'good'"))
            let payload = try #require(try Data.fetchOne(db, sql: "SELECT save_payload FROM effect_acknowledgements WHERE execution_id = 'good'"))
            #expect(try String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), '$.performance.document.source')", arguments: [ack]) == "｛若葉｝。")
            #expect(try String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), '$.work.ddl')", arguments: [payload]) == "｛若葉｝。")
            #expect(try String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), '$.performance.document.macro_locks')", arguments: [ack]) == String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), '$.performance.document.macro_locks')", arguments: [good.1]))
            #expect(try String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), '$.performance.configuration.definitions')", arguments: [ack]) == String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), '$.performance.configuration.definitions')", arguments: [good.1]))
            let outer = try #require(try Data.fetchOne(db, sql: "SELECT snapshot FROM execution_snapshots WHERE id = 'good'"))
            let encoded = try #require(try String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), '$.snapshot')", arguments: [outer]))
            let inner = try #require(Data(base64Encoded: encoded))
            #expect(try String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), '$.document.source')", arguments: [inner]) == "｛若葉｝。")
            let effectSnapshot = try #require(try Data.fetchOne(db, sql: "SELECT snapshot FROM effect_acknowledgements WHERE execution_id = 'good'"))
            let effectEncoded = try #require(try String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), '$.snapshot')", arguments: [effectSnapshot]))
            let effectInner = try #require(Data(base64Encoded: effectEncoded))
            #expect(try String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), '$.document.source')", arguments: [effectInner]) == "｛若葉｝。")
            #expect(try Data.fetchOne(db, sql: "SELECT snapshot FROM execution_snapshots WHERE id = 'bad'") == bad.0)
        }
        try reader.close()
        let files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        let backupURL = try #require(files.first { $0.lastPathComponent.hasPrefix(".inku-before-v6-") })
        let backup = try DatabaseQueue(path: backupURL.path)
        #expect(try await backup.read { try Int.fetchOne($0, sql: "PRAGMA user_version") } == 5)
        try backup.close()
        let reportURL = try #require(files.first { $0.lastPathComponent.hasPrefix(".inku-plugin-names-v6-") })
        let report = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: reportURL)) as? [String: Any])
        #expect(report["changed"] as? Int == 1)
        #expect((report["refused"] as? [[String: Any]])?.contains { $0["id"] as? String == "bad_1" } == true)
        let reopened = try InkuDatabase(url: file)
        #expect(try await reopened.work(id: "good_1")?.ddl == "｛若葉｝。")
        let again = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        #expect(again.filter { $0.lastPathComponent.hasPrefix(".inku-before-v6-") }.count == 1)
        #expect(again.filter { $0.lastPathComponent.hasPrefix(".inku-plugin-names-v6-") }.count == 1)
    }
}
