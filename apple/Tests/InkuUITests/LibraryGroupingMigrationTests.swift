import XCTest
@testable import InkuUI

final class LibraryGroupingMigrationTests: XCTestCase {
    func testOldGroupedBooleanAndNewGrouping() throws {
        func grouping(_ text: String) throws -> String {
            try DisplayPreferences.decodeInterfaceFile(Data(text.utf8)).resolvedLibraryGrouping
        }
        XCTAssertEqual(try grouping("{}"), "timeline")
        XCTAssertEqual(try grouping(#"{"libraryGrouped":false}"#), "timeline")
        XCTAssertEqual(try grouping(#"{"libraryGrouped":true}"#), "lineage")
        XCTAssertEqual(try grouping(#"{"libraryGrouped":true,"libraryGrouping":"description"}"#), "description")
    }
}
