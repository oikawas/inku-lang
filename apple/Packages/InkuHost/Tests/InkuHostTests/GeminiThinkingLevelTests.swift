import Foundation
import XCTest
@testable import InkuHost

final class GeminiThinkingLevelTests: XCTestCase {
    // Failure: a fixed minimal level is refused by Pro/3.8/2.5 models, while
    // flash-lite starts thinking unnecessarily when a thinkingConfig is sent.
    func testPipelineAndVisionSendServerThinkingLevels() throws {
        let cases: [(String, String?)] = [
            ("gemini-3.8-flash", "low"),
            ("gemini-3.6-flash", "minimal"),
            ("gemini-3.5-flash-lite", "minimal"),
            ("gemini-3.1-pro-preview", "low"),
            ("gemini-3-flash-preview", "minimal"),
            ("gemini-3-pro-preview", "low"),
            ("gemini-2.5-pro", "low"),
            ("gemini-2.5-flash", "low"),
            ("gemini-2.5-flash-lite", nil),
            ("gemma-4-31b-it", "minimal"),
            ("gemini-3.8-flash-preview", "low"),
            ("gemini-2.5-flash-preview-09-2025", "low"),
            ("gemini-2.5-flash-lite-preview-09-2025", nil),
            ("gemini-4-pro-preview", "low"),
            ("gemini-2.5-flash-liteish", "low"),
            ("gemini-3.8-flashish", "minimal"),
            ("gemini-3.1-prototype", "minimal"),
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
        for (name, level) in cases {
            for model in [name, "models/" + name] {
                let pipeline = try ProviderWire.request(action: action.data, provider: provider, model: model, maxTokens: 64, key: nil)
                let auxiliary = try AuxiliaryWire.request(prompt: vision, provider: provider, model: model, key: nil)
                for (request, tokens) in [(pipeline, 64), (auxiliary, 320)] {
                    let body = try ExactJSON(data: XCTUnwrap(request.httpBody))
                    let config = body["generationConfig"]
                    let expected: ExactJSON = level.map { .object(["thinkingLevel": .string($0)]) } ?? .null
                    XCTAssertEqual(config["thinkingConfig"], expected, model)
                    XCTAssertEqual(config["maxOutputTokens"], .integer(tokens), model)
                    if level == nil { XCTAssertFalse(try XCTUnwrap(config.object).keys.contains("thinkingConfig"), model) }
                }
            }
        }
    }
}
