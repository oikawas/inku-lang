import Foundation
import GRDB
import Testing
@testable import InkuPersistence

struct LineageVisibilityMigrationTests {
    @Test func oldIntermediateWorksBecomeHistoryWithoutChangingArtwork() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-lineage-v5-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("works.sqlite")
        let resources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Sources/InkuPersistence/Resources")
        let old = try DatabaseQueue(path: file.path)
        let hidden = SavedWork(id: "intermediate", at: 2, input: "test data", score: "{\"exact\":1}", svg: "<svg>exact</svg>", ddl: "circle", historyVisibility: "lineage_only", lineageNodeID: "hidden-node")
        let normal = SavedWork(id: "normal", at: 1, input: "test data", score: "{}", svg: "<svg/>", lineageNodeID: "normal-node")
        try await old.write { db in
            for name in ["schema-v1", "migration-v2", "migration-v3", "migration-v4"] {
                try db.execute(sql: String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8))
            }
            try hidden.insert(db); try normal.insert(db)
            try LineageNode(id: "hidden-node", historyID: hidden.id, state: "lineage_only", at: 2).insert(db)
            try LineageNode(id: "normal-node", historyID: normal.id, at: 1).insert(db)
        }
        let before = try await old.read { db in
            (try Int.fetchOne(db, sql: "SELECT count(*) FROM history WHERE history_visibility = 'normal'") ?? 0,
             try Int.fetchOne(db, sql: "SELECT count(*) FROM history WHERE history_visibility = 'lineage_only'") ?? 0)
        }
        try old.close()
        let db = try InkuDatabase(url: file)
        let migrated = try await db.work(id: hidden.id)
        #expect(before.0 == 1 && before.1 == 1)
        #expect(migrated?.historyVisibility == "normal")
        #expect(migrated?.ddl == hidden.ddl && migrated?.score == hidden.score && migrated?.svg == hidden.svg)
        #expect(try await db.node(id: "hidden-node")?.state == "active")
        #expect(try await db.libraryPage().total == 2)
        let backup = try #require(FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil).first { $0.lastPathComponent.hasPrefix(".inku-before-v5-") })
        let snapshot = try DatabaseQueue(path: backup.path)
        #expect(try await snapshot.read { try Int.fetchOne($0, sql: "SELECT count(*) FROM history WHERE history_visibility = 'lineage_only'") } == 1)
        try snapshot.close()
    }
}
