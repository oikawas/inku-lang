import Foundation
import Testing
@testable import InkuPersistence

struct UnreadWordLedgerTests {
    // Concrete failure: repeated feedback loses its original frequency/contexts on
    // backup restore. One local database checks the Server upsert and aggregation.
    @Test func feedbackAggregatesDistinctContextsAndSurvivesBackup() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-unread-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let db = try InkuDatabase(url: directory.appendingPathComponent("work.sqlite"))
        try await db.recordUnreadWords(["  未読語 ", "未読語", "", "alpha"], context: " first ", at: 10)
        try await db.recordUnreadWords(["未読語"], context: "first", at: 20)
        for (index, context) in ["second", "third", "fourth"].enumerated() {
            try await db.recordUnreadWords(["未読語"], context: context, at: Int64(30 + index))
        }
        let items = try await db.unreadWords()
        #expect(items.map(\.word) == ["未読語", "alpha"])
        #expect(items[0].frequency == 5)
        #expect(items[0].firstAt == 10 && items[0].lastAt == 32)
        #expect(items[0].contexts == ["first", "second", "third"])
        let backup = directory.appendingPathComponent("backup.sqlite")
        try await db.backup(to: backup)
        try await db.recordUnreadWords(["later"], context: "post backup", at: 40)
        try await db.restore(from: backup)
        #expect(try await db.unreadWords() == items)
    }
}
