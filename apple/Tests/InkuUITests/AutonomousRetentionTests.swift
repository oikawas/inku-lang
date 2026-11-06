import Foundation
import InkuPersistence
import XCTest
@testable import InkuUI

@MainActor final class AutonomousRetentionTests: XCTestCase {
    func testRetainsNewestFiftyAndPendingRun() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-autonomous-retention-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        var runs = (0..<60).map { index in
            var run = AutonomousRun(sourceID: "source-\(index)", moves: 1, kinds: ["laws"], note: nil, model: "fixture", language: "en", wild: false)
            run.state = "done"
            return run
        }
        var pending = AutonomousRun(sourceID: "pending", moves: 1, kinds: ["laws"], note: nil, model: "fixture", language: "en", wild: false)
        pending.pendingChildID = "pending-child"
        runs.append(pending)
        let file = folder.appendingPathComponent("works.autonomous-runs.json")
        try JSONEncoder().encode(runs).write(to: file)
        let model = AutonomousRefinementModel()
        try await model.connect(database: database)
        let saved = try JSONDecoder().decode([AutonomousRun].self, from: Data(contentsOf: file))
        XCTAssertEqual(saved.filter { $0.state == "done" }.map(\.sourceID), (10..<60).map { "source-\($0)" })
        XCTAssertEqual(saved.last?.pendingChildID, "pending-child")
    }
}
