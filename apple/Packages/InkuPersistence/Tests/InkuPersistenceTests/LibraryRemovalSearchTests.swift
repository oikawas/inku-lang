import Foundation
import GRDB
import Testing
@testable import InkuPersistence

struct LibraryRemovalSearchTests {
    @Test func versionThreeExportMarkRemovalAndLegacyRestorePreserveOtherValues() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-remove-export-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("works.sqlite")
        let resources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Sources/InkuPersistence/Resources")
        let old = try DatabaseQueue(path: file.path)
        let work = SavedWork(id: "legacy-export-mark", at: 1, input: "Exact source", score: "{}", svg: "<svg>exact</svg>", lineageNodeID: "node")
        try await old.write { db in
            for name in ["schema-v1", "migration-v2", "migration-v3"] {
                try db.execute(sql: String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8))
            }
            try work.insert(db)
            try LineageNode(id: "node", historyID: work.id, at: 1).insert(db)
            try db.execute(sql: "INSERT INTO library_annotations VALUES (?, 'Keep comment', 1, 1)", arguments: [work.id])
            try db.execute(sql: "INSERT INTO execution_snapshots VALUES ('execution', 2, ?)", arguments: [Data([0, 255, 7])])
        }
        try old.close()
        let backup = folder.appendingPathComponent("v3-backup.sqlite")
        try FileManager.default.copyItem(at: file, to: backup)
        let originalBackup = try Data(contentsOf: backup)
        let db = try InkuDatabase(url: file)
        for restoring in [false, true] {
            if restoring { try await db.restore(from: backup) }
            #expect(try await db.work(id: work.id) == work)
            #expect(try await db.node(id: "node")?.historyID == work.id)
            #expect(try await db.libraryAnnotation(id: work.id) == LibraryAnnotation(note: "Keep comment", forRevision: true))
            #expect(try await db.loadExecution(id: "execution")?.snapshot == Data([0, 255, 7]))
            let inspect = try DatabaseQueue(path: file.path)
            let fields = try await inspect.read { database in
                (try Int.fetchOne(database, sql: "PRAGMA user_version"),
                 try String.fetchAll(database, sql: "SELECT name FROM pragma_table_info('library_annotations')"))
            }
            #expect(fields.0 == 4)
            #expect(fields.1 == ["history_id", "note", "for_revision"])
            try inspect.close()
        }
        #expect(try Data(contentsOf: backup) == originalBackup)
    }

    @Test func searchMatchesHashPrefixesSuffixesAndSavedIDs() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-library-search-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let hash = "rh3:abcdef" + String(repeating: "1", count: 54) + "cdef"
        let uuid = "a1b2c3d4-1111-2222-3333-444455556666"
        let native = "e1e2e3e4" + String(repeating: "0", count: 24) + "_0"
        let legacyNative = "f1f2f3f4" + String(repeating: "2", count: 56) + "_6"
        for (id, text, at) in [(uuid, "A quiet blue field", Int64(1)), (native, "Another drawing", Int64(2)),
                               (legacyNative, "Legacy drawing", Int64(3))] {
            try await db.save(SavedWork(id: id, at: at, input: text, score: "{}", svg: "<svg/>", renderHash: id == uuid ? hash : nil,
                                       lineageNodeID: "node-" + id), node: LineageNode(id: "node-" + id, historyID: id, at: at))
        }
        for query in ["quiet blue", "rh3:abcdef", "ABCDEF", "CDEF", hash, String(hash.dropFirst(4)), uuid, "A1B2C3D4-111", "a1b2"] {
            #expect(try await db.libraryPage(query: LibraryQuery(text: query)).items.map(\.id) == [uuid])
        }
        for query in [native, String(native.prefix(14))] {
            #expect(try await db.libraryPage(query: LibraryQuery(text: query)).items.map(\.id) == [native])
        }
        for query in [legacyNative, String(legacyNative.prefix(60))] {
            #expect(try await db.libraryPage(query: LibraryQuery(text: query)).items.map(\.id) == [legacyNative])
        }
        #expect(try await db.libraryPage(query: LibraryQuery(text: "zz-not-present")).total == 0)
        #expect(try await db.list().count == 3)
    }
}
