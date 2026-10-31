import Foundation
import InkuPersistence
import XCTest
@testable import InkuUI

private final class StartupGate: @unchecked Sendable {
    private let lock = NSLock()
    private let semaphore = DispatchSemaphore(value: 0)
    private var entered = false
    private var released = false
    func open(_ url: URL) throws -> InkuDatabase {
        lock.lock(); entered = true; lock.unlock()
        semaphore.wait()
        return try InkuDatabase(url: url)
    }
    func state() -> (entered: Bool, released: Bool) {
        lock.lock(); defer { lock.unlock() }; return (entered, released)
    }
    func release() {
        lock.lock(); released = true; lock.unlock()
        semaphore.signal()
    }
}

@MainActor final class StartupResponsivenessTests: XCTestCase {
    func testMainActorRemainsResponsiveWhileDatabaseOpenIsBlocked() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("inku-startup-responsive-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let gate = StartupGate()
        // A broken implementation must not hang the test process indefinitely.
        DispatchQueue.global().asyncAfter(deadline: .now() + 2) { gate.release() }
        let app = AppModel(databaseURL: root.appendingPathComponent("works.sqlite"), openDatabase: { try gate.open($0) })
        let initialization = Task { await app.initialize() }
        for _ in 0..<200 {
            if gate.state().entered { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        let duringOpen = gate.state()
        gate.release()
        await initialization.value
        XCTAssertTrue(duringOpen.entered)
        XCTAssertFalse(duringOpen.released, "the main actor could not run until the blocking open was released")
        XCTAssertNil(app.errorText)
    }
}
