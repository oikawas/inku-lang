import XCTest
@testable import InkuUI

/// Web `click`/`dblclick` on a library picture: the first click previews, the second click of a double click opens.
@MainActor
final class LibraryClickTests: XCTestCase {
    func testFirstClickPreviewsAndSecondClickOpens() {
        XCTAssertFalse(LibraryClick.opensWork(clickCount: 1))
        XCTAssertTrue(LibraryClick.opensWork(clickCount: 2))
        XCTAssertTrue(LibraryClick.opensWork(clickCount: 3))
    }

    func testKeyOrAccessibilityPressPreviews() {
        // No mouse event is current in a test, as for a key or accessibility press.
        XCTAssertEqual(LibraryClick.currentClickCount, 1)
        var calls: [String] = []
        LibraryClick.press(preview: { calls.append("preview") }, open: { calls.append("open") })
        XCTAssertEqual(calls, ["preview"])
    }
}
