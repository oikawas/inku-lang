import Foundation
import XCTest
@testable import InkuHost

final class HoleCompletionIssueTests: XCTestCase {
    private static let check: ExactJSON = .object(["results": .array([
        .object(["hole_id": .string("hole:a1"), "status": .string("rejected"), "reason": .string("numeric_range_outside_words"), "source": .string("右下に")]),
        .object(["hole_id": .string("hole:b2"), "status": .string("unresolved"), "source": .string("many square")]),
        .object(["hole_id": .string("hole:c3"), "status": .string("passed"), "source": .string("passed sentence")]),
    ])])
    private static func snapshot(_ tag: String, reason: String? = nil) -> ExactJSON {
        var phase: ExactJSON = .object(["tag": .string(tag)])
        if let reason { phase["reason"] = .string(reason) }
        return .object(["phase": phase, "hole_completion_check": check])
    }

    // Failure: the uncompleted holes were not shown when the author must decide, shown at other times,
    // or a hole that passed was listed (Web holeCompletionIssues).
    func testIssuesFollowWebConditions() {
        let expected = [HoleCompletionIssue(holeID: "hole:a1", source: "右下に", reason: "numeric_range_outside_words"),
                        HoleCompletionIssue(holeID: "hole:b2", source: "many square", reason: "unknown")]
        XCTAssertEqual(HoleCompletionIssue.issues(snapshot: Self.snapshot("awaiting_patch_approval")), expected)
        XCTAssertEqual(HoleCompletionIssue.issues(snapshot: Self.snapshot("needs_user_edit", reason: "hole_completion_failed")), expected)
        XCTAssertEqual(HoleCompletionIssue.issues(snapshot: Self.snapshot("failed", reason: "hole_completion_context_limit")), expected)
        XCTAssertEqual(HoleCompletionIssue.issues(snapshot: Self.snapshot("needs_user_edit", reason: "stage1_failed")), [])
        XCTAssertEqual(HoleCompletionIssue.issues(snapshot: Self.snapshot("completed")), [])
    }
}
