import Foundation
import InkuHost
import InkuPersistence
import XCTest
@testable import InkuUI

@MainActor final class RefinementCleanupTests: XCTestCase {
    func testDiscardKeepsSavedCandidateAndDeletesUnsavedCandidate() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-refinement-cleanup-\(UUID())")
        defer { try? FileManager.default.removeItem(at: folder) }
        let app = AppModel(databaseURL: folder.appendingPathComponent("db.sqlite"))
        await app.initialize()
        let database = try app.auxiliaryDatabase()
        let work = SavedWork(id: "saved_0", at: 1, input: "test", score: "{}", svg: "<svg/>", lineageNodeID: "node")
        try await database.save(work, node: LineageNode(id: "node", historyID: work.id, at: 1))
        for id in ["saved", "unsaved"] {
            _ = try await database.compareAndSwapExecution(id: id, expectedRevision: nil, snapshot: Data("{}".utf8))
        }
        let saved = RefinementCandidate(prepared: PreparedCandidate(executionID: "saved", work: work, authority: "test"), kind: .layout, number: 1, savedWork: work)
        let unsaved = RefinementCandidate(prepared: PreparedCandidate(executionID: "unsaved", work: work, authority: "test"), kind: .layout, number: 2)
        let model = RefinementModel(work: work, candidates: [saved, unsaved], app: app)
        model.discardCandidates()
        for _ in 0..<1000 {
            if try await database.loadExecution(id: "unsaved") == nil { break }
            await Task.yield()
        }
        let discarded = try await database.loadExecution(id: "unsaved")
        let kept = try await database.loadExecution(id: "saved")
        XCTAssertNil(discarded)
        XCTAssertNotNil(kept)
    }
}
