import XCTest
@testable import InkuUI

@MainActor final class ShareSheetCompletionTests: XCTestCase {
    func testAcceptedPresentationWaitsForActivityAndFinishesOnlyOnce() async {
        var replies: [Bool] = []
        let completion = ShareSheetCompletion { replies.append($0) }
        completion.presentationReturned(attached: true)

        // UIKit may defer animation or replace the presentation while the activity is pending.
        await Task.yield()
        XCTAssertTrue(replies.isEmpty)
        completion.finish(true)
        completion.finish(false)
        XCTAssertEqual(replies, [true])
    }

    func testRejectedPresentationReturnsWithoutActivityCallback() {
        var replies: [Bool] = []
        let completion = ShareSheetCompletion { replies.append($0) }
        completion.presentationReturned(attached: false)
        XCTAssertEqual(replies, [false])
    }
}
