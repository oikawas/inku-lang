import Foundation
import InkuPersistence
import XCTest
@testable import InkuUI

@MainActor final class RecentMetadataExportTests: XCTestCase {
    func testGeneratedWorkIsShownWithFullSVGWhenRecentListIsLightweight() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-recent-generation-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"))
        await app.initialize()
        app.inputMode = "ddl"
        app.ddlText = "place one green square at center."
        app.seedText = "42"
        await app.generate()
        XCTAssertNil(app.errorText)
        XCTAssertEqual(app.works.count, 1)
        XCTAssertEqual(app.works.first?.svg, "")
        XCTAssertFalse(try XCTUnwrap(app.selectedWork?.svg).isEmpty)
    }

    func testMetadataListLoadsFullSVGForExport() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-recent-export-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"))
        await app.initialize()
        let database = try app.auxiliaryDatabase()
        let svg = #"<svg xmlns="http://www.w3.org/2000/svg"><rect width="2" height="3"/></svg>"#
        let work = SavedWork(id: "example", at: 1, input: "example", score: #"{"instructions":[]}"#, svg: svg,
                             renderHash: "hash", lineageNodeID: "node")
        try await database.save(work, node: LineageNode(id: "node", historyID: work.id, at: 1, renderHash: "hash"))
        await app.refreshWorks()
        let metadata = try XCTUnwrap(app.works.first)
        XCTAssertEqual(metadata.svg, "")
        XCTAssertEqual(metadata.score, "{}")
        let sources = try await app.prepareExportSources(works: [metadata])
        XCTAssertEqual(sources.first?.work.svg, svg)
        XCTAssertEqual(sources.first?.work.score, work.score)
        try await database.setTrashed(ids: [work.id], trashed: true)
        do {
            _ = try await app.prepareExportSources(works: [metadata])
            XCTFail("a work moved to the trash was exported from a stale selection")
        } catch { }
    }
}
