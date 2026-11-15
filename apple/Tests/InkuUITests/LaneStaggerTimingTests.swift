import XCTest
@testable import InkuUI

final class LaneStaggerTimingTests: XCTestCase {
    @MainActor func testDelayIsDrawnWhenEachLaneStartsAndForgottenWhenItWaits() {
        var timing = LaneStaggerTiming()
        var draws = 0
        func draw() -> Int { draws += 1; return 400 }
        XCTAssertNil(timing.delay(for: .waiting, draw: draw))
        XCTAssertEqual(draws, 0)
        XCTAssertEqual(timing.delay(for: .running, draw: draw), 400)
        XCTAssertNil(timing.delay(for: .running, draw: draw))
        XCTAssertEqual(draws, 1)
        XCTAssertNil(timing.delay(for: .waiting, draw: draw))
        XCTAssertEqual(timing.delay(for: .running, draw: draw), 400)
        XCTAssertEqual(draws, 2)
    }
}
