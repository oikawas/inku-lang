import Foundation
import XCTest
@testable import InkuHost

private struct NoCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}

final class AuxiliaryServerParityChecks: XCTestCase, @unchecked Sendable {
    private static let answer = #"{"choices":[{"message":{"role":"assistant","content":"a quiet pond"}}]}"#

    private func run(_ server: LoopbackHTTP, purpose: AuxiliaryPrompt.Purpose) async throws -> String {
        let provider = ProviderSettings(id: "local", baseURL: URL(string: "http://127.0.0.1:\(server.port)/v1")!, requiresAPIKey: false)
        let prompt = AuxiliaryPrompt(system: "s", message: "m", temperature: 0.9, maximumTokens: 16, timeoutSeconds: 10, purpose: purpose)
        return try await URLSessionProviderTransport().performAuxiliary(prompt: prompt, modelReference: "local:m",
            settings: HostSettings(providers: [provider]), credentials: NoCredentials(), onBytes: { _ in })
    }

    // Failure: a pooled connection from an earlier auxiliary request is reused (the -1005 candidate);
    // Server opens one HTTP client per request.
    func testEachAuxiliaryRequestOpensItsOwnConnection() async throws {
        let server = try await LoopbackHTTP([(200, Self.answer), (200, Self.answer)])
        _ = try await run(server, purpose: .vision)
        _ = try await run(server, purpose: .vision)
        XCTAssertEqual(server.requests, 2)
        XCTAssertEqual(server.connections, 2)
        // Control: one shared session does reuse the keep-alive connection this server offers.
        let control = try await LoopbackHTTP([(200, Self.answer), (200, Self.answer)])
        let shared = URLSession(configuration: .ephemeral)
        defer { shared.invalidateAndCancel() }
        for _ in 0..<2 {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:\(control.port)/v1/chat/completions")!)
            request.httpMethod = "POST"; request.httpBody = Data("{}".utf8)
            _ = try await shared.data(for: request)
        }
        XCTAssertEqual(control.connections, 1)
    }

    // Failure: the demo gives up on a transient 503 that Server's SDK retries, or retries what the SDK does not.
    func testDemoRetriesLikeTheSDKAndVisionDoesNot() async throws {
        let demo = try await LoopbackHTTP([(503, "{}"), (200, Self.answer)])
        let text = try await run(demo, purpose: .demo)
        XCTAssertEqual(text, "a quiet pond")
        XCTAssertEqual(demo.requests, 2)
        let rejected = try await LoopbackHTTP([(400, "{}"), (200, Self.answer)])
        do { _ = try await run(rejected, purpose: .demo); XCTFail("400 must not be retried") }
        catch { XCTAssertEqual((error as? HostError)?.code, "provider_rejected") }
        XCTAssertEqual(rejected.requests, 1)
        let vision = try await LoopbackHTTP([(503, "{}"), (200, Self.answer)])
        do { _ = try await run(vision, purpose: .vision); XCTFail("Vision has no retry") }
        catch { XCTAssertEqual((error as? HostError)?.code, "transport_unavailable") }
        XCTAssertEqual(vision.requests, 1)

        let failure = { (status: Int, header: Bool?, after: Double?) in HTTPFailure(status: status, retryAfter: 60, shouldRetry: header, serverDelay: after) }
        XCTAssertEqual(URLSessionProviderTransport.sdkRetryDelay(failure(409, nil, nil), retry: 1, kind: .openAICompatible, random: 0), 1.0)
        XCTAssertNil(URLSessionProviderTransport.sdkRetryDelay(failure(500, false, nil), retry: 0, kind: .anthropic))
        XCTAssertEqual(URLSessionProviderTransport.sdkRetryDelay(failure(400, true, 3), retry: 0, kind: .anthropic), 3)
        XCTAssertEqual(URLSessionProviderTransport.sdkRetryDelay(failure(429, nil, 90), retry: 0, kind: .anthropic, random: 0), 0.5)
        XCTAssertEqual(URLSessionProviderTransport.sdkRetryDelay(failure(429, nil, 90), retry: 0, kind: .openAICompatible), 90)
        XCTAssertNil(URLSessionProviderTransport.sdkRetryDelay(failure(429, true, 130), retry: 0, kind: .openAICompatible))
        XCTAssertEqual(URLSessionProviderTransport.sdkRetryDelay(URLError(.networkConnectionLost), retry: 0, kind: .anthropic, random: 0), 0.5)
    }

    // Failure: a null or absent answer fails as malformed where Server reads empty text, or the demo drops
    // Gemini thought text that Server's demo keeps.
    func testAnswerTextFollowsServerReaders() throws {
        func text(_ raw: String, _ kind: ProviderKind, _ purpose: AuxiliaryPrompt.Purpose = .vision) throws -> String {
            try AuxiliaryWire.responseText(Data(raw.utf8), kind: kind, purpose: purpose)
        }
        XCTAssertEqual(try text(#"{"choices":[{"message":{"content":null}}]}"#, .openAICompatible), "")
        XCTAssertEqual(try text(#"{"id":"x"}"#, .anthropic), "")
        XCTAssertEqual(try text(#"{"promptFeedback":{}}"#, .gemini), "")
        let thought = #"{"candidates":[{"content":{"parts":[{"text":"plan","thought":true},{"text":"pond"}]}}]}"#
        XCTAssertEqual(try text(thought, .gemini), "pond")
        XCTAssertEqual(try text(thought, .gemini, .demo), "plan\npond")
        XCTAssertThrowsError(try text(#"{"choices":[]}"#, .openAICompatible))
    }

    // Failure: the advice and colophon context differs from Server's json.dumps(sort_keys=True) text.
    func testContextJSONMatchesPythonDumps() throws {
        let value = try ExactJSON(data: Data(#"{"user_direction":"「線」\"q\" \\ \n\t\b\f\u0001\#u{7F}\#u{2028}/","instruction":"若葉","allowed_suggested_kinds":["layout_change"],"constraints":{"no_score":true,"b":null,"n":[1,{}],"z":[]},"é":1,"Z":2}"#.utf8))
        // Captured from Python 3 json.dumps(value, ensure_ascii=False, sort_keys=True).
        let python = #"{"Z": 2, "allowed_suggested_kinds": ["layout_change"], "constraints": {"b": null, "n": [1, {}], "no_score": true, "z": []}, "instruction": "若葉", "user_direction": "「線」\"q\" \\ \n\t\b\f\u0001\#u{7F}\#u{2028}/", "é": 1}"#
        XCTAssertEqual(value.pythonText, python)
    }
}
