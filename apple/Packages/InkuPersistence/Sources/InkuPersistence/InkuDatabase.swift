import Foundation
import GRDB

public enum PersistenceError: Error, Sendable, Equatable {
    case invalidFileURL
    case invalidHostIdentifier
    case unknownSchema
    case corruptDatabase
    case invalidRecord(String)
    case revisionConflict
    case effectConflict
    case backupAlreadyExists
}

/// One actor owns one SQLite writer. No database handle escapes this boundary.
public actor InkuDatabase {
    public nonisolated let url: URL
    private let queue: DatabaseQueue

    public init(url: URL) throws {
        guard url.isFileURL else { throw PersistenceError.invalidFileURL }
        self.url = url.standardizedFileURL
        let exists = FileManager.default.fileExists(atPath: self.url.path)
        if exists {
            // Inspect existing bytes read-only before enabling any writer configuration.
            let inspection = try Self.readOnlyQueue(at: self.url)
            try inspection.read { try Self.validateSchema($0) }
            try inspection.close()
        } else {
            try FileManager.default.createDirectory(
                at: self.url.deletingLastPathComponent(), withIntermediateDirectories: true)
        }
        var configuration = Configuration()
        configuration.foreignKeysEnabled = true
        configuration.busyMode = .timeout(5)
        self.queue = try DatabaseQueue(path: self.url.path, configuration: configuration)
        if !exists {
            try queue.write { db in try db.execute(sql: Self.schemaSQL()) }
        }
        try queue.read { try Self.validateSchema($0) }
    }

    public nonisolated static func applicationSupportURL(hostIdentifier: String) throws -> URL {
        guard !hostIdentifier.isEmpty,
              hostIdentifier != ".", hostIdentifier != "..",
              hostIdentifier.unicodeScalars.allSatisfy({
                  CharacterSet.alphanumerics.contains($0) || $0 == "." || $0 == "-" || $0 == "_"
              }) else { throw PersistenceError.invalidHostIdentifier }
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory, in: .userDomainMask,
            appropriateFor: nil, create: true)
        return base.appendingPathComponent(hostIdentifier, isDirectory: true)
            .appendingPathComponent("inku.sqlite", isDirectory: false)
    }

    /// Inserts history and its lineage together; a collision always throws.
    public func save(_ work: SavedWork, node: LineageNode, edge: LineageEdge? = nil) throws {
        try queue.write { db in try Self.insert(work, node: node, edge: edge, in: db) }
    }

    public func work(id: String) throws -> SavedWork? {
        try queue.read { try SavedWork.fetchOne($0, key: id) }
    }

    public func list(limit: Int = 100, offset: Int = 0) throws -> [SavedWork] {
        guard (1...1000).contains(limit), offset >= 0 else {
            throw PersistenceError.invalidRecord("invalid page")
        }
        return try queue.read {
            try SavedWork.fetchAll($0, sql: "SELECT * FROM history ORDER BY at DESC, id ASC LIMIT ? OFFSET ?",
                                   arguments: [limit, offset])
        }
    }

    public func node(id: String) throws -> LineageNode? {
        try queue.read { try LineageNode.fetchOne($0, key: id) }
    }

    public func edge(childNodeID: String) throws -> LineageEdge? {
        try queue.read {
            try LineageEdge.fetchOne($0, sql: "SELECT * FROM lineage_edges WHERE child_node_id = ?",
                                     arguments: [childNodeID])
        }
    }

    public func loadExecution(id: String) throws -> ExecutionSnapshot? {
        try queue.read { try Self.execution(id: id, in: $0) }
    }

    /// nil expects absence and creates revision 0. Existing revisions advance by one.
    public func compareAndSwapExecution(
        id: String, expectedRevision: Int64?, snapshot: Data
    ) throws -> ExecutionSnapshot {
        try queue.write { db in
            try Self.compareAndSwap(id: id, expectedRevision: expectedRevision, snapshot: snapshot, in: db)
        }
    }

    /// ACK, snapshot revision and optional save effect become durable in one commit.
    /// An identical retry returns the original ACK and snapshot, even after later revisions.
    public func commitEffect(
        id: String, expectedRevision: Int64, effectID: String, snapshot: Data,
        acknowledgement: Data, work: SavedWork? = nil,
        node: LineageNode? = nil, edge: LineageEdge? = nil
    ) throws -> EffectCommitResult {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let savePayload = try encoder.encode(EffectSave(work: work, node: node, edge: edge))
        return try queue.write { db in
            if let prior = try Row.fetchOne(db, sql: """
                SELECT revision, snapshot, acknowledgement, save_payload FROM effect_acknowledgements
                WHERE execution_id = ? AND effect_id = ?
                """, arguments: [id, effectID]) {
                let priorSnapshot: Data = prior["snapshot"]
                let priorACK: Data = prior["acknowledgement"]
                let priorSavePayload: Data = prior["save_payload"]
                let priorRevision: Int64 = prior["revision"]
                guard priorSnapshot == snapshot, priorACK == acknowledgement, priorSavePayload == savePayload,
                      expectedRevision >= 0, expectedRevision < Int64.max,
                      priorRevision == expectedRevision + 1 else {
                    throw PersistenceError.effectConflict
                }
                return EffectCommitResult(
                    execution: ExecutionSnapshot(id: id, revision: priorRevision, snapshot: priorSnapshot),
                    acknowledgement: priorACK, wasAlreadyCommitted: true)
            }
            guard !effectID.isEmpty else { throw PersistenceError.invalidRecord("empty effect ID") }
            let updated = try Self.compareAndSwap(
                id: id, expectedRevision: expectedRevision, snapshot: snapshot, in: db)
            if let work, let node {
                try Self.insert(work, node: node, edge: edge, in: db)
            } else if work != nil || node != nil || edge != nil {
                throw PersistenceError.invalidRecord("save effect requires history and lineage node")
            }
            try db.execute(sql: """
                INSERT INTO effect_acknowledgements
                (execution_id, effect_id, revision, snapshot, acknowledgement, save_payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """, arguments: [id, effectID, updated.revision, snapshot, acknowledgement, savePayload])
            return EffectCommitResult(
                execution: updated, acknowledgement: acknowledgement, wasAlreadyCommitted: false)
        }
    }

    private struct EffectSave: Codable {
        let work: SavedWork?
        let node: LineageNode?
        let edge: LineageEdge?
    }

    public func acknowledgement(executionID: String, effectID: String) throws -> Data? {
        try queue.read {
            try Data.fetchOne($0, sql: """
                SELECT acknowledgement FROM effect_acknowledgements
                WHERE execution_id = ? AND effect_id = ?
                """, arguments: [executionID, effectID])
        }
    }

    /// SQLite Backup API includes committed journal/WAL contents. No raw file copy is used.
    /// Actor ordering includes every save that finished before this call starts.
    public func backup(to destination: URL) throws {
        guard destination.isFileURL, destination.standardizedFileURL != url else {
            throw PersistenceError.invalidFileURL
        }
        guard !FileManager.default.fileExists(atPath: destination.path) else {
            throw PersistenceError.backupAlreadyExists
        }
        try FileManager.default.createDirectory(
            at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        let stagingURL = destination.deletingLastPathComponent()
            .appendingPathComponent(".inku-backup-\(UUID().uuidString).sqlite")
        let backup = try DatabaseQueue(path: stagingURL.path)
        defer { try? FileManager.default.removeItem(at: stagingURL) }
        do {
            try queue.backup(to: backup)
            // Publish one standalone backup file, without temporary WAL sidecars.
            try backup.writeWithoutTransaction { try $0.execute(sql: "PRAGMA journal_mode = DELETE") }
            try backup.read { try Self.validateRestore($0) }
            try backup.close()
            // Publish a completed standalone snapshot without overwriting an existing file.
            try FileManager.default.moveItem(at: stagingURL, to: destination)
        } catch {
            try? backup.close()
            throw error
        }
    }

    /// Call after stopping the host pipeline. The actor serializes all writes during restore.
    /// Validate an isolated SQLite Backup API snapshot before touching the active database.
    /// The original backup remains read-only, and SQLite commits the replacement atomically.
    public func restore(from source: URL) throws {
        guard source.isFileURL, source.standardizedFileURL != url else {
            throw PersistenceError.invalidFileURL
        }
        let original = try Self.readOnlyQueue(at: source)
        defer { try? original.close() }
        try original.read { try Self.validateSchema($0) }
        let temporary = FileManager.default.temporaryDirectory
            .appendingPathComponent("inku-restore-\(UUID().uuidString).sqlite")
        let isolated = try DatabaseQueue(path: temporary.path)
        defer {
            try? isolated.close()
            try? FileManager.default.removeItem(at: temporary)
        }
        try original.backup(to: isolated)
        try isolated.read { try Self.validateRestore($0) }
        try isolated.backup(to: queue)
    }

    private static func insert(
        _ work: SavedWork, node: LineageNode, edge: LineageEdge?, in db: Database
    ) throws {
        try validate(work)
        guard work.lineageNodeID == node.id, node.historyID == work.id,
              edge == nil || edge?.childNodeID == node.id else {
            throw PersistenceError.invalidRecord("history and lineage identities disagree")
        }
        // INSERT, never UPSERT/REPLACE, preserves the history collision contract.
        try work.insert(db)
        try node.insert(db)
        if let edge {
            try validateJSONObject(edge.metadataJSON)
            try edge.insert(db)
        }
    }

    private static func validate(_ work: SavedWork) throws {
        guard !work.id.isEmpty else { throw PersistenceError.invalidRecord("empty history ID") }
        for seed in [work.renderSeed, work.compositionSeed, work.variationSeed].compactMap({ $0 }) {
            guard !seed.isEmpty, seed.utf8.allSatisfy({ (48...57).contains($0) }) else {
                throw PersistenceError.invalidRecord("seed must be unsigned decimal text")
            }
        }
        if let ratio = work.renderCanvasAspectRatio, !ratio.isFinite {
            throw PersistenceError.invalidRecord("canvas aspect ratio must be finite")
        }
        for document in [work.score, work.renderColorProfile, work.renderColorMap, work.renderLimits].compactMap({ $0 }) {
            try validateJSONObject(document)
        }
    }

    private static func validateJSONObject(_ document: String) throws {
        guard let bytes = document.data(using: .utf8),
              (try? JSONSerialization.jsonObject(with: bytes)) is [String: Any] else {
            throw PersistenceError.invalidRecord("stored JSON must be an object")
        }
    }

    private static func execution(id: String, in db: Database) throws -> ExecutionSnapshot? {
        guard let row = try Row.fetchOne(db, sql: "SELECT * FROM execution_snapshots WHERE id = ?",
                                        arguments: [id]) else { return nil }
        return ExecutionSnapshot(id: row["id"], revision: row["revision"], snapshot: row["snapshot"])
    }

    private static func compareAndSwap(
        id: String, expectedRevision: Int64?, snapshot: Data, in db: Database
    ) throws -> ExecutionSnapshot {
        guard !id.isEmpty else { throw PersistenceError.invalidRecord("empty execution ID") }
        let next: Int64
        if let expectedRevision {
            guard expectedRevision >= 0, expectedRevision < Int64.max else {
                throw PersistenceError.revisionConflict
            }
            next = expectedRevision + 1
            try db.execute(sql: """
                UPDATE execution_snapshots SET revision = ?, snapshot = ? WHERE id = ? AND revision = ?
                """, arguments: [next, snapshot, id, expectedRevision])
            guard db.changesCount == 1 else { throw PersistenceError.revisionConflict }
        } else {
            guard try execution(id: id, in: db) == nil else { throw PersistenceError.revisionConflict }
            next = 0
            try db.execute(sql: "INSERT INTO execution_snapshots (id, revision, snapshot) VALUES (?, ?, ?)",
                           arguments: [id, next, snapshot])
        }
        return ExecutionSnapshot(id: id, revision: next, snapshot: snapshot)
    }

    private static func readOnlyQueue(at url: URL) throws -> DatabaseQueue {
        var configuration = Configuration()
        configuration.readonly = true
        configuration.foreignKeysEnabled = true
        return try DatabaseQueue(path: url.path, configuration: configuration)
    }

    private static func schemaSQL() throws -> String {
        guard let resource = Bundle.module.url(forResource: "schema-v1", withExtension: "sql") else {
            throw PersistenceError.unknownSchema
        }
        return try String(contentsOf: resource, encoding: .utf8)
    }

    private struct SchemaObject: Equatable {
        let type: String
        let name: String
        let table: String
        let sql: String
    }

    private static func schemaObjects(in db: Database) throws -> [SchemaObject] {
        try Row.fetchAll(db, sql: """
            SELECT type, name, tbl_name, sql FROM sqlite_master
            WHERE substr(name, 1, 7) <> 'sqlite_' ORDER BY type, name, tbl_name
            """).map {
                let sql: String = $0["sql"]
                return SchemaObject(type: $0["type"], name: $0["name"], table: $0["tbl_name"],
                                    sql: sql.split(whereSeparator: { $0.isWhitespace }).joined(separator: " "))
            }
    }

    private static func validateSchema(_ db: Database) throws {
        let expected = try DatabaseQueue()
        try expected.write { try $0.execute(sql: schemaSQL()) }
        let expectedObjects = try expected.read { try schemaObjects(in: $0) }
        guard try Int.fetchOne(db, sql: "PRAGMA user_version") == 1,
              try schemaObjects(in: db) == expectedObjects,
              try String.fetchAll(db, sql: "SELECT identifier FROM schema_migrations ORDER BY identifier")
                == ["swift-v1-contract-v2"] else {
            throw PersistenceError.unknownSchema
        }
    }

    private static func validateRestore(_ db: Database) throws {
        try validateSchema(db)
        guard try String.fetchAll(db, sql: "PRAGMA integrity_check") == ["ok"],
              try Row.fetchAll(db, sql: "PRAGMA foreign_key_check").isEmpty else {
            throw PersistenceError.corruptDatabase
        }
        for work in try SavedWork.fetchAll(db) { try validate(work) }
        for edge in try LineageEdge.fetchAll(db) { try validateJSONObject(edge.metadataJSON) }
        let inconsistent = try Int.fetchOne(db, sql: """
            SELECT count(*) FROM history AS h LEFT JOIN lineage_nodes AS n ON n.id = h.lineage_node_id
            WHERE h.lineage_node_id IS NOT NULL AND (n.id IS NULL OR n.history_id IS NULL OR n.history_id <> h.id)
            """)
        guard inconsistent == 0 else { throw PersistenceError.corruptDatabase }
    }
}
