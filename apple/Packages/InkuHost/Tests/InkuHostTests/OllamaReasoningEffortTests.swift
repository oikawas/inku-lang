import Foundation
import XCTest
@testable import InkuHost

final class OllamaReasoningEffortTests: XCTestCase {
    // Failure: none leaves gpt-oss reasoning through the answer budget, and
    // Vision/demo omit the thinking controls the drawing pipeline sends.
    func testDrawingVisionAndDemoSendServerOllamaSampling() throws {
        let action: ExactJSON = .object(["payload": .object(["prompt": .object([
            "system": .string("system"), "message": .string("message"),
            "action_name": .string("generate_normalized_ddl"),
            "response_schema": .object(["type": .string("object"), "properties": .object([:])]),
        ])])])
        let png = "data:image/png;base64," + Data([137, 80, 78, 71, 13, 10, 26, 10]).base64EncodedString()
        let vision = AuxiliaryPrompt(system: "system", message: "message", images: [png], temperature: 0.35, maximumTokens: 320)
        let demo = AuxiliaryPrompt(system: "system", message: "message", temperature: 0.9, maximumTokens: 180, purpose: .demo)
        let cases = [("gpt-oss:20b", "low", 8192), ("gpt-oss:120b", "low", 8192),
                     ("gpt-oss", "low", 8192), ("gpt-oss-120b", "low", 8192),
                     ("gemma4:31b", "none", 0), ("gpt-ossish:20b", "none", 0), ("openai/gpt-oss-120b", "none", 0)]
        for id in ["ollama", "ollama-cloud", "nvidia"] {
            let base = id == "ollama" ? "http://localhost:11434/v1" : "https://\(id).invalid/v1"
            let provider = ProviderSettings(id: id, baseURL: URL(string: base)!, requiresAPIKey: false)
            for (model, effort, room) in cases {
                let pipeline = try ProviderWire.request(action: action.data, provider: provider, model: model, maxTokens: 2048, key: nil)
                let advice = try AuxiliaryWire.request(prompt: vision, provider: provider, model: model, key: nil)
                let instruction = try AuxiliaryWire.request(prompt: demo, provider: provider, model: model, key: nil)
                for (request, tokens, temperature) in [(pipeline, 2048, "0.3"), (advice, 320, "0.35"), (instruction, 180, "0.9")] {
                    let body = try ExactJSON(data: XCTUnwrap(request.httpBody))
                    let expectedRoom = id == "nvidia" ? 0 : room
                    XCTAssertEqual(body["max_tokens"], .integer(tokens + expectedRoom), "\(id):\(model)")
                    XCTAssertEqual(body["reasoning_effort"], id == "nvidia" ? .null : .string(effort), "\(id):\(model)")
                    XCTAssertEqual(body["temperature"], .number(temperature), "\(id):\(model)")
                }
            }
        }
    }

    // Failure: an answer stopped at length is used when content or a tool call
    // looks complete; the malformed_payload code must retain the retry route.
    func testDrawingRejectsLengthForReasoningTextAndToolCalls() throws {
        let answer = #"{"ddl":"pond"}"#
        let messages: [ExactJSON] = [
            .object(["content": .null, "reasoning": .string("unfinished thought")]),
            .object(["content": .string(answer)]),
            .object(["tool_calls": .array([.object(["function": .object([
                "name": .string(ProviderWire.responseName), "arguments": .string(answer),
            ])])])]),
        ]
        for message in messages {
            var response: ExactJSON = .object([
                "choices": .array([.object(["finish_reason": .string("length"), "message": message])]),
                "usage": .object(["completion_tokens": .integer(2048), "completion_tokens_details": .object(["reasoning_tokens": .integer(2048)])]),
            ])
            XCTAssertThrowsError(try ProviderWire.responseText(response.data, kind: .openAICompatible)) {
                XCTAssertEqual(($0 as? HostError)?.code, "malformed_payload")
            }
            if message["reasoning"] == .null {
                response["choices"] = .array([.object(["finish_reason": .string("stop"), "message": message])])
                XCTAssertEqual(try ProviderWire.responseText(response.data, kind: .openAICompatible), answer)
            }
        }
    }
}
