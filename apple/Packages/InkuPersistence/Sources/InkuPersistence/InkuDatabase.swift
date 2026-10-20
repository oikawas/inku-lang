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

public enum LibraryAnnotationMark: Sendable {
    case revision
}

/// One actor owns one SQLite writer. No database handle escapes this boundary.
public actor InkuDatabase {
    public nonisolated let url: URL
    let queue: DatabaseQueue

    public init(url: URL) throws {
        guard url.isFileURL else { throw PersistenceError.invalidFileURL }
        self.url = url.standardizedFileURL
        let exists = FileManager.default.fileExists(atPath: self.url.path)
        if exists {
            // Inspect existing bytes read-only before enabling any writer configuration.
            let inspection = try Self.readOnlyQueue(at: self.url)
            try inspection.read { try Self.validateRestore($0) }
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
        } else {
            try queue.write { db in
                if try Int.fetchOne(db, sql: "PRAGMA user_version") == 1 {
                    try Self.validateSchema(db)
                    try db.execute(sql: Self.resourceSQL("migration-v2"))
                }
                if try Int.fetchOne(db, sql: "PRAGMA user_version") == 2 {
                    try Self.validateSchema(db)
                    try db.execute(sql: Self.resourceSQL("migration-v3"))
                }
                if try Int.fetchOne(db, sql: "PRAGMA user_version") == 3 {
                    try Self.validateSchema(db)
                    try db.execute(sql: Self.resourceSQL("migration-v4"))
                }
            }
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

    /// Every stored work, trashed ones included, with the render hash of the SVG it holds (Server
    /// `history_render_hashes`). The thumbnail store compares these without reading any SVG.
    public func thumbnailSources() throws -> [(id: String, renderHash: String?)] {
        try queue.read { db in
            try Row.fetchAll(db, sql: "SELECT id, render_hash FROM history").map { (id: $0["id"], renderHash: $0["render_hash"]) }
        }
    }

    /// The works a juxtaposition may borrow a sentence from (Server `owned_description_sources`): not in the trash, not
    /// kept only in a lineage, with the stored description (labels and all) and the comment. The host leaves out the
    /// labelled (DDL, demo), `test data` and DDL-held works, which this store does not judge.
    public func juxtapositionSources() throws -> [(id: String, text: String, note: String?)] {
        try queue.read { db in
            try Row.fetchAll(db, sql: """
                SELECT h.id, COALESCE(h.source_text, h.input) AS text, a.note FROM history h
                LEFT JOIN library_annotations a ON a.history_id = h.id
                WHERE h.trashed = 0 AND h.history_visibility = 'normal' ORDER BY h.at ASC, h.id ASC
                """).map { (id: $0["id"], text: $0["text"] ?? "", note: $0["note"]) }
        }
    }

    /// The stored SVG of each id, for baking thumbnails in batches (one SVG can be megabytes).
    public func svgs(ids: [String]) throws -> [String: String] {
        guard !ids.isEmpty else { return [:] }
        return try queue.read { db in
            var result: [String: String] = [:]
            for start in stride(from: 0, to: ids.count, by: 500) {
                let chunk = Array(ids[start..<min(ids.count, start + 500)])
                for row in try Row.fetchAll(db, sql: "SELECT id, svg FROM history WHERE id IN (\(chunk.map { _ in "?" }.joined(separator: ",")))",
                                            arguments: StatementArguments(chunk)) {
                    result[row["id"]] = row["svg"]
                }
            }
            return result
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

    /// Root is generation 1; every primary-parent edge adds one, including tombstones.
    /// Missing nodes are omitted, matching the Server history-list projection.
    public func lineageGenerations(nodeIDs: [String]) throws -> [String: Int] {
        try queue.read { db in
            var result: [String: Int] = [:]
            for id in Set(nodeIDs) where try LineageNode.fetchOne(db, key: id) != nil {
                result[id] = try Self.generation(id: id, in: db)
            }
            return result
        }
    }

    /// Count and select the same database predicate in one consistent read.
    public func libraryPage(query: LibraryQuery = LibraryQuery(), limit: Int = 24,
                            offset: Int = 0, rootNodeID: String? = nil, includeSVG: Bool = true) throws -> LibraryPage {
        try Self.validatePage(limit: limit, offset: offset)
        return try queue.read { db in
            var filter = Self.libraryFilter(query)
            if let rootNodeID {
                guard let root = try LineageNode.fetchOne(db, key: rootNodeID),
                      (root.rootNodeID ?? root.id) == rootNodeID else {
                    return LibraryPage(items: [], total: 0)
                }
                filter.sql += " AND coalesce(n.root_node_id, n.id) = ?"
                filter.arguments += [rootNodeID]
            }
            let total = try Int.fetchOne(db, sql: "SELECT count(*) \(Self.libraryJoin) WHERE \(filter.sql)",
                                         arguments: filter.arguments) ?? 0
            let rows = try Row.fetchAll(db, sql: """
                SELECT \(Self.libraryProjection(includeSVG: includeSVG)), a.note AS library_note,
                       coalesce(a.for_revision, 0) AS library_revision
                \(Self.libraryJoin) WHERE \(filter.sql)
                ORDER BY h.at \(query.order == .newest ? "DESC" : "ASC"), h.id ASC LIMIT ? OFFSET ?
                """, arguments: filter.arguments + [limit, offset])
            return LibraryPage(items: try rows.map(Self.libraryItem), total: total)
        }
    }

    /// Zero-based position under the exact library predicate and ordering.
    public func libraryIndex(id: String, query: LibraryQuery = LibraryQuery()) throws -> Int? {
        try queue.read { db in
            let filter = Self.libraryFilter(query)
            return try Int.fetchOne(db, sql: """
                SELECT position FROM (
                    SELECT h.id AS history_id,
                           row_number() OVER (ORDER BY h.at \(query.order == .newest ? "DESC" : "ASC"), h.id ASC) - 1 AS position
                    \(Self.libraryJoin) WHERE \(filter.sql)
                ) WHERE history_id = ?
                """, arguments: filter.arguments + [id])
        }
    }

    public func recordUnreadWords(_ words: [String], context: String, at: Int64) throws {
        let words = Set(words.map { String(String.UnicodeScalarView($0.trimmingCharacters(in: .whitespacesAndNewlines).unicodeScalars.prefix(120))) }
            .filter { !$0.isEmpty }).sorted()
        guard !words.isEmpty else { return }
        let context = String(String.UnicodeScalarView(context.trimmingCharacters(in: .whitespacesAndNewlines).unicodeScalars.prefix(1000)))
        try queue.write { db in
            for word in words {
                try db.execute(sql: """
                    INSERT INTO unread_words (id, word, context, frequency, first_at, last_at) VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT (word, context) DO UPDATE SET frequency = frequency + 1, last_at = excluded.last_at
                    """, arguments: [UUID().uuidString, word, context, at, at])
            }
        }
    }

    public func unreadWords(limit: Int = 500) throws -> [UnreadWord] {
        guard (1...2000).contains(limit) else { throw PersistenceError.invalidRecord("invalid unread word limit") }
        return try queue.read { db in
            let rows = try Row.fetchAll(db, sql: """
                SELECT word, sum(frequency) AS frequency, min(first_at) AS first_at, max(last_at) AS last_at
                FROM unread_words GROUP BY word ORDER BY frequency DESC, last_at DESC, word COLLATE BINARY ASC LIMIT ?
                """, arguments: [limit])
            return try rows.map { row in
                let word: String = row["word"]
                // Match the Server's first three distinct nonempty contexts in insertion order.
                let contexts = try String.fetchAll(db, sql: """
                    SELECT context FROM unread_words WHERE word = ? AND context <> '' ORDER BY rowid ASC LIMIT 3
                    """, arguments: [word])
                return UnreadWord(word: word, frequency: row["frequency"], firstAt: row["first_at"], lastAt: row["last_at"], contexts: contexts)
            }
        }
    }

    /// Group filtering and pagination happen before fetching representative SVGs. As Server
    /// `GET /api/history/lineage-groups`: `includeWorkID` keeps that work's lineage when the minimum would drop it, and
    /// `anchorWorkID` begins the page at that work's lineage (and keeps it). Either applies only to a work that passes
    /// the filter; the anchor wins over the include.
    public func libraryGroups(query: LibraryQuery = LibraryQuery(), limit: Int = 12,
                              offset: Int = 0, minimumItemCount: Int = 1, includeSVG: Bool = true,
                              includeWorkID: String? = nil, anchorWorkID: String? = nil) throws -> LibraryGroupPage {
        try Self.validatePage(limit: limit, offset: offset)
        guard minimumItemCount >= 1 else { throw PersistenceError.invalidRecord("invalid group size") }
        return try queue.read { db in
            let filter = Self.libraryFilter(query)
            // One read, so the anchor's place and the page it begins cannot disagree.
            let anchor = try anchorWorkID.flatMap {
                try Self.groupPosition(of: $0, filter: filter, order: query.order, minimumItemCount: minimumItemCount, in: db)
            }
            let start = anchor?.index ?? offset
            let included = minimumItemCount > 1
                ? try (anchorWorkID ?? includeWorkID).flatMap { try Self.groupRoot(of: $0, filter: filter, in: db) } : nil
            let (grouped, arguments) = Self.groupedLibrary(filter: filter, minimumItemCount: minimumItemCount, includedRoot: included)
            let total = try Int.fetchOne(db, sql: "SELECT count(*) FROM (\(grouped))", arguments: arguments) ?? 0
            let rows = try Row.fetchAll(db, sql: """
                \(grouped) ORDER BY latest_at \(query.order == .newest ? "DESC" : "ASC"), root_id ASC
                LIMIT ? OFFSET ?
                """, arguments: arguments + [limit, start])
            let groups = try rows.map { row -> LibraryGroup in
                let root: String = row["root_id"]
                guard let representative = try Row.fetchOne(db, sql: """
                    SELECT \(Self.libraryProjection(includeSVG: includeSVG)), a.note AS library_note, coalesce(a.for_revision, 0) AS library_revision
                    \(Self.libraryJoin) WHERE \(filter.sql) AND coalesce(n.root_node_id, n.id) = ?
                    ORDER BY h.at DESC, h.id ASC LIMIT 1
                    """, arguments: filter.arguments + [root]) else {
                    throw PersistenceError.corruptDatabase
                }
                return LibraryGroup(rootNodeID: root, representative: try Self.libraryItem(representative),
                                    itemCount: row["item_count"], starredCount: row["starred_count"],
                                    revisionCount: row["revision_count"], latestAt: row["latest_at"])
            }
            return LibraryGroupPage(groups: groups, total: total, offset: start, anchorRootNodeID: anchor?.rootNodeID)
        }
    }

    /// Zero-based place of a work's lineage in the grouped listing under the library predicate and ordering, counting
    /// that lineage even when the minimum would drop it (Server `lineage_group_position`). nil when the filter leaves
    /// the work out or it has no lineage node.
    public func libraryGroupIndex(id: String, query: LibraryQuery = LibraryQuery(),
                                  minimumItemCount: Int = 1) throws -> LibraryGroupPosition? {
        guard minimumItemCount >= 1 else { throw PersistenceError.invalidRecord("invalid group size") }
        return try queue.read { db in
            try Self.groupPosition(of: id, filter: Self.libraryFilter(query), order: query.order,
                                   minimumItemCount: minimumItemCount, in: db)
        }
    }

    private static func groupRoot(of id: String, filter: (sql: String, arguments: StatementArguments),
                                  in db: Database) throws -> String? {
        try String.fetchOne(db, sql: """
            SELECT coalesce(n.root_node_id, n.id) \(libraryJoin) WHERE \(filter.sql) AND n.id IS NOT NULL AND h.id = ?
            """, arguments: filter.arguments + [id])
    }

    private static func groupPosition(of id: String, filter: (sql: String, arguments: StatementArguments),
                                      order: LibraryOrder, minimumItemCount: Int, in db: Database) throws -> LibraryGroupPosition? {
        guard let root = try groupRoot(of: id, filter: filter, in: db) else { return nil }
        let (grouped, arguments) = groupedLibrary(filter: filter, minimumItemCount: minimumItemCount, includedRoot: root)
        let index = try Int.fetchOne(db, sql: """
            SELECT position FROM (
                SELECT root_id, row_number() OVER (ORDER BY latest_at \(order == .newest ? "DESC" : "ASC"), root_id ASC) - 1 AS position
                FROM (\(grouped))
            ) WHERE root_id = ?
            """, arguments: arguments + [root])
        return index.map { LibraryGroupPosition(index: $0, rootNodeID: root) }
    }

    /// The lineages under the library predicate with at least `minimumItemCount` matching works, and `includedRoot`
    /// whatever its count.
    private static func groupedLibrary(filter: (sql: String, arguments: StatementArguments), minimumItemCount: Int,
                                       includedRoot: String?) -> (sql: String, arguments: StatementArguments) {
        var arguments = filter.arguments + [minimumItemCount]
        if let includedRoot { arguments += [includedRoot] }
        return ("""
            SELECT coalesce(n.root_node_id, n.id) AS root_id, count(*) AS item_count,
                   sum(h.starred) AS starred_count, sum(coalesce(a.for_revision, 0)) AS revision_count,
                   max(h.at) AS latest_at
            \(libraryJoin) WHERE \(filter.sql) AND n.id IS NOT NULL
            GROUP BY coalesce(n.root_node_id, n.id)
            HAVING count(*) >= ?\(includedRoot == nil ? "" : " OR coalesce(n.root_node_id, n.id) = ?")
            """, arguments)
    }

    public func trashCount() throws -> Int {
        try queue.read {
            try Int.fetchOne($0, sql: "SELECT count(*) FROM history WHERE trashed = 1 AND history_visibility = 'normal'") ?? 0
        }
    }

    /// Preserve caller order and reject stale, deleted, hidden or trashed export selections.
    public func exportWorks(ids: [String]) throws -> [SavedWork] {
        try queue.read { db in
            try ids.map { id in
                guard let work = try SavedWork.fetchOne(db, key: id), !work.trashed,
                      work.historyVisibility == "normal" else {
                    throw PersistenceError.invalidRecord("selection is no longer exportable")
                }
                return work
            }
        }
    }

    @discardableResult
    public func setStarred(ids: [String], starred: Bool) throws -> Int {
        try queue.write { db in
            var count = 0
            for id in Set(ids) {
                try db.execute(sql: "UPDATE history SET starred = ? WHERE id = ?", arguments: [starred, id])
                count += db.changesCount
            }
            return count
        }
    }

    public func libraryAnnotation(id: String) throws -> LibraryAnnotation {
        try queue.read { db in
            guard try Bool.fetchOne(db, sql: "SELECT EXISTS(SELECT 1 FROM history WHERE id = ?)", arguments: [id]) == true else {
                throw PersistenceError.invalidRecord("work no longer exists")
            }
            return try Self.annotation(id: id, in: db)
        }
    }

    /// Read and invert the durable mark together, independent of any visible page cache.
    public func toggleAnnotation(id: String, mark: LibraryAnnotationMark) throws -> LibraryAnnotation {
        let column: String
        switch mark {
        case .revision: column = "for_revision"
        }
        return try queue.write { db in
            guard try SavedWork.fetchOne(db, key: id) != nil else {
                throw PersistenceError.invalidRecord("work no longer exists")
            }
            try db.execute(sql: "INSERT OR IGNORE INTO library_annotations (history_id) VALUES (?)", arguments: [id])
            try db.execute(sql: "UPDATE library_annotations SET \(column) = NOT \(column) WHERE history_id = ?",
                           arguments: [id])
            return try Self.annotation(id: id, in: db)
        }
    }

    public func setAnnotation(id: String, note: String? = nil, forRevision: Bool? = nil) throws {
        try queue.write { db in
            guard try SavedWork.fetchOne(db, key: id) != nil else {
                throw PersistenceError.invalidRecord("work no longer exists")
            }
            try db.execute(sql: "INSERT OR IGNORE INTO library_annotations (history_id) VALUES (?)", arguments: [id])
            if let note {
                // Python's [:240] counts Unicode scalar values, rather than grapheme clusters.
                let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
                let clean = String(String.UnicodeScalarView(trimmed.unicodeScalars.prefix(240)))
                try db.execute(sql: "UPDATE library_annotations SET note = ? WHERE history_id = ?",
                               arguments: [clean.isEmpty ? nil : clean, id])
            }
            if let forRevision {
                try db.execute(sql: "UPDATE library_annotations SET for_revision = ? WHERE history_id = ?",
                               arguments: [forRevision, id])
            }
        }
    }

    @discardableResult
    public func setTrashed(ids: [String], trashed: Bool) throws -> Int {
        try queue.write { db in
            var count = 0
            for id in Set(ids) {
                try db.execute(sql: "UPDATE history SET trashed = ? WHERE id = ? AND trashed <> ?",
                               arguments: [trashed, id, trashed])
                count += db.changesCount
            }
            return count
        }
    }

    /// A tombstone retains the original node and every connection, never a substitute identity.
    @discardableResult
    public func permanentlyDelete(ids: [String], requireTrashed: Bool = true,
                                  deletedAt: Int64 = Int64(Date().timeIntervalSince1970 * 1000)) throws -> Int {
        try queue.write { db in
            var count = 0
            for id in Set(ids) {
                guard let work = try SavedWork.fetchOne(db, key: id), !requireTrashed || work.trashed else { continue }
                if let nodeID = work.lineageNodeID {
                    try db.execute(sql: """
                        UPDATE lineage_nodes SET state = 'tombstone', history_id = NULL,
                            description_hash = NULL, render_hash = NULL, deleted_at = ? WHERE id = ?
                        """, arguments: [deletedAt, nodeID])
                    try db.execute(sql: """
                        UPDATE lineage_edges SET metadata_json = '{}' WHERE parent_node_id = ? OR child_node_id = ?
                        """, arguments: [nodeID, nodeID])
                }
                try db.execute(sql: "DELETE FROM history WHERE id = ?", arguments: [id])
                count += db.changesCount
            }
            return count
        }
    }

    @discardableResult
    public func emptyTrash() throws -> Int {
        let ids = try queue.read { try String.fetchAll($0, sql: "SELECT id FROM history WHERE trashed = 1") }
        return try permanentlyDelete(ids: ids)
    }

    /// Both the original reader response and the user's adopted wording travel in backups.
    public func colophons(targetNodeID: String? = nil) throws -> [ColophonRecord] {
        try queue.read { db in
            let rows = try Row.fetchAll(db, sql: """
                SELECT * FROM auxiliary_colophons \(targetNodeID == nil ? "" : "WHERE target_node_id = ?")
                ORDER BY at DESC, id ASC
                """, arguments: targetNodeID.map { StatementArguments([$0]) } ?? StatementArguments())
            return try rows.map(Self.colophon)
        }
    }

    public func saveColophon(_ record: ColophonRecord) throws {
        try Self.validate(record)
        try queue.write { db in
            if let priorRow = try Row.fetchOne(db, sql: "SELECT * FROM auxiliary_colophons WHERE id = ?", arguments: [record.id]) {
                var prior = try Self.colophon(priorRow)
                prior.adoptedBody = record.adoptedBody
                guard prior == record else { throw PersistenceError.invalidRecord("colophon source is immutable") }
                try db.execute(sql: "UPDATE auxiliary_colophons SET adopted_body = ? WHERE id = ?", arguments: [record.adoptedBody, record.id])
            } else {
                try Self.insertColophon(record, into: db)
            }
        }
    }

    /// New colophons are immutable. A repeated adoption of the same result is idempotent.
    public func insertColophon(_ record: ColophonRecord) throws {
        try Self.validate(record)
        try queue.write { db in
            if let row = try Row.fetchOne(db, sql: "SELECT * FROM auxiliary_colophons WHERE id = ?", arguments: [record.id]) {
                guard try Self.colophon(row) == record else {
                    throw PersistenceError.invalidRecord("colophon is immutable")
                }
                return
            }
            try Self.insertColophon(record, into: db)
        }
    }

    private static func insertColophon(_ record: ColophonRecord, into db: Database) throws {
        let encoder = JSONEncoder()
        let branch = String(decoding: try encoder.encode(record.branchSnapshot), as: UTF8.self)
        let warnings = String(decoding: try encoder.encode(record.warnings), as: UTF8.self)
        try db.execute(sql: """
            INSERT INTO auxiliary_colophons
            (id, target_node_id, branch_snapshot, model, at, language, generated_body, adopted_body,
             signature, warnings_json, fact_sheet_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, arguments: [record.id, record.targetNodeID, branch, record.model, record.at,
                               record.language, record.generatedBody, record.adoptedBody, record.signature,
                               warnings, record.factSheetJSON])
    }

    public func deleteColophon(id: String) throws {
        try queue.write { try $0.execute(sql: "DELETE FROM auxiliary_colophons WHERE id = ?", arguments: [id]) }
    }

    private static func colophon(_ row: Row) throws -> ColophonRecord {
        let branch: String = row["branch_snapshot"]
        let warnings: String = row["warnings_json"]
        return ColophonRecord(id: row["id"], targetNodeID: row["target_node_id"],
            branchSnapshot: try JSONDecoder().decode([String].self, from: Data(branch.utf8)),
            model: row["model"], at: row["at"], language: row["language"], generatedBody: row["generated_body"],
            adoptedBody: row["adopted_body"], signature: row["signature"],
            warnings: try JSONDecoder().decode([String].self, from: Data(warnings.utf8)), factSheetJSON: row["fact_sheet_json"])
    }

    private static func validate(_ record: ColophonRecord) throws {
        guard !record.id.isEmpty, !record.model.isEmpty, ["ja", "en"].contains(record.language),
              !record.generatedBody.isEmpty, !record.branchSnapshot.isEmpty,
              record.branchSnapshot.last == record.targetNodeID else {
            throw PersistenceError.invalidRecord("invalid colophon")
        }
        try validateJSONObject(record.factSheetJSON)
    }

    /// Promotion changes visibility, without changing any of the saved work's content.
    public func promoteLineageNode(id: String) throws {
        try queue.write { db in
            guard let node = try LineageNode.fetchOne(db, key: id), node.state == "lineage_only",
                  let historyID = node.historyID else { throw PersistenceError.invalidRecord("node cannot be promoted") }
            try db.execute(sql: "UPDATE lineage_nodes SET state = 'active' WHERE id = ?", arguments: [id])
            try db.execute(sql: "UPDATE history SET history_visibility = 'normal' WHERE id = ?", arguments: [historyID])
        }
    }

    /// Web's explicit overview reads from the root, keeping the selected focus.
    public func lineageOverview(focusNodeID: String, nodeLimit: Int = 200) throws -> LineageGraph? {
        guard let rootID = try queue.read({ db in
            try LineageNode.fetchOne(db, key: focusNodeID)?.rootNodeID
        }), let overview = try lineage(focusNodeID: rootID, descendantDepth: 200, nodeLimit: nodeLimit) else { return nil }
        return LineageGraph(focusNodeID: focusNodeID, nodes: overview.nodes, edges: overview.edges,
                            truncated: overview.truncated, pathOnly: false)
    }

    public func lineage(focusNodeID: String, descendantDepth: Int = 2,
                        nodeLimit: Int = 200, pathOnly: Bool = false) throws -> LineageGraph? {
        let depth = min(200, max(0, descendantDepth))
        let limit = min(200, max(1, nodeLimit))
        return try queue.read { db in
            guard try LineageNode.fetchOne(db, key: focusNodeID) != nil else { return nil }
            var selectedEdges: [LineageEdge] = []
            var selectedIDs: Set<String> = [focusNodeID]
            var current = focusNodeID
            var ancestorIDs = [focusNodeID]
            var truncated = false
            while let edge = try LineageEdge.fetchOne(db, sql: "SELECT * FROM lineage_edges WHERE child_node_id = ?",
                                                     arguments: [current]) {
                guard !selectedIDs.contains(edge.parentNodeID) else { break }
                guard pathOnly || selectedIDs.count < limit else { truncated = true; break }
                selectedEdges.append(edge); selectedIDs.insert(edge.parentNodeID)
                ancestorIDs.append(edge.parentNodeID); current = edge.parentNodeID
            }
            if !pathOnly {
                var frontier = [focusNodeID]
                for level in 0..<depth {
                    var next: [String] = []
                    let edges = try frontier.flatMap { parent in
                        try LineageEdge.fetchAll(db, sql: "SELECT * FROM lineage_edges WHERE parent_node_id = ? ORDER BY id ASC",
                                                 arguments: [parent])
                    }.sorted { $0.id < $1.id }
                    for edge in edges where !selectedIDs.contains(edge.childNodeID) {
                        guard selectedIDs.count < limit else { truncated = true; break }
                        selectedEdges.append(edge); selectedIDs.insert(edge.childNodeID); next.append(edge.childNodeID)
                    }
                    frontier = next
                    if frontier.isEmpty { break }
                    if level == depth - 1 {
                        for id in frontier where try Int.fetchOne(db, sql: "SELECT count(*) FROM lineage_edges WHERE parent_node_id = ?",
                                                                  arguments: [id]) ?? 0 > 0 { truncated = true }
                    }
                }
            }
            let orderedIDs = pathOnly ? ancestorIDs.reversed().map { $0 } : selectedIDs.sorted()
            let items = try orderedIDs.map { id -> LineageItem in
                guard let node = try LineageNode.fetchOne(db, key: id) else { throw PersistenceError.corruptDatabase }
                let work = try node.historyID.flatMap { try SavedWork.fetchOne(db, key: $0) }
                let annotation = try node.historyID.map { try Self.annotation(id: $0, in: db) } ?? LibraryAnnotation()
                let childCount = try Int.fetchOne(db, sql: "SELECT count(*) FROM lineage_edges WHERE parent_node_id = ?",
                                                 arguments: [id]) ?? 0
                return LineageItem(node: node, work: work, annotation: annotation,
                                   generation: try Self.generation(id: id, in: db), childCount: childCount)
            }
            return LineageGraph(focusNodeID: focusNodeID,
                                nodes: pathOnly ? items : items.sorted { ($0.node.at, $0.id) < ($1.node.at, $1.id) },
                                edges: selectedEdges.sorted { ($0.at, $0.id) < ($1.at, $1.id) },
                                truncated: truncated, pathOnly: pathOnly)
        }
    }

    private static let libraryJoin = """
        FROM history h LEFT JOIN library_annotations a ON a.history_id = h.id
        LEFT JOIN lineage_nodes n ON n.id = h.lineage_node_id
        """

    private static func validatePage(limit: Int, offset: Int) throws {
        guard (1...1000).contains(limit), offset >= 0 else { throw PersistenceError.invalidRecord("invalid page") }
    }

    private static func libraryFilter(_ query: LibraryQuery) -> (sql: String, arguments: StatementArguments) {
        var clauses = ["h.history_visibility = 'normal'", "h.trashed = ?"]
        var arguments: StatementArguments = [query.trashed]
        if query.starred { clauses.append("h.starred = 1") }
        if query.forRevision { clauses.append("coalesce(a.for_revision, 0) = 1") }
        let search = query.text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !search.isEmpty && query.canvasSearch {
            let uuid = search.range(of: "^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", options: [.regularExpression, .caseInsensitive]) != nil
            let nativeID = search.range(of: "^(?:[0-9a-f]{32}|[0-9a-f]{64})_[0-9]+$", options: [.regularExpression, .caseInsensitive]) != nil
            if uuid || nativeID {
                clauses.append("lower(h.id) = lower(?)"); arguments += [search]
            } else {
                let literal = search.replacingOccurrences(of: "/", with: "//")
                    .replacingOccurrences(of: "%", with: "/%").replacingOccurrences(of: "_", with: "/_")
                var fields = ["coalesce(h.source_text, h.input) LIKE ? ESCAPE '/'"]
                arguments += ["%\(literal)%"]
                for column in ["h.render_hash", "h.description_hash"] {
                    fields += ["\(column) LIKE ? ESCAPE '/'", "\(column) LIKE ? ESCAPE '/'"]
                    arguments += ["\(literal)%", "%\(literal)"]
                    if !search.contains(":") {
                        fields.append("\(column) LIKE ? ESCAPE '/'"); arguments += ["%:\(literal)%"]
                    }
                }
                clauses.append("(" + fields.joined(separator: " OR ") + ")")
            }
        } else if !search.isEmpty {
            var searchClauses = ["h.input LIKE ?", "h.ddl LIKE ?", "h.stage1_model LIKE ?", "h.stage2_model LIKE ?", "h.catalog_id LIKE ?"]
            for _ in searchClauses { arguments += ["%\(search)%"] }
            let shortHash = search.utf8.count == 4 && search.utf8.allSatisfy {
                (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0)
            }
            let wholeHash = search.range(of: "^(?:[a-z0-9]+:)?[0-9a-f]{64}$", options: [.regularExpression, .caseInsensitive]) != nil
            if shortHash || wholeHash { searchClauses.append("h.render_hash LIKE ?"); arguments += ["%\(search)"] }
            // Server persistence/search.py: hashes accept their whole spelling, digest prefix, or chip suffix.
            if search.range(of: "^(?:[a-z0-9]+:)?[0-9a-f]{1,64}$", options: [.regularExpression, .caseInsensitive]) != nil {
                searchClauses.append("h.render_hash LIKE ?"); arguments += ["\(search)%"]
                if !search.contains(":") { searchClauses.append("h.render_hash LIKE ?"); arguments += ["%:\(search)%"] }
            }
            let uuidPrefix = (1...36).contains(search.count) && search.enumerated().allSatisfy { index, character in
                [8, 13, 18, 23].contains(index) ? character == "-" : character.isASCII && character.isHexDigit
            }
            // Saved native IDs use 32 or 64 hex digits with an optional candidate suffix.
            let nativeID = search.range(of: "^[0-9a-f]{1,64}(?:_[0-9]*)?$", options: [.regularExpression, .caseInsensitive]) != nil
            if uuidPrefix || nativeID { searchClauses.append("h.id LIKE ?"); arguments += ["\(search)%"] }
            clauses.append("(" + searchClauses.joined(separator: " OR ") + ")")
        }
        return (clauses.joined(separator: " AND "), arguments)
    }

    /// Server `include_svg=false`: keep list metadata and byte size without copying SVG text.
    private static func libraryProjection(includeSVG: Bool) -> String {
        let columns = includeSVG ? "h.*" : SavedWork.CodingKeys.allCases.map {
            $0 == .svg ? "'' AS svg" : "h.\($0.rawValue)"
        }.joined(separator: ", ")
        return columns + ", length(CAST(h.svg AS BLOB)) AS library_svg_bytes"
    }

    private static func libraryItem(_ row: Row) throws -> LibraryItem {
        LibraryItem(work: try SavedWork(row: row), annotation: LibraryAnnotation(
            note: row["library_note"], forRevision: row["library_revision"]), svgBytes: row["library_svg_bytes"])
    }

    private static func annotation(id: String, in db: Database) throws -> LibraryAnnotation {
        guard let row = try Row.fetchOne(db, sql: "SELECT * FROM library_annotations WHERE history_id = ?", arguments: [id]) else {
            return LibraryAnnotation()
        }
        return LibraryAnnotation(note: row["note"], forRevision: row["for_revision"])
    }

    private static func generation(id: String, in db: Database) throws -> Int {
        var seen: Set<String> = [id]
        var current = id
        var generation = 1
        while let parent = try String.fetchOne(db, sql: "SELECT parent_node_id FROM lineage_edges WHERE child_node_id = ?",
                                               arguments: [current]), seen.insert(parent).inserted {
            generation += 1; current = parent
        }
        return generation
    }

    public func loadExecution(id: String) throws -> ExecutionSnapshot? {
        try queue.read { try Self.execution(id: id, in: $0) }
    }

    /// Read stored executions without restoring drivers or repeating provider effects.
    public func listExecutionIDs(limit: Int = 100) throws -> [String] {
        try queue.read { db in
            try String.fetchAll(db, sql: "SELECT id FROM execution_snapshots ORDER BY rowid DESC LIMIT ?",
                                arguments: [min(100, max(1, limit))])
        }
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

    /// Project menu eligibility without transferring/parsing/serializing every saved document.
    /// The object/string guards mirror PipelineHost.savedAuthoringContext's required fields.
    public func savedAuthoringSummaries(locations: [(workID: String, executionID: String, effectID: String)]) throws -> [String: SavedAuthoringSummary] {
        guard !locations.isEmpty else { return [:] }
        return try queue.read { db in
            var result: [String: SavedAuthoringSummary] = [:]
            for start in stride(from: 0, to: locations.count, by: 250) {
                let chunk = locations[start..<min(locations.count, start + 250)]
                let values = chunk.map { _ in "(?, ?, ?)" }.joined(separator: ",")
                let arguments = chunk.flatMap { [$0.workID, $0.executionID, $0.effectID] }
                let rows = try Row.fetchAll(db, sql: """
                    WITH wanted(work_id, execution_id, effect_id) AS (VALUES \(values)),
                    records AS (
                        SELECT wanted.work_id, CASE WHEN json_valid(CAST(a.acknowledgement AS TEXT))
                            THEN CAST(a.acknowledgement AS TEXT) ELSE '{}' END AS document
                        FROM wanted JOIN effect_acknowledgements a
                        ON a.execution_id = wanted.execution_id AND a.effect_id = wanted.effect_id
                    )
                    SELECT work_id, json_extract(document, '$.performance.authority.authority') AS authority,
                           json_extract(document, '$.performance.authority.origin') AS origin
                    FROM records
                    WHERE json_extract(document, '$.work_id') = work_id
                    AND json_type(document, '$.performance.configuration') = 'object'
                    AND json_type(document, '$.performance.options') = 'object'
                    AND json_type(document, '$.performance.clip') = 'object'
                    AND json_type(document, '$.performance.authority') = 'object'
                    AND json_type(document, '$.performance.authority.authority') = 'text'
                    AND json_type(document, '$.performance.authority.origin') = 'text'
                    AND json_type(document, '$.performance.authority.revision') = 'text'
                    """, arguments: StatementArguments(arguments))
                for row in rows {
                    result[row["work_id"]] = SavedAuthoringSummary(authority: row["authority"], origin: row["origin"])
                }
            }
            return result
        }
    }

    /// Project only saved labels/line numbers; malformed or mismatched journals supply no label.
    public func savedDisplayLabels(locations: [(workID: String, executionID: String, effectID: String)]) throws -> [String: String] {
        guard !locations.isEmpty else { return [:] }
        return try queue.read { db in
            var labels: [String: String] = [:]
            for start in stride(from: 0, to: locations.count, by: 250) {
                let chunk = locations[start..<min(locations.count, start + 250)]
                let values = chunk.map { _ in "(?, ?, ?)" }.joined(separator: ",")
                let arguments = chunk.flatMap { [$0.workID, $0.executionID, $0.effectID] }
                let rows = try Row.fetchAll(db, sql: """
                    WITH wanted(work_id, execution_id, effect_id) AS (VALUES \(values)),
                    records AS (
                        SELECT wanted.work_id, CASE WHEN json_valid(CAST(a.acknowledgement AS TEXT))
                            THEN CAST(a.acknowledgement AS TEXT) ELSE '{}' END AS document
                        FROM wanted JOIN effect_acknowledgements a
                        ON a.execution_id = wanted.execution_id AND a.effect_id = wanted.effect_id
                    )
                    SELECT work_id,
                        json_extract(document, '$.performance.presentation.provenance.displayLabel') AS label,
                        json_type(document, '$.performance.presentation.provenance.displayLabel') AS label_type,
                        json_extract(document, '$.performance.presentation.provenance.batchLineNumber') AS line,
                        json_type(document, '$.performance.presentation.provenance.batchLineNumber') AS line_type,
                        json_extract(document, '$.performance.authority.origin') AS origin
                    FROM records WHERE json_extract(document, '$.work_id') = work_id
                    """, arguments: StatementArguments(arguments))
                for row in rows {
                    let id: String = row["work_id"]
                    if row["label_type"] as String? == "text", let label: String = row["label"], !label.isEmpty {
                        labels[id] = label
                    } else if row["line_type"] as String? == "integer", let line: Int = row["line"], line > 0 {
                        labels[id] = "#\(line)"
                    } else if let origin: String = row["origin"], ["direct_ddl", "user_authored_ddl"].contains(origin) {
                        labels[id] = "DDL"
                    }
                }
            }
            return labels
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
        try isolated.write { db in
            if try Int.fetchOne(db, sql: "PRAGMA user_version") == 1 {
                try db.execute(sql: Self.resourceSQL("migration-v2"))
            }
            if try Int.fetchOne(db, sql: "PRAGMA user_version") == 2 {
                try db.execute(sql: Self.resourceSQL("migration-v3"))
            }
            if try Int.fetchOne(db, sql: "PRAGMA user_version") == 3 {
                try db.execute(sql: Self.resourceSQL("migration-v4"))
            }
        }
        try isolated.read { try Self.validateRestore($0) }
        // Artwork rollback must not reopen reservations already charged by this DB.
        try retainLiveProviderRates(in: isolated)
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

    private static func resourceSQL(_ name: String) throws -> String {
        guard let resource = Bundle.module.url(forResource: name, withExtension: "sql") else {
            throw PersistenceError.unknownSchema
        }
        return try String(contentsOf: resource, encoding: .utf8)
    }

    private static func schemaSQL(version: Int = 4) throws -> String {
        let baseline = try resourceSQL("schema-v1")
        if version == 1 { return baseline }
        let second = baseline + "\n" + (try resourceSQL("migration-v2"))
        if version == 2 { return second }
        let third = second + "\n" + (try resourceSQL("migration-v3"))
        return version == 3 ? third : third + "\n" + (try resourceSQL("migration-v4"))
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
        guard let version = try Int.fetchOne(db, sql: "PRAGMA user_version"), [1, 2, 3, 4].contains(version) else {
            throw PersistenceError.unknownSchema
        }
        let expected = try DatabaseQueue()
        try expected.write { try $0.execute(sql: schemaSQL(version: version)) }
        let expectedObjects = try expected.read { try schemaObjects(in: $0) }
        var identifiers = ["swift-v1-contract-v2"]
        if version >= 2 { identifiers.append("swift-v2-library-annotations") }
        if version >= 3 { identifiers.append("swift-v3-provider-rate-state") }
        if version >= 4 { identifiers.append("swift-v4-remove-export-mark") }
        guard try schemaObjects(in: db) == expectedObjects,
              try String.fetchAll(db, sql: "SELECT identifier FROM schema_migrations ORDER BY identifier")
                == identifiers else {
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
        if (try Int.fetchOne(db, sql: "PRAGMA user_version") ?? 0) >= 2 {
            for row in try Row.fetchAll(db, sql: "SELECT * FROM auxiliary_colophons") { try validate(colophon(row)) }
            let invalidUnread = try Int.fetchOne(db, sql: """
                SELECT count(*) FROM unread_words WHERE length(word) = 0 OR length(word) > 120
                OR length(context) > 1000 OR frequency <= 0
                """)
            guard invalidUnread == 0 else { throw PersistenceError.corruptDatabase }
        }
        if (try Int.fetchOne(db, sql: "PRAGMA user_version") ?? 0) >= 3 {
            for row in try Row.fetchAll(db, sql: "SELECT provider_id, state_json FROM provider_rate_state") {
                let provider: String = row["provider_id"]
                guard !provider.isEmpty else { throw PersistenceError.corruptDatabase }
                let data: Data = row["state_json"]
                try ProviderRateState.decode(data).validate()
            }
        }
        let inconsistent = try Int.fetchOne(db, sql: """
            SELECT count(*) FROM history AS h LEFT JOIN lineage_nodes AS n ON n.id = h.lineage_node_id
            WHERE h.lineage_node_id IS NOT NULL AND (n.id IS NULL OR n.history_id IS NULL OR n.history_id <> h.id)
            """)
        guard inconsistent == 0 else { throw PersistenceError.corruptDatabase }
    }
}
