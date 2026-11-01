import Foundation
import GRDB
import InkuCore

/// A saved work and its acknowledgement are one unit. Execution logs remain historical.
enum SaijikiV3Migration {
    static func run(_ db: Database) throws -> Data {
        let started = Date()
        var records: [String: [(String, String, Data, Data)]] = [:]
        for row in try Row.fetchAll(db, sql: "SELECT execution_id, effect_id, acknowledgement, save_payload FROM effect_acknowledgements") {
            let ack: Data = row["acknowledgement"], payload: Data = row["save_payload"]
            if let id = try value(db, ack, "$.work_id") {
                records[id, default: []].append((row["execution_id"], row["effect_id"], ack, payload))
            }
        }
        var changed = 0, already = 0, ddlChanged = 0
        var refusals: [[String: String]] = []
        var replacements: [String: Int] = [:]
        var unassociatedTools: [[String: Any]] = [], unassociatedSweeps: [[String: Any]] = []
        var unadjusted: [[String: Any]] = []
        let works = try Row.fetchAll(db, sql: "SELECT id, ddl FROM history")
        for row in works {
            let id: String = row["id"]
            func refuse(_ reason: String) { refusals.append(["id": id, "reason": reason]) }
            guard let source: String = row["ddl"], let matches = records[id], matches.count == 1 else {
                refuse("missing_or_ambiguous_context"); continue
            }
            let (execution, effect, ack, payload) = matches[0]
            guard try value(db, ack, "$.performance.document.source") == source,
                  try value(db, payload, "$.work.ddl") == source else {
                refuse("inconsistent_source"); continue
            }
            let edition = try value(db, ack, "$.performance.document.saijiki")
            if edition == "inku.saijiki.v3" { already += 1; continue }
            guard edition == "inku.saijiki.v2" else { refuse("other_edition"); continue }
            guard let document = try value(db, ack, "$.performance.document"),
                  let definitions = try value(db, ack, "$.performance.configuration.definitions") else {
                refuse("missing_context"); continue
            }
            let answer = InkuCore.migrateSaijikiV2(Data("{\"document\":\(document),\"definitions\":\(definitions)}".utf8))
            guard let json = try? JSONSerialization.jsonObject(with: answer) as? [String: Any] else {
                refuse("invalid_core_response"); continue
            }
            if let error = json["error"] as? String { refuse(error); continue }
            guard let doc = json["document"] as? [String: Any], let entries = json["definitions"] as? [[String: Any]] else {
                refuse("invalid_core_response"); continue
            }
            if let error = doc["error"] as? [String: Any] { refuse(error["code"] as? String ?? "document_refused"); continue }
            if let error = entries.compactMap({ $0["error"] as? [String: Any] }).first {
                refuse(error["code"] as? String ?? "definition_refused"); continue
            }
            guard let output = doc["document"] as? [String: Any], let newSource = output["source"] as? String,
                  let edits = doc["edits"] as? [[String: Any]], let tools = doc["unassociated_tools"] as? [[String: Any]],
                  let sweeps = doc["unassociated_sweeps"] as? [[String: Any]],
                  let originalCount = try Int.fetchOne(db, sql: "SELECT json_array_length(?)", arguments: [definitions]),
                  entries.count == originalCount,
                  entries.allSatisfy({ $0["definition"] is [String: Any] }),
                  let newDocument = try value(db, answer, "$.document.document"),
                  let newDefinitions = try String.fetchOne(db, sql: "SELECT json_group_array(json_extract(value, '$.definition')) FROM json_each(CAST(? AS TEXT), '$.definitions')", arguments: [answer]) else {
                refuse("invalid_core_response"); continue
            }
            try db.execute(sql: "UPDATE history SET ddl = ? WHERE id = ?", arguments: [newSource, id])
            try db.execute(sql: """
                UPDATE effect_acknowledgements
                SET acknowledgement = CAST(json_set(CAST(acknowledgement AS TEXT),
                    '$.performance.document', json(?), '$.performance.configuration.definitions', json(?)) AS BLOB),
                    save_payload = CAST(json_set(CAST(save_payload AS TEXT), '$.work.ddl', ?) AS BLOB)
                WHERE execution_id = ? AND effect_id = ?
                """, arguments: [newDocument, newDefinitions, newSource, execution, effect])
            changed += 1
            if source != newSource { ddlChanged += 1 }
            for edit in edits {
                if let old = edit["original"] as? String, let new = edit["replacement"] as? String {
                    replacements[old + " → " + new, default: 0] += 1
                }
            }
            if !tools.isEmpty { unassociatedTools.append(["id": id, "spans": tools]) }
            if !sweeps.isEmpty { unassociatedSweeps.append(["id": id, "spans": sweeps]) }
            for entry in entries {
                if let paths = entry["unadjusted_thinness"] as? [String], !paths.isEmpty {
                    unadjusted.append(["id": id, "qualified_name": entry["qualified_name"] ?? "", "version": entry["version"] ?? "", "paths": paths])
                }
            }
        }
        let report: [String: Any] = ["schema": "inku.saijiki-v3-v7-report.v1", "works": works.count,
            "changed": changed, "ddl_changed": ddlChanged, "already": already, "refused": refusals,
            "replacements": replacements, "unassociated_tools": unassociatedTools,
            "unassociated_sweeps": unassociatedSweeps, "unadjusted_thinness": unadjusted,
            "seconds": Date().timeIntervalSince(started)]
        return try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
    }

    private static func value(_ db: Database, _ data: Data, _ path: String) throws -> String? {
        guard try Int.fetchOne(db, sql: "SELECT json_valid(CAST(? AS TEXT))", arguments: [data]) == 1 else { return nil }
        return try String.fetchOne(db, sql: "SELECT json_extract(CAST(? AS TEXT), ?)", arguments: [data, path])
    }
}
