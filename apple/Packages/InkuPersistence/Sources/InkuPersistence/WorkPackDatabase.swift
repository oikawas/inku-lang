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
    func forEach(kind: String, _ body: ([String: Any]) throws -> Void) throws {
        try queue.read { db in
            let rows = try Row.fetchCursor(db, sql: "SELECT payload FROM records WHERE kind = ? ORDER BY rowid", arguments: [kind])
            while let row = try rows.next() {
                let data: Data = row[0]
                guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw WorkPackError.invalid("record") }
                try body(object)
            }
        }
    }
}

extension InkuDatabase {
    private func packDecision(_ reader: WorkPackReader, db: Database) throws -> WorkPackDecision {
        let works = Set(try String.fetchAll(db, sql: "SELECT id FROM history"))
        var roots: [String: String] = [:], parents: [String: String] = [:]
        for row in try Row.fetchAll(db, sql: "SELECT id, root_node_id FROM lineage_nodes") {
            let id: String = row[0]; roots[id] = (row[1] as String?) ?? id
        }
        for row in try Row.fetchAll(db, sql: "SELECT id, parent_node_id, child_node_id FROM lineage_edges") {
            let parent: String = row[1], child: String = row[2]
            parents[child] = parent
        }
        return try WorkPackPlanner.decide(reader.identity, existingWorks: works, existingRoots: roots,
                                          existingParents: parents)
    }

    public func previewWorkPack(_ reader: WorkPackReader) throws -> WorkPackDecision {
        try queue.read { try packDecision(reader, db: $0) }
    }

    /// All accepted records are inserted in one transaction; any failed constraint rolls it back.
    public func importWorkPack(_ reader: WorkPackReader) throws -> WorkPackDecision {
        try queue.write { db in
            let plan = try packDecision(reader, db: db)
            func insert(_ object: [String: Any], kind: String, table: String, overrides: [String: DatabaseValue] = [:]) throws {
                let fields = WorkPackFields.records[kind]!.filter { object[$0.name] != nil || overrides[$0.name] != nil }
                let columns = fields.map(\.name)
                var values: [DatabaseValue] = []
                for field in fields {
                    if let override = overrides[field.name] { values.append(override); continue }
                    let item = object[field.name]!
                    if item is NSNull { values.append(.null) }
                    else if let string = item as? String { values.append(string.databaseValue) }
                    else if let number = item as? NSNumber {
                        values.append(field.encoding == "finite_number" ? number.doubleValue.databaseValue : number.int64Value.databaseValue)
                    } else { throw WorkPackError.invalid("unsupported value") }
                }
                try db.execute(sql: "INSERT INTO \(table) (\(columns.joined(separator: ","))) VALUES (\(Array(repeating: "?", count: columns.count).joined(separator: ",")))", arguments: StatementArguments(values))
            }
            try reader.forEach(kind: "history") { row in
                guard let id = row["id"] as? String, plan.workIDs.contains(id) else { return }
                try insert(row, kind: "history", table: "history")
            }
            try reader.forEach(kind: "lineage_node") { row in
                guard let id = row["id"] as? String, plan.nodeRoots[id] != nil else { return }
                try insert(row, kind: "lineage_node", table: "lineage_nodes", overrides: ["root_node_id": .null])
            }
            for (id, root) in plan.nodeRoots {
                try db.execute(sql: "UPDATE lineage_nodes SET root_node_id = ? WHERE id = ?", arguments: [root, id])
            }
            try reader.forEach(kind: "lineage_edge") { row in
                guard let id = row["id"] as? String, plan.edgeIDs.contains(id) else { return }
                try insert(row, kind: "lineage_edge", table: "lineage_edges")
            }
            try reader.forEach(kind: "annotation") { row in
                guard let id = row["history_id"] as? String, plan.workIDs.contains(id) else { return }
                let note = (row["note"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
                try db.execute(sql: "INSERT INTO library_annotations (history_id,note,for_revision) VALUES (?,?,?)", arguments: [id, note, WorkPackReader.integer(row["for_revision"])!])
            }
            try reader.forEach(kind: "colophon") { row in
                guard let target = row["target_node_id"] as? String, plan.nodeRoots[target] != nil else { return }
                let model = row["model"] as! String, language = row["language"] as! String
                let at = WorkPackReader.integer(row["at"])!
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
            for id in works {
                if try Bool.fetchOne(db, sql: "SELECT EXISTS(SELECT 1 FROM library_annotations WHERE history_id = ?)", arguments: [id]) == true { annotations.append(id) }
            }
            let counts = ["history": works.count, "lineage_node": nodes.count, "lineage_edge": edges.count, "annotation": annotations.count, "colophon": colophons.count]
            let header: [String: Any] = ["format": "inku.workpack", "format_version": 1, "persistence_contract_version": 2, "exported_at": Int64(Date().timeIntervalSince1970 * 1000), "producer": ["host": host, "app_version": appVersion, "build": build, "schema_version": Self.currentSchemaVersion], "counts": counts]
            guard FileManager.default.createFile(atPath: destination.path, contents: nil) else { throw WorkPackError.invalid("cannot create file") }
            let output = try FileHandle(forWritingTo: destination)
            defer { try? output.close() }
            var written = 0
            func write(_ object: [String: Any]) throws {
                let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .fragmentsAllowed])
                guard data.count <= 64 * 1024 * 1024 else { throw WorkPackError.tooLarge }
                written += data.count + 1
                guard written <= 256 * 1024 * 1024 else { throw WorkPackError.tooLarge }
                try output.write(contentsOf: data); try output.write(contentsOf: Data([10]))
            }
            func common(_ kind: String, table: String, id: String) throws {
                guard let row = try Row.fetchOne(db, sql: "SELECT * FROM \(table) WHERE id = ?", arguments: [id]) else { throw WorkPackError.invalid("missing export record") }
                var object: [String: Any] = ["kind": kind]
                for field in WorkPackFields.records[kind]! {
                    let value: DatabaseValue = row[field.name]
                    switch value.storage {
                    case .null: object[field.name] = NSNull()
                    case .int64(let n): object[field.name] = n
                    case .double(let n): object[field.name] = n
                    case .string(let s): object[field.name] = s
                    case .blob: throw WorkPackError.invalid("unexpected binary field")
                    }
                }
                try write(object)
            }
            do {
                try write(header)
                for id in works { try common("history", table: "history", id: id) }
                for id in nodes { try common("lineage_node", table: "lineage_nodes", id: id) }
                for id in edges { try common("lineage_edge", table: "lineage_edges", id: id) }
                for id in annotations {
                    guard let row = try Row.fetchOne(db, sql: "SELECT note,for_revision FROM library_annotations WHERE history_id = ?", arguments: [id]) else { continue }
                    let note: String? = row[0]; let revision: Int = row[1]
                    try write(["kind": "annotation", "history_id": id, "note": note?.trimmingCharacters(in: .whitespacesAndNewlines) as Any? ?? NSNull(), "for_revision": revision])
                }
                for id in colophons {
                    guard let row = try Row.fetchOne(db, sql: "SELECT * FROM auxiliary_colophons WHERE id = ?", arguments: [id]) else { continue }
                    let generated: String = row["generated_body"], adopted: String? = row["adopted_body"]
                    let object: [String: Any] = ["kind": "colophon", "id": id, "target_node_id": row["target_node_id"] as String, "branch_snapshot": row["branch_snapshot"] as String, "model": row["model"] as String, "at": row["at"] as Int64, "language": row["language"] as String, "body": adopted ?? generated, "generated_body": generated, "adopted_body": adopted as Any? ?? NSNull(), "signature": row["signature"] as String, "warnings_json": row["warnings_json"] as String, "fact_sheet_json": row["fact_sheet_json"] as String]
                    try write(object)
                }
            } catch { try? FileManager.default.removeItem(at: destination); throw error }
        }
    }
}
