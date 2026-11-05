import Foundation
import GRDB
import Testing
@testable import InkuPersistence

struct DrawOptionsMigrationTests {
    @Test func versionSevenAddsOnlyEmptyFields() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-draw-options-\(UUID())")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("works.sqlite")
        let resources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Sources/InkuPersistence/Resources")
        let old = try DatabaseQueue(path: file.path)
        try await old.write { db in
            for name in ["schema-v1", "migration-v2", "migration-v3", "migration-v4", "migration-v5", "migration-v6", "migration-v7"] {
                try db.execute(sql: String(contentsOf: resources.appendingPathComponent(name + ".sql"), encoding: .utf8))
            }
            try db.execute(sql: "INSERT INTO history(id,at,input,score,svg,render_hash,render_wild) VALUES ('work',1,'input','{}','<svg/>','exact',1)")
        }
        try old.close()
        let migrated = try InkuDatabase(url: file)
        let work = try #require(try await migrated.work(id: "work"))
        #expect(work.renderHash == "exact" && work.svg == "<svg/>" && work.renderWild == true)
        #expect(work.drawRoute == nil && work.sketchRequested == nil && work.compositionRequested == nil && work.catalogMode == nil)
        let reader = try DatabaseQueue(path: file.path)
        #expect(try await reader.read { try Int.fetchOne($0, sql: "PRAGMA user_version") } == 8)
        try reader.close()
    }
}
