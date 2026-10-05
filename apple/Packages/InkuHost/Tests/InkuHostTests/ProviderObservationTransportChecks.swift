import Foundation
import XCTest
@testable import InkuHost

final class ProviderObservationTransportChecks: XCTestCase, @unchecked Sendable {
    // Failure: a refused connection loses its OS cause, or an ordinary HTTP failure
    // persists a credential/body instead of bounded diagnostics. No real HTTP is used.
    func testSafeFailureDiagnosticsWithoutRawCapture() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-provider-failure-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let models = ModelSelection(stage1Model: "fixture:offered", stage2Model: "fixture:unused")
        let action = Self.action(secret: "fixture-system")
        let connectionSink = ObservationSink(url: folder.appendingPathComponent("connection.json"))
        let connection = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("connection-usage.json"),
            http: ObservationCannotConnectHTTP())
        let local = ProviderSettings(id: "fixture", baseURL: URL(string: "http://127.0.0.1:1/private-path")!, requiresAPIKey: false)
        let failed = try ExactJSON(data: await connection.performObserved(action: action, models: models, providers: [local],
            credentials: ObservationCredentials(secret: nil), observation: .init(),
            willSend: { try await connectionSink.save($0) }, didFinish: { try await connectionSink.save($0) }, onBytes: { _ in }))
        XCTAssertEqual(failed["tag"].string, "provider_failed")
        XCTAssertEqual(failed["failure"].string, "transport_unavailable")
        let connectionRecord = try JSONDecoder().decode(ProviderAttemptObservation.self, from: Data(contentsOf: connectionSink.url))
        let network = try XCTUnwrap(connectionRecord.metric.diagnostic)
        XCTAssertEqual(network.kind, .network)
        XCTAssertEqual(network.errorDomain, NSURLErrorDomain)
        XCTAssertEqual(network.errorCode, URLError.cannotConnectToHost.rawValue)
        XCTAssertEqual(network.reason, "Could not connect to the provider host.")
        XCTAssertEqual(network.endpoint, "http://127.0.0.1:1")
        XCTAssertFalse(connectionRecord.metric.sent)
        XCTAssertNil(connectionRecord.metric.httpStatus)
        XCTAssertNil(connectionRecord.raw)

        // The old on-disk metric has no diagnostic member, rather than a null value.
        var legacy = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(connectionRecord.metric)) as? [String: Any])
        legacy.removeValue(forKey: "diagnostic")
        XCTAssertNil(try JSONDecoder().decode(ProviderAttemptMetric.self, from: JSONSerialization.data(withJSONObject: legacy)).diagnostic)

        let secret = "fixture-key-quote\"-slash\\-end"
        let secretLike = "AIzaFixtureSecret123456"
        let refusalBody = ExactJSON.object(["error": .object(["code": .string("invalid-" + secret),
            "type": .string("authentication_error"), "param": .string("keyABCDEF123456"), "status": .integer(401),
            "message": .string("Denied " + secret + " and " + secretLike + ". " + String(repeating: "x", count: 300)),
            "private": .string("must-not-persist-response-body")])]).data
        let refusalSink = ObservationSink(url: folder.appendingPathComponent("refusal.json"))
        let refusal = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("refusal-usage.json"),
            http: ObservationRefusalHTTP(body: refusalBody))
        let remote = ProviderSettings(id: "fixture", baseURL: URL(string: "https://fixture.invalid/private-api/v1")!)
        let rejected = try ExactJSON(data: await refusal.performObserved(action: action, models: models, providers: [remote],
            credentials: ObservationCredentials(secret: secret), observation: .init(),
            willSend: { try await refusalSink.save($0) }, didFinish: { try await refusalSink.save($0) }, onBytes: { _ in }))
        XCTAssertEqual(rejected["failure"].string, "provider_rejected")
        let stored = try Data(contentsOf: refusalSink.url)
        let refusalRecord = try JSONDecoder().decode(ProviderAttemptObservation.self, from: stored)
        let http = try XCTUnwrap(refusalRecord.metric.diagnostic)
        XCTAssertEqual(http.kind, .http)
        XCTAssertEqual(http.httpStatus, 401)
        XCTAssertEqual(http.endpoint, "https://fixture.invalid")
        XCTAssertEqual(http.providerCode, "invalid-[redacted]")
        XCTAssertEqual(http.providerType, "authentication_error")
        XCTAssertEqual(http.providerParameter, "[redacted]")
        XCTAssertEqual(http.providerStatus, "401")
        XCTAssertLessThanOrEqual(try XCTUnwrap(http.providerMessage).count, 240)
        XCTAssertTrue(http.providerMessage?.contains("[redacted]") == true)
        XCTAssertTrue(refusalRecord.metric.sent)
        XCTAssertEqual(refusalRecord.metric.httpStatus, 401)
        XCTAssertNil(refusalRecord.raw)
        let savedText = String(decoding: stored, as: UTF8.self)
        XCTAssertFalse(savedText.contains("fixture-key-quote"))
        XCTAssertFalse(savedText.contains(secretLike))
        XCTAssertFalse(savedText.contains("keyABCDEF123456"))
        XCTAssertFalse(savedText.contains("must-not-persist-response-body"))
        XCTAssertFalse(savedText.contains("private-api"))
    }

    // Failure: composition used Stage1's metric bucket, actual usage was estimated,
    // or provider IO bypassed durable saving / lost received bytes on a failed read.
    func testJSONSSEDurabilityAndPartialBoundary() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-provider-observation-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let secret = "fixture-key-quote\"-slash\\-end"
        let action = Self.action(secret: secret)
        let provider = ProviderSettings(id: "fixture", baseURL: URL(string: "https://fixture.invalid/v1")!)
        let models = ModelSelection(stage1Model: "fixture:offered", stage2Model: "fixture:must-not-route", stage1MaxTokens: 777, holeMaxTokens: 333)
        let jsonSink = ObservationSink(url: folder.appendingPathComponent("json.json"))
        let jsonHTTP = ObservationJSONHTTP(recordURL: jsonSink.url, secret: secret)
        let ordinary = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("usage.json"), http: jsonHTTP)
        let result = try ExactJSON(data: await ordinary.performObserved(action: action, models: models, providers: [provider],
            credentials: ObservationCredentials(secret: secret), observation: .init(captureRaw: true),
            willSend: { try await jsonSink.save($0) }, didFinish: { try await jsonSink.save($0) }, onBytes: { _ in }))
        XCTAssertEqual(result["tag"].string, "composition_read")
        XCTAssertEqual(result["identity"], try ExactJSON(data: action)["identity"])
        let jsonRecords = await jsonSink.values
        let json = try XCTUnwrap(jsonRecords.last)
        XCTAssertEqual(jsonRecords.count, 2)
        XCTAssertEqual(json.metric.stage, .composition)
        XCTAssertEqual(json.metric.model, "offered")
        XCTAssertEqual(json.metric.usage, ProviderUsage(inputTokens: 0, outputTokens: 7))
        XCTAssertEqual(json.metric.httpStatus, 200)
        XCTAssertEqual(json.metric.outcome, .completed)
        XCTAssertTrue(json.metric.sent)
        XCTAssertGreaterThanOrEqual(json.metric.elapsedMS ?? 0, 1)
        XCTAssertEqual(json.raw?.captureComplete, true)
        XCTAssertEqual(json.raw?.responseIncomplete, false)
        XCTAssertEqual(json.raw?.requestTruncated, false)
        XCTAssertEqual(json.raw?.responseTruncated, false)
        XCTAssertEqual(json.metric.responseModel, "reported-[redacted]")
        let savedJSON = try String(decoding: Data(contentsOf: jsonSink.url), as: UTF8.self)
        XCTAssertFalse(savedJSON.contains(secret))
        XCTAssertFalse(json.raw?.requestBody?.contains(secret) ?? true)
        XCTAssertFalse(json.raw?.responseBody?.contains("\\u0066\\u0069\\u0078") ?? true)
        XCTAssertTrue(json.raw?.responseBody?.contains("[redacted]") == true)
        let actualRequest = await jsonHTTP.lastRequest
        let sentRequest = try XCTUnwrap(actualRequest)
        let sentBody = try ExactJSON(data: XCTUnwrap(sentRequest.httpBody))
        XCTAssertEqual(sentBody["model"].string, "offered")
        XCTAssertEqual(sentBody["max_tokens"].number, "777")
        XCTAssertEqual(sentBody["tools"].array?.first?["function"]["parameters"], try ExactJSON(data: action)["payload"]["prompt"]["response_schema"])
        XCTAssertTrue(String(decoding: sentRequest.httpBody!, as: UTF8.self).contains("fixture-key-quote"))

        // The synthetic fixture reuses the existing runtime check's cached, connected
        // profile shape. No OAuth, model discovery, Keychain or network client is used.
        let fixture = try ObservationPersonalFixture(folder: folder.appendingPathComponent("personal"))
        let personalSink = ObservationSink(url: folder.appendingPathComponent("personal.json"))
        let sseHTTP = ObservationSSEHTTP(recordURL: personalSink.url, partial: false)
        let runtime = ChatGPTPlanRuntime(store: fixture.store, http: sseHTTP)
        let session = try await runtime.pin()
        let route = PersonalPlanRoutingTransport(ordinary: ordinary, runtime: runtime)
        let personalModels = ModelSelection(stage1Model: "chatgpt:offered", stage2Model: "chatgpt:must-not-route")
        let personalAction = Self.action(secret: "fixture-access-token")
        let personalResult = try ExactJSON(data: await route.performPersonalPlanObserved(action: personalAction, models: personalModels,
            providers: [.personalPlan], session: session, argumentLimit: 4096, credentials: ObservationCredentials(secret: nil),
            observation: .init(captureRaw: true), willSend: { try await personalSink.save($0) }, didFinish: { try await personalSink.save($0) },
            onBytes: { _ in }, onDiagnostic: { _ in }))
        XCTAssertEqual(personalResult["tag"].string, "composition_read")
        XCTAssertEqual(personalResult["identity"], try ExactJSON(data: personalAction)["identity"])
        let personalRecords = await personalSink.values
        let personal = try XCTUnwrap(personalRecords.last)
        XCTAssertEqual(personalRecords.count, 2)
        XCTAssertEqual(personal.metric.stage, .composition)
        XCTAssertEqual(personal.metric.usage, ProviderUsage(inputTokens: 11, outputTokens: 0, totalTokens: 11))
        XCTAssertEqual(personal.metric.responseModel, "offered")
        XCTAssertEqual(personal.raw?.captureComplete, true)
        XCTAssertFalse(personal.raw?.responseBody?.contains("fixture-refresh-token") ?? true)
        XCTAssertFalse(personal.raw?.requestBody?.contains("fixture-access-token") ?? true)
        let sseCount = await sseHTTP.calls
        XCTAssertEqual(sseCount, 1)

        let blockedHTTP = ObservationJSONHTTP(recordURL: folder.appendingPathComponent("not-created.json"), secret: secret)
        let blocked = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("blocked-usage.json"), http: blockedHTTP)
        do {
            _ = try await blocked.performObserved(action: action, models: models, providers: [provider], credentials: ObservationCredentials(secret: secret),
                observation: .init(captureRaw: true), willSend: { _ in throw HostError("fixture_sink_failed") },
                didFinish: { _ in XCTFail("Pre-send save failure reached final adoption") }, onBytes: { _ in })
            XCTFail("Pre-send save failure was converted to a retryable provider result")
        } catch { XCTAssertEqual(error as? ProviderObservationFailure, .requestSaveFailed) }
        let blockedCount = await blockedHTTP.calls
        XCTAssertEqual(blockedCount, 0)

        let partialSink = ObservationSink(url: folder.appendingPathComponent("partial.json"))
        let partialHTTP = ObservationSSEHTTP(recordURL: partialSink.url, partial: true)
        let partialRuntime = ChatGPTPlanRuntime(store: fixture.store, http: partialHTTP)
        let partialRoute = PersonalPlanRoutingTransport(ordinary: ordinary, runtime: partialRuntime)
        let failed = try ExactJSON(data: await partialRoute.performPersonalPlanObserved(action: personalAction, models: personalModels,
            providers: [.personalPlan], session: session, argumentLimit: 4096, credentials: ObservationCredentials(secret: nil),
            observation: .init(captureRaw: true), willSend: { try await partialSink.save($0) }, didFinish: { try await partialSink.save($0) },
            onBytes: { _ in }, onDiagnostic: { _ in }))
        XCTAssertEqual(failed["tag"].string, "provider_failed")
        let partialRecords = await partialSink.values
        let partial = try XCTUnwrap(partialRecords.last)
        XCTAssertEqual(partial.metric.stage, .composition)
        XCTAssertEqual(partial.metric.httpStatus, 200)
        XCTAssertEqual(partial.metric.outcome, .failed)
        XCTAssertTrue(partial.metric.sent)
        XCTAssertNil(partial.metric.usage)
        XCTAssertEqual(partial.raw?.responseTruncated, true)
        XCTAssertEqual(partial.raw?.responseIncomplete, true)
        XCTAssertEqual(partial.raw?.captureComplete, false)
        XCTAssertTrue(partial.raw?.responseBody?.hasPrefix("data: ") == true)
        XCTAssertFalse(partial.raw?.responseBody?.contains("fixture-refresh-") ?? true)
        let partialCount = await partialHTTP.calls
        XCTAssertEqual(partialCount, 1)
    }

    private static func action(secret: String) -> Data {
        ExactJSON.object(["tag": .string("read_composition"), "identity": .object(["action_id": .string("fixture-composition"),
            "attempt": .integer(1), "request_digest": .string("fixture-digest")]), "timeout_ms": .string("2000"),
            "payload": .object(["prompt": .object(["system": .string("system " + secret), "message": .string("message"),
                "action_name": .string("read_composition"), "response_schema": .object(["type": .string("object"),
                    "properties": .object(["composition": .object(["type": .string("string")])]),
                    "propertyOrdering": .array([.string("composition")])])])])]).data
    }
}

private actor ObservationSink {
    nonisolated let url: URL
    private(set) var values: [ProviderAttemptObservation] = []
    init(url: URL) { self.url = url }
    func save(_ value: ProviderAttemptObservation) throws {
        try JSONEncoder().encode(value).write(to: url, options: .atomic)
        values.append(value)
    }
}
private struct ObservationCredentials: CredentialStore {
    let secret: String?
    func key(for credentialID: String) async throws -> String? { secret }
}
private struct ObservationCannotConnectHTTP: ProviderHTTPClient {
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse {
        throw URLError(.cannotConnectToHost)
    }
}
private struct ObservationRefusalHTTP: ProviderHTTPClient {
    let body: Data
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse {
        onResponse(.init(status: 401, data: body, sent: true, complete: true, truncated: false))
        return .init(status: 401, data: body)
    }
}
private actor ObservationJSONHTTP: ProviderHTTPClient {
    let recordURL: URL
    let secret: String
    private(set) var calls = 0
    private(set) var lastRequest: URLRequest?
    init(recordURL: URL, secret: String) { self.recordURL = recordURL; self.secret = secret }
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse {
        calls += 1; lastRequest = request
        let durable = try JSONDecoder().decode(ProviderAttemptObservation.self, from: Data(contentsOf: recordURL))
        guard durable.metric.outcome == .requestSaved, durable.raw?.requestBody != nil else { throw HostError("fixture_missing_durable_request") }
        try await Task.sleep(for: .milliseconds(5))
        var wire = ExactJSON.object(["model": .string("reported-" + secret), "usage": .object(["prompt_tokens": .integer(0), "completion_tokens": .integer(7)]),
            "choices": .array([.object(["message": .object(["content": .string("{\"composition\":\"fixture\"}")])])])]).text
        let encoded = String(ExactJSON.string(secret).text.dropFirst().dropLast())
        let unicode = secret.utf16.map { String(format: "\\u%04x", $0) }.joined()
        wire = wire.replacingOccurrences(of: encoded, with: unicode)
        let data = Data(wire.utf8)
        onBytes(data.count); onResponse(.init(status: 200, data: data, sent: true, complete: true, truncated: false))
        return .init(status: 200, data: data)
    }
}
private struct ObservationPersonalFixture {
    let store: ChatGPTPlanStore
    init(folder: URL) throws {
        store = ChatGPTPlanStore(directory: folder, keys: ObservationVaultKeys())
        let id = "00000000-0000-4000-8000-000000000001"
        var state = ChatGPTVaultState(); state.enabled = true; state.activeProfileID = id
        state.profiles[id] = ChatGPTStoredProfile(id: id, issuer: "https://auth.openai.com", subject: "fixture-subject", email: nil,
            clientID: "fixture-client", label: "fixture", state: "connected", generation: 1,
            accessToken: "fixture-access-token", refreshToken: "fixture-refresh-token", idToken: nil,
            scopes: ["chatgpt.tokens.use.direct"], expiresAt: Date().addingTimeInterval(3600), earliestRefreshAt: Date(timeIntervalSince1970: 0),
            models: [.init(id: "offered", label: "Offered")], modelsExpireAt: Date().addingTimeInterval(300))
        try store.write(state)
    }
}
private final class ObservationVaultKeys: ChatGPTVaultKeyStore, @unchecked Sendable {
    private let lock = NSLock()
    private var key: Data?
    func readKey() -> Data? { lock.withLock { key } }
    func saveKey(_ key: Data) { lock.withLock { self.key = key } }
}
private actor ObservationSSEHTTP: ObservedChatGPTHTTPClient {
    let recordURL: URL
    let partial: Bool
    private(set) var calls = 0
    init(recordURL: URL, partial: Bool) { self.recordURL = recordURL; self.partial = partial }
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void) async throws -> ChatGPTHTTPResponse {
        try await sendObserved(request, maximumBytes: maximumBytes, onBytes: onBytes, onResponse: { _ in })
    }
    func sendObserved(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
                      onResponse: @escaping ProviderHTTPReadHandler) async throws -> ChatGPTHTTPResponse {
        calls += 1
        guard request.url == ChatGPTEndpoints.responses else { throw HostError("fixture_unexpected_auth_or_discovery_http") }
        let durable = try JSONDecoder().decode(ProviderAttemptObservation.self, from: Data(contentsOf: recordURL))
        guard durable.metric.outcome == .requestSaved, durable.raw?.requestBody != nil else { throw HostError("fixture_missing_durable_request") }
        let body = try ExactJSON(data: request.httpBody!)
        guard body["model"].string == "offered", body["tools"].array?.first?["tools"].array?.first?["parameters"]["propertyOrdering"].array == [.string("composition")] else {
            throw HostError("fixture_wire_changed")
        }
        let item: ExactJSON = .object(["type": .string("function_call"), "id": .string("call"), "namespace": .string("inku"),
            "name": .string("submit_pipeline_response"), "arguments": .string("{\"composition\":\"fixture\"}")])
        func frame(_ value: ExactJSON) -> String { "data: " + value.text + "\n\n" }
        var wire = frame(.object(["type": .string("response.output_item.added"), "item": item]))
        if partial {
            wire += "data: {\"type\":\"response.incomplete\",\"private\":\"fixture-refresh-"
            let data = Data(wire.utf8)
            onBytes(data.count); onResponse(.init(status: 200, data: data, sent: true, complete: false, truncated: true))
            throw HostError("chatgpt_response_too_large")
        }
        wire += frame(.object(["type": .string("response.completed"), "response": .object(["status": .string("completed"), "model": .string("offered"),
            "output": .array([item]), "usage": .object(["input_tokens": .integer(11), "output_tokens": .integer(0), "total_tokens": .integer(11)]),
            "private": .string("fixture-refresh-token")])]))
        let data = Data(wire.utf8)
        onBytes(data.count); onResponse(.init(status: 200, data: data, sent: true, complete: true, truncated: false))
        return .init(status: 200, data: data)
    }
}
