import Foundation
import XCTest
@testable import InkuHost

/// The core writes schema keys in name order; the reading schema's propertyOrdering says the order to send.
enum SchemaOrderFixture {
    static let string: ExactJSON = .object(["type": .string("string")])
    static let ordered: ExactJSON = .object(["type": .string("object"),
        "properties": .object(["relations": .object(["type": .string("array"), "items": .object(["type": .string("object"),
            "properties": .object(["layers": string, "side": string, "toward": string, "type": string]),
            "propertyOrdering": .array(["type", "layers", "side", "toward"].map { .string($0) })])]),
            "tension": string, "thesis": string]),
        "propertyOrdering": .array(["thesis", "tension", "relations"].map { .string($0) })])
    static let unordered: ExactJSON = .object(["type": .string("object"),
        "properties": .object(["ddl": string, "alpha": string]), "required": .array([.string("ddl")])])
    static let top = #""properties":{"thesis":{"type":"string"},"tension":{"type":"string"},"relations":{"items":{"#
    static let nested = #""properties":{"type":{"type":"string"},"layers":{"type":"string"},"side":{"type":"string"},"toward":{"type":"string"}}"#

    static func action(_ schema: ExactJSON) -> Data {
        ExactJSON.object(["tag": .string("read_composition"), "identity": .object(["action_id": .string("order-fixture"),
            "attempt": .integer(1), "request_digest": .string("digest")]), "timeout_ms": .string("2000"),
            "payload": .object(["prompt": .object(["system": .string("system"), "message": .string("message"),
                "action_name": .string("read_composition"), "response_schema": schema])])]).data
    }
}

final class SchemaPropertyOrderWireTests: XCTestCase {
    private static let paths: [(String, ProviderSettings, String)] = [
        ("openai-responses", ProviderSettings(id: "openai", baseURL: URL(string: "https://api.openai.com/v1")!, requiresAPIKey: false), "gpt-4.1"),
        ("chat-tools", ProviderSettings(id: "custom", baseURL: URL(string: "https://example.invalid/v1")!, requiresAPIKey: false), "model"),
        ("ollama-format", ProviderSettings(id: "ollama", baseURL: URL(string: "http://localhost:11434/v1")!, requiresAPIKey: false), "gemma4:31b"),
        ("mlx-format", ProviderSettings(id: "mlx-local", baseURL: URL(string: "http://127.0.0.1:8080/v1")!, apiProfile: "mlx", requiresAPIKey: false), "model"),
        ("anthropic", ProviderSettings(id: "anthropic", kind: .anthropic, baseURL: URL(string: "https://api.anthropic.com")!, requiresAPIKey: false), "claude"),
    ]

    // Failure: a dialect other than Gemini sent the reading schema's properties in the core's name order.
    func testEveryDialectSendsPropertiesInPropertyOrdering() throws {
        for (name, provider, model) in Self.paths {
            let request = try ProviderWire.request(action: SchemaOrderFixture.action(SchemaOrderFixture.ordered), provider: provider, model: model, maxTokens: 2048, key: nil)
            let text = String(decoding: try XCTUnwrap(request.httpBody), as: UTF8.self)
            XCTAssertTrue(text.contains(SchemaOrderFixture.top), name)
            XCTAssertTrue(text.contains(SchemaOrderFixture.nested), name)
        }
    }

    // Failure: moving body byte order to core changes the schema's contents.
    func testSchemasWithoutOrderingKeepTheirContents() throws {
        for (name, provider, model) in Self.paths {
            let request = try ProviderWire.request(action: SchemaOrderFixture.action(SchemaOrderFixture.unordered), provider: provider, model: model, maxTokens: 2048, key: nil)
            let body = try XCTUnwrap(request.httpBody)
            let json = try ExactJSON(data: body)
            let tool = json["tools"].array?.first ?? .null
            let schema = [tool["parameters"], tool["function"]["parameters"], tool["input_schema"],
                          json["response_format"]["json_schema"]["schema"]].first { $0.object != nil }
            XCTAssertEqual(schema, SchemaOrderFixture.unordered, name)
        }
    }
}
