import Foundation
import XCTest
@testable import InkuHost

final class NIMGemmaThinkingTests: XCTestCase {
    // Failure: NIM's Gemma 4 keeps thinking on drawing, Vision and demo requests
    // because its chat-template switch is absent from the outgoing JSON.
    func testOnlyNIMGemma4DisablesThinkingInAllThreeRequests() throws {
        let action: ExactJSON = .object(["payload": .object(["prompt": .object([
            "system": .string("system"), "message": .string("message"),
            "action_name": .string("generate_normalized_ddl"),
            "response_schema": .object(["type": .string("object"), "properties": .object([:])]),
        ])])])
        let png = "data:image/png;base64," + Data([137, 80, 78, 71, 13, 10, 26, 10]).base64EncodedString()
        let vision = AuxiliaryPrompt(system: "system", message: "message", images: [png], temperature: 0.35, maximumTokens: 320)
        let demo = AuxiliaryPrompt(system: "system", message: "message", temperature: 0.9, maximumTokens: 180, purpose: .demo)
        let cases = [("google/gemma-4-31b-it", true), ("google/gemma4-31b-it", true),
                     ("google/GEMMA_4_31B_IT", true), ("gemma-4", true),
                     ("meta/llama-3.2-90b-vision-instruct", false), ("google/gemma-3n-e4b-it", false),
                     ("google/gemma-40-31b-it", false), ("gemma-4/vendor-model", false), ("google/gemma-4/", false)]
        for id in ["nvidia", "other"] {
            let provider = ProviderSettings(id: id, baseURL: URL(string: "https://integrate.api.nvidia.invalid/v1")!, requiresAPIKey: false)
            for (model, gemma4) in cases {
                let drawing = try ProviderWire.request(action: action.data, provider: provider, model: model, maxTokens: 2048, key: nil)
                let advice = try AuxiliaryWire.request(prompt: vision, provider: provider, model: model, key: nil)
                let instruction = try AuxiliaryWire.request(prompt: demo, provider: provider, model: model, key: nil)
                for (request, tokens, temperature) in [(drawing, 2048, "0.3"), (advice, 320, "0.35"), (instruction, 180, "0.9")] {
                    let body = try ExactJSON(data: XCTUnwrap(request.httpBody))
                    if id == "nvidia" && gemma4 {
                        XCTAssertEqual(body["chat_template_kwargs"], .object(["enable_thinking": .bool(false)]), model)
                    } else {
                        XCTAssertFalse(try XCTUnwrap(body.object).keys.contains("chat_template_kwargs"), "\(id):\(model)")
                    }
                    XCTAssertEqual(body["max_tokens"], .integer(tokens), model)
                    XCTAssertEqual(body["temperature"], .number(temperature), model)
                    XCTAssertEqual(body["extra_body"], .null, model)
                    XCTAssertEqual(body["enable_thinking"], .null, model)
                }
            }
        }
    }
}
