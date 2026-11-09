import XCTest
@testable import InkuUI

@MainActor final class BatchProgressCopyTests: XCTestCase {
    func testTileWordsFollowTheWebTemplates() {
        let display = DisplaySettings()
        display.preferences.language = "ja"
        XCTAssertEqual(BatchProgressCopy.rowOfTotal(current: 3, total: 180, display: display), "180 行中 3 行目")
        XCTAssertEqual(BatchProgressCopy.elapsed(45, display: display), "バッチ開始から 45 秒")
        XCTAssertEqual(BatchProgressCopy.elapsed(723, display: display), "バッチ開始から 12 分 03 秒")
        XCTAssertEqual(BatchProgressCopy.elapsed(3723, display: display), "バッチ開始から 1 時間 02 分 03 秒")
        XCTAssertEqual(BatchProgressCopy.average(83, display: display), "1 枚 平均 1 分 23 秒")
        display.preferences.language = "en"
        XCTAssertEqual(BatchProgressCopy.rowOfTotal(current: 3, total: 180, display: display), "line 3 of 180")
        XCTAssertEqual(BatchProgressCopy.elapsed(723, display: display), "12 min 03 s since the batch started")
        XCTAssertEqual(BatchProgressCopy.average(83, display: display), "avg 1 min 23 s per work")
        // elapsed.ts batchClockTime
        XCTAssertEqual(BatchProgressCopy.clock(5), "0:05")
        XCTAssertEqual(BatchProgressCopy.clock(723), "12:03")
        XCTAssertEqual(BatchProgressCopy.clock(3723), "1:02:03")
    }

    /// state.svelte.ts `summaryCurrent`: a retry round's position reads as a position among the whole plan.
    func testLineAmongThePlanInARetryRound() {
        var summary = BatchRunSummary()
        summary.start(planTotal: 10, at: Date(timeIntervalSince1970: 0))
        XCTAssertEqual(summary.current, 0)
        summary.beginRound(10)
        summary.beginWork(position: 4)
        XCTAssertEqual(summary.current, 4)
        summary.beginRound(2)
        XCTAssertEqual(summary.current, 0)
        summary.beginWork(position: 1)
        XCTAssertEqual(summary.current, 9)
        summary.beginWork(position: 2)
        XCTAssertEqual(summary.current, 10)
    }

    /// state.svelte.ts `recordWorkDuration`: only saved works make the average.
    func testAverageCountsOnlySavedWorks() {
        let start = Date(timeIntervalSince1970: 0)
        var summary = BatchRunSummary()
        summary.start(planTotal: 3, at: start)
        summary.beginRound(3)
        XCTAssertNil(summary.averageWork)
        summary.beginWork(position: 1, at: start)
        summary.finishWork(saved: false, at: start.addingTimeInterval(500))
        XCTAssertNil(summary.averageWork)
        summary.beginWork(position: 2, at: start)
        summary.finishWork(saved: true, at: start.addingTimeInterval(60))
        summary.beginWork(position: 3, at: start)
        summary.finishWork(saved: true, at: start.addingTimeInterval(120))
        XCTAssertEqual(summary.averageWork, 90)
    }

    /// score-version.ts: no Score, a Score without a version, and a recorded version are three answers.
    func testScoreVersionReadsTheSavedJSONAsItIs() {
        XCTAssertNil(ScoreVersionDisplay.text(scoreJSON: "", notRecorded: "記録なし"))
        XCTAssertEqual(ScoreVersionDisplay.text(scoreJSON: #"{"instructions":[]}"#, notRecorded: "記録なし"), "記録なし")
        XCTAssertEqual(ScoreVersionDisplay.text(scoreJSON: #"{"version":"0.24.0","instructions":[]}"#, notRecorded: "記録なし"), "0.24.0")
    }
}
