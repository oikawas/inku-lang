import Foundation
import XCTest
@testable import InkuHost

final class ProviderOutputLimitTests: XCTestCase {
    private static let anthropic = ProviderSettings(id: "anthropic", kind: .anthropic, baseURL: URL(string: "https://api.anthropic.com")!, requiresAPIKey: false)

    // Failure: Claude 5 spent the drawing or Vision budget thinking before it answered, or Claude 4 got room it does not use.
    func testClaudeFiveDrawingAndVisionLeaveRoomForThinking() throws {
        let vision = AuxiliaryPrompt(system: "system", message: "message", images: [], temperature: 0.35, maximumTokens: 320)
        for (model, room) in [("claude-sonnet-5", 8192), ("claude-opus-5-5", 8192), ("claude-mythos-preview", 8192), ("claude-sonnet-4-5", 0)] {
            let drawing = try ProviderWire.request(action: SchemaOrderFixture.action(SchemaOrderFixture.unordered), provider: Self.anthropic,
                                                   model: model, maxTokens: 2048, key: nil)
            XCTAssertEqual(try ExactJSON(data: XCTUnwrap(drawing.httpBody))["max_tokens"], .integer(2048 + room), model)
            let advice = try AuxiliaryWire.request(prompt: vision, provider: Self.anthropic, model: model, key: nil)
            XCTAssertEqual(try ExactJSON(data: XCTUnwrap(advice.httpBody))["max_tokens"], .integer(320 + room), model)
        }
    }

    // Failure: a Claude tool call stopped at max_tokens was taken as the whole answer.
    func testClaudeAnswerCutAtMaxTokensIsRefused() throws {
        var response: ExactJSON = .object(["stop_reason": .string("max_tokens"), "content": .array([
            .object(["type": .string("thinking"), "thinking": .string("…")]),
            .object(["type": .string("tool_use"), "name": .string(ProviderWire.responseName), "input": .object(["ddl": .string("pond")])]),
        ]), "usage": .object(["output_tokens": .integer(10240)])])
        XCTAssertThrowsError(try ProviderWire.responseText(response.data, kind: .anthropic)) {
            XCTAssertEqual(($0 as? HostError)?.code, "malformed_payload")
        }
        response["stop_reason"] = .string("tool_use")
        XCTAssertEqual(try ProviderWire.responseText(response.data, kind: .anthropic), #"{"ddl":"pond"}"#)
    }

    // Failure: the cut-off record left out or misread a field Server logs.
    func testCutOffRecordsMatchServerFields() throws {
        let claude: ExactJSON = .object(["stop_reason": .string("max_tokens"), "usage": .object(["output_tokens": .integer(2048)]),
            "content": .array([.object(["type": .string("redacted_thinking")]), .object(["type": .string("text"), "text": .string("{")])])])
        XCTAssertEqual(ProviderOutputLimit.record(claude, kind: .anthropic, responses: false), .object([
            "stop_reason": .string("max_tokens"), "output_tokens": .integer(2048), "thinking_blocks": .integer(1),
            "has_text": .bool(true), "has_tool_use": .bool(false)]))
        let gemini: ExactJSON = .object(["candidates": .array([.object(["finishReason": .string("MAX_TOKENS"), "content": .object(["parts": .array([
            .object(["text": .string("plan"), "thought": .bool(true)]), .object(["functionCall": .object(["name": .string("x")])])])])])]),
            "usageMetadata": .object(["candidatesTokenCount": .integer(12), "thoughtsTokenCount": .integer(8180)])])
        XCTAssertEqual(ProviderOutputLimit.record(gemini, kind: .gemini, responses: false), .object([
            "finish_reason": .string("MAX_TOKENS"), "output_tokens": .integer(12), "thought_tokens": .integer(8180),
            "has_text": .bool(false), "has_function_call": .bool(true)]))
        let responses: ExactJSON = .object(["status": .string("incomplete"), "incomplete_details": .object(["reason": .string("max_output_tokens")]),
            "output": .array([.object(["type": .string("reasoning")])]),
            "usage": .object(["output_tokens": .integer(25256), "output_tokens_details": .object(["reasoning_tokens": .integer(25256)])])])
        XCTAssertEqual(ProviderOutputLimit.record(responses, kind: .openAICompatible, responses: true), .object([
            "incomplete_reason": .string("max_output_tokens"), "output_tokens": .integer(25256), "reasoning_tokens": .integer(25256),
            "has_text": .bool(false), "has_function_call": .bool(false)]))
        let chat: ExactJSON = .object(["choices": .array([.object(["finish_reason": .string("length"),
            "message": .object(["reasoning_content": .string("…"), "content": .null])])]), "usage": .object(["completion_tokens": .integer(2048)])])
        let record = try XCTUnwrap(ProviderOutputLimit.record(chat, kind: .openAICompatible, responses: false))
        XCTAssertEqual(record, .object(["finish_reason": .string("length"), "output_tokens": .integer(2048), "reasoning_tokens": .null,
            "has_reasoning": .bool(true), "has_text": .bool(false), "has_tool_call": .bool(false)]))
        XCTAssertNil(ProviderOutputLimit.record(.object(["stop_reason": .string("end_turn")]), kind: .anthropic, responses: false))
        // pipeline_provider: json.dumps(..., sort_keys=True, separators=(",", ":")).
        XCTAssertEqual(ProviderOutputLimit.line(action: "generate_normalized_ddl", provider: "custom", model: "m",
                                                outputBudget: .integer(2048), cut: record),
            #"provider_output_limit {"action":"generate_normalized_ddl","finish_reason":"length","has_reasoning":true,"has_text":false,"has_tool_call":false,"max_tokens":2048,"model":"m","output_tokens":2048,"provider":"custom","reasoning_tokens":null}"#)
    }
}
