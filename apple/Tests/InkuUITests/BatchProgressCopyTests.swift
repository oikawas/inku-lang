import XCTest
@testable import InkuUI

@MainActor final class BatchProgressCopyTests: XCTestCase {
    func testElapsedBoundariesAndRowOrdering() {
        let display = DisplaySettings()
        display.preferences.language = "ja"
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 45, display: display), "180 行中 3 行目　バッチ開始から 45 秒")
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 723, display: display), "180 行中 3 行目　バッチ開始から 12 分 03 秒")
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 3723, display: display), "180 行中 3 行目　バッチ開始から 1 時間 02 分 03 秒")
        display.preferences.language = "en"
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 45, display: display), "row 3 of 180　Since batch start 45 s")
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 723, display: display), "row 3 of 180　Since batch start 12 min 03 s")
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 3723, display: display), "row 3 of 180　Since batch start 1 h 02 min 03 s")
    }
}
