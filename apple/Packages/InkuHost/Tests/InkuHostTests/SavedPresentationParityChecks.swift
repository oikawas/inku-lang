import Foundation
import XCTest
@testable import InkuHost

final class SavedPresentationParityChecks: XCTestCase, @unchecked Sendable {
    // Failure (H13): a render warning the core raised is lost from the saved work's diagnostics, or a stale one
    // survives a replay; Server keeps render_warnings only when that render raised any.
    func testRenderWarningsFollowTheRender() {
        let warning: ExactJSON = .array([.object(["kind": .string("host_color_invalid"), "name": .string("background")])])
        let kept = SavedPresentation.withRenderWarnings(.object(["render_diagnostics": .null]), .object(["render_warnings": warning]))
        XCTAssertEqual(kept["render_warnings"], warning)
        let cleared = SavedPresentation.withRenderWarnings(kept, .object(["render_warnings": .array([])]))
        XCTAssertNil(cleared.object?["render_warnings"])
        XCTAssertNotNil(cleared.object?["render_diagnostics"])
    }
}
