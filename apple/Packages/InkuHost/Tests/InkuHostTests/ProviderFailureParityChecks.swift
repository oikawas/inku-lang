import Foundation
import InkuPersistence
import XCTest
@testable import InkuHost

private struct NoKeys: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}

private actor CountingHTTP: ProviderHTTPClient {
    private(set) var generations = 0
    private(set) var counts = 0
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse {
        let value: ExactJSON
        if request.url!.path.hasSuffix(":countTokens") {
            counts += 1; value = .object(["totalTokens": .integer(100)])
        } else if request.url!.path.hasSuffix(":generateContent") {
            generations += 1
            value = .object(["usageMetadata": .object(["promptTokenCount": .integer(85)]), "candidates": .array([.object(["content": .object(["parts": .array([
                .object(["functionCall": .object(["name": .string(ProviderWire.responseName), "args": .object(["composition": .string("fixture")])])])])])])])])
        } else {
            generations += 1
            value = .object(["choices": .array([.object(["message": .object(["content": .string("{\"composition\":\"fixture\"}")])])])])
        }
        onResponse(.init(status: 200, data: value.data, sent: true, complete: true, truncated: false))
        return .init(status: 200, data: value.data)
    }
}

private actor InFlightHTTP: ProviderHTTPClient {
    private(set) var current = 0
    private(set) var peak = 0
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse {
        current += 1; peak = max(peak, current)
        try await Task.sleep(for: .milliseconds(150))
        current -= 1
        let value: ExactJSON = .object(["choices": .array([.object(["message": .object(["content": .string("{\"composition\":\"fixture\"}")])])])])
        onResponse(.init(status: 200, data: value.data, sent: true, complete: true, truncated: false))
        return .init(status: 200, data: value.data)
    }
}

final class ProviderFailureParityChecks: XCTestCase, @unchecked Sendable {
    private var folder: URL!
    override func setUpWithError() throws {
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-failure-parity-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    }
    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: folder) }

    private static func action(_ id: String, timeout: String) -> Data {
        ExactJSON.object(["tag": .string("read_composition"), "identity": .object(["action_id": .string(id), "attempt": .integer(1), "request_digest": .string("d-" + id)]),
            "timeout_ms": .string(timeout), "payload": .object(["prompt": .object(["system": .string("s"), "message": .string("m"),
                "action_name": .string("read_composition"), "response_schema": .object(["type": .string("object")])])])]).data
    }
    private func perform(_ transport: URLSessionProviderTransport, _ provider: ProviderSettings, id: String, timeout: String = "2000") async throws -> ExactJSON {
        try ExactJSON(data: await transport.perform(action: Self.action(id, timeout: timeout),
            models: .init(stage1Model: provider.id + ":m", stage2Model: provider.id + ":m"), providers: [provider], credentials: NoKeys(), onBytes: { _ in }))
    }

    // Failure (D4): an oversized answer is retried as malformed_payload, and a zero timeout escapes as a schema
    // violation; Server returns provider_rejected and transport_timeout (measured with SingleAttemptProvider).
    func testOversizedAnswerAndZeroTimeoutFollowServer() async throws {
        let server = try await LoopbackHTTP([(200, #"{"choices":[{"message":{"content":""# + String(repeating: "x", count: 400) + #""}}]}"#)])
        let provider = ProviderSettings(id: "local", baseURL: URL(string: "http://127.0.0.1:\(server.port)/v1")!, requiresAPIKey: false)
        let transport = URLSessionProviderTransport(maximumResponseBytes: 64, usageURL: folder.appendingPathComponent("usage.json"), http: nil)
        let oversized = try await perform(transport, provider, id: "big")
        XCTAssertEqual(oversized["failure"].string, "provider_rejected")
        let zero = try await perform(transport, provider, id: "zero", timeout: "0")
        XCTAssertEqual(zero["tag"].string, "provider_failed")
        XCTAssertEqual(zero["failure"].string, "transport_timeout")
        XCTAssertEqual(server.requests, 1)
    }

    // Failure (D5): a full rate window ends the attempt at once instead of waiting it out as Server does, and a
    // Gemini daily refusal skips the countTokens call Server sends before admission.
    func testRateWaitRunsToTheAttemptDeadlineAndCountPrecedesDailyRefusal() async throws {
        let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let http = CountingHTTP()
        let transport = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("usage.json"), http: http, database: database)
        let minute = ProviderSettings(id: "minute", baseURL: URL(string: "https://fixture.invalid/v1")!, requiresAPIKey: false,
                                      rateLimits: .init(requestsPerMinute: 1, tokensPerMinute: 0, requestsPerDay: 0))
        let first = try await perform(transport, minute, id: "first")
        XCTAssertEqual(first["tag"].string, "composition_read")
        let began = ContinuousClock.now
        let waited = try await perform(transport, minute, id: "waited", timeout: "300")
        let elapsed = began.duration(to: .now)
        XCTAssertEqual(waited["failure"].string, "rate_limited")
        XCTAssertGreaterThanOrEqual(elapsed, .milliseconds(250))
        let generations = await http.generations
        XCTAssertEqual(generations, 1)

        let daily = ProviderSettings(id: "gemini-daily", kind: .gemini, baseURL: URL(string: "https://fixture.invalid")!, requiresAPIKey: false,
                                     rateLimits: .init(requestsPerMinute: 0, tokensPerMinute: 1_000, requestsPerDay: 1))
        let admitted = try await perform(transport, daily, id: "day-1")
        XCTAssertEqual(admitted["tag"].string, "composition_read")
        let refused = try await perform(transport, daily, id: "day-2")
        XCTAssertEqual(refused["failure"].string, "rate_limited")
        let counts = await http.counts, sent = await http.generations
        XCTAssertEqual(counts, 2)
        XCTAssertEqual(sent, 2)
    }

    // Failure (D7): three simultaneous Ollama Cloud requests are sent at once, where Server holds the third
    // until one of two slots is free; other providers are not slowed.
    func testOllamaCloudTakesTwoRequestsAtOnce() async throws {
        for (id, expected) in [("ollama-cloud", 2), ("ollama", 3)] {
            let http = InFlightHTTP()
            let transport = URLSessionProviderTransport(usageURL: folder.appendingPathComponent(id + ".json"), http: http,
                database: try InkuDatabase(url: folder.appendingPathComponent(id + ".sqlite")))
            let provider = ProviderSettings(id: id, baseURL: URL(string: "https://fixture.invalid/v1")!, requiresAPIKey: false)
            async let a = perform(transport, provider, id: id + "-a")
            async let b = perform(transport, provider, id: id + "-b")
            async let c = perform(transport, provider, id: id + "-c")
            let tags = try await [a, b, c].map { $0["tag"].string }
            XCTAssertEqual(tags, Array(repeating: "composition_read", count: 3))
            let peak = await http.peak
            XCTAssertEqual(peak, expected, id)
        }
    }
}
