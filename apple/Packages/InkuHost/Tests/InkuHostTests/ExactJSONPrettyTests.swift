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
    let keys = ["2", "10", "a", "A", "ä", "B"]
    let object = Dictionary(uniqueKeysWithValues: keys.map { ($0, 0) })
    let expected = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
    let input = try JSONSerialization.data(withJSONObject: object)
    #expect(try ExactJSON(data: input).prettyText == String(decoding: expected, as: UTF8.self))
}
