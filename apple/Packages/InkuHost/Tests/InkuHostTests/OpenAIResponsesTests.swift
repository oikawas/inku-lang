import Foundation
import InkuPersistence
import XCTest
@testable import InkuHost

final class OpenAIResponsesTests: XCTestCase, @unchecked Sendable {
    private static let action: Data = ExactJSON.object([
        "tag": .string("generate_normalized_ddl"),
        "identity": .object(["action_id": .string("openai-fixture"), "attempt": .integer(1), "request_digest": .string("digest")]),
        "timeout_ms": .string("2000"), "payload": .object(["prompt": .object([
            "system": .string("system"), "message": .string("message"), "action_name": .string("generate_normalized_ddl"),
            "response_schema": .object(["type": .string("object"), "properties": .object(["ddl": .object(["type": .string("string")])])]),
        ])]),
    ]).data
    private static let provider = ProviderSettings(id: "openai", baseURL: URL(string: "https://api.openai.com/v1")!,
        requiresAPIKey: false, rateLimits: .init(requestsPerMinute: 0, tokensPerMinute: 0, requestsPerDay: 0))
    private static let arguments = #"{"ddl":"pond"}"#
    private static let call: ExactJSON = .object(["type": .string("function_call"), "name": .string(ProviderWire.responseName),
        "arguments": .string(arguments)])

    // Failure: GPT-6 tool requests go to Chat Completions or carry unsupported
    // reasoning/sampling, while auxiliary requests need their Chat dialect.
    func testOfficialAPIUsesResponsesOnlyForDrawingAndServerSamplingForAllPaths() throws {
        let cases: [(String, String?, Int)] = [
            ("gpt-4.1", nil, 0), ("gpt-5.1", "none", 0), ("gpt-5.6-luna", "none", 0),
            ("gpt-6-luna", "none", 0), ("gpt-6-sol", "none", 0), ("gpt-6-sol-latest", "none", 0),
            ("gpt-6.1-sol", "low", 25000), ("gpt-6-astra", "low", 25000),
            ("gpt-5", "low", 25000), ("o3", "low", 25000), ("o4-mini", "low", 25000), ("gpt-6-lunaish", "low", 25000),
        ]
        let schema = try ExactJSON(data: Self.action)["payload"]["prompt"]["response_schema"]
        for (model, effort, room) in cases {
            let drawing = try ProviderWire.request(action: Self.action, provider: Self.provider, model: model, maxTokens: 2048, key: nil)
            let body = try ExactJSON(data: XCTUnwrap(drawing.httpBody))
            XCTAssertEqual(drawing.url?.path, "/v1/responses", model)
            var expected: ExactJSON = .object([
                "model": .string(model), "store": .bool(false), "instructions": .string("system"),
                "input": .array([.object(["role": .string("user"), "content": .string("message")])]),
                "tools": .array([.object(["type": .string("function"), "name": .string(ProviderWire.responseName),
                    "description": .string("Submit the requested pipeline response."), "parameters": schema, "strict": .bool(false)])]),
                "tool_choice": .string("required"), "parallel_tool_calls": .bool(false), "max_output_tokens": .integer(2048 + room),
            ])
            if let effort { expected["reasoning"] = .object(["effort": .string(effort)]) }
            else { expected["temperature"] = .number("0.3") }
            XCTAssertEqual(body, expected, model)
            for (purpose, tokens, temperature) in [(AuxiliaryPrompt.Purpose.vision, 320, "0.35"), (.demo, 180, "0.9")] {
                let prompt = AuxiliaryPrompt(system: "s", message: "m", temperature: Double(temperature)!, maximumTokens: tokens, purpose: purpose)
                let request = try AuxiliaryWire.request(prompt: prompt, provider: Self.provider, model: model, key: nil)
                let auxiliary = try ExactJSON(data: XCTUnwrap(request.httpBody))
                XCTAssertEqual(request.url?.path, "/v1/chat/completions", model)
                XCTAssertEqual(auxiliary["max_completion_tokens"], .integer(tokens + room), model)
                XCTAssertEqual(auxiliary["reasoning_effort"], effort.map(ExactJSON.string) ?? .null, model)
                XCTAssertEqual(auxiliary["temperature"], effort == nil ? .number(temperature) : .null, model)
            }
        }
        let custom = ProviderSettings(id: "openai", baseURL: URL(string: "https://api.openai.com.invalid/v1")!, requiresAPIKey: false)
        let request = try ProviderWire.request(action: Self.action, provider: custom, model: "gpt-6.1-sol", maxTokens: 2048, key: nil)
        let body = try ExactJSON(data: XCTUnwrap(request.httpBody))
        XCTAssertEqual(request.url?.path, "/v1/chat/completions")
        XCTAssertEqual(body["max_tokens"], .integer(2048))
        XCTAssertEqual(body["reasoning_effort"], .null)
        XCTAssertEqual(body["tools"].array?.first?["function"]["parameters"], schema)
    }

    // Failure: Responses output is read as choices, incomplete output is used,
    // or an ambiguous/unexpected function call bypasses the response contract.
    func testTransportReadsOnlyCompletedResponsesWithOneExpectedCallOrText() async throws {
        let text: ExactJSON = .object(["type": .string("message"), "content": .array([
            .object(["type": .string("output_text"), "text": .string("pond ")]),
            .object(["type": .string("output_text"), "text": .string("at dusk")]),
        ])])
        var wrong = Self.call; wrong["name"] = .string("unexpected")
        var badArguments = Self.call; badArguments["arguments"] = .object([:])
        let cases: [(ExactJSON, String?)] = [
            (.object(["status": .string("completed"), "output": .array([.object(["type": .string("reasoning")]), Self.call])]), Self.arguments),
            (.object(["status": .string("completed"), "output": .array([text])]), "pond at dusk"),
            (.object(["status": .string("completed"), "output": .array([Self.call, Self.call])]), nil),
            (.object(["status": .string("completed"), "output": .array([wrong, text])]), nil),
            (.object(["status": .string("completed"), "output": .array([badArguments])]), nil),
            (.object(["status": .string("completed"), "output": .object([:])]), nil),
            (.object(["status": .string("completed"), "output": .array([])]), nil),
            (.object(["status": .string("failed"), "output": .array([Self.call])]), nil),
            (.object(["output": .array([Self.call])]), nil),
            (.object(["status": .string("incomplete"), "incomplete_details": .object(["reason": .string("max_output_tokens")]),
                "output": .array([Self.call, text]), "usage": .object(["output_tokens": .integer(25256),
                    "output_tokens_details": .object(["reasoning_tokens": .integer(25200)])])]), nil),
        ]
        for (raw, answer) in cases {
            let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-openai-response-" + UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: folder) }
            let http = OpenAIResponseHTTP(data: raw.data)
            let transport = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("usage.json"), http: http)
            let data = try await transport.perform(action: Self.action, models: .init(stage1Model: "openai:gpt-6.1-sol"),
                providers: [Self.provider], credentials: OpenAIResponseCredentials(), onBytes: { _ in })
            let result = try ExactJSON(data: data)
            if let answer {
                XCTAssertEqual(result["tag"].string, "normalized_ddl_generated")
                XCTAssertEqual(result["response"].string, answer)
            } else {
                XCTAssertEqual(result["tag"].string, "provider_failed")
                XCTAssertEqual(result["failure"].string, "malformed_payload")
            }
        }
    }

    // Failure: Responses input_tokens is missed by the real transport's TPM
    // settlement, leaving its reservation unknown despite reported usage.
    func testResponsesUsageReachesRateSettlementAndObservation() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-openai-usage-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        var provider = Self.provider; provider.rateLimits = .init(requestsPerMinute: 0, tokensPerMinute: 100000, requestsPerDay: 0)
        let raw: ExactJSON = .object(["status": .string("completed"), "output": .array([Self.call]),
            "usage": .object(["input_tokens": .integer(12), "prompt_tokens": .integer(999), "output_tokens": .integer(7), "total_tokens": .integer(19)])])
        let http = OpenAIResponseHTTP(data: raw.data)
        let transport = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("usage.json"), http: http, database: database)
        let sink = OpenAIResponseObservationSink()
        let data = try await transport.performObserved(action: Self.action, models: .init(stage1Model: "openai:gpt-6.1-sol"),
            providers: [provider], credentials: OpenAIResponseCredentials(), observation: .init(),
            willSend: { await sink.save($0) }, didFinish: { await sink.save($0) }, onBytes: { _ in })
        XCTAssertEqual(try ExactJSON(data: data)["response"].string, Self.arguments)
        let optionalState = try await database.providerRateState(providerID: provider.id)
        let state = try XCTUnwrap(optionalState)
        XCTAssertEqual(state.events.last?.tokens, 12)
        XCTAssertEqual(state.notBefore, 0)
        let records = await sink.records
        XCTAssertEqual(records.last?.metric.usage, ProviderUsage(inputTokens: 12, outputTokens: 7, totalTokens: 19))
        let request = await http.request
        XCTAssertEqual(request?.url?.path, "/v1/responses")
    }
}

private struct OpenAIResponseCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}
private actor OpenAIResponseHTTP: ProviderHTTPClient {
    let data: Data
    private(set) var request: URLRequest?
    init(data: Data) { self.data = data }
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse {
        self.request = request
        onResponse(.init(status: 200, data: data, sent: true, complete: true, truncated: false))
        onBytes(data.count)
        return .init(status: 200, data: data)
    }
}
private actor OpenAIResponseObservationSink {
    private(set) var records: [ProviderAttemptObservation] = []
    func save(_ value: ProviderAttemptObservation) { records.append(value) }
}
