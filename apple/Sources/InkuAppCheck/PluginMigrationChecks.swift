import Foundation
import InkuCore
import InkuHost
import InkuPersistence

/// Isolated v5 database; the author's database and provider storage are never opened.
@MainActor func runPluginNameMigrationChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plugin-migration-check-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let file = folder.appendingPathComponent("works.sqlite")
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    let fixture = root.appendingPathComponent("core/crates/inku-ddl/tests/fixtures/nature-leaves-2.1-v1.json")
    let package = try ExactJSON(data: Data(contentsOf: fixture))
    guard let definition = package["entries"].array?.first?["definition"] else { throw CheckFailure.message("Missing migration fixture") }
    let catalogRequest: ExactJSON = .object(["maximum_entries": .integer(64), "canonical": .array([.object([
        "source_id": .string("fixture"), "definition_json": .string(definition.text), "summary": .string("")])]),
        "legacy": .array([]), "bundled_packages": .array([]), "language": .string("ja")])
    let catalog = try ExactJSON(data: InkuCore.resolveMacroCatalog(catalogRequest.data))
    guard var lock = catalog["locks"].array?.first, let digest = lock["digest"].string else { throw CheckFailure.message("Missing fixture lock") }
    lock["digest"] = .string(digest.hasPrefix("sha256:") ? digest : "sha256:" + digest)
    lock["aliases"] = .array([.string("Nature.若葉")])
    let source = "Nature.若葉。"
    let document: ExactJSON = .object(["source": .string(source), "language": .string("ja"), "macro_locks": .array([lock])])
    let config: ExactJSON = .object(["definitions": .array([definition])])
    let inner: ExactJSON = .object(["document": document, "config": config])
    let outer: ExactJSON = .object(["schema": .string("inku.swift-pipeline-execution.v1"), "snapshot": .string(inner.data.base64EncodedString())])
    let ack: ExactJSON = .object(["work_id": .string("fixture_1"), "performance": .object(["configuration": config, "document": document])])
    let payload: ExactJSON = .object(["work": .object(["ddl": .string(source), "score": .string("{}"), "svg": .string("<svg/>")])])
    func literal(_ text: String) -> String { "'" + text.replacingOccurrences(of: "'", with: "''") + "'" }
    let resources = root.appendingPathComponent("apple/Packages/InkuPersistence/Sources/InkuPersistence/Resources")
    var sql = ""
    for name in ["schema-v1", "migration-v2", "migration-v3", "migration-v4", "migration-v5"] {
        sql += try String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8) + "\n"
    }
    sql += "INSERT INTO history (id,at,input,ddl,score,svg,instruction_lang_resolved) VALUES ('fixture_1',1,'fixture',\(literal(source)),'{}','<svg/>','ja');\n"
    sql += "INSERT INTO execution_snapshots (id,revision,snapshot) VALUES ('fixture',0,CAST(\(literal(outer.text)) AS BLOB));\n"
    sql += "INSERT INTO effect_acknowledgements (execution_id,effect_id,revision,snapshot,acknowledgement,save_payload) VALUES ('fixture','save-render:1',0,CAST(\(literal(outer.text)) AS BLOB),CAST(\(literal(ack.text)) AS BLOB),CAST(\(literal(payload.text)) AS BLOB));"
    let sqlite = Process(); sqlite.executableURL = URL(fileURLWithPath: "/usr/bin/sqlite3"); sqlite.arguments = [file.path, sql]
    try sqlite.run(); sqlite.waitUntilExit()
    guard sqlite.terminationStatus == 0 else { throw CheckFailure.message("Could not create isolated v5 fixture") }
    let database = try InkuDatabase(url: file)
    guard let work = try await database.work(id: "fixture_1"), work.ddl == "｛若葉｝。", work.score == "{}", work.svg == "<svg/>",
          let saved = try await database.acknowledgement(executionID: "fixture", effectID: "save-render:1"),
          try ExactJSON(data: saved)["performance"]["document"]["source"].string == "｛若葉｝。" else {
        throw CheckFailure.message("v6 migration failed to update the saved DDL copies")
    }
    let files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
    guard files.contains(where: { $0.lastPathComponent.hasPrefix(".inku-before-v6-") }),
          files.contains(where: { $0.lastPathComponent.hasPrefix(".inku-plugin-names-v6-") }) else {
        throw CheckFailure.message("v6 snapshot or report is missing")
    }
    print("Plugin name v6 migration passed on an isolated DB with real core; no provider calls.")
}
