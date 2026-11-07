import XCTest
@testable import InkuUI
#if os(macOS)
import AppKit
#endif

/// The count of a library or lineage picture press comes from the mouse-down on that picture, not the current event.
final class LibraryClickTests: XCTestCase {
    private let picture = CGRect(x: 100, y: 200, width: 150, height: 110)

    private func press(_ count: Int, at point: CGPoint = CGPoint(x: 160, y: 250), window: Int = 7,
                       time: TimeInterval = 10) -> LibraryClick.Press {
        LibraryClick.Press(clickCount: count, windowNumber: window, locationInWindow: point, time: time)
    }

    private func opens(_ press: LibraryClick.Press?, window: Int? = 7, now: TimeInterval = 10.1) -> Bool {
        LibraryClick.opensWork(press: press, windowNumber: window, contains: { picture.contains($0) }, now: now, interval: 1)
    }

    func testSecondClickOnThisPictureOpens() {
        XCTAssertTrue(opens(press(2)))
        XCTAssertTrue(opens(press(3)))
    }

    func testFirstClickPreviews() {
        XCTAssertFalse(opens(press(1)))
    }

    func testAPressOnAnotherCardOrWindowPreviews() {
        XCTAssertFalse(opens(press(2, at: CGPoint(x: 400, y: 250))))
        XCTAssertFalse(opens(press(2, window: 8)))
        XCTAssertFalse(opens(press(2), window: nil))
    }

    func testAnOldOrMissingPressPreviews() {
        XCTAssertFalse(opens(press(2), now: 12))
        XCTAssertFalse(opens(press(2, time: 11), now: 10.5))
        XCTAssertFalse(opens(nil))
    }

    #if os(macOS)
    /// The anchor answers in the window's base coordinates, whatever the window's layout.
    @MainActor func testAnchorContainsAPressInTheWindow() {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 400), styleMask: [.titled], backing: .buffered, defer: false)
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 600, height: 400))
        window.contentView = content
        let anchor = NSView(frame: NSRect(x: 80, y: 60, width: 150, height: 110))
        content.addSubview(anchor)
        let inside = anchor.convert(NSPoint(x: 10, y: 10), to: nil)
        let outside = anchor.convert(NSPoint(x: 200, y: 10), to: nil)
        XCTAssertTrue(anchor.bounds.contains(anchor.convert(inside, from: nil)))
        XCTAssertFalse(anchor.bounds.contains(anchor.convert(outside, from: nil)))
    }

    /// The lineage left under the library does not pan, so library presses over its canvas reach the cards.
    func testCoveredLineageDoesNotPan() {
        XCTAssertTrue(LineageScrolling.pans(isEnabled: true, covered: false))
        XCTAssertFalse(LineageScrolling.pans(isEnabled: true, covered: true))
        XCTAssertFalse(LineageScrolling.pans(isEnabled: false, covered: false))
    }
    #endif
}
