import XCTest
@testable import InkuUI

@MainActor final class BatchProgressCopyTests: XCTestCase {
    func testElapsedBoundariesAndRowOrdering() {
        let display = DisplaySettings()
        display.preferences.language = "ja"
        XCTAssertEqual(ServerTips.template("batchRowOfTotal", language: "ja", argumentCount: 2), "%@ 行中 %@ 行目")
        XCTAssertEqual(ServerTips.template("batchElapsed", language: "ja", argumentCount: 1), "バッチ開始から %@")
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 45, display: display), "180 行中 3 行目　バッチ開始から 45 秒")
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 723, display: display), "180 行中 3 行目　バッチ開始から 12 分 03 秒")
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 3723, display: display), "180 行中 3 行目　バッチ開始から 1 時間 02 分 03 秒")
        display.preferences.language = "en"
        XCTAssertEqual(ServerTips.template("batchRowOfTotal", language: "en", argumentCount: 2), "line %@ of %@")
        XCTAssertEqual(ServerTips.template("batchElapsed", language: "en", argumentCount: 1), "%@ since the batch started")
        for language in ["ja", "en"] {
            XCTAssertNotNil(ServerTips.template("elapsedSeconds", language: language, argumentCount: 1))
            XCTAssertNotNil(ServerTips.template("elapsedMinutes", language: language, argumentCount: 2))
            XCTAssertNotNil(ServerTips.template("elapsedHours", language: language, argumentCount: 3))
        }
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 45, display: display), "line 3 of 180　45 s since the batch started")
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 723, display: display), "line 3 of 180　12 min 03 s since the batch started")
        XCTAssertEqual(BatchProgressCopy.line(current: 3, total: 180, elapsed: 3723, display: display), "line 3 of 180　1 h 02 min 03 s since the batch started")
    }
}
