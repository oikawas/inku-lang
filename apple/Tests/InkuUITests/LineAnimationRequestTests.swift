import Foundation
import InkuCore
import InkuHost
import XCTest
@testable import InkuUI

@MainActor final class LineAnimationRequestTests: XCTestCase {
    func testExportRequestPassesThePersistedScoreToCore() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("inku-line-score-\(UUID())")
        defer { try? FileManager.default.removeItem(at: directory) }
        let app = AppModel(databaseURL: directory.appendingPathComponent("works.sqlite"))
        await app.initialize()
        app.seedText = "42"
        let drawn = await app.drawNewDDL("place one red circle at center.")
        XCTAssertTrue(drawn, app.errorText ?? "")
        let work = try XCTUnwrap(app.selectedWork)
        let sources = try await app.prepareExportSources(works: [work], lineAnimation: true)
        var request = try XCTUnwrap(sources.first?.lineAnimationRequest)
        let savedScore = try ExactJSON(data: Data(work.score.utf8))
        XCTAssertNotNil(savedScore.object)
        XCTAssertEqual(request["saved_score"], savedScore)

        request["show_ddl"] = .bool(false)
        request["font_family"] = .string("")
        let response = try ExactJSON(data: InkuCore.lineAnimation(request.data))
        XCTAssertEqual(response["source"].string, "saved_score", response["message"].string ?? "")
        XCTAssertEqual(response["matches_saved_svg"].bool, true)
        XCTAssertEqual(response["frames"].array?.count, 2)
    }
}
