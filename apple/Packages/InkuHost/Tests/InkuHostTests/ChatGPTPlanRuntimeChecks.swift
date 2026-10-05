import Foundation
import XCTest
@testable import InkuHost

final class ChatGPTPlanRuntimeChecks: XCTestCase {
    // Failure: a one-provider bare model skipped pinning, or a reserved personal reference fell into an API-key route.
    func testPersonalSelectionUsesOrdinaryResolutionRulesAndRefusesMissingReservedProvider() throws {
        XCTAssertEqual(try PersonalPlanRoutingTransport.personalModel("offered", providers: [.personalPlan]), "offered")
        XCTAssertEqual(try PersonalPlanRoutingTransport.personalModel("chatgpt:offered", providers: [.personalPlan]), "offered")
        XCTAssertThrowsError(try PersonalPlanRoutingTransport.personalModel("chatgpt:offered", providers: [])) {
            XCTAssertEqual(($0 as? HostError)?.code, "chatgpt_provider_selection_required")
        }
    }
    // Failure: a refresh completed after local sign-out and resurrected tokens or sent the queued request.
    func testBlockedRefreshCannotResurrectSignedOutSession() async throws {
        let fixture = try RuntimeFixture(expired: true)
        defer { fixture.remove() }
        let client = RuntimeHTTP(blockRefresh: true)
        let runtime = ChatGPTPlanRuntime(store: fixture.store, http: client)
        let session = try await runtime.pin()
        let pending = Task { try await runtime.models(session: session) }
        await client.waitForRefresh()
        let confirmed = try await runtime.signOut(session.profileID)
        XCTAssertFalse(confirmed)
        do { _ = try await pending.value; XCTFail("Signed-out refresh produced a model catalog") }
        catch { XCTAssertEqual(ChatGPTPlanRuntime.diagnostic(error).code, "chatgpt_session_changed") }
        let profile = try XCTUnwrap(fixture.store.load().profiles[session.profileID])
        XCTAssertEqual(profile.generation, session.generation + 1)
        XCTAssertEqual(profile.state, "signed_out")
        XCTAssertNil(profile.accessToken); XCTAssertNil(profile.refreshToken)
        let responseCount = await client.responseCount()
        XCTAssertEqual(responseCount, 0)
        do { try await runtime.validate(session); XCTFail("An old journal pin was silently repinned") }
        catch { XCTAssertEqual((error as? HostError)?.code, "chatgpt_session_changed") }
        let sealed = try Data(contentsOf: fixture.store.stateURL)
        XCTAssertNil(String(data: sealed, encoding: .utf8))
        XCTAssertFalse(sealed.range(of: Data("fixture-refresh-token".utf8)) != nil)
    }

    // Failure: a completed SSE frame hid a late quota error, and subsequent requests bypassed the quota pause.
    func testLateQuotaPausesUntilExplicitRetryAndUsesOnlyCanonicalResponsesBody() async throws {
        let fixture = try RuntimeFixture(expired: false)
        defer { fixture.remove() }
        let client = RuntimeHTTP(blockRefresh: false)
        let runtime = ChatGPTPlanRuntime(store: fixture.store, http: client)
        let session = try await runtime.pin()
        do {
            _ = try await runtime.perform(action: Self.action, session: session, model: "offered", argumentLimit: 4096, onBytes: { _ in })
            XCTFail("Late quota error returned a completed result")
        } catch { XCTAssertEqual(ChatGPTPlanRuntime.diagnostic(error).code, "subscription_sharing_usage_limit_exceeded") }
        XCTAssertEqual(try fixture.store.load().profiles[session.profileID]?.state, "quota")
        do {
            _ = try await runtime.perform(action: Self.action, session: session, model: "offered", argumentLimit: 4096, onBytes: { _ in })
            XCTFail("Paused profile sent another request")
        } catch { XCTAssertEqual(ChatGPTPlanRuntime.diagnostic(error).code, "chatgpt_quota") }
        let pausedCount = await client.responseCount()
        XCTAssertEqual(pausedCount, 1)
        try await runtime.retryQuota(session.profileID)
        let answer = try await runtime.perform(action: Self.action, session: session, model: "offered", argumentLimit: 4096, onBytes: { _ in })
        XCTAssertEqual(answer, #"{"normalized_ddl":"赤い円"}"#)
        let retriedCount = await client.responseCount()
        XCTAssertEqual(retriedCount, 2)
        let lastRequest = await client.lastResponseRequest()
        let request = try XCTUnwrap(lastRequest)
        let body = try ExactJSON(data: XCTUnwrap(request.httpBody))
        XCTAssertEqual(request.url, URL(string: "https://api.openai.com/v1/responses"))
        XCTAssertEqual(body["store"].bool, false); XCTAssertEqual(body["stream"].bool, true)
        XCTAssertEqual(body["tool_choice"].string, "required")
        XCTAssertEqual(body["tools"].array?.first?["name"].string, "inku")
        XCTAssertEqual(body["tools"].array?.first?["tools"].array?.first?["name"].string, "submit_pipeline_response")
        XCTAssertEqual(body["max_tokens"], .null); XCTAssertEqual(body["max_output_tokens"], .null); XCTAssertEqual(body["temperature"], .null)
        XCTAssertEqual(try fixture.store.load().profiles[session.profileID]?.generation, session.generation)
    }

    private static var action: Data {
        ExactJSON.object(["tag": .string("generate_normalized_ddl"), "identity": .object(["action_id": .string("fixture")]),
            "timeout_ms": .string("2000"), "payload": .object(["prompt": .object(["system": .string("system"), "message": .string("message"),
                "response_schema": .object(["type": .string("object")])])])]).data
    }
}

private struct RuntimeFixture {
    let folder: URL
    let store: ChatGPTPlanStore
    init(expired: Bool) throws {
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plan-runtime-" + UUID().uuidString, isDirectory: true)
        store = ChatGPTPlanStore(directory: folder, keys: RuntimeKeyStore())
        let id = UUID().uuidString
        var value = ChatGPTVaultState(); value.enabled = true; value.activeProfileID = id
        value.profiles[id] = ChatGPTStoredProfile(id: id, issuer: "https://auth.openai.com", subject: "fixture-subject", email: nil,
            clientID: "fixture-client", label: "fixture", state: "connected", generation: 1,
            accessToken: "fixture-access-token", refreshToken: "fixture-refresh-token", idToken: nil,
            scopes: ["chatgpt.tokens.use.direct"], expiresAt: Date().addingTimeInterval(expired ? -1 : 3600),
            earliestRefreshAt: Date(timeIntervalSince1970: 0), models: [.init(id: "offered", label: "Offered")], modelsExpireAt: expired ? nil : Date().addingTimeInterval(300))
        try store.write(value)
    }
    func remove() { try? FileManager.default.removeItem(at: folder) }
}

private final class RuntimeKeyStore: ChatGPTVaultKeyStore, @unchecked Sendable {
    private let lock = NSLock()
    private var value: Data?
    func readKey() -> Data? { lock.withLock { value } }
    func saveKey(_ key: Data) { lock.withLock { value = key } }
}

private actor RuntimeHTTP: ChatGPTHTTPClient {
    let blockRefresh: Bool
    private var refreshEntered = false
    private var refreshWaiters: [CheckedContinuation<Void, Never>] = []
    private var responses = 0
    private var responseRequest: URLRequest?
    init(blockRefresh: Bool) { self.blockRefresh = blockRefresh }
    func waitForRefresh() async { if !refreshEntered { await withCheckedContinuation { refreshWaiters.append($0) } } }
    func responseCount() -> Int { responses }
    func lastResponseRequest() -> URLRequest? { responseRequest }
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void) async throws -> ChatGPTHTTPResponse {
        switch request.url!.path {
        case "/api/accounts/oauth/token":
            refreshEntered = true; let waiters = refreshWaiters; refreshWaiters = []; waiters.forEach { $0.resume() }
            if blockRefresh { try await Task.sleep(for: .seconds(5)) }
            return .init(status: 200, data: Data(#"{"token_type":"Bearer","access_token":"rotated-access","refresh_token":"rotated-refresh","expires_in":3600}"#.utf8))
        case "/.well-known/openid-configuration": return .init(status: 200, data: Data(#"{"issuer":"https://auth.openai.com"}"#.utf8))
        case "/v1/models": return .init(status: 200, data: Data(#"{"models":[{"visibility":"list","slug":"offered","display_name":"Offered"},{"visibility":"hidden","slug":"hidden","display_name":"Hidden"}]}"#.utf8))
        case "/v1/responses":
            responses += 1; responseRequest = request
            let arguments = #"{"normalized_ddl":"赤い円"}"#
            let item: ExactJSON = .object(["type": .string("function_call"), "id": .string("call"), "namespace": .string("inku"),
                "name": .string("submit_pipeline_response"), "arguments": .string(arguments)])
            func frame(_ value: ExactJSON) -> String { "data: " + value.text + "\n\n" }
            var wire = frame(.object(["type": .string("response.output_item.added"), "item": item]))
            wire += frame(.object(["type": .string("response.completed"), "response": .object(["status": .string("completed"), "output": .array([item])])]))
            if responses == 1 { wire += frame(.object(["type": .string("error"), "error": .object(["code": .string("subscription_sharing_usage_limit_exceeded")])])) }
            return .init(status: 200, data: Data(wire.utf8))
        default: throw HostError("unexpected_fixture_route")
        }
    }
}
