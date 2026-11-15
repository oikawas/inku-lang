import XCTest
import InkuHost
@testable import InkuUI

final class CompositionThingsTests: XCTestCase {
    func testOneThingHighlightsEveryChunk() {
        let units: [ExactJSON] = [
            .object(["thing": .integer(4), "title": .string("一"), "lines": .array([.integer(2)])]),
            .object(["thing": .integer(4), "title": .string("二"), "lines": .array([.integer(5), .integer(6)])]),
            .object(["thing": .integer(9), "title": .string("三"), "lines": .array([.integer(8)])])
        ]
        XCTAssertEqual(CompositionThings.lines(units, for: "4"), [2, 5, 6])
        XCTAssertEqual(CompositionThings.thing(units, atLine: 5), "4")
        XCTAssertEqual(CompositionThings.units(units, for: "4").count, 2)
    }
}
