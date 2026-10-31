import Foundation
import XCTest
@testable import InkuHost

private final class MeterCalculationGate: @unchecked Sendable {
    private let lock = NSLock()
    private let permits = DispatchSemaphore(value: 0)
    private var calls: [String] = []
    func calculate(_ text: String) -> Data {
        lock.lock(); calls.append(text); lock.unlock()
        permits.wait()
        return Data(#"{"mora":1,"phrases":[],"unread":[]}"#.utf8)
    }
    func started() -> [String] { lock.lock(); defer { lock.unlock() }; return calls }
    func release() { permits.signal() }
}

final class DescriptionMeterSchedulingTests: XCTestCase, @unchecked Sendable {
    func testCanonicallyEquivalentTextDoesNotShareAnExactTextResult() async throws {
        let gate = MeterCalculationGate()
        defer { for _ in 0..<2 { gate.release() } }
        let meter = DescriptionMeter(calculate: { text, _, _ in gate.calculate(text) })
        let first = Task { try await meter.count(text: "é", language: "ja") }
        let second = Task { try await meter.count(text: "e\u{301}", language: "ja") }
        for _ in 0..<200 {
            if gate.started().count == 2 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTAssertEqual(gate.started().count, 2)
        gate.release(); gate.release()
        _ = try await first.value
        _ = try await second.value
    }

    func testCancelledWaiterDoesNotCancelSharedWorkOrStartQueuedWork() async throws {
        let gate = MeterCalculationGate()
        defer { for _ in 0..<4 { gate.release() } }
        let meter = DescriptionMeter(calculate: { text, _, _ in gate.calculate(text) })
        let first = Task { try await meter.count(text: "first", language: "ja") }
        for _ in 0..<200 where gate.started().count < 1 { try await Task.sleep(for: .milliseconds(5)) }
        XCTAssertEqual(gate.started(), ["first"])
        let shared = Task { try await meter.count(text: "first", language: "ja") }
        let second = Task { try await meter.count(text: "second", language: "ja") }
        for _ in 0..<200 where gate.started().count < 2 { try await Task.sleep(for: .milliseconds(5)) }
        XCTAssertEqual(Set(gate.started()), Set(["first", "second"]))
        let queued = Task { try await meter.count(text: "queued", language: "ja") }
        for _ in 0..<200 {
            if await meter.waitingCountForChecks(text: "first", language: "ja") == 2,
               await meter.waitingCountForChecks(text: "queued", language: "ja") == 1 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let sharedWaiters = await meter.waitingCountForChecks(text: "first", language: "ja")
        let queuedWaiters = await meter.waitingCountForChecks(text: "queued", language: "ja")
        XCTAssertEqual(sharedWaiters, 2)
        XCTAssertEqual(queuedWaiters, 1)
        shared.cancel(); queued.cancel()
        do { _ = try await shared.value; XCTFail("cancelled waiter returned a value") } catch is CancellationError { }
        do { _ = try await queued.value; XCTFail("cancelled queued request returned a value") } catch is CancellationError { }
        gate.release(); gate.release()
        let firstAnswer = try await first.value
        let secondAnswer = try await second.value
        XCTAssertEqual(firstAnswer.mora, 1)
        XCTAssertEqual(secondAnswer.mora, 1)
        XCTAssertEqual(gate.started().count, 2)
    }
}
