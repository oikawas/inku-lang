import Foundation
import Network
import XCTest
@testable import InkuHost

private struct NoCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}

/// A keep-alive HTTP/1.1 server on 127.0.0.1 that answers scripted statuses and counts TCP connections.
private final class LoopbackHTTP: @unchecked Sendable {
    private let listener: NWListener
    private let queue = DispatchQueue(label: "inku.loopback.http")
    private let lock = NSLock()
    private var script: [(status: Int, body: String)]
    private var connectionCount = 0
    private var requestCount = 0
    var connections: Int { lock.withLock { connectionCount } }
    var requests: Int { lock.withLock { requestCount } }
    private(set) var port: UInt16 = 0

    init(_ script: [(Int, String)]) async throws {
        self.script = script.map { (status: $0.0, body: $0.1) }
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: .any)
        listener = try NWListener(using: parameters)
        listener.newConnectionHandler = { [unowned self] connection in
            self.lock.withLock { self.connectionCount += 1 }
            connection.start(queue: self.queue)
            self.receive(connection, buffer: Data())
        }
        port = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<UInt16, any Error>) in
            // State updates arrive on the serial queue, so the flag needs no lock.
            final class Once: @unchecked Sendable { var done = false }
            let once = Once()
            listener.stateUpdateHandler = { [listener] state in
                guard !once.done else { return }
                switch state {
                case .ready: once.done = true; continuation.resume(returning: listener.port!.rawValue)
                case .failed(let error): once.done = true; continuation.resume(throwing: error)
                default: break
                }
            }
            listener.start(queue: queue)
        }
    }
    deinit { listener.cancel() }

    private func receive(_ connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [self] data, _, complete, error in
            var buffer = buffer + (data ?? Data())
            while let end = buffer.range(of: Data("\r\n\r\n".utf8)) {
                let head = String(decoding: buffer[..<end.lowerBound], as: UTF8.self).lowercased()
                let length = head.split(separator: "\r\n").first { $0.hasPrefix("content-length:") }
                    .flatMap { Int($0.dropFirst(15).trimmingCharacters(in: .whitespaces)) } ?? 0
                guard buffer.distance(from: buffer.startIndex, to: end.upperBound) + length <= buffer.count else { break }
                buffer = Data(buffer[buffer.index(end.upperBound, offsetBy: length)...])
                let reply = lock.withLock { () -> (status: Int, body: String) in
                    requestCount += 1
                    return script.isEmpty ? (500, "{}") : script.removeFirst()
                }
                let body = Data(reply.body.utf8)
                let header = "HTTP/1.1 \(reply.status) Fixture\r\nContent-Type: application/json\r\nContent-Length: \(body.count)\r\nConnection: keep-alive\r\n\r\n"
                connection.send(content: Data(header.utf8) + body, completion: .contentProcessed { _ in })
            }
            if complete || error != nil { connection.cancel() } else { receive(connection, buffer: buffer) }
        }
    }
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
