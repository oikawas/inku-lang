import CryptoKit
import Foundation
import XCTest
@testable import InkuHost

final class GeminiSchemaOrderChecks: XCTestCase, @unchecked Sendable {
    // Failure (D10): the composition reading reaches Gemini with properties in name order, so the thesis is no
    // longer written first; Server writes them in propertyOrdering order.
    func testGeminiSchemaTextMatchesServerProjection() throws {
        let root = URL(fileURLWithPath: #filePath)
        let fixture = (0..<6).reduce(root) { url, _ in url.deletingLastPathComponent() }
            .appendingPathComponent("core/crates/inku-pipeline/tests/data/composition-reading-prompt-v1.json")
        let schema = try ExactJSON(data: Data(contentsOf: fixture))["response_schemas"]["3"]
        let provider = ProviderSettings(id: "gemini", kind: .gemini, baseURL: URL(string: "https://example.invalid")!, requiresAPIKey: false)
        let request = try ProviderWire.request(action: SchemaOrderFixture.action(schema), provider: provider, model: "fixture", maxTokens: 1024, key: nil)
        let tools = try ExactJSON.rawMember("tools", in: XCTUnwrap(request.httpBody))
        let tool = try XCTUnwrap(ExactJSON.rawElements(in: tools).first)
        let declarations = try ExactJSON.rawMember("functionDeclarations", in: tool)
        let declaration = try XCTUnwrap(ExactJSON.rawElements(in: declarations).first)
        let text = String(decoding: try ExactJSON.rawMember("parametersJsonSchema", in: declaration), as: UTF8.self)
        // Build1162: json.dumps(_gemini_json_schema(schema with core key order), ensure_ascii=False, separators=(",", ":")).
        let digest = SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(text.utf8.count, 2371)
        XCTAssertEqual(digest, "9132bb7ff8e5d9ec021b5c474bbaccb120cbdd90e09cab70d28cd72993336986")
        XCTAssertTrue(text.hasPrefix(#"{"properties":{"thesis":{"type":"string"},"roles":"#))
    }
}
