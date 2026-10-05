import Foundation
import XCTest
@testable import InkuHost

final class ChatGPTDecoderChecks: XCTestCase, @unchecked Sendable {
    private let arguments = "{\"seed\":18446744073709551615,\"text\":\"若葉e\u{301}\"}"
    private func item(_ arguments: String = "", namespace: String = "inku") -> ExactJSON {
        .object(["type": .string("function_call"), "id": .string("fc_fixture"), "call_id": .string("call_fixture"),
            "name": .string("submit_pipeline_response"), "namespace": .string(namespace), "arguments": .string(arguments)])
    }
    private func event(_ type: String, _ fields: [String: ExactJSON]) -> Data {
        var fields = fields; fields["type"] = .string(type)
        return Data(("event: " + type + "\r\ndata: " + ExactJSON.object(fields).text + "\r\n\r\n").utf8)
    }
    private var started: Data {
        event("response.created", ["response": .object(["id": .string("resp_fixture")])]) +
        event("response.output_item.added", ["item": item()])
    }
    private func completion(_ text: String, responseID: String = "resp_fixture") -> Data {
        event("response.completed", ["response": .object(["id": .string(responseID), "status": .string("completed"),
            "output": .array([.object(["type": .string("reasoning")]), item(text)])])])
    }
    private func assertCode(_ code: String, _ body: () throws -> Void) {
        XCTAssertThrowsError(try body()) { XCTAssertEqual(($0 as? HostError)?.code, code) }
    }

    // Failure: arbitrary network/UTF-8/CRLF boundaries alter exact tool arguments or a result is returned before completed inference.
    func testFragmentedSSEDeliversOneMatchingCompletedObjectWithoutRounding() throws {
        var decoder = ChatGPTResponseDecoder(argumentLimit: 512)
        let split = arguments.index(arguments.startIndex, offsetBy: 14)
        let stream = started +
            event("response.function_call_arguments.delta", ["item_id": .string("fc_fixture"), "delta": .string(String(arguments[..<split]))]) +
            event("response.function_call_arguments.delta", ["item_id": .string("fc_fixture"), "delta": .string(String(arguments[split...]))]) +
            event("response.function_call_arguments.done", ["item_id": .string("fc_fixture"), "arguments": .string(arguments)]) +
            event("response.output_item.done", ["item": item(arguments)]) + completion(arguments) + Data("data: [DONE]\n\n".utf8)
        for byte in stream { try decoder.feed(Data([byte])) }
        XCTAssertEqual(Array(try decoder.finish().utf8), Array(arguments.utf8))
        XCTAssertEqual(decoder.terminalResponse?["id"].string, "resp_fixture")
        XCTAssertEqual(try ExactJSON(data: Data(decoder.finish().utf8))["seed"].number, "18446744073709551615")
    }

    // Failure: partial arguments survive late quota/refusal/incomplete, wrong namespace/completion, or byte budget failure.
    func testUnsafePartialStreamsNeverDeliverAndKeepFixedFailureCodes() throws {
        let done = event("response.function_call_arguments.done", ["item_id": .string("fc_fixture"), "arguments": .string(arguments)])
        var incomplete = ChatGPTResponseDecoder(argumentLimit: 512)
        try incomplete.feed(started + done)
        assertCode("chatgpt_response_incomplete") { _ = try incomplete.finish() }
        var quota = ChatGPTResponseDecoder(argumentLimit: 512)
        try quota.feed(started + done)
        assertCode("subscription_sharing_usage_limit_exceeded") {
            try quota.feed(event("response.failed", ["response": .object(["error": .object(["code": .string("subscription_sharing_usage_limit_exceeded"), "message": .string("private raw text")])])]))
        }
        assertCode("subscription_sharing_usage_limit_exceeded") { _ = try quota.finish() }
        var refused = ChatGPTResponseDecoder(argumentLimit: 512)
        try refused.feed(started)
        assertCode("chatgpt_refused") { try refused.feed(event("response.refusal.delta", ["delta": .string("private raw text")])) }
        assertCode("chatgpt_refused") { _ = try refused.finish() }
        var wrong = ChatGPTResponseDecoder(argumentLimit: 512)
        assertCode("chatgpt_unexpected_tool") { try wrong.feed(event("response.output_item.added", ["item": item(namespace: "other")])) }
        var mismatch = ChatGPTResponseDecoder(argumentLimit: 512)
        try mismatch.feed(started + done)
        assertCode("chatgpt_response_invalid") { try mismatch.feed(completion("{}")) }
        var mismatchedResponse = ChatGPTResponseDecoder(argumentLimit: 512)
        try mismatchedResponse.feed(started + done)
        assertCode("chatgpt_response_invalid") { try mismatchedResponse.feed(completion(arguments, responseID: "resp_other")) }
        var tooLarge = ChatGPTResponseDecoder(argumentLimit: 8)
        try tooLarge.feed(started)
        assertCode("chatgpt_response_too_large") { try tooLarge.feed(done) }
        var completedThenQuota = ChatGPTResponseDecoder(argumentLimit: 512)
        try completedThenQuota.feed(started + done + completion(arguments))
        assertCode("subscription_sharing_usage_limit_exceeded") { try completedThenQuota.feed(event("error", ["code": .string("subscription_sharing_usage_limit_exceeded")])) }
        assertCode("subscription_sharing_usage_limit_exceeded") { _ = try completedThenQuota.finish() }
    }
    // Failure: a completed event with an empty summary, or assistant text beside the call, fails although Server delivers the finalized call.
    func testEmptySummaryAndAssistantTextFollowServer() throws {
        let finalized = started + event("response.output_item.done", ["item": item(arguments)])
        let message = ExactJSON.object(["type": .string("message"), "role": .string("assistant"),
            "content": .array([.object(["type": .string("output_text"), "text": .string("note")])])])
        for output: ExactJSON? in [nil, .null, .array([])] {
            var decoder = ChatGPTResponseDecoder(argumentLimit: 512)
            var response: [String: ExactJSON] = ["id": .string("resp_fixture"), "status": .string("completed")]
            if let output { response["output"] = output }
            try decoder.feed(finalized + event("response.completed", ["response": .object(response)]))
            XCTAssertEqual(try decoder.finish(), arguments)
        }
        var withText = ChatGPTResponseDecoder(argumentLimit: 512)
        try withText.feed(started + event("response.output_item.done", ["item": message]) + event("response.output_item.done", ["item": item(arguments)]) +
            event("response.completed", ["response": .object(["id": .string("resp_fixture"), "status": .string("completed"),
                "output": .array([message, item(arguments)])])]))
        XCTAssertEqual(try withText.finish(), arguments)
        var deltasOnly = ChatGPTResponseDecoder(argumentLimit: 512)
        try deltasOnly.feed(started + event("response.function_call_arguments.done", ["item_id": .string("fc_fixture"), "arguments": .string(arguments)]))
        assertCode("chatgpt_unexpected_tool") { try deltasOnly.feed(event("response.completed", ["response": .object(["status": .string("completed"), "output": .array([])])])) }
        var refusedPart = ChatGPTResponseDecoder(argumentLimit: 512)
        try refusedPart.feed(started)
        assertCode("chatgpt_refused") { try refusedPart.feed(event("response.output_item.done", ["item": .object(["type": .string("message"), "role": .string("assistant"),
            "content": .array([.object(["type": .string("refusal"), "refusal": .string("no")])])])])) }
        var otherItem = ChatGPTResponseDecoder(argumentLimit: 512)
        assertCode("chatgpt_unexpected_tool") { try otherItem.feed(event("response.output_item.added", ["item": .object(["type": .string("web_search_call"), "id": .string("ws")])])) }
    }
}
