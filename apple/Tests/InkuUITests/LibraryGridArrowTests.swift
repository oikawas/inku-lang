import XCTest
@testable import InkuUI

final class LibraryGridArrowTests: XCTestCase {
    func testArrowDestinationsAndColumnSizing() {
        typealias Paging = LibraryGridPaging
        let cases: [(Int, Paging.Direction, Int, Int, Bool, Bool, Paging.Destination)] = [
            (3, .left, 3, 8, true, true, .slot(2)),
            (3, .right, 3, 8, true, true, .slot(4)),
            (4, .up, 3, 8, true, true, .slot(1)),
            (1, .down, 3, 8, true, true, .slot(4)),
            (5, .down, 3, 8, true, true, .slot(7)),
            (0, .left, 3, 8, true, true, .previousPage),
            (1, .up, 3, 8, true, true, .previousPage),
            (7, .right, 3, 8, true, true, .nextPage),
            (6, .down, 3, 8, true, true, .nextPage),
            (0, .left, 3, 8, false, true, .stay),
            (1, .up, 3, 8, false, true, .stay),
            (7, .right, 3, 8, true, false, .stay),
            (6, .down, 3, 8, true, false, .stay),
            (0, .down, 1, 3, false, true, .slot(1)),
            (2, .down, 1, 3, true, true, .nextPage),
            (0, .up, 1, 3, true, true, .previousPage),
            (0, .right, 1, 0, false, false, .stay),
        ]
        for (slot, direction, columns, count, previous, next, expected) in cases {
            XCTAssertEqual(Paging.destination(slot: slot, direction: direction, columns: columns, count: count,
                                              hasPrevious: previous, hasNext: next), expected)
        }
        XCTAssertEqual(Paging.columns(width: 142), 1)
        XCTAssertEqual(Paging.columns(width: 291), 1)
        XCTAssertEqual(Paging.columns(width: 292), 2)
        XCTAssertEqual(Paging.columns(width: 0), 1)
    }
}
