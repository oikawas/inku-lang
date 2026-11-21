import Foundation
import GRDB

public struct WorkPackPreview: Sendable {
    public let id: String
    public let svg: String
    public let sourceText: String
}

extension WorkPackReader {
    public func previews(limit: Int = 4) throws -> [WorkPackPreview] {
        try queue.read { db in
            let rows = try Row.fetchCursor(db, sql: "SELECT payload FROM records WHERE kind = 'history' ORDER BY rowid LIMIT ?", arguments: [max(0, limit)])
            var previews: [WorkPackPreview] = [], totalBytes = 0
            while let row = try rows.next() {
                let data: Data = row[0]
                // The full record remains staged; do not retain several huge SVGs just for the confirmation sheet.
                guard data.count <= 8 * 1024 * 1024, totalBytes + data.count <= 16 * 1024 * 1024 else { continue }
                guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let id = object["id"] as? String, let svg = object["svg"] as? String,
                      let input = object["input"] as? String else { throw WorkPackError.invalid("preview") }
                totalBytes += data.count
                previews.append(WorkPackPreview(id: id, svg: svg, sourceText: object["source_text"] as? String ?? input))
            }
            return previews
        }
    }
    func forEach(kind: String, keys: [String], _ body: ([String: Any]) throws -> Void) throws {
        try queue.read { db in
            let query = try db.cachedStatement(sql: "SELECT payload FROM records WHERE kind = ? AND key = ?")
            for key in keys {
                guard let data = try Data.fetchOne(query, arguments: [kind, key]),
                      let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                    throw WorkPackError.invalid("record")
                }
                try body(object)
            }
        }
    }
}

// Swift's schema uses the portable names as its column names. The extra history
// columns belong only to this database; core owns validation of the portable fields.
private func workPackColumns(_ table: String, in db: Database) throws -> [String] {
    let columns = try db.columns(in: table).map(\.name)
    guard table == "history" else { return columns }
    let local = ["draw_route", "sketch_requested", "composition_requested", "catalog_mode"]
    return columns.filter { !local.contains($0) }
}

extension InkuDatabase {
    private func packDecision(_ reader: WorkPackReader, db: Database) throws -> WorkPackDecision {
        var workIDs = Set<String>(), nodeIDs = Set<String>(), childIDs = Set<String>()
        for record in reader.records {
            switch record.kind {
            case "history":
                workIDs.insert(record.key)
                if let node = record.identity["node_id"] ?? nil { nodeIDs.insert(node) }
            case "lineage_node":
                nodeIDs.insert(record.key)
            case "lineage_edge":
                if let parent = record.identity["parent"] ?? nil { nodeIDs.insert(parent) }
                if let child = record.identity["child"] ?? nil { nodeIDs.insert(child); childIDs.insert(child) }
            default: break
            }
        }

        func lookup(_ ids: Set<String>, prefix: String, each: (Row) -> Void) throws {
            let ordered = ids.sorted()
            // Bound SQL parameters even on SQLite builds with a low variable limit.
            for start in stride(from: 0, to: ordered.count, by: 500) {
                let batch = ordered[start..<min(ordered.count, start + 500)]
                let marks = Array(repeating: "?", count: batch.count).joined(separator: ",")
                let rows = try Row.fetchCursor(db, sql: prefix + "(\(marks))", arguments: StatementArguments(batch))
                while let row = try rows.next() { each(row) }
            }
        }

        var existing = WorkPackExisting()
        try lookup(workIDs, prefix: "SELECT id FROM history WHERE id IN ") { existing.works.append($0[0]) }
        try lookup(nodeIDs, prefix: "SELECT id,root_node_id FROM lineage_nodes WHERE id IN ") {
            let id: String = $0[0]
            existing.nodeRoots[id] = ($0[1] as String?) ?? id
        }
        try lookup(childIDs, prefix: "SELECT child_node_id,parent_node_id FROM lineage_edges WHERE child_node_id IN ") {
            existing.parents[$0[0] as String] = $0[1] as String
        }
        return try reader.plan(existing: existing)
    }

    public func previewWorkPack(_ reader: WorkPackReader) throws -> WorkPackDecision {
        try queue.read { try packDecision(reader, db: $0) }
    }

    /// All accepted records are inserted in one transaction; any failed constraint rolls it back.
    public func importWorkPack(_ reader: WorkPackReader) throws -> WorkPackDecision {
        try queue.write { db in
            let plan = try packDecision(reader, db: db)
            func insert(_ object: [String: Any], columns: [String], table: String,
                        overrides: [String: DatabaseValue] = [:]) throws {
                let present = columns.filter { object[$0] != nil || overrides[$0] != nil }
                let values: [DatabaseValue] = try present.map { column in
                    if let override = overrides[column] { return override }
                    let item = object[column]
                    if item is NSNull { return .null }
                    if let text = item as? String { return text.databaseValue }
                    if let number = item as? NSNumber {
                        // The canvas aspect ratio has REAL affinity. Other portable numbers are signed integers.
                        return column == "render_canvas_aspect_ratio" ? number.doubleValue.databaseValue : number.int64Value.databaseValue
                    }
                    throw WorkPackError.invalid("unsupported value")
                }
                let names = present.map { "\"" + $0.replacingOccurrences(of: "\"", with: "\"\"") + "\"" }.joined(separator: ",")
                let marks = Array(repeating: "?", count: present.count).joined(separator: ",")
                try db.execute(sql: "INSERT INTO \(table) (\(names)) VALUES (\(marks))", arguments: StatementArguments(values))
            }

            let historyColumns = try workPackColumns("history", in: db)
            let nodeColumns = try workPackColumns("lineage_nodes", in: db)
            let edgeColumns = try workPackColumns("lineage_edges", in: db)
            try reader.forEach(kind: "history", keys: plan.workIDs) {
                try insert($0, columns: historyColumns, table: "history")
            }
            // The reply's node_roots is an object; preserve the file order from the validated identity rows.
            let nodeIDs = reader.records.filter { $0.kind == "lineage_node" && plan.nodeRoots[$0.key] != nil }.map(\.key)
            try reader.forEach(kind: "lineage_node", keys: nodeIDs) {
                try insert($0, columns: nodeColumns, table: "lineage_nodes", overrides: ["root_node_id": .null])
            }
            for id in nodeIDs {
                try db.execute(sql: "UPDATE lineage_nodes SET root_node_id = ? WHERE id = ?", arguments: [plan.nodeRoots[id], id])
            }
            try reader.forEach(kind: "lineage_edge", keys: plan.edgeIDs) {
                try insert($0, columns: edgeColumns, table: "lineage_edges")
            }
            try reader.forEach(kind: "annotation", keys: plan.annotationIDs) { row in
                let id = row["history_id"] as! String
                let note = (row["note"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
                try db.execute(sql: "INSERT INTO library_annotations (history_id,note,for_revision) VALUES (?,?,?)", arguments: [id, note, (row["for_revision"] as! NSNumber).int64Value])
            }
            try reader.forEach(kind: "colophon", keys: plan.colophonIDs) { row in
                let target = row["target_node_id"] as! String
                let model = row["model"] as! String, language = row["language"] as! String
                let at = (row["at"] as! NSNumber).int64Value
                let formatter = DateFormatter(); formatter.dateFormat = "yyyy-MM-dd"
                formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = TimeZone(identifier: "Asia/Tokyo")
                let date = formatter.string(from: Date(timeIntervalSince1970: Double(at) / 1000))
                let signature = row["signature"] as? String ?? (language == "en" ? "Reader: \(model) / \(date)" : "読み手: \(model) / \(date)")
                try db.execute(sql: "INSERT INTO auxiliary_colophons (id,target_node_id,branch_snapshot,model,at,language,generated_body,adopted_body,signature,warnings_json,fact_sheet_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)", arguments: [row["id"] as! String, target, row["branch_snapshot"] as! String, model, at, language, row["generated_body"] as? String ?? row["body"] as! String, row["adopted_body"] as? String, signature, row["warnings_json"] as! String, row["fact_sheet_json"] as! String])
            }
            return plan
        }
    }
}

extension InkuDatabase {
    public func exportWorkPack(ids: [String], to destination: URL, host: String, appVersion: String, build: Int) throws {
        try queue.read { db in
            var works: [String] = [], nodes: [String] = [], edges: [String] = [], annotations: [String] = [], colophons: [String] = []
            var seen = Set<String>()
            for id in ids where seen.insert(id).inserted {
                guard let row = try Row.fetchOne(db, sql: "SELECT id,lineage_node_id FROM history WHERE id = ? AND trashed = 0", arguments: [id]) else { continue }
                works.append(id); if let node: String = row[1] { nodes.append(node) }
            }
            let nodeSet = Set(nodes)
            for node in nodes {
                if let row = try Row.fetchOne(db, sql: "SELECT id,parent_node_id FROM lineage_edges WHERE child_node_id = ?", arguments: [node]) {
                    let id: String = row[0], parent: String = row[1]; if nodeSet.contains(parent) { edges.append(id) }
                }
                colophons += try String.fetchAll(db, sql: "SELECT id FROM auxiliary_colophons WHERE target_node_id = ? ORDER BY at,id", arguments: [node])
            }
            func annotationLine(_ id: String) throws -> Data? {
                guard let row = try Row.fetchOne(db, sql: "SELECT note,for_revision FROM library_annotations WHERE history_id = ?", arguments: [id]) else { return nil }
                let note: String? = row[0]
                return try WorkPackWire.encode(["kind": "annotation", "record": [
                    "history_id": id, "note": note as Any? ?? NSNull(), "for_revision": row[1] as Int
                ]])
            }
            // Count only rows that core will emit; retain their IDs, not their encoded bodies.
            for id in works where try annotationLine(id) != nil { annotations.append(id) }
            let counts = ["history": works.count, "lineage_node": nodes.count, "lineage_edge": edges.count, "annotation": annotations.count, "colophon": colophons.count]
            let header: [String: Any] = ["kind": "header", "exported_at": Int64(Date().timeIntervalSince1970 * 1000), "producer": ["host": host, "app_version": appVersion, "build": build, "schema_version": Self.currentSchemaVersion], "counts": counts]
            guard FileManager.default.createFile(atPath: destination.path, contents: nil) else { throw WorkPackError.invalid("cannot create file") }
            let output = try FileHandle(forWritingTo: destination)
            defer { try? output.close() }
            var written = 0
            func write(_ data: Data) throws {
                written += data.count + 1
                guard written <= 256 * 1024 * 1024 else { throw WorkPackError.tooLarge }
                try output.write(contentsOf: data); try output.write(contentsOf: Data([10]))
            }
            func writeRecord(_ kind: String, _ record: [String: Any]) throws {
                guard let data = try WorkPackWire.encode(["kind": kind, "record": record]) else {
                    throw WorkPackError.invalid("missing export record")
                }
                try write(data)
            }
            func common(_ kind: String, table: String, columns: [String], id: String) throws {
                guard let row = try Row.fetchOne(db, sql: "SELECT * FROM \(table) WHERE id = ?", arguments: [id]) else { throw WorkPackError.invalid("missing export record") }
                var object: [String: Any] = [:]
                for column in columns {
                    let value: DatabaseValue = row[column]
                    switch value.storage {
                    case .null: object[column] = NSNull()
                    case .int64(let n): object[column] = n
                    case .double(let n): object[column] = n
                    case .string(let s): object[column] = s
                    case .blob: throw WorkPackError.invalid("unexpected binary field")
                    }
                }
                try writeRecord(kind, object)
            }
            do {
                guard let headerLine = try WorkPackWire.encode(header) else { throw WorkPackError.invalid("header") }
                try write(headerLine)
                let historyColumns = try workPackColumns("history", in: db)
                let nodeColumns = try workPackColumns("lineage_nodes", in: db)
                let edgeColumns = try workPackColumns("lineage_edges", in: db)
                for id in works { try common("history", table: "history", columns: historyColumns, id: id) }
                for id in nodes { try common("lineage_node", table: "lineage_nodes", columns: nodeColumns, id: id) }
                for id in edges { try common("lineage_edge", table: "lineage_edges", columns: edgeColumns, id: id) }
                for id in annotations {
                    guard let line = try annotationLine(id) else { throw WorkPackError.invalid("missing export record") }
                    try write(line)
                }
                for id in colophons {
                    guard let row = try Row.fetchOne(db, sql: "SELECT * FROM auxiliary_colophons WHERE id = ?", arguments: [id]) else { continue }
                    let generated: String = row["generated_body"], adopted: String? = row["adopted_body"]
                    let object: [String: Any] = ["id": id, "target_node_id": row["target_node_id"] as String, "branch_snapshot": row["branch_snapshot"] as String, "model": row["model"] as String, "at": row["at"] as Int64, "language": row["language"] as String, "body": adopted ?? generated, "generated_body": generated, "adopted_body": adopted as Any? ?? NSNull(), "signature": row["signature"] as String, "warnings_json": row["warnings_json"] as String, "fact_sheet_json": row["fact_sheet_json"] as String]
                    try writeRecord("colophon", object)
                }
            } catch { try? FileManager.default.removeItem(at: destination); throw error }
        }
    }
}
