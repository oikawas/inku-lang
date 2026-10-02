import Foundation
import Testing
@testable import InkuPersistence

struct ColophonBackupTests {
    @Test func adoptedColophonIsBackedUpWithoutReplacingOriginalReaderText() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("inku-colophon-backup-\(UUID().uuidString)").appendingPathComponent("test.sqlite")
        defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        let db = try InkuDatabase(url: file)
        let work = SavedWork(id: "work", at: 1, input: "exact\r\nsource", score: "{}", svg: "exact SVG", lineageNodeID: "node")
        try await db.save(work, node: LineageNode(id: "node", historyID: work.id, at: 1, rootNodeID: "node"))
        var record = ColophonRecord(id: "colophon", targetNodeID: "node", branchSnapshot: ["node"], model: "service:vision",
            at: 2, language: "ja", generatedBody: "私には、円が見える。\r\n", signature: "読み手: service:vision / 2026-10-03",
            warnings: [], factSheetJSON: "{\"invariants\":{}}")
        try await db.saveColophon(record)
        record.adoptedBody = "作者が編集した奥書。"
        try await db.saveColophon(record)
        let changed = ColophonRecord(id: record.id, targetNodeID: record.targetNodeID, branchSnapshot: record.branchSnapshot,
            model: record.model, at: record.at, language: record.language, generatedBody: "must not replace",
            adoptedBody: record.adoptedBody, signature: record.signature, warnings: [], factSheetJSON: record.factSheetJSON)
        await #expect(throws: PersistenceError.invalidRecord("colophon source is immutable")) { try await db.saveColophon(changed) }
        let backup = file.deletingLastPathComponent().appendingPathComponent("backup.sqlite")
        try await db.backup(to: backup)
        let originalBackupBytes = try Data(contentsOf: backup)
        try await db.deleteColophon(id: record.id)
        #expect(try await db.colophons().isEmpty)
        try await db.restore(from: backup)
        #expect(try await db.colophons(targetNodeID: "node") == [record])
        #expect(try await db.work(id: work.id) == work)
        #expect(try Data(contentsOf: backup) == originalBackupBytes)
    }
}
