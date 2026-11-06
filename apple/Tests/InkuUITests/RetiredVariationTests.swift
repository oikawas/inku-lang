import XCTest
import InkuHost
@testable import InkuUI

final class RetiredVariationTests: XCTestCase {
    func testBootstrapRejectsVariation() throws {
        let bootstrap = try Bootstrap()
        XCTAssertThrowsError(try bootstrap.request(inputMode: "ddl", source: "", description: "", language: "ja",
            catalogID: "", canvasID: "", seed: "1", wild: false, settings: HostSettings(), derivationKind: "variation")) { error in
            XCTAssertEqual((error as? HostError)?.code, "variation_retired")
        }
    }
}
