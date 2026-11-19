import Foundation
import CoreFoundation
import GRDB

public enum WorkPackError: Error, LocalizedError {
    case invalid(String)
    case newerVersion
    case tooLarge
    public var errorDescription: String? {
        switch self {
        case .newerVersion: return "新しい inku で書き出したファイルです。アプリを更新してください。"
        case .tooLarge: return "作品パックが大きすぎます。"
        case .invalid(let reason): return "作品パックが壊れています: \(reason)"
        }
    }
}

/// Validates one bounded line at a time and holds payloads in a temporary SQLite database.
public final class WorkPackReader: @unchecked Sendable {
    static let kinds = ["history", "lineage_node", "lineage_edge", "annotation", "colophon"]
    let queue: DatabaseQueue
    private let temporaryURL: URL
    public private(set) var identity = WorkPackIdentity(works: [], nodes: [], edges: [])
    public private(set) var counts: [String: Int] = [:]

    public init(url: URL) throws {
        temporaryURL = FileManager.default.temporaryDirectory.appendingPathComponent("inku-workpack-\(UUID().uuidString).sqlite")
        queue = try DatabaseQueue(path: temporaryURL.path)
        do {
            try queue.write { db in
                try db.execute(sql: "CREATE TABLE records (kind TEXT NOT NULL, key TEXT NOT NULL, payload BLOB NOT NULL, UNIQUE(kind,key))")
            }
            try read(url)
        } catch {
            try? queue.close(); try? FileManager.default.removeItem(at: temporaryURL)
            throw error
        }
    }
    deinit { try? queue.close(); try? FileManager.default.removeItem(at: temporaryURL) }

    private func read(_ url: URL) throws {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var buffer = Data(), total = 0, lineNumber = 0, lastKind = -1
        var expected: [String: Int] = [:]
        func accept(_ line: Data) throws {
            lineNumber += 1
            guard !line.isEmpty, String(data: line, encoding: .utf8) != nil,
                  let value = try JSONSerialization.jsonObject(with: line) as? [String: Any] else {
                throw WorkPackError.invalid("line \(lineNumber)")
            }
            if lineNumber == 1 {
                guard value["format"] as? String == "inku.workpack", let version = Self.integer(value["format_version"]), version >= 1 else { throw WorkPackError.invalid("header") }
                guard version <= 1 else { throw WorkPackError.newerVersion }
                guard Self.integer(value["persistence_contract_version"]) != nil,
                      Self.integer(value["exported_at"]) != nil, let producer = value["producer"] as? [String: Any],
                      producer["host"] is String, producer["app_version"] is String,
                      Self.integer(producer["build"]) != nil, Self.integer(producer["schema_version"]) != nil,
                      let rawCounts = value["counts"] as? [String: Any] else { throw WorkPackError.invalid("header") }
                for kind in Self.kinds {
                    guard let n = Self.integer(rawCounts[kind]), n >= 0 else { throw WorkPackError.invalid("counts") }
                    expected[kind] = n
                }
                return
            }
            guard let kind = value["kind"] as? String else { throw WorkPackError.invalid("kind") }
            guard let rank = Self.kinds.firstIndex(of: kind) else { return }
            guard rank >= lastKind else { throw WorkPackError.invalid("record order") }
            lastKind = rank
            try Self.validate(value, kind: kind)
            let key: String
            switch kind {
            case "history":
                key = value["id"] as! String
                identity.works.append(.init(id: key, nodeID: value["lineage_node_id"] as? String))
            case "lineage_node":
                key = value["id"] as! String
                identity.nodes.append(.init(id: key, historyID: value["history_id"] as? String))
            case "lineage_edge":
                key = value["id"] as! String
                identity.edges.append(.init(id: key, parent: value["parent_node_id"] as! String, child: value["child_node_id"] as! String))
            case "annotation": key = value["history_id"] as! String
            default: key = value["id"] as! String
            }
            do { try queue.write { db in try db.execute(sql: "INSERT INTO records VALUES (?, ?, ?)", arguments: [kind, key, line]) } }
            catch { throw WorkPackError.invalid("duplicate \(kind) id") }
            counts[kind, default: 0] += 1
        }
        while let chunk = try handle.read(upToCount: 65536), !chunk.isEmpty {
            total += chunk.count
            guard total <= 256 * 1024 * 1024 else { throw WorkPackError.tooLarge }
            buffer.append(chunk)
            while let index = buffer.firstIndex(of: 10) {
                guard buffer.distance(from: buffer.startIndex, to: index) <= 64 * 1024 * 1024 else { throw WorkPackError.tooLarge }
                let line = Data(buffer[..<index]); buffer.removeSubrange(...index)
                try accept(line)
            }
            guard buffer.count <= 64 * 1024 * 1024 else { throw WorkPackError.tooLarge }
        }
        guard buffer.isEmpty, lineNumber > 0 else { throw WorkPackError.invalid("truncated line") }
        for kind in Self.kinds where counts[kind, default: 0] != expected[kind] { throw WorkPackError.invalid("counts") }
        _ = try WorkPackPlanner.decide(identity, existingWorks: [], existingRoots: [:], existingParents: [:])
    }

    static func integer(_ value: Any?) -> Int? {
        guard let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID(),
              n.doubleValue.isFinite, n.doubleValue.rounded() == n.doubleValue,
              n.doubleValue >= Double(Int.min), n.doubleValue < Double(Int.max) else { return nil }
        return n.intValue
    }
    private static func validate(_ value: [String: Any], kind: String) throws {
        if let fields = WorkPackFields.records[kind] {
            for field in fields {
                guard let object = value[field.name] else {
                    if field.optional { continue }
                    throw WorkPackError.invalid("missing \(field.name)")
                }
                if object is NSNull {
                    guard field.nullable else { throw WorkPackError.invalid("null \(field.name)") }
                    continue
                }
                let valid: Bool
                switch field.encoding {
                case "text", "utf8_text", "utf8_svg", "rh3_or_legacy_text", "dh1_or_legacy_text": valid = object is String
                case "null_or_legacy_expanded": valid = (object as? String) == "legacy_expanded"
                case "canonical_json_object":
                    if let text = object as? String, let data = text.data(using: .utf8),
                       let json = try? JSONSerialization.jsonObject(with: data) { valid = json is [String: Any] }
                    else { valid = false }
                case "unsigned_decimal_text":
                    if let text = object as? String { valid = !text.isEmpty && text.utf8.allSatisfy { (48...57).contains($0) } }
                    else { valid = false }
                case "boolean_0_1": valid = integer(object).map { $0 == 0 || $0 == 1 } ?? false
                case "unix_epoch_milliseconds", "integer_milliseconds": valid = integer(object) != nil
                case "finite_number": valid = (object as? NSNumber).map { CFGetTypeID($0) != CFBooleanGetTypeID() && $0.doubleValue.isFinite } ?? false
                default: throw WorkPackError.invalid("unknown encoding \(field.encoding)")
                }
                guard valid else { throw WorkPackError.invalid("type \(field.name)") }
            }
            if kind == "lineage_edge", value["parent_node_id"] as? String == value["child_node_id"] as? String { throw WorkPackError.invalid("self edge") }
            return
        }
        if kind == "annotation" {
            guard let id = value["history_id"] as? String, !id.isEmpty,
                  let note = value["note"], (note is NSNull || (note as? String).map({ $0.count <= 240 }) == true),
                  let mark = integer(value["for_revision"]), (0...1).contains(mark) else { throw WorkPackError.invalid("annotation") }
            return
        }
        for name in ["id", "target_node_id", "branch_snapshot", "model", "language", "body", "warnings_json", "fact_sheet_json"] {
            guard let s = value[name] as? String, !s.isEmpty else { throw WorkPackError.invalid("colophon \(name)") }
        }
        guard integer(value["at"]) != nil, ["ja", "en"].contains(value["language"] as? String ?? "") else { throw WorkPackError.invalid("colophon") }
        guard let branch = (value["branch_snapshot"] as? String)?.data(using: .utf8),
              let ids = try? JSONDecoder().decode([String].self, from: branch),
              ids.last == value["target_node_id"] as? String,
              let warnings = (value["warnings_json"] as? String)?.data(using: .utf8),
              (try? JSONDecoder().decode([String].self, from: warnings)) != nil,
              let facts = (value["fact_sheet_json"] as? String)?.data(using: .utf8),
              (try? JSONSerialization.jsonObject(with: facts)) is [String: Any] else { throw WorkPackError.invalid("colophon JSON") }
        for name in ["generated_body", "adopted_body", "signature"] {
            if let v = value[name], !(v is NSNull), !(v is String) { throw WorkPackError.invalid("colophon \(name)") }
        }
    }
}
