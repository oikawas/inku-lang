import Foundation
import XCTest
@testable import InkuHost

/// Sign in with ChatGPT step 5. Failure: the binding Swift calls answers a procedure step differently from the core
/// the shared rows were written from (`server/tests/data/sign-in-flow-cases.json`, each a request and its answer).
final class SignInFlowCasesChecks: XCTestCase {
    func testEverySharedFlowRowThroughTheSwiftBinding() throws {
        let url = try ProviderWireMigrationChecks.casesURL().deletingLastPathComponent().appendingPathComponent("sign-in-flow-cases.json")
        let rows = try XCTUnwrap(ExactJSON(data: Data(contentsOf: url)).array)
        XCTAssertEqual(rows.count, 106)
        for row in rows {
            let answer = try ChatGPTPolicy.evaluate(row["request"])
            XCTAssertEqual(answer, row["expect"], row["why"].string ?? "flow row")
        }
        print("Shared sign-in flow rows checked: \(rows.count) through the Swift binding; HTTP=0")
    }
}
