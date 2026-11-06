import Foundation
import InkuPersistence
import XCTest
@testable import InkuUI

@MainActor final class HistoryGenerationReuseTests: XCTestCase {
    func testStripListsWithoutSVGAndLoadsCompleteWorkOnNavigation() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-history-svg-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"))
        await app.initialize()
        let database = try app.auxiliaryDatabase()
        let work = SavedWork(id: "svg-work", at: 1, input: "test", score: "{}", svg: "<svg>fixture</svg>")
        try await database.save(work)
        let history = HistoryModel()
        await history.connect(app: app)
        XCTAssertEqual(history.library.works.map(\.svg).joined().utf8.count, 0)
        XCTAssertEqual(history.library.svgSizes[work.id], Int64(work.svg.utf8.count))
        let selected = await history.navigate(app: app, boundary: "latest", selectWork: false)
        XCTAssertEqual(selected?.svg, work.svg)
    }
    func testPageGenerationSnapshotIsRefreshedWhenHistoryChanges() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-history-generation-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"))
        await app.initialize()
        let database = try app.auxiliaryDatabase()
        let parent = SavedWork(id: "parent", at: 1, input: "parent", score: "{}", svg: "<svg/>", lineageNodeID: "node-parent")
        let parentNode = LineageNode(id: "node-parent", historyID: parent.id, at: 1)
        try await database.save(parent, node: parentNode)
        let history = HistoryModel()
        await history.connect(app: app)
        await history.refreshGenerations()
        XCTAssertEqual(history.generations["node-parent"], 1)

        let child = SavedWork(id: "child", at: 2, input: "child", score: "{}", svg: "<svg/>", lineageNodeID: "node-child")
        let childNode = LineageNode(id: "node-child", historyID: child.id, at: 2, rootNodeID: parentNode.id)
        let edge = LineageEdge(id: "edge-child", parentNodeID: parentNode.id, childNodeID: childNode.id, derivationKind: "ddl_edit", at: 2)
        try await database.save(child, node: childNode, edge: edge)
        await history.library.refresh()
        await history.refreshGenerations()
        XCTAssertEqual(history.generations["node-child"], 2)
        XCTAssertEqual(history.generations["node-parent"], 1)

        // The same node id can have a different generation after a restore.
        let replacement = try InkuDatabase(url: root.appendingPathComponent("replacement.sqlite"))
        let standaloneNode = LineageNode(id: "node-child", historyID: child.id, at: 2, rootNodeID: "node-child")
        try await replacement.save(child, node: standaloneNode)
        let backup = root.appendingPathComponent("restore.sqlite")
        try await replacement.backup(to: backup)
        try await database.restore(from: backup)
        await history.library.resetAfterRestore()
        await history.refreshGenerations()
        XCTAssertEqual(history.generations["node-child"], 1)
        XCTAssertNil(history.generations["node-parent"])
    }
}
