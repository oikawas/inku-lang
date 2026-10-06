import Foundation
import GRDB

/// One stored thumbnail: the PNG and the render hash of the SVG it was baked from.
public struct StoredThumbnail: Sendable, Equatable {
    public let png: Data
    public let sourceRenderHash: String?
}

/// The thumbnail store, a derived SQLite file beside the canonical database (Server `thumbs_db.py`).
/// Every row can be baked again from the works, so the file is outside backups, and a file that
/// cannot be opened is replaced by an empty one rather than reported.
public actor ThumbnailStore {
    /// Server `BASE_WIDTH`; a row's scale times this is the PNG's width, its height follows the work.
    public static let baseWidth = 256

    public nonisolated let url: URL
    private let queue: DatabaseQueue

    public init(url: URL) throws {
        guard url.isFileURL else { throw PersistenceError.invalidFileURL }
        self.url = url.standardizedFileURL
        try FileManager.default.createDirectory(at: self.url.deletingLastPathComponent(), withIntermediateDirectories: true)
        do {
            queue = try Self.open(self.url)
        } catch {
            for suffix in ["", "-wal", "-shm"] { try? FileManager.default.removeItem(atPath: self.url.path + suffix) }
            queue = try Self.open(self.url)
        }
    }

    /// `thumbs.sqlite` in the canonical database's folder.
    public nonisolated static func url(besideDatabase database: URL) -> URL {
        database.deletingLastPathComponent().appendingPathComponent("thumbs.sqlite", isDirectory: false)
    }

    private static func open(_ url: URL) throws -> DatabaseQueue {
        var configuration = Configuration()
        configuration.busyMode = .timeout(5)
        let queue = try DatabaseQueue(path: url.path, configuration: configuration)
        try queue.write { db in
            // Server `ThumbRow`: one row per work and scale.
            try db.execute(sql: """
                CREATE TABLE IF NOT EXISTS thumbs (
                    history_id TEXT NOT NULL,
                    scale INTEGER NOT NULL,
                    png BLOB NOT NULL,
                    source_render_hash TEXT,
                    built_at INTEGER NOT NULL,
                    PRIMARY KEY (history_id, scale)
                );
                CREATE INDEX IF NOT EXISTS index_thumbs_source_render_hash ON thumbs (source_render_hash);
                """)
            _ = try Row.fetchOne(db, sql: "SELECT history_id, scale, png, source_render_hash, built_at FROM thumbs LIMIT 1")
        }
        return queue
    }

    public func thumbnail(historyID: String, scale: Int) throws -> StoredThumbnail? {
        try queue.read { db in
            try Row.fetchOne(db, sql: "SELECT png, source_render_hash FROM thumbs WHERE history_id = ? AND scale = ?",
                             arguments: [historyID, scale])
                .map { StoredThumbnail(png: $0["png"], sourceRenderHash: $0["source_render_hash"]) }
        }
    }

    /// Replaces in place, so a work keeps its old thumbnail until the new one is written.
    public func put(historyID: String, scale: Int, png: Data, sourceRenderHash: String?,
                    builtAt: Int64 = Int64(Date().timeIntervalSince1970 * 1000)) throws {
        try queue.write { db in
            try db.execute(sql: """
                INSERT INTO thumbs (history_id, scale, png, source_render_hash, built_at) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (history_id, scale) DO UPDATE SET
                    png = excluded.png, source_render_hash = excluded.source_render_hash, built_at = excluded.built_at
                """, arguments: [historyID, scale, png, sourceRenderHash, builtAt])
        }
    }

    /// Every work stored at this scale, with the render hash it was baked from.
    public func storedHashes(scale: Int) throws -> [String: String?] {
        try queue.read { db in
            var result: [String: String?] = [:]
            for row in try Row.fetchAll(db, sql: "SELECT history_id, source_render_hash FROM thumbs WHERE scale = ?",
                                        arguments: [scale]) {
                result[row["history_id"]] = row["source_render_hash"] as String?
            }
            return result
        }
    }

    public func storedIDs() throws -> Set<String> {
        try queue.read { Set(try String.fetchAll($0, sql: "SELECT DISTINCT history_id FROM thumbs")) }
    }

    @discardableResult
    public func delete(historyIDs: [String]) throws -> Int {
        guard !historyIDs.isEmpty else { return 0 }
        return try queue.write { db in
            var count = 0
            for start in stride(from: 0, to: historyIDs.count, by: 500) {
                let chunk = Array(historyIDs[start..<min(historyIDs.count, start + 500)])
                try db.execute(sql: "DELETE FROM thumbs WHERE history_id IN (\(chunk.map { _ in "?" }.joined(separator: ",")))",
                               arguments: StatementArguments(chunk))
                count += db.changesCount
            }
            return count
        }
    }

    public func count(scale: Int) throws -> Int {
        try queue.read { try Int.fetchOne($0, sql: "SELECT count(*) FROM thumbs WHERE scale = ?", arguments: [scale]) ?? 0 }
    }
}
