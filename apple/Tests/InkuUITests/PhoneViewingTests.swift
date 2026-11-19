import Foundation
import XCTest
@testable import InkuUI

@MainActor final class PhoneViewingTests: XCTestCase {
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
        XCTAssertTrue(permissions.canStar); XCTAssertTrue(permissions.canShare); XCTAssertFalse(permissions.canWrite)
        let locked = PhoneViewingPermissions(browsingLocked: true, writingLocked: true, mutating: false, trashed: false, sharing: false)
        XCTAssertTrue(locked.canStar); XCTAssertTrue(locked.canShare); XCTAssertFalse(locked.canWrite)
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
