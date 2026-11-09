import XCTest
@testable import InkuUI

/// iOS step 6: a continued-processing task must keep reporting progress during a row that takes minutes.
final class ContinuedRunProgressTests: XCTestCase {
    func testStepsEveryFiveSecondsWithinARowAndRestartsOnTheNextRow() {
        var progress = ContinuedRunProgress()
        let start = Date(timeIntervalSince1970: 0)
        XCTAssertEqual(progress.advance(rowsDone: 0, now: start), 0)
        XCTAssertEqual(progress.advance(rowsDone: 0, now: start.addingTimeInterval(4)), 0)
        XCTAssertEqual(progress.advance(rowsDone: 0, now: start.addingTimeInterval(5)), 1)
        // A minute-long answer still moves the count: the system's cadence is about a minute.
        var last: Int64 = 1
        for second in stride(from: 10, through: 70, by: 5) {
            let value = progress.advance(rowsDone: 0, now: start.addingTimeInterval(TimeInterval(second)))
            XCTAssertGreaterThan(value, last); last = value
        }
        // The next row starts at its own thousand, past anything the first row reported.
        XCTAssertEqual(progress.advance(rowsDone: 1, now: start.addingTimeInterval(71)), 1000)
        XCTAssertEqual(progress.advance(rowsDone: 1, now: start.addingTimeInterval(76)), 1001)
    }

    func testARowNeverReachesTheNextRowsCount() {
        var progress = ContinuedRunProgress()
        let start = Date(timeIntervalSince1970: 0)
        var value: Int64 = 0
        for step in 0...2000 { value = progress.advance(rowsDone: 2, now: start.addingTimeInterval(TimeInterval(step * 5))) }
        XCTAssertEqual(value, 2990)
    }
}
