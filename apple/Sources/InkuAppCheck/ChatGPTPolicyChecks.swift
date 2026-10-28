import Foundation
import InkuCore
import InkuHost

private func policyMatches(_ actual: ExactJSON, _ expected: ExactJSON) -> Bool {
    switch (actual, expected) {
    case (.object(let actual), .object(let expected)):
        return expected.allSatisfy { key, value in actual[key].map { policyMatches($0, value) } ?? false }
    case (.array(let actual), .array(let expected)):
        return actual.count == expected.count && zip(actual, expected).allSatisfy(policyMatches)
    case (.number(let a), .number(let b)):
        return a == b || (Double(a) != nil && Double(a) == Double(b))
    default: return actual == expected
    }
}
func runChatGPTPolicyChecks(wireURL: URL, addendumURL: URL) throws {
    let rows = try ExactJSON(data: Data(contentsOf: wireURL))["chatgpt"].array ?? []
    let actions = Set(["chatgpt_publication", "chatgpt_publication_update", "chatgpt_offered", "chatgpt_usable", "chatgpt_cache"])
    let cases = rows.filter { row in
        let action = row["request"]["action"].string ?? ""
        return action.hasPrefix("chatgpt_auth_") || actions.contains(action)
    }
    let addendum = try ExactJSON(data: Data(contentsOf: addendumURL)).array ?? []
    guard cases.count == 59, addendum.count == 37 else { throw CheckFailure.message("Expected 59 and 37 ChatGPT policy cases") }
    for row in cases + addendum {
        var request = row["request"]
        request["schema"] = .string("inku.model-catalog-request.v1")
        let answer = try ChatGPTPolicy.evaluate(request)
        guard policyMatches(answer, row["expect"]) else {
            throw CheckFailure.message("ChatGPT policy case \(row["name"].string ?? row["why"].string ?? "?") failed: \(answer.text)")
        }
    }
    print("ChatGPT policy passed: 59 shared and 37 addendum cases. No provider calls.")
}
