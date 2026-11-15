import XCTest
import InkuHost
@testable import InkuUI

final class PlacePresentationTests: XCTestCase {
    @MainActor func testCorePlaceAndRefusalPresentation() {
        let display = DisplaySettings()
        let unit: ExactJSON = .object(["at": .string("center"), "places": .object([
            "center": .string("unchanged"), "golden_ul": .string("clamped"), "third_top": .string("fitted")])])
        XCTAssertTrue(PlacePresentation.title(unit: unit, place: "center", display: display).contains("今"))
        XCTAssertTrue(PlacePresentation.title(unit: unit, place: "third_top", display: display).contains("はめ込んだ"))
        XCTAssertTrue(PlacePresentation.label(what: "海", unit: unit, place: "golden_ul", display: display).contains("画面の端"))
        XCTAssertFalse(PlacePresentation.label(what: "海", unit: unit, place: "golden_ul", display: display).contains("golden_ul"))
        let fitted: ExactJSON = .object(["at": .null, "places": .object(["center": .string("fitted")])])
        XCTAssertFalse(PlacePresentation.title(unit: fitted, place: "center", display: display).contains("（今）"))
    }
}
