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
    private func read(_ wire: Data, limit: Int = 512) throws -> ChatGPTWire.Stream {
        try ChatGPTWire.read(text: false, answerLimit: limit, wire: wire)
    }
    private func answer(_ wire: Data) throws -> String { try read(wire).result.get() }
    private func assertCode(_ code: String, _ wire: Data, limit: Int = 512, temporary: Bool? = nil, file: StaticString = #filePath, line: UInt = #line) {
        do {
            guard case .failure(let failure) = try read(wire, limit: limit).result else { return XCTFail("A failing stream answered", file: file, line: line) }
            XCTAssertEqual(failure.diagnostic.code, code, file: file, line: line)
            if let temporary { XCTAssertEqual(failure.diagnostic.action == "retry", temporary, file: file, line: line) }
        } catch { XCTFail("\(error)", file: file, line: line) }
    }

    // Failure: CRLF framing, [DONE] or a big integer alters exact tool arguments, or a result is returned before completed inference.
    func testWholeStreamDeliversOneMatchingCompletedObjectWithoutRounding() throws {
        let split = arguments.index(arguments.startIndex, offsetBy: 14)
        let stream = started +
            event("response.function_call_arguments.delta", ["item_id": .string("fc_fixture"), "delta": .string(String(arguments[..<split]))]) +
            event("response.function_call_arguments.delta", ["item_id": .string("fc_fixture"), "delta": .string(String(arguments[split...]))]) +
            event("response.function_call_arguments.done", ["item_id": .string("fc_fixture"), "arguments": .string(arguments)]) +
            event("response.output_item.done", ["item": item(arguments)]) + completion(arguments) + Data("data: [DONE]\n\n".utf8)
        let result = try read(stream)
        XCTAssertEqual(Array(try result.result.get().utf8), Array(arguments.utf8))
        XCTAssertEqual(result.terminal?["id"].string, "resp_fixture")
        XCTAssertEqual(try ExactJSON(data: Data(result.result.get().utf8))["seed"].number, "18446744073709551615")
    }

    // Failure: partial arguments survive late quota/refusal/incomplete, wrong namespace/completion, or byte budget failure.
    func testUnsafePartialStreamsNeverDeliverAndKeepFixedFailureCodes() throws {
        let done = event("response.function_call_arguments.done", ["item_id": .string("fc_fixture"), "arguments": .string(arguments)])
        // A stream that ends before completion is temporary, as Server classifies it.
        assertCode("chatgpt_response_incomplete", started + done, temporary: true)
        assertCode("subscription_sharing_usage_limit_exceeded", started + done +
            event("response.failed", ["response": .object(["error": .object(["code": .string("subscription_sharing_usage_limit_exceeded"), "message": .string("private raw text")])])]))
        assertCode("chatgpt_refused", started + event("response.refusal.delta", ["delta": .string("private raw text")]))
        assertCode("chatgpt_unexpected_tool", event("response.output_item.added", ["item": item(namespace: "other")]))
        assertCode("chatgpt_response_invalid", started + done + completion("{}"))
        assertCode("chatgpt_response_invalid", started + done + completion(arguments, responseID: "resp_other"))
        assertCode("chatgpt_response_too_large", started + done, limit: 8)
        assertCode("subscription_sharing_usage_limit_exceeded", started + done + completion(arguments) +
            event("error", ["code": .string("subscription_sharing_usage_limit_exceeded")]))
    }
    // Failure: a completed event with an empty summary, or assistant text beside the call, fails although Server delivers the finalized call.
    func testEmptySummaryAndAssistantTextFollowServer() throws {
        let finalized = started + event("response.output_item.done", ["item": item(arguments)])
        let message = ExactJSON.object(["type": .string("message"), "role": .string("assistant"),
            "content": .array([.object(["type": .string("output_text"), "text": .string("note")])])])
        for output: ExactJSON? in [nil, .null, .array([])] {
            var response: [String: ExactJSON] = ["id": .string("resp_fixture"), "status": .string("completed")]
            if let output { response["output"] = output }
            XCTAssertEqual(try answer(finalized + event("response.completed", ["response": .object(response)])), arguments)
        }
        XCTAssertEqual(try answer(started + event("response.output_item.done", ["item": message]) + event("response.output_item.done", ["item": item(arguments)]) +
            event("response.completed", ["response": .object(["id": .string("resp_fixture"), "status": .string("completed"),
                "output": .array([message, item(arguments)])])])), arguments)
        assertCode("chatgpt_unexpected_tool", started + event("response.function_call_arguments.done", ["item_id": .string("fc_fixture"), "arguments": .string(arguments)]) +
            event("response.completed", ["response": .object(["status": .string("completed"), "output": .array([])])]))
        assertCode("chatgpt_refused", started + event("response.output_item.done", ["item": .object(["type": .string("message"), "role": .string("assistant"),
            "content": .array([.object(["type": .string("refusal"), "refusal": .string("no")])])])]))
        assertCode("chatgpt_unexpected_tool", event("response.output_item.added", ["item": .object(["type": .string("web_search_call"), "id": .string("ws")])]))
    }
}
