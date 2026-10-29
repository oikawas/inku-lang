import Foundation
import GRDB
import InkuCore

/// The core decides which spellings can change. SQLite changes only the DDL fields;
/// definitions, locks, score and SVG are never decoded and re-encoded by Swift.
enum PluginNamesMigration {
    struct Refusal: Encodable { let kind: String; let id: String; let reason: String }
    struct Report: Encodable {
        let schema = "inku.plugin-name-migration-report.v1"
        var historyRows = 0
        var changed = 0
        var unchanged = 0
        var snapshotsChanged = 0
        var refused: [Refusal] = []
    }

    private enum UnitResult { case value(String), refused(String) }

    private static func jsonValue(_ db: Database, _ data: Data, _ path: String) throws -> String? {
        guard try Int.fetchOne(db, sql: "SELECT json_valid(CAST(? AS TEXT))", arguments: [data]) == 1 else { return nil }
        return try String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), ?)", arguments: [data, path])
    }

    private static func replacing(_ db: Database, _ data: Data, _ path: String, _ value: String) throws -> Data {
        guard let result = try Data.fetchOne(db, sql: "SELECT CAST(json_set(CAST(? AS TEXT), ?, ?) AS BLOB)", arguments: [data, path, value]) else {
            throw PersistenceError.invalidRecord("plugin_migration_json")
        }
        return result
    }

    private static func quote(_ text: String) throws -> String {
        String(decoding: try JSONEncoder().encode(text), as: UTF8.self)
    }

    private static func migrate(source: String, language: String, definitions: String, locks: String) -> UnitResult {
        do {
            guard language == "ja" || language == "en" else { return .refused("missing_language") }
            let request = "{\"definitions\":\(definitions),\"document\":{\"source\":\(try quote(source)),\"language\":\(try quote(language)),\"macro_locks\":\(locks)}}"
            let data = InkuCore.migratePluginNames(Data(request.utf8))
            guard let result = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { return .refused("invalid_core_response") }
            if let error = result["error"] as? String { return .refused(error) }
            if let problems = result["problems"] as? [[String: Any]], !problems.isEmpty {
                return .refused(problems.compactMap { $0["code"] as? String }.joined(separator: ","))
            }
            guard result["schema"] as? String == "inku.plugin-name-migration.v1",
                  let document = result["document"] as? [String: Any], let output = document["source"] as? String else {
                return .refused("invalid_core_response")
            }
            return .value(output)
        } catch { return .refused("invalid_core_response") }
    }

    static func run(_ db: Database) throws -> Report {
        var report = Report()
        var acknowledgements: [String: [(String, String, Data, Data, Data)]] = [:]
        for row in try Row.fetchAll(db, sql: "SELECT execution_id, effect_id, snapshot, acknowledgement, save_payload FROM effect_acknowledgements") {
            let execution: String = row["execution_id"], effect: String = row["effect_id"]
            let snapshot: Data = row["snapshot"], ack: Data = row["acknowledgement"], payload: Data = row["save_payload"]
            if let workID = try jsonValue(db, ack, "$.work_id") {
                acknowledgements[workID, default: []].append((execution, effect, snapshot, ack, payload))
            }
        }
        var refusedExecutions = Set<String>()
        var snapshotUpdates: [(String, Data)] = []
        for row in try Row.fetchAll(db, sql: "SELECT id, snapshot FROM execution_snapshots") {
            let id: String = row["id"], outer: Data = row["snapshot"]
            guard let encoded = try jsonValue(db, outer, "$.snapshot"), let inner = Data(base64Encoded: encoded),
                  try Int.fetchOne(db, sql: "SELECT json_valid(CAST(? AS TEXT))", arguments: [inner]) == 1 else {
                refusedExecutions.insert(id)
                report.refused.append(Refusal(kind: "execution", id: id, reason: "invalid_snapshot")); continue
            }
            guard let source = try jsonValue(db, inner, "$.document.source"), !source.isEmpty else { continue }
            guard let language = try jsonValue(db, inner, "$.document.language"),
                  let definitions = try jsonValue(db, inner, "$.config.definitions"),
                  let locks = try jsonValue(db, inner, "$.document.macro_locks") else {
                refusedExecutions.insert(id); report.refused.append(Refusal(kind: "execution", id: id, reason: "missing_context")); continue
            }
            switch migrate(source: source, language: language, definitions: definitions, locks: locks) {
            case .refused(let reason): refusedExecutions.insert(id); report.refused.append(Refusal(kind: "execution", id: id, reason: reason))
            case .value(let migrated):
                guard migrated != source else { continue }
                let newInner = try replacing(db, inner, "$.document.source", migrated)
                let newOuter = try replacing(db, outer, "$.snapshot", newInner.base64EncodedString())
                snapshotUpdates.append((id, newOuter))
            }
        }
        for row in try Row.fetchAll(db, sql: "SELECT id, ddl, instruction_lang_resolved FROM history") {
            let id: String = row["id"]
            let source: String? = row["ddl"], language: String? = row["instruction_lang_resolved"]
            report.historyRows += 1
            guard let source, !source.isEmpty else { report.unchanged += 1; continue }
            guard let records = acknowledgements[id], records.count == 1 else {
                if let separator = id.lastIndex(of: "_") { refusedExecutions.insert(String(id[..<separator])) }
                for record in acknowledgements[id] ?? [] { refusedExecutions.insert(record.0) }
                report.unchanged += 1; report.refused.append(Refusal(kind: "history", id: id, reason: "missing_or_ambiguous_context")); continue
            }
            let (execution, effect, savedSnapshot, ack, payload) = records[0]
            guard !refusedExecutions.contains(execution) else {
                report.unchanged += 1; report.refused.append(Refusal(kind: "history", id: id, reason: "execution_refused")); continue
            }
            guard let language, let definitions = try jsonValue(db, ack, "$.performance.configuration.definitions"),
                  let locks = try jsonValue(db, ack, "$.performance.document.macro_locks"),
                  try jsonValue(db, ack, "$.performance.document.source") == source else {
                refusedExecutions.insert(execution); report.unchanged += 1
                report.refused.append(Refusal(kind: "history", id: id, reason: "missing_or_inconsistent_context")); continue
            }
            let payloadSource = try jsonValue(db, payload, "$.work.ddl")
            guard payloadSource == source else {
                refusedExecutions.insert(execution); report.unchanged += 1
                report.refused.append(Refusal(kind: "history", id: id, reason: "inconsistent_save_payload")); continue
            }
            switch migrate(source: source, language: language, definitions: definitions, locks: locks) {
            case .refused(let reason):
                refusedExecutions.insert(execution); report.unchanged += 1
                report.refused.append(Refusal(kind: "history", id: id, reason: reason))
            case .value(let migrated):
                guard migrated != source else { report.unchanged += 1; continue }
                guard let encoded = try jsonValue(db, savedSnapshot, "$.snapshot"),
                      let inner = Data(base64Encoded: encoded),
                      try jsonValue(db, inner, "$.document.source") == source,
                      let snapshotLanguage = try jsonValue(db, inner, "$.document.language"),
                      let snapshotDefinitions = try jsonValue(db, inner, "$.config.definitions"),
                      let snapshotLocks = try jsonValue(db, inner, "$.document.macro_locks") else {
                    refusedExecutions.insert(execution); report.unchanged += 1
                    report.refused.append(Refusal(kind: "history", id: id, reason: "inconsistent_effect_snapshot")); continue
                }
                guard case .value(let snapshotSource) = migrate(source: source, language: snapshotLanguage, definitions: snapshotDefinitions, locks: snapshotLocks), snapshotSource == migrated else {
                    refusedExecutions.insert(execution); report.unchanged += 1
                    report.refused.append(Refusal(kind: "history", id: id, reason: "effect_snapshot_refused")); continue
                }
                let newInner = try replacing(db, inner, "$.document.source", migrated)
                let newSnapshot = try replacing(db, savedSnapshot, "$.snapshot", newInner.base64EncodedString())
                let newAck = try replacing(db, ack, "$.performance.document.source", migrated)
                let newPayload = try replacing(db, payload, "$.work.ddl", migrated)
                try db.execute(sql: "UPDATE history SET ddl = ? WHERE id = ?", arguments: [migrated, id])
                try db.execute(sql: "UPDATE effect_acknowledgements SET snapshot = ?, acknowledgement = ?, save_payload = ? WHERE execution_id = ? AND effect_id = ?",
                               arguments: [newSnapshot, newAck, newPayload, execution, effect])
                report.changed += 1
            }
        }
        for (id, snapshot) in snapshotUpdates where !refusedExecutions.contains(id) {
            try db.execute(sql: "UPDATE execution_snapshots SET snapshot = ? WHERE id = ?", arguments: [snapshot, id])
            report.snapshotsChanged += 1
        }
        return report
    }
}
