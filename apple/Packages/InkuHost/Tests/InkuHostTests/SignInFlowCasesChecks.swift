import Foundation
import XCTest
@testable import InkuHost

/// Sign in with ChatGPT step 5. Failure: the binding Swift calls answers a procedure step differently from the core
/// the shared rows were written from (`server/tests/data/sign-in-flow-cases.json`, each a request and its answer).
final class SignInFlowCasesChecks: XCTestCase {
    func testEverySharedFlowRowThroughTheSwiftBinding() throws {
        let url = try ProviderWireMigrationChecks.casesURL().deletingLastPathComponent().appendingPathComponent("sign-in-flow-cases.json")
        let rows = try XCTUnwrap(ExactJSON(data: Data(contentsOf: url)).array)
        XCTAssertEqual(rows.count, 122)
        for row in rows {
            let answer = try ChatGPTPolicy.evaluate(row["request"])
            XCTAssertEqual(answer, row["expect"], row["why"].string ?? "flow row")
        }
        print("Shared sign-in flow rows checked: \(rows.count) through the Swift binding; HTTP=0")
    }

    /// Failure: a member only the core reads (`retained_id_token`, the id token kept for `id_token_hint` after a
    /// sign-out) was dropped when a flow's `write` went through the vault and came back on `read`.
    func testMembersOnlyCoreReadsSurviveTheVault() throws {
        let written = try ExactJSON(data: Data(#"""
            {"id":"p1","issuer":"https://auth.openai.com","sub":"user-1","client_id":"client-1","label":"a / client-1",
             "generation":2,"state":"signed_out","email":null,"scopes":[],"access_token":null,"refresh_token":null,
             "id_token":null,"refresh_owner":"runtime","expires_at":0,"earliest_refresh_at":0,"published_models":["m"],
             "model_purposes":{"m":["llm"]},"catalog":{"models":[],"expires_at":0},
             "retained_id_token":"header.payload.signature","oidc_nonce":"n"}
            """#.utf8))
        let read = ChatGPTPolicy.profile(try ChatGPTPolicy.storedProfile(written))
        XCTAssertEqual(read["retained_id_token"], .string("header.payload.signature"))
        XCTAssertEqual(read["oidc_nonce"], .string("n"))
        XCTAssertEqual(read["client_id"], .string("client-1"))
        XCTAssertEqual(read["published_models"], written["published_models"])
    }
}
