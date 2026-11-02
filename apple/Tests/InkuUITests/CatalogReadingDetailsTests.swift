import XCTest
import InkuHost
@testable import InkuUI

final class CatalogReadingDetailsTests: XCTestCase {
    func testRecordedMethodsAndDroppedItemsUseWebWording() {
        let model = CatalogReadingDetails(.object(["method": .string("model"), "reading_text": .string("そのまま\n読み")]), japanese: true)
        XCTAssertEqual(model.method, "光と色の読みから選んだ")
        XCTAssertEqual(model.text, "そのまま\n読み")
        XCTAssertNil(model.dropped)
        let seed = CatalogReadingDetails(.object(["method": .string("seed"), "dropped_axes": .integer(1), "dropped_colors": .integer(2)]), japanese: true)
        XCTAssertEqual(seed.method, "読めるものが無く、実行の種で選んだ")
        XCTAssertEqual(seed.dropped, "記述に無いため落とした項目：軸 1・色 2")
        let missing = CatalogReadingDetails(.object([:]), japanese: false)
        XCTAssertEqual(missing.method, "The choice failed; the default catalog")
        XCTAssertNil(missing.dropped)
        let english = CatalogReadingDetails(.object(["method": .string("model"), "dropped_axes": .integer(1), "dropped_colors": .integer(2)]), japanese: false)
        XCTAssertEqual(english.method, "Chosen from the light and color reading")
        XCTAssertEqual(english.dropped, "Dropped as not in the description: 1 axes, 2 colors")
        XCTAssertEqual(CatalogReadingDetails(.object(["method": .string("seed")]), japanese: false).method, "Nothing could be read; chosen by the run's seed")
    }
}
