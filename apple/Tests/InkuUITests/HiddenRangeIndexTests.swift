import Foundation
import XCTest
@testable import InkuUI

final class HiddenRangeIndexTests: XCTestCase {
    func testOverlappingAndAdjacentRangesMatchLinearLookup() {
        let ranges = [NSRange(location: 8, length: 5), NSRange(location: 2, length: 8),
                      NSRange(location: 13, length: 2), NSRange(location: 20, length: 1),
                      NSRange(location: 16, length: 0)]
        let index = InkuHiddenRangeIndex(ranges)
        for offset in 0...22 {
            XCTAssertEqual(index.contains(offset), ranges.contains { NSLocationInRange(offset, $0) }, "offset \(offset)")
        }
    }

    @MainActor func testEditorStillFoldsExactUTF16Range() {
        let text = "é at the left half (horizontal 0 to 1/2, vertical 0 to 1)"
        let hidden = RangeFoldingProbe.hiddenCharacters(text: text, display: DisplaySettings())
        let range = (text as NSString).range(of: " (horizontal 0 to 1/2, vertical 0 to 1)")
        XCTAssertEqual(Set(hidden), Set(range.location..<NSMaxRange(range)))
    }
}
