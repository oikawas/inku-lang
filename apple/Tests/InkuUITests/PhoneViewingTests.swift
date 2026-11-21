import Foundation
import InkuPersistence
import XCTest
@testable import InkuUI

@MainActor final class PhoneViewingTests: XCTestCase {
    func test3DInitialViewKeepsTheFittedPaperAndCorrectsForTheTopInset() {
        let portrait = CGSize(width: 402, height: 820)
        let square = Ddl3DInitialView.phoneViewer(area: portrait, aspect: 1, topInset: 48)
        XCTAssertEqual(square, Ddl3DInitialView(pixelWidth: 402, pixelHeight: 402, panX: 0, panY: -24, zoom: 1))

        let wide = Ddl3DInitialView.phoneViewer(area: portrait, aspect: 809.0 / 500.0, topInset: 64)
        XCTAssertEqual(wide.pixelWidth, 402)
        XCTAssertEqual(wide.pixelHeight, 402.0 * 500.0 / 809.0, accuracy: 0.0001)
        XCTAssertEqual(wide.panX, 0)
        XCTAssertEqual(wide.panY, -32)
        XCTAssertEqual(wide.zoom, 1)

        let tall = Ddl3DInitialView.phoneViewer(area: portrait, aspect: 0.4, topInset: 48)
        XCTAssertEqual(tall.pixelWidth, 328, accuracy: 0.0001)
        XCTAssertEqual(tall.pixelHeight, 820, accuracy: 0.0001)
    }

    func testTimelinePagesKeepOpeningStarAndSearchFilter() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-view-filter-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let database = try InkuDatabase(url: root.appendingPathComponent("works.sqlite"))
        for (index, input, starred) in [(1, "moon", true), (2, "moon", false), (3, "sun", true), (4, "moon", true)] {
            let id = "work-\(index)", node = "node-\(index)"
            var work = SavedWork(id: id, at: Int64(index), input: input, score: "{}", svg: "<svg/>", lineageNodeID: node)
            work.starred = starred
            try await database.save(work, node: LineageNode(id: node, historyID: id, at: Int64(index)))
        }
        var homeQuery = LibraryQuery(text: "moon", starred: true)
        let reader = PhoneViewingPageReader(query: homeQuery)
        homeQuery.starred = false
        let first = try await reader.page(database: database, offset: 0, limit: 1)
        let second = try await reader.page(database: database, offset: 1, limit: 1)
        var order = PhoneViewingOrder(ids: first.items.map(\.id), currentID: "work-4")
        order.append(second.items.map(\.id))
        XCTAssertEqual(order.ids, ["work-4", "work-1"])
        XCTAssertEqual(first.total, 2)
    }
    func testSnapshotKeepsUnstarredWorkAndHandlesPagingDeletionAndNewWorks() {
        var order = PhoneViewingOrder(ids: ["a", "b", "c", "b"], currentID: "b")
        // A filtered library may now omit b; it must not rewrite the session's snapshot.
        XCTAssertEqual(order.ids, ["a", "b", "c"])
        order.move(1); XCTAssertEqual(order.currentID, "c")
        order.append(["c", "d", "e"]); order.move(1); XCTAssertEqual(order.currentID, "d")
        order.insertFirst("new", select: false); XCTAssertEqual(order.currentID, "d")
        order.insertFirst("child", select: true); XCTAssertEqual(order.currentID, "child")
        order.remove("child"); XCTAssertEqual(order.currentID, "new")
        order.last(); order.remove("e"); XCTAssertEqual(order.currentID, "d")
        for id in order.ids { order.remove(id) }
        XCTAssertNil(order.currentID)
    }

    func testBusyDrawingAllowsStarAndSavedCardWithoutChangingSelectedWork() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-phone-view-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"))
        await app.initialize()
        app.seedText = "42"
        let drawn = await app.drawNewDDL("place one red circle at center.")
        XCTAssertTrue(drawn)
        let work = try XCTUnwrap(app.selectedWork)
        await app.library.toggleStar(work)
        let storedStarred = try await app.auxiliaryDatabase().work(id: work.id)
        let starredWork = try XCTUnwrap(storedStarred)
        XCTAssertTrue(starredWork.starred)
        let viewingOrder = PhoneViewingOrder(ids: [work.id, "another"], currentID: work.id)
        let latch = PhoneViewingLatch()
        let running = Task { await app.performComparison(status: "fixture") { _ in await latch.wait() } }
        defer { Task { await latch.release() } }
        for _ in 0..<300 {
            if await latch.entered { break }
            try await Task.sleep(for: .milliseconds(10))
        }
        guard await latch.entered, app.isBusy else { await latch.release(); _ = await running.value; XCTFail("fixture did not enter busy state"); return }
        let permissions = PhoneViewingPermissions(browsingLocked: app.isBrowsingLocked, writingLocked: app.isBusy,
                                                  mutating: false, trashed: false, sharing: false)
        XCTAssertTrue(permissions.canStar); XCTAssertTrue(permissions.canShare); XCTAssertTrue(permissions.canBrowse); XCTAssertFalse(permissions.canWrite)
        let locked = PhoneViewingPermissions(browsingLocked: true, writingLocked: true, mutating: false, trashed: false, sharing: false)
        XCTAssertTrue(locked.canStar); XCTAssertTrue(locked.canShare); XCTAssertFalse(locked.canBrowse); XCTAssertFalse(locked.canWrite)
        await app.library.toggleStar(starredWork)
        let starred = try await app.auxiliaryDatabase().work(id: work.id)
        XCTAssertEqual(starred?.starred, false)
        XCTAssertEqual(viewingOrder.ids, [work.id, "another"])
        XCTAssertEqual(viewingOrder.currentID, work.id)
        let artifact = try await app.preparePhoneShareCard(workID: work.id)
        XCTAssertEqual(Array(artifact.data.prefix(8)), [137, 80, 78, 71, 13, 10, 26, 10])
        XCTAssertEqual(app.selectedWorkID, work.id)
        XCTAssertTrue(app.isBusy)
        await latch.release(); _ = await running.value
    }
}

private actor PhoneViewingLatch {
    private(set) var entered = false
    private var continuation: CheckedContinuation<Void, Never>?
    func wait() async {
        entered = true
        await withCheckedContinuation { continuation = $0 }
    }
    func release() { continuation?.resume(); continuation = nil }
}
