import XCTest
@testable import InkuUI

/// iOS step 5: the registry that stops every run as its stop button would when iOS may not keep the app running.
@MainActor final class RunStopRegistryTests: XCTestCase {
    private final class FakeRun: StoppableRun {
        var running = true
        var stops = 0
        var rows: (done: Int, total: Int)?
        var isStoppableRunActive: Bool { running }
        var stoppableRunRows: (done: Int, total: Int)? { rows }
        func stop(app: AppModel) async { stops += 1; running = false }
    }

    func testStopAllStopsOnlyActiveOwnersOnceAndForgetsReleasedOnes() async {
        let app = AppModel()
        let registry = RunStopRegistry()
        let batch = FakeRun(); batch.rows = (2, 5)
        let idle = FakeRun(); idle.running = false
        registry.track(batch); registry.track(batch); registry.track(idle)
        var released: FakeRun? = FakeRun()
        registry.track(released!)
        released = nil

        XCTAssertTrue(registry.anyActive)
        XCTAssertEqual(registry.rows?.done, 2)
        XCTAssertEqual(registry.rows?.total, 5)
        await registry.stopAll(app: app)
        XCTAssertEqual(batch.stops, 1, "an owner tracked twice is stopped once")
        XCTAssertEqual(idle.stops, 0, "an owner that is not running is not stopped")
        XCTAssertFalse(registry.anyActive)
        XCTAssertNil(registry.rows)
    }

    func testAppHasActiveRunFollowsTheRegistry() {
        let app = AppModel()
        XCTAssertFalse(app.hasActiveRun)
        let run = FakeRun()
        app.runStops.track(run)
        XCTAssertTrue(app.hasActiveRun)
        run.running = false
        XCTAssertFalse(app.hasActiveRun)
    }
}
