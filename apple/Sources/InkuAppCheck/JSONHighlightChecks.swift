import Foundation
import InkuUI

/// Failure: the generation information JSON tab colors a token differently from the Web `highlightJsonLine`.
/// The expected offsets and kinds come from running the Build1162 Web regular expression in node.
@MainActor
func runJSONHighlightChecks() throws {
    let cases: [(String, [(Int, Int, String)])] = [
        ("  \"schema\" : \"inku.score.v1\",", [(2, 10, "key"), (13, 15, "string")]),
        ("    \"seed\": 9007199254740991,", [(4, 7, "key"), (12, 16, "number")]),
        ("  \"x\" : -12.5e+3,", [(2, 5, "key"), (8, 8, "number")]),
        ("  \"ok\" : true, \"no\": false,", [(2, 6, "key"), (9, 4, "bool"), (15, 5, "key"), (21, 5, "bool")]),
        ("  \"none\" : null", [(2, 8, "key"), (11, 4, "null")]),
        ("  \"esc\" : \"a\\\"b\\\\c\\u00e9\",", [(2, 7, "key"), (10, 15, "string")]),
        ("  [1, 2.0, -3]", [(3, 1, "number"), (6, 3, "number"), (11, 2, "number")]),
        ("  \"日本語\" : \"春の月\"", [(2, 7, "key"), (10, 5, "string")]),
    ]
    for (line, expected) in cases {
        let actual = JSONHighlight.tokens(line).map { ($0.range.location, $0.range.length, $0.kind.rawValue) }
        guard actual.count == expected.count, zip(actual, expected).allSatisfy({ $0 == $1 }) else {
            throw CheckFailure.message("JSON tokens differ from the Web for \(line): \(actual)")
        }
    }
    print("JSON highlight passed: \(cases.count) lines, \(cases.map(\.1.count).reduce(0, +)) tokens match the Web classes.")
}
