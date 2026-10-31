import XCTest
@testable import InkuUI

final class ThumbnailDecoderWaitTests: XCTestCase, @unchecked Sendable {
    func testScreenDecodeIsServedBeforeQueuedPrefetch() async throws {
        let thumbnails = ArtworkThumbnails()
        for _ in 0..<ArtworkThumbnails.displayDecoders { try await thumbnails.acquireDecoder(prefetch: false) }
        let order = DecoderOrder()
        let prefetch = Task {
            try await thumbnails.acquireDecoder(prefetch: true)
            await order.record("prefetch")
            await thumbnails.releaseDecoder()
        }
        let screen = Task {
            try await thumbnails.acquireDecoder(prefetch: false)
            await order.record("screen")
            await thumbnails.releaseDecoder()
        }
        for _ in 0..<200 {
            if await thumbnails.decoderWaiterCountForChecks() == 2 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let waiting = await thumbnails.decoderWaiterCountForChecks()
        XCTAssertEqual(waiting, 2)
        await thumbnails.releaseDecoder()
        try await screen.value
        let first = await order.values.first
        XCTAssertEqual(first, "screen")
        for _ in 1..<ArtworkThumbnails.displayDecoders { await thumbnails.releaseDecoder() }
        try await prefetch.value
    }

    func testCancelledQueuedDecodeDoesNotHoldOrStealSlot() async throws {
        let thumbnails = ArtworkThumbnails()
        for _ in 0..<ArtworkThumbnails.displayDecoders { try await thumbnails.acquireDecoder(prefetch: false) }
        let queued = Task { try await thumbnails.acquireDecoder(prefetch: false); await thumbnails.releaseDecoder() }
        for _ in 0..<200 {
            if await thumbnails.decoderWaiterCountForChecks() == 1 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let waiting = await thumbnails.decoderWaiterCountForChecks()
        XCTAssertEqual(waiting, 1)
        queued.cancel()
        do { try await queued.value; XCTFail("cancelled decode acquired a slot") } catch is CancellationError { }
        let afterCancellation = await thumbnails.decoderWaiterCountForChecks()
        XCTAssertEqual(afterCancellation, 0)
        for _ in 0..<ArtworkThumbnails.displayDecoders { await thumbnails.releaseDecoder() }
        try await thumbnails.acquireDecoder(prefetch: false)
        await thumbnails.releaseDecoder()
    }
}

private actor DecoderOrder {
    private(set) var values: [String] = []
    func record(_ value: String) { values.append(value) }
}
