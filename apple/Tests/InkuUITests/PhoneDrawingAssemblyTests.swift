import CoreGraphics
import XCTest
@testable import InkuUI

@MainActor final class PhoneDrawingAssemblyTests: XCTestCase {
    func testReadyFramesPlayForAtMostSixSeconds() async throws {
        let savedAt = ContinuousClock.now
        let frame = try testFrame()
        let frames = await PhoneDrawingAssembly.prepare(savedAt: savedAt, now: { savedAt }, sleep: { _ in
            try await Task.sleep(for: .seconds(30))
        }) {
            [frame, frame, frame]
        }
        XCTAssertEqual(frames.count, 3)
        for count in 1...24 {
            XCTAssertLessThanOrEqual(PhoneDrawingAssembly.frameInterval(count: count) * count, .seconds(6))
        }
    }

    func testOneInstructionAndExpiredDeadlineSkipLoading() async {
        let savedAt = ContinuousClock.now
        let one = await PhoneDrawingAssembly.prepare(savedAt: savedAt, commandCount: 1, now: { savedAt }, sleep: { _ in
            XCTFail("A single instruction does not need a timer")
        }) {
            XCTFail("A single instruction does not need frames")
            return []
        }
        XCTAssertTrue(one.isEmpty)
        let late = await PhoneDrawingAssembly.prepare(savedAt: savedAt, now: { savedAt.advanced(by: .milliseconds(1500)) },
                                                     sleep: { _ in XCTFail("The deadline already passed") }) {
            XCTFail("The deadline already passed")
            return []
        }
        XCTAssertTrue(late.isEmpty)
    }

    func testTimeoutReturnsWhileTheProducerIsStillWaiting() async {
        let savedAt = ContinuousClock.now
        let (started, signalStart) = AsyncStream<Void>.makeStream()
        let (released, signalRelease) = AsyncStream<Void>.makeStream()
        let (finished, signalFinish) = AsyncStream<Void>.makeStream()
        let pending = Task {
            let result = await PhoneDrawingAssembly.prepare(savedAt: savedAt, now: { savedAt }, sleep: { deadline in
                XCTAssertEqual(savedAt.duration(to: deadline), .milliseconds(1500))
                for await _ in started { break }
            }) {
                signalStart.yield(())
                // A detached producer represents a synchronous core call that can't be interrupted.
                await Task.detached {
                    for await _ in released { break }
                }.value
                return []
            }
            XCTAssertTrue(result.isEmpty)
            signalFinish.yield(())
        }
        var completed = false
        let watchdog = Task {
            try? await Task.sleep(for: .seconds(1))
            signalFinish.finish()
        }
        for await _ in finished { completed = true; break }
        XCTAssertTrue(completed, "The timeout must return before the producer is released")
        signalRelease.yield(())
        signalRelease.finish()
        await pending.value
        watchdog.cancel()
    }

    func testRefusalAndSingleInstructionResponseHaveNoPlayback() async throws {
        let savedAt = ContinuousClock.now
        let frame = try testFrame()
        for returned in [[], [frame, frame]] {
            let frames = await PhoneDrawingAssembly.prepare(savedAt: savedAt, now: { savedAt }, sleep: { _ in
                try await Task.sleep(for: .seconds(30))
            }) { returned }
            XCTAssertTrue(frames.isEmpty)
        }
    }

    private func testFrame() throws -> PhoneDrawingAssembly.Frame {
        let context = try XCTUnwrap(CGContext(data: nil, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
                                             space: CGColorSpaceCreateDeviceRGB(),
                                             bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        return PhoneDrawingAssembly.Frame(image: try XCTUnwrap(context.makeImage()), lines: [1...1])
    }
}
