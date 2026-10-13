import Foundation
import XCTest
@testable import InkuHost

final class GeminiThinkingLevelTests: XCTestCase {
    // Failure: newer models and latest aliases refuse minimal, image models
    // refuse any level, and thoughts consume the answer's output budget.
    func testPipelineAndVisionSendServerThinkingLevels() throws {
        let cases: [(String, String?)] = [
            ("gemini-3.8-flash", "low"),
            ("gemini-3.7-flash", "low"),
            ("gemini-flash-latest", "low"),
            ("gemini-pro-latest", "low"),
            ("gemini-3.6-flash", "minimal"),
            ("gemini-3.5-flash", "minimal"),
            ("gemini-3.5-flash-lite", "minimal"),
            ("gemini-flash-lite-latest", "minimal"),
            ("gemini-3.1-flash-lite", "minimal"),
            ("gemini-3.1-flash-lite-preview", "minimal"),
            ("gemini-3.1-flash-image", "minimal"),
            ("gemini-3.1-flash-image-preview", "minimal"),
            ("gemini-3.1-flash-lite-image", "minimal"),
            ("gemini-robotics-er-2-preview", "minimal"),
            ("nano-banana-pro-preview", "minimal"),
            ("gemini-nano-banana-2.1", "minimal"),
            ("gemini-3.1-pro-preview", "low"),
            ("gemini-3-flash-preview", "minimal"),
            ("gemini-3-pro-preview", "low"),
            ("gemini-2.5-pro", "low"),
            ("gemini-2.5-flash", "low"),
            ("gemini-2.5-flash-lite", nil),
            ("gemini-2.5-flash-image", nil),
            ("gemini-2.5-flash-image-preview", nil),
            ("antigravity-gemini-3.1-pro", nil),
            ("gemma-4-31b-it", "minimal"),
            ("gemini-3.8-flash-preview", "low"),
            ("gemini-2.5-flash-preview-09-2025", "low"),
            ("gemini-2.5-flash-lite-preview-09-2025", nil),
            ("gemini-4-pro-preview", "low"),
            ("gemini-2.5-flash-liteish", "low"),
            ("gemini-3.8-flashish", "low"),
            ("gemini-3.1-prototype", "low"),
            ("gemini-3.6-flash-preview", "low"),
            ("unknown-model", "low"),
        ]
        let provider = ProviderSettings(id: "gemini", kind: .gemini,
            baseURL: URL(string: "https://generativelanguage.invalid")!, requiresAPIKey: false)
        let action: ExactJSON = .object(["payload": .object(["prompt": .object([
            "system": .string("system"), "message": .string("message"),
            "action_name": .string("generate_normalized_ddl"),
            "response_schema": .object(["type": .string("object"), "properties": .object([:])]),
        ])])])
        let png = "data:image/png;base64," + Data([137, 80, 78, 71, 13, 10, 26, 10]).base64EncodedString()
        let vision = AuxiliaryPrompt(system: "system", message: "message", images: [png], temperature: 0.35, maximumTokens: 320)
        let demo = AuxiliaryPrompt(system: "system", message: "message", temperature: 0.9, maximumTokens: 180, purpose: .demo)
        for (name, level) in cases {
            for model in [name, "models/" + name] {
                let pipeline = try ProviderWire.request(action: action.data, provider: provider, model: model, maxTokens: 1024, key: nil)
                let auxiliary = try AuxiliaryWire.request(prompt: vision, provider: provider, model: model, key: nil)
                let instruction = try AuxiliaryWire.request(prompt: demo, provider: provider, model: model, key: nil)
                for (request, tokens) in [(pipeline, 1024), (auxiliary, 320), (instruction, 180)] {
                    let body = try ExactJSON(data: XCTUnwrap(request.httpBody))
                    let config = body["generationConfig"]
                    let expected: ExactJSON = level.map { .object(["thinkingLevel": .string($0)]) } ?? .null
                    XCTAssertEqual(config["thinkingConfig"], expected, model)
                    var expectedConfig: ExactJSON = .object(["maxOutputTokens": .integer(tokens + (level == nil ? 0 : 8192))])
                    if level != nil { expectedConfig["thinkingConfig"] = expected }
                    XCTAssertEqual(config, expectedConfig, model)
                    if level == nil { XCTAssertFalse(try XCTUnwrap(config.object).keys.contains("thinkingConfig"), model) }
                }
            }
        }
    }

    // Failure: a complete-looking function call is accepted even though Gemini
    // explicitly ended it at MAX_TOKENS.
    func testDrawingRejectsGeminiOutputCutOffEvenWithCompleteFunctionCall() throws {
        var response: ExactJSON = .object(["candidates": .array([.object([
            "finishReason": .string("MAX_TOKENS"),
            "content": .object(["parts": .array([.object(["functionCall": .object([
                "name": .string(ProviderWire.responseName), "args": .object(["ddl": .string("pond")]),
            ])])])]),
        ])])])
        XCTAssertThrowsError(try ProviderWire.responseText(response.data, kind: .gemini)) {
            XCTAssertEqual(($0 as? HostError)?.code, "malformed_payload")
        }
        var candidate = try XCTUnwrap(response["candidates"].array?.first)
        candidate["finishReason"] = .string("STOP")
        response["candidates"] = .array([candidate])
        XCTAssertEqual(try ProviderWire.responseText(response.data, kind: .gemini), candidate["content"]["parts"].array?.first?["functionCall"]["args"].text)
    }

    // Failure: Claude Sonnet 5 rejects the demo's temperature, or adaptive
    // thinking exhausts its 180-token instruction budget.
    func testClaudeDemoSendsNoTemperatureAndAddsServerThinkingRoom() throws {
        let provider = ProviderSettings(id: "claude", kind: .anthropic,
            baseURL: URL(string: "https://anthropic.invalid")!, requiresAPIKey: false)
        let demo = AuxiliaryPrompt(system: "system", message: "message", temperature: 0.9, maximumTokens: 180, purpose: .demo)
        let cases = [("claude-sonnet-5", 8372), ("claude-opus-5", 8372), ("claude-haiku-5", 8372),
                     ("claude-fable-5", 8372), ("claude-mythos-5", 8372), ("claude-mythos-preview", 8372),
                     ("claude-sonnet-5-latest", 8372), ("claude-sonnet-4-6", 180), ("claude-sonnet-50", 180)]
        for (model, tokens) in cases {
            let request = try AuxiliaryWire.request(prompt: demo, provider: provider, model: model, key: nil)
            let body = try ExactJSON(data: XCTUnwrap(request.httpBody))
            XCTAssertFalse(try XCTUnwrap(body.object).keys.contains("temperature"), model)
            XCTAssertEqual(body["max_tokens"], .integer(tokens), model)
        }
    }
}
