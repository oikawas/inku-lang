import Foundation
import InkuPersistence
import XCTest
@testable import InkuHost

final class ChatGPTPlanRuntimeChecks: XCTestCase {
    // Failure: a one-provider bare model skipped pinning, or a reserved personal reference fell into an API-key route.
    func testPersonalSelectionUsesOrdinaryResolutionRulesAndRefusesMissingReservedProvider() throws {
        // Server's resolver never gives a bare reference to the plan: it falls to the stage default provider.
        XCTAssertNil(try PersonalPlanRoutingTransport.personalModel("offered", providers: [.personalPlan]))
        XCTAssertEqual(try PersonalPlanRoutingTransport.personalModel("chatgpt:offered", providers: [.personalPlan]), "offered")
        XCTAssertThrowsError(try PersonalPlanRoutingTransport.personalModel("chatgpt:offered", providers: [])) {
            XCTAssertEqual(($0 as? HostError)?.code, "chatgpt_provider_selection_required")
        }
    }
    // Failure (D9): one listed row without a display name refuses the whole catalog; Server skips that row.
    func testCatalogSkipsRowsWithoutStringNames() async throws {
        let fixture = try RuntimeFixture(expired: false)
        defer { fixture.remove() }
        let runtime = ChatGPTPlanRuntime(store: fixture.store, http: RuntimeHTTP(blockRefresh: false))
        let models = try await runtime.models(force: true)
        XCTAssertEqual(models.map(\.id), ["offered"])
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

    // Failure: model settings published a model the profile was not offered, or wrote another profile's choice.
    func testPublicationSavesOnlyOfferedModelsOfTheActiveProfile() async throws {
        let other = UUID().uuidString
        let fixture = try RuntimeFixture(expired: false, published: nil, otherProfileID: other)
        defer { fixture.remove() }
        let client = RuntimeHTTP(blockRefresh: false)
        let runtime = ChatGPTPlanRuntime(store: fixture.store, http: client)
        let opened = try await runtime.publication()
        XCTAssertEqual(opened.models.map(\.id), ["offered", "second"])
        XCTAssertEqual(opened.published, [])
        let saved = try await runtime.savePublication(profileID: opened.profileID, generation: opened.generation, models: ["second", "offered", "second"])
        XCTAssertEqual(saved.publishedModels.map(\.id), ["offered", "second"])
        XCTAssertEqual(try fixture.store.load().profiles[fixture.activeID]?.publishedModels, ["second", "offered"])
        for (profileID, generation, models, code) in [(opened.profileID, opened.generation, ["missing"], "chatgpt_model_not_offered"),
                                                      (other, Int64(1), ["offered"], "chatgpt_session_changed"),
                                                      (opened.profileID, opened.generation + 1, ["offered"], "chatgpt_session_changed")] {
            do { _ = try await runtime.savePublication(profileID: profileID, generation: generation, models: models); XCTFail("Saved \(models) for \(code)") }
            catch { XCTAssertEqual((error as? HostError)?.code, code) }
        }
        XCTAssertNil(try fixture.store.load().profiles[other]?.publishedModels)
        // Server refresh: the fetched catalog replaces the saved one, and the published marks follow it.
        let refreshed = try await runtime.refreshPublication()
        XCTAssertEqual(refreshed.models.map(\.id), ["offered"])
        XCTAssertEqual(refreshed.publishedModels.map(\.id), ["offered"])
        let responseCount = await client.responseCount()
        XCTAssertEqual(responseCount, 0)
    }
    // Failure: a model the profile was offered but never published still reached the Responses endpoint.
    func testUnpublishedModelIsRefusedBeforeTheRequest() async throws {
        let fixture = try RuntimeFixture(expired: false, published: nil)
        defer { fixture.remove() }
        let client = RuntimeHTTP(blockRefresh: false)
        let runtime = ChatGPTPlanRuntime(store: fixture.store, http: client)
        let session = try await runtime.pin()
        do {
            _ = try await runtime.perform(action: Self.action, session: session, model: "offered", argumentLimit: 4096, onBytes: { _ in })
            XCTFail("An unpublished model was sent")
        } catch { XCTAssertEqual(ChatGPTPlanRuntime.diagnostic(error).code, "chatgpt_model_not_offered") }
        let responseCount = await client.responseCount()
        XCTAssertEqual(responseCount, 0)
    }
    // Failure: a vault saved before published models existed no longer opens.
    func testProfileSavedWithoutPublishedModelsDecodes() throws {
        let fixture = try RuntimeFixture(expired: false)
        defer { fixture.remove() }
        let profile = try XCTUnwrap(fixture.store.load().profiles[fixture.activeID])
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(profile)) as? [String: Any])
        XCTAssertNotNil(object.removeValue(forKey: "publishedModels"))
        let old = try JSONDecoder().decode(ChatGPTStoredProfile.self, from: JSONSerialization.data(withJSONObject: object))
        XCTAssertNil(old.publishedModels)
        XCTAssertEqual(old.models?.map(\.id), ["offered", "second"])
    }

    // Failure: a model chosen for one purpose served the other, or a model without a purpose was published.
    func testPurposesDefaultToBothAndGateEachRequest() async throws {
        let fixture = try RuntimeFixture(expired: false)
        defer { fixture.remove() }
        let client = VisionHTTP(answer: "観察")
        let runtime = ChatGPTPlanRuntime(store: fixture.store, http: client)
        let session = try await runtime.pin()
        let opened = try await runtime.publication()
        XCTAssertEqual(opened.purposes(of: "offered"), ["llm", "vision"])
        XCTAssertEqual(opened.purposes(of: "second"), ["llm", "vision"])
        let visionOnly = try await runtime.savePublication(profileID: opened.profileID, generation: opened.generation,
                                                           models: ["offered"], purposes: ["offered": ["vision"]])
        XCTAssertEqual(visionOnly.purposes(of: "offered"), ["vision"])
        do {
            _ = try await runtime.savePublication(profileID: opened.profileID, generation: opened.generation,
                                                  models: ["offered", "second"], purposes: ["second": []])
            XCTFail("A model without a purpose was published")
        } catch { XCTAssertEqual((error as? HostError)?.code, "chatgpt_model_not_offered") }
        do {
            _ = try await runtime.savePublication(profileID: opened.profileID, generation: opened.generation,
                                                  models: ["offered"], purposes: ["offered": ["draw"]])
            XCTFail("A purpose other than LLM or Vision was saved")
        } catch { XCTAssertEqual((error as? HostError)?.code, "chatgpt_model_not_offered") }
        XCTAssertEqual(try fixture.store.load().profiles[fixture.activeID]?.publishedModels, ["offered"])
        do {
            _ = try await runtime.perform(action: Self.action, session: session, model: "offered", argumentLimit: 4096, onBytes: { _ in })
            XCTFail("A Vision-only model drew")
        } catch { XCTAssertEqual(ChatGPTPlanRuntime.diagnostic(error).code, "chatgpt_model_not_offered") }
        _ = try await runtime.savePublication(profileID: opened.profileID, generation: opened.generation,
                                              models: ["offered"], purposes: ["offered": ["llm"]])
        do {
            _ = try await runtime.visionText(session: session, model: "offered", system: "s", message: "m", images: [],
                                             timeoutSeconds: 5, onBytes: { _ in })
            XCTFail("An LLM-only model answered Vision")
        } catch { XCTAssertEqual(ChatGPTPlanRuntime.diagnostic(error).code, "chatgpt_model_not_offered") }
        let sent = await client.requests()
        XCTAssertEqual(sent.count, 0)
    }
    // Failure: Vision on the plan sent tools, a temperature or an output limit, lost the image, or read no answer.
    func testVisionSendsImagesWithoutToolsAndReadsTheAnswer() async throws {
        let fixture = try RuntimeFixture(expired: false)
        defer { fixture.remove() }
        let client = VisionHTTP(answer: "左の円が右で大きい。")
        let runtime = ChatGPTPlanRuntime(store: fixture.store, http: client)
        let routed = PersonalPlanRoutingTransport(ordinary: NoOrdinaryTransport(), runtime: runtime)
        let settings = HostSettings(providers: [.personalPlan])
        let image = "data:image/png;base64,iVBORw0KGgo="
        let answer = try await routed.performAuxiliary(
            prompt: AuxiliaryPrompt(system: "system", message: "message", images: [image], temperature: 0.35, maximumTokens: 320),
            modelReference: "chatgpt:offered", settings: settings, credentials: NoCredentials(), onBytes: { _ in })
        XCTAssertEqual(answer, "左の円が右で大きい。")
        let sent = await client.requests()
        let request = try XCTUnwrap(sent.last)
        XCTAssertEqual(request.url, URL(string: "https://api.openai.com/v1/responses"))
        let body = try ExactJSON(data: XCTUnwrap(request.httpBody))
        XCTAssertEqual(body["model"].string, "offered"); XCTAssertEqual(body["instructions"].string, "system")
        XCTAssertEqual(body["store"].bool, false); XCTAssertEqual(body["stream"].bool, true)
        XCTAssertEqual(body["tools"], .null); XCTAssertEqual(body["tool_choice"], .null)
        XCTAssertEqual(body["temperature"], .null); XCTAssertEqual(body["max_output_tokens"], .null)
        let content = try XCTUnwrap(body["input"].array?.first?["content"].array)
        XCTAssertEqual(content.map { $0["type"].string }, ["input_text", "input_image"])
        XCTAssertEqual(content[0]["text"].string, "message"); XCTAssertEqual(content[1]["image_url"].string, image)
        do {
            _ = try await routed.performAuxiliary(
                prompt: AuxiliaryPrompt(system: "s", message: "seed", temperature: 0.9, maximumTokens: 180, purpose: .demo),
                modelReference: "chatgpt:offered", settings: settings, credentials: NoCredentials(), onBytes: { _ in })
            XCTFail("The demo description ran on the plan")
        } catch { XCTAssertEqual((error as? HostError)?.code, "chatgpt_operation_not_supported") }
        let afterDemo = await client.requests()
        XCTAssertEqual(afterDemo.count, sent.count)
    }
    // Failure: a tool call passed as a Vision answer, or a usage-limit failure did not pause the profile.
    func testVisionRefusesToolsAndPausesOnQuota() async throws {
        var decoder = ChatGPTResponseDecoder(textLimit: 4096)
        let call = #"data: {"type":"response.output_item.added","item":{"type":"function_call","id":"c","namespace":"inku","name":"submit_pipeline_response","arguments":"{}"}}"# + "\n\n"
        XCTAssertThrowsError(try decoder.feed(Data(call.utf8))) { XCTAssertEqual(($0 as? HostError)?.code, "chatgpt_unexpected_tool") }
        let fixture = try RuntimeFixture(expired: false)
        defer { fixture.remove() }
        let runtime = ChatGPTPlanRuntime(store: fixture.store, http: VisionHTTP(answer: nil))
        let session = try await runtime.pin()
        do {
            _ = try await runtime.visionText(session: session, model: "offered", system: "s", message: "m", images: [],
                                             timeoutSeconds: 5, onBytes: { _ in })
            XCTFail("A usage-limit failure returned an answer")
        } catch { XCTAssertEqual(ChatGPTPlanRuntime.diagnostic(error).code, "subscription_sharing_usage_limit_exceeded") }
        XCTAssertEqual(try fixture.store.load().profiles[session.profileID]?.state, "quota")
    }

    // Failure: a Vision answer was taken from deltas alone, read an unfinished item, ignored a function call event,
    // or kept a limit other than Server's 512 KiB (chatgpt_provider.TextSSEDecoder, request_vision).
    func testVisionAnswerIsOnlyCompletedText() throws {
        func frame(_ value: ExactJSON) -> String { "data: " + value.text + "\n\n" }
        func message(_ text: String, status: String? = nil) -> ExactJSON {
            var item: [String: ExactJSON] = ["type": .string("message"), "id": .string("m"), "role": .string("assistant"),
                "content": .array([.object(["type": .string("output_text"), "text": .string(text)])])]
            if let status { item["status"] = .string(status) }
            return .object(item)
        }
        func completed(_ output: [ExactJSON]) -> String {
            frame(.object(["type": .string("response.completed"), "response": .object(["status": .string("completed"), "output": .array(output)])]))
        }
        func read(_ wire: String, limit: Int = 4096) throws -> String {
            var decoder = ChatGPTResponseDecoder(textLimit: limit)
            try decoder.feed(Data(wire.utf8)); return try decoder.finish()
        }
        func code(_ wire: String, limit: Int = 4096) -> String? {
            do { _ = try read(wire, limit: limit); return nil } catch { return (error as? HostError)?.code }
        }
        let delta = frame(.object(["type": .string("response.output_text.delta"), "delta": .string("断片")]))
        XCTAssertEqual(code(delta + completed([])), "chatgpt_response_invalid")
        let done = frame(.object(["type": .string("response.output_item.done"), "item": message("確定")]))
        XCTAssertEqual(try read(delta + done + completed([])), "確定")
        XCTAssertEqual(code(completed([message("途中", status: "in_progress")])), "chatgpt_response_incomplete")
        XCTAssertEqual(code(completed([message("")])), "chatgpt_response_invalid")
        let image: ExactJSON = .object(["type": .string("message"), "role": .string("assistant"),
            "content": .array([.object(["type": .string("output_image")])])])
        XCTAssertEqual(code(completed([image])), "chatgpt_response_invalid")
        let call = frame(.object(["type": .string("response.function_call_arguments.delta"), "delta": .string("{")]))
        XCTAssertEqual(code(call + completed([message("x")])), "chatgpt_unexpected_tool")
        XCTAssertEqual(ChatGPTPlanRuntime.visionTextLimit, 512 * 1024)
        XCTAssertEqual(try read(completed([message("12345678")]), limit: 8), "12345678")
        XCTAssertEqual(code(completed([message("123456789")]), limit: 8), "chatgpt_response_too_large")
    }

    // Failure: a colophon on the plan was not pinned to one profile, reused a reading across a reconnection,
    // or reused one after the model stopped being published for Vision (Server okugaki / check_vision_access).
    func testColophonOnThePlanPinsAndKeepsReadingsPerProfile() async throws {
        let fixture = try RuntimeFixture(expired: false)
        defer { fixture.remove() }
        let client = VisionHTTP(answer: "円がある")
        let runtime = ChatGPTPlanRuntime(store: fixture.store, http: client)
        let routed = PersonalPlanRoutingTransport(ordinary: NoOrdinaryTransport(), runtime: runtime)
        let settings = HostSettings(providers: [.personalPlan])
        let provider = AuxiliaryProvider(transport: routed, credentials: NoCredentials())
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plan-colophon-\(UUID().uuidString)").appendingPathComponent("test.sqlite")
        defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        let database = try InkuDatabase(url: file)
        let root = SavedWork(id: "root", at: 1, input: "円", score: "{\"instructions\":[{\"primitive\":\"circle\",\"color\":\"red\",\"center\":[0.5,0.5]}]}", svg: "first", lineageNodeID: "node-root")
        try await database.save(root, node: LineageNode(id: "node-root", historyID: root.id, at: 1, rootNodeID: "node-root"))
        let lineage = try await database.lineage(focusNodeID: "node-root", pathOnly: true)
        let branch = try XCTUnwrap(lineage)
        let png: @Sendable ([String]) async throws -> Data? = { _ in Data([137, 80, 78, 71, 13, 10, 26, 10]) }
        func colophon() async throws {
            _ = try await provider.colophon(branch: branch, modelReference: "chatgpt:offered", language: "ja", settings: settings, png: png)
        }
        try await colophon()
        let first = await client.requests().count
        XCTAssertEqual(first, 2)
        try await colophon()
        let cached = await client.requests().count
        XCTAssertEqual(cached, first)
        var value = try fixture.store.load()
        value.profiles[fixture.activeID]?.generation = 2
        try fixture.store.write(value)
        try await colophon()
        let reconnected = await client.requests().count
        XCTAssertEqual(reconnected, first * 2)
        let run = try await routed.beginAuxiliaryRun(modelReference: "chatgpt:offered", settings: settings)
        XCTAssertEqual(run.chatGPTSession, ChatGPTPlanSession(profileID: fixture.activeID, generation: 2))
        _ = try await runtime.savePublication(profileID: fixture.activeID, generation: 2, models: ["offered"], purposes: ["offered": ["llm"]])
        do {
            try await routed.checkAuxiliaryRun(run, modelReference: "chatgpt:offered", settings: settings)
            XCTFail("A reading was reusable after the model stopped serving Vision")
        } catch { XCTAssertEqual(ChatGPTPlanRuntime.diagnostic(error).code, "chatgpt_model_not_offered") }
        do {
            try await colophon()
            XCTFail("A colophon ran on a model not published for Vision")
        } catch { XCTAssertEqual(ChatGPTPlanRuntime.diagnostic(error).code, "chatgpt_model_not_offered") }
        let refused = await client.requests().count
        XCTAssertEqual(refused, reconnected)
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
    let activeID: String
    init(expired: Bool, published: [String]? = ["offered"], otherProfileID: String? = nil) throws {
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-plan-runtime-" + UUID().uuidString, isDirectory: true)
        store = ChatGPTPlanStore(directory: folder, keys: RuntimeKeyStore())
        let id = UUID().uuidString
        activeID = id
        var value = ChatGPTVaultState(); value.enabled = true; value.activeProfileID = id
        for profileID in [id] + (otherProfileID.map { [$0] } ?? []) {
            value.profiles[profileID] = ChatGPTStoredProfile(id: profileID, issuer: "https://auth.openai.com", subject: "fixture-subject", email: nil,
                clientID: "fixture-client", label: "fixture", state: "connected", generation: 1,
                accessToken: "fixture-access-token", refreshToken: "fixture-refresh-token", idToken: nil,
                scopes: ["chatgpt.tokens.use.direct"], expiresAt: Date().addingTimeInterval(expired ? -1 : 3600),
                earliestRefreshAt: Date(timeIntervalSince1970: 0), models: [.init(id: "offered", label: "Offered"), .init(id: "second", label: "Second")],
                modelsExpireAt: expired ? nil : Date().addingTimeInterval(300), publishedModels: published)
        }
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
        case "/v1/models": return .init(status: 200, data: Data(#"{"models":[{"visibility":"list","slug":"offered","display_name":"Offered"},{"visibility":"hidden","slug":"hidden","display_name":"Hidden"},{"visibility":"list","slug":"unnamed"},{"visibility":"list","slug":"numbered","display_name":5}]}"#.utf8))
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

/// Answers Vision requests with assistant text; a nil answer is a usage-limit failure event.
private actor VisionHTTP: ChatGPTHTTPClient {
    let answer: String?
    private var sent: [URLRequest] = []
    init(answer: String?) { self.answer = answer }
    func requests() -> [URLRequest] { sent }
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void) async throws -> ChatGPTHTTPResponse {
        guard request.url?.path == "/v1/responses" else { throw HostError("unexpected_fixture_route") }
        sent.append(request)
        func frame(_ value: ExactJSON) -> String { "data: " + value.text + "\n\n" }
        guard let answer else {
            return .init(status: 200, data: Data(frame(.object(["type": .string("error"), "error": .object(["code": .string("subscription_sharing_usage_limit_exceeded")])])).utf8))
        }
        let message: ExactJSON = .object(["type": .string("message"), "role": .string("assistant"),
            "content": .array([.object(["type": .string("output_text"), "text": .string(answer)])])])
        var wire = frame(.object(["type": .string("response.output_item.added"), "item": .object(["type": .string("message"), "role": .string("assistant"), "content": .array([])])]))
        wire += frame(.object(["type": .string("response.output_text.delta"), "delta": .string(answer)]))
        wire += frame(.object(["type": .string("response.completed"), "response": .object(["status": .string("completed"), "output": .array([message])])]))
        return .init(status: 200, data: Data(wire.utf8))
    }
}

private struct NoOrdinaryTransport: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data { throw HostError("unexpected_ordinary_provider") }
}

private struct NoCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}
