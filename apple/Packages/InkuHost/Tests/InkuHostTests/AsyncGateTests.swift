import Foundation
import XCTest
@testable import InkuHost

final class AsyncGateTests: XCTestCase, @unchecked Sendable {
    func testRequiredCleanupStillAcquiresAfterTaskCancellation() async throws {
        let gate = AsyncGate()
        await gate.lock()
        let flag = GateCleanupFlag()
        let cleanup = Task {
            await gate.lock()
            let wasCancelled = Task.isCancelled
            await gate.unlock()
            await flag.finish(wasCancelled: wasCancelled)
        }
        for _ in 0..<200 {
            if await gate.waitingCountForChecks() == 1 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let waiting = await gate.waitingCountForChecks()
        XCTAssertEqual(waiting, 1)
        cleanup.cancel()
        await gate.unlock()
        for _ in 0..<200 {
            if await flag.wasCancelled != nil { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let wasCancelled = await flag.wasCancelled
        XCTAssertEqual(wasCancelled, true)
        guard wasCancelled != nil else { return }
        try await gate.lockCancellable()
        await gate.unlock()
    }

    func testCancellingAQueuedWaiterDoesNotBlockNextWaiter() async throws {
        let gate = AsyncGate()
        await gate.lock()
        let cancelled = Task { try await gate.lockCancellable(); await gate.unlock() }
        for _ in 0..<200 {
            if await gate.waitingCountForChecks() == 1 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let initialWaiters = await gate.waitingCountForChecks()
        XCTAssertEqual(initialWaiters, 1)
        cancelled.cancel()
        do { try await cancelled.value; XCTFail("cancelled waiter acquired the gate") } catch is CancellationError { }
        let afterCancellation = await gate.waitingCountForChecks()
        XCTAssertEqual(afterCancellation, 0)
        await gate.unlock()
        try await gate.lockCancellable()
        await gate.unlock()
    }
}

private actor GateCleanupFlag {
    private(set) var wasCancelled: Bool?
    func finish(wasCancelled: Bool) { self.wasCancelled = wasCancelled }
}
