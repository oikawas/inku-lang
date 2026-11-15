import XCTest
@testable import InkuUI

final class ThesisInputTests: XCTestCase {
    func testLongPasteStopsAtFourHundredUnicodeScalars() {
        let input = String(repeating: "雪", count: 399) + "😀続き"
        let result = ThesisInput.limited(input)
        XCTAssertEqual(result.unicodeScalars.count, 400)
        XCTAssertTrue(result.hasSuffix("😀"))
        XCTAssertEqual(ThesisInput.limited("短い"), "短い")
    }
}
