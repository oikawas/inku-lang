import CoreGraphics
import Foundation
import InkuPersistence
import XCTest
@testable import InkuUI

private actor DelayedThumbnailBaker {
    private(set) var oldStarted = false
    private(set) var oldCalls = 0
    private var oldWaiter: CheckedContinuation<Void, Never>?
    func bake(_ svg: String) async throws -> (CGImage, Data) {
        if svg == "old" || svg.contains("id=\"delayed\"") {
            oldCalls += 1
            oldStarted = true
            await withCheckedContinuation { oldWaiter = $0 }
        }
        guard let context = CGContext(data: nil, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
                                      space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue),
              let image = context.makeImage() else { throw CocoaError(.fileReadUnknown) }
        return (image, Data(svg.utf8))
    }
    func releaseOld() { oldWaiter?.resume(); oldWaiter = nil }
}

final class ThumbnailRestoreRaceTests: XCTestCase, @unchecked Sendable {
    func testVisibleThumbnailDoesNotWaitForBackgroundBake() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-thumb-visible-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let db = try InkuDatabase(url: root.appendingPathComponent("works.sqlite"))
        let store = try ThumbnailStore(url: root.appendingPathComponent("thumbs.sqlite"))
        let baker = DelayedThumbnailBaker()
        defer { Task { await baker.releaseOld() } }
        let thumbnails = ArtworkThumbnails(backgroundBaker: { try await baker.bake($0) })
        await thumbnails.connect(store: store, database: db)
        let svg = #"<svg xmlns="http://www.w3.org/2000/svg" id="delayed" width="10" height="10"><rect width="10" height="10"/></svg>"#
        let work = SavedWork(id: "work", at: 1, input: "visible", score: "{}", svg: svg, renderHash: "hash")
        let background = await thumbnails.startSavedBake(work)
        for _ in 0..<200 {
            if await baker.oldStarted { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let started = await baker.oldStarted
        XCTAssertTrue(started)
        let image = try await thumbnails.image(for: work)
        XCTAssertEqual(image.width, Int(ArtworkThumbnails.width))
        let whileBlocked = try await store.thumbnail(historyID: work.id, scale: 2)
        XCTAssertTrue(whileBlocked?.png.starts(with: [0x89, 0x50, 0x4e, 0x47]) == true)
        await baker.releaseOld()
        await background.value
        let afterOld = try await store.thumbnail(historyID: work.id, scale: 2)
        XCTAssertEqual(afterOld, whileBlocked)
        let statistics = await thumbnails.currentStatistics()
        XCTAssertEqual(statistics.failed, 0)
    }

    func testDuplicateBackgroundBakeDoesNotStartTwice() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-thumb-duplicate-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let db = try InkuDatabase(url: root.appendingPathComponent("works.sqlite"))
        let store = try ThumbnailStore(url: root.appendingPathComponent("thumbs.sqlite"))
        let baker = DelayedThumbnailBaker()
        defer { Task { await baker.releaseOld() } }
        let thumbnails = ArtworkThumbnails(backgroundBaker: { try await baker.bake($0) })
        await thumbnails.connect(store: store, database: db)
        let work = SavedWork(id: "work", at: 1, input: "old", score: "{}", svg: "old", renderHash: "old")
        let first = await thumbnails.startSavedBake(work)
        for _ in 0..<200 {
            if await baker.oldStarted { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let started = await baker.oldStarted
        XCTAssertTrue(started)
        let second = await thumbnails.startSavedBake(work)
        for _ in 0..<200 {
            if await thumbnails.backgroundWaiterCountForChecks(id: work.id, renderHash: work.renderHash) == 2 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let waiters = await thumbnails.backgroundWaiterCountForChecks(id: work.id, renderHash: work.renderHash)
        XCTAssertEqual(waiters, 2)
        let calls = await baker.oldCalls
        XCTAssertEqual(calls, 1)
        await baker.releaseOld()
        await first.value
        await second.value
        let saved = try await store.thumbnail(historyID: work.id, scale: 2)
        XCTAssertEqual(saved?.png, Data("old".utf8))
    }

    func testLatePreRestoreBakeCannotReplaceRestoredThumbnail() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-thumb-restore-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let db = try InkuDatabase(url: root.appendingPathComponent("works.sqlite"))
        let old = SavedWork(id: "work", at: 1, input: "old", score: "{}", svg: "old", renderHash: "old", lineageNodeID: "node")
        try await db.save(old, node: LineageNode(id: "node", historyID: "work", at: 1, renderHash: "old"))
        let store = try ThumbnailStore(url: root.appendingPathComponent("thumbs.sqlite"))
        let baker = DelayedThumbnailBaker()
        defer { Task { await baker.releaseOld() } }
        let thumbnails = ArtworkThumbnails(backgroundBaker: { try await baker.bake($0) })
        await thumbnails.connect(store: store, database: db)
        let oldTask = await thumbnails.startSavedBake(old)
        for _ in 0..<200 {
            if await baker.oldStarted { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let started = await baker.oldStarted
        XCTAssertTrue(started)

        let replacement = try InkuDatabase(url: root.appendingPathComponent("replacement.sqlite"))
        let new = SavedWork(id: "work", at: 1, input: "new", score: "{}", svg: "new", renderHash: "new", lineageNodeID: "node")
        try await replacement.save(new, node: LineageNode(id: "node", historyID: "work", at: 1, renderHash: "new"))
        let backup = root.appendingPathComponent("restore.sqlite")
        try await replacement.backup(to: backup)
        try await db.restore(from: backup)
        await thumbnails.synchronize()
        await thumbnails.passFinished()
        await baker.releaseOld()
        await oldTask.value
        let saved = try await store.thumbnail(historyID: "work", scale: 2)
        XCTAssertEqual(saved?.sourceRenderHash, "new")
        XCTAssertEqual(saved?.png, Data("new".utf8))
    }
}
