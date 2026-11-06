import Foundation
import Testing
@testable import InkuHost

@Test func prettyJSONPreservesNumberLexemes() throws {
    for spelling in ["1.0", "1e3", "12345678901234567890"] {
        let json = try ExactJSON(data: Data("{\"z\":\(spelling),\"a\":[\(spelling)]}".utf8))
        let pretty = json.prettyText
        #expect(pretty == "{\n  \"a\" : [\n    \(spelling)\n  ],\n  \"z\" : \(spelling)\n}")
        #expect(try ExactJSON(data: Data(pretty.utf8)) == json)
    }
}
