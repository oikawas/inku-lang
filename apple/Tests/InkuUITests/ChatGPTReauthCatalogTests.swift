import CryptoKit
import Foundation
import XCTest
@testable import InkuHost
@testable import InkuUI

@MainActor final class ChatGPTReauthCatalogTests: XCTestCase {
    func testImageReviewSavesDigestsBeforeSendingAndAfterReceiving() async throws {
        let previousMode = ProcessInfo.processInfo.environment["INKU_DEVELOPER_MODE"]
        setenv("INKU_DEVELOPER_MODE", "1", 1)
        defer {
            if let previousMode { setenv("INKU_DEVELOPER_MODE", previousMode, 1) }
            else { unsetenv("INKU_DEVELOPER_MODE") }
        }
        let fixture = try ReauthFixture(existing: true, failure: .observedDraw)
        defer { fixture.remove() }
        let app = fixture.app
        await app.initialize()
        var settings = await app.hostSettings()
        settings.providers.append(.personalPlan)
        try await app.updateHostSettings(settings)
        await app.synchronizePersonalPlanModels()
        var defaults = app.drawDefaults
        defaults["describe"]?.models.stage1 = "chatgpt:offered"
        defaults["describe"]?.models.stage2 = "chatgpt:offered"
        defaults["describe"]?.route = "read_and_draw"
        defaults["describe"]?.composition = "off"
        defaults["describe"]?.sketch = "off"
        try app.saveDrawDefaults(defaults)
        var request = try app.requestForPhoneDescription("a red circle")
        request.descriptionReview = true
        request.captureProviderIO = true
        let pinned = try await app.pinPersonalPlanRequests([request])[0]
        let http = fixture.http
        let work = await app.runAutomation(request: pinned, onExecutionStarted: { [app] id in
            await http.verifyImageRequest { [weak app] body in
                guard let app else { throw HostError("fixture_app_unavailable") }
                let observations = try await app.providerObservations(executionID: id)
                guard let saved = observations.first(where: { $0.metric.action == "review_description_ddl" }),
                      saved.metric.outcome == .requestSaved, let requestBody = saved.raw?.requestBody,
                      try ExactJSON(data: Data(requestBody.utf8)) == captureDigest(body) else {
                    throw HostError("fixture_missing_durable_image_digest")
                }
            }
        })
        let savedWork = try XCTUnwrap(work, app.errorText ?? "")
        let execution = try WorkIdentity.location(savedWork.id).executionID
        let observations = try await app.providerObservations(executionID: execution)
        let review = try XCTUnwrap(observations.first { $0.metric.action == "review_description_ddl" })
        XCTAssertEqual(review.metric.outcome, .completed)
        XCTAssertEqual(review.metric.httpStatus, 200)
        let imageExchange = await http.imageExchange
        let exchange = try XCTUnwrap(imageExchange)
        let requestBody = try XCTUnwrap(review.raw?.requestBody)
        XCTAssertEqual(try ExactJSON(data: Data(requestBody.utf8)), captureDigest(exchange.request))
        let responseBody = try XCTUnwrap(review.raw?.responseBody)
        XCTAssertEqual(try ExactJSON(data: Data(responseBody.utf8)), captureDigest(exchange.response))
        XCTAssertTrue(String(decoding: exchange.response, as: UTF8.self).contains("data:image/png;base64,"))
        let writing = try XCTUnwrap(observations.first { $0.metric.action == "write_description_ddl" })
        XCTAssertNotNil(writing.raw?.requestBody)
        XCTAssertTrue(writing.raw?.responseBody?.contains("response.completed") == true)
    }

    func testPhoneDrawSavesAfterAProviderDiagnosticWithoutShowingFailure() async throws {
        let fixture = try ReauthFixture(existing: true, failure: .recoveredDraw)
        defer { fixture.remove() }
        await fixture.app.initialize()
        var settings = await fixture.app.hostSettings()
        settings.providers.append(.personalPlan)
        try await fixture.app.updateHostSettings(settings)
        await fixture.app.synchronizePersonalPlanModels()
        var defaults = fixture.app.drawDefaults
        defaults["describe"]?.models.stage1 = "chatgpt:offered"
        defaults["describe"]?.models.stage2 = "chatgpt:offered"
        defaults["describe"]?.route = "read_and_draw"
        defaults["describe"]?.composition = "off"
        defaults["describe"]?.sketch = "on"
        try fixture.app.saveDrawDefaults(defaults)
        fixture.app.phoneDrawText = "a red circle"

        let work = await fixture.app.drawPhoneDescription()
        let saved = try XCTUnwrap(work, fixture.app.phoneDrawFailure ?? "")
        XCTAssertEqual(fixture.app.phoneDrawingWait?.completion?.id, saved.id)
        let calls = await fixture.http.drawingCalls
        XCTAssertEqual(calls, 3, "Reading was rejected before writing and review completed")
        let report = try XCTUnwrap(fixture.app.phoneDrawingWait?.report["finished"].array)
        XCTAssertEqual(report.first?["action"].string, "read_description")
        XCTAssertEqual(report.first?["outcome"].string, "fallback")
        XCTAssertNil(fixture.app.errorText)
        XCTAssertNil(fixture.app.phoneDrawFailure)
    }

    func testPhoneDrawPinsChatGPTSessionBeforeRunning() async throws {
        let fixture = try ReauthFixture(existing: true, failure: .none)
        defer { fixture.remove() }
        await fixture.app.initialize()
        var settings = await fixture.app.hostSettings()
        settings.providers.append(.personalPlan)
        try await fixture.app.updateHostSettings(settings)
        await fixture.app.synchronizePersonalPlanModels()
        var defaults = fixture.app.drawDefaults
        defaults["describe"]?.models.stage1 = "chatgpt:offered"
        defaults["describe"]?.models.stage2 = "chatgpt:offered"
        defaults["describe"]?.route = "stages"
        defaults["describe"]?.sketch = "off"
        try fixture.app.saveDrawDefaults(defaults)
        fixture.app.phoneDrawText = "a red circle"
        let fresh = try fixture.app.requestForPhoneDescription(fixture.app.phoneDrawText)
        XCTAssertNil(fresh.chatGPTSession)
        let pinned = try await fixture.app.pinPersonalPlanRequests([fresh])[0]
        XCTAssertEqual(pinned.chatGPTSession?.profileID, fixture.profileID)
        XCTAssertEqual(pinned.chatGPTSession?.generation, 1)
        _ = await fixture.app.drawPhoneDescription()
        let calls = await fixture.http.otherCalls
        XCTAssertGreaterThan(calls, 0, "The actual home draw must pass pin validation and reach the local HTTP fixture")
        XCTAssertNotEqual(fixture.app.phoneDrawFailure, "chatgpt_session_pin_required")
        XCTAssertEqual(fixture.app.phoneDrawingFailureText("chatgpt_session_pin_required"),
                       ChatGPTStatusCopy.text("chatgpt_session_pin_required", language: fixture.app.display.preferences.language))
        XCTAssertEqual(fixture.app.phoneDrawingFailureText("chatgpt_session_changed"),
                       ChatGPTStatusCopy.text("chatgpt_session_changed", language: fixture.app.display.preferences.language))
        XCTAssertEqual(fixture.app.phoneDrawingFailureText("already localized"), "already localized")
    }

    func testPhoneAdoptsTerraOnlyWhenCurrentDefaultCannotBeUsed() async throws {
        for usable in [false, true] {
            let fixture = try ReauthFixture(existing: true, failure: .none)
            defer { fixture.remove() }
            var vault = try fixture.store.load()
            var profile = try XCTUnwrap(vault.profiles[fixture.profileID])
            profile.models = (profile.models ?? []) + [.init(id: "gpt-6.1-terra", label: "Terra")]
            vault.profiles[fixture.profileID] = profile
            try fixture.store.write(vault)
            await fixture.app.initialize()
            var settings = await fixture.app.hostSettings()
            settings.providers.append(.personalPlan)
            try await fixture.app.updateHostSettings(settings)
            await fixture.app.synchronizePersonalPlanModels()
            var defaults = fixture.app.drawDefaults
            let reference = usable ? "chatgpt:offered" : "missing:model"
            defaults["describe"]?.models.stage1 = reference
            defaults["describe"]?.models.stage2 = reference
            try fixture.app.saveDrawDefaults(defaults)
            try await fixture.app.adoptPhoneChatGPTDefaultIfNeeded()
            let publication = try await fixture.runtime.publication()
            XCTAssertEqual(publication.published.contains("gpt-6.1-terra"), !usable)
            XCTAssertEqual(fixture.app.drawDefaults["describe"]?.models.stage1, usable ? "chatgpt:offered" : "chatgpt:gpt-6.1-terra")
            XCTAssertEqual(fixture.app.display.preferences.drawDefaults?["describe"]?.models.stage2, usable ? "chatgpt:offered" : "chatgpt:gpt-6.1-terra")
        }
    }

    func testAuthorizationRefreshesOnceAndPreservesPublication() async throws {
        for mode in ["new", "reauth", "consent"] {
            let fixture = try ReauthFixture(existing: mode != "new", failure: .none)
            defer { fixture.remove() }
            await fixture.app.initialize()
            let model = ChatGPTPlanSettingsModel()
            await model.load(app: fixture.app)
            let before = await fixture.http.modelCalls
            XCTAssertEqual(before, 0, "Opening settings must not fetch the catalog")
            await model.authorize(consent: mode == "consent", app: fixture.app) { url in
                fixture.accept(url)
            }
            XCTAssertTrue(model.connected, mode)
            XCTAssertNil(model.code)
            let calls = await fixture.http.modelCalls
            XCTAssertEqual(calls, 1, mode)
            let publication = try await fixture.runtime.publication()
            XCTAssertEqual(publication.models.map(\.id), ["offered"])
            XCTAssertEqual(publication.publishedModels.map(\.id), mode == "new" ? [] : ["offered"])
            if mode != "new" {
                let settings = await fixture.app.hostSettings()
                XCTAssertEqual(settings.providers.first(where: { $0.kind == .chatGPTPlan })?.models?.map(\.id), ["offered"])
            }
        }
    }

    func testCatalogFailureKeepsLoginAndShowsSameStatusCopy() async throws {
        let fixture = try ReauthFixture(existing: true, failure: .catalog)
        defer { fixture.remove() }
        await fixture.app.initialize()
        let model = ChatGPTPlanSettingsModel()
        await model.authorize(app: fixture.app) { fixture.accept($0) }
        XCTAssertTrue(model.connected)
        XCTAssertEqual(model.code, "chatgpt_transport_unavailable")
        let calls = await fixture.http.modelCalls
        XCTAssertEqual(calls, 1)
        let saved = try XCTUnwrap(fixture.store.load().profiles[fixture.profileID])
        XCTAssertEqual(saved.state, "connected")
        XCTAssertEqual(saved.generation, 2)
        XCTAssertEqual(saved.publishedModels, ["offered"])
    }

    func testFailedAndCancelledLoginNeverFetchCatalog() async throws {
        for cancelled in [false, true] {
            let fixture = try ReauthFixture(existing: true, failure: .login)
            defer { fixture.remove() }
            await fixture.app.initialize()
            let model = ChatGPTPlanSettingsModel()
            await model.authorize(app: fixture.app) { url in
                if cancelled { Task { @MainActor in await model.cancel(app: fixture.app) } }
                else { fixture.accept(url) }
            }
            let calls = await fixture.http.modelCalls
            XCTAssertEqual(calls, 0)
            let saved = try XCTUnwrap(fixture.store.load().profiles[fixture.profileID])
            XCTAssertEqual(saved.generation, 1)
            if !cancelled { XCTAssertNotNil(model.code) }
        }
    }
}

private final class FixtureKeyStore: ChatGPTVaultKeyStore, @unchecked Sendable {
    private let lock = NSLock()
    private var value: Data?
    func readKey() -> Data? { lock.withLock { value } }
    func saveKey(_ key: Data) { lock.withLock { value = key } }
}

@MainActor private final class ReauthFixture {
    let folder: URL
    let store: ChatGPTPlanStore
    let profileID = UUID().uuidString
    let http: ReauthHTTP
    let runtime: ChatGPTPlanRuntime
    let app: AppModel
    init(existing: Bool, failure: ReauthHTTP.Failure) throws {
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-reauth-" + UUID().uuidString)
        store = ChatGPTPlanStore(directory: folder.appendingPathComponent("vault"), keys: FixtureKeyStore())
        http = try ReauthHTTP(failure: failure)
        runtime = ChatGPTPlanRuntime(store: store, http: http)
        app = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), personalRuntime: runtime)
        var value = ChatGPTVaultState(); value.enabled = true
        if existing {
            value.activeProfileID = profileID
            value.profiles[profileID] = ChatGPTStoredProfile(id: profileID, issuer: "https://auth.openai.com", subject: "fixture-subject", email: nil,
                clientID: "fixture-client", label: "fixture", state: "connected", generation: 1, accessToken: "access", refreshToken: "refresh",
                idToken: nil, scopes: ["chatgpt.tokens.use.direct"], expiresAt: Date().addingTimeInterval(3600), earliestRefreshAt: Date(timeIntervalSince1970: 0),
                models: [.init(id: "offered", label: "Offered")], modelsExpireAt: Date().addingTimeInterval(300), publishedModels: ["offered"])
        }
        try store.write(value)
    }
    func accept(_ url: URL) {
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        let items = Dictionary(uniqueKeysWithValues: components.queryItems!.map { ($0.name, $0.value ?? "") })
        Task {
            await http.setNonce(items["nonce"]!)
            var callback = URLComponents(string: items["redirect_uri"]!)!
            guard callback.scheme == "http", callback.host == "127.0.0.1" else { return }
            callback.queryItems = [.init(name: "state", value: items["state"]), .init(name: "code", value: "fixture-code"), .init(name: "client_id", value: "fixture-client")]
            _ = try? await URLSession.shared.data(from: callback.url!)
        }
    }
    func remove() { try? FileManager.default.removeItem(at: folder) }
}

private func captureDigest(_ body: Data) -> ExactJSON {
    .object(["capture": .string("digest_only"), "byte_len": .integer(body.count),
             "sha256": .string(SHA256.hash(data: body).map { String(format: "%02x", $0) }.joined())])
}

private actor ReauthHTTP: ChatGPTHTTPClient {
    enum Failure { case none, login, catalog, recoveredDraw, observedDraw }
    let failure: Failure
    let key: P256.Signing.PrivateKey
    var nonce = ""
    private(set) var modelCalls = 0
    private(set) var otherCalls = 0
    private(set) var drawingCalls = 0
    private(set) var imageExchange: (response: Data, request: Data)?
    private var imageRequestVerifier: (@Sendable (Data) async throws -> Void)?
    init(failure: Failure) throws { self.failure = failure; key = try P256.Signing.PrivateKey(rawRepresentation: Data(repeating: 0, count: 31) + Data([1])) }
    func setNonce(_ value: String) { nonce = value }
    func verifyImageRequest(_ verify: @escaping @Sendable (Data) async throws -> Void) { imageRequestVerifier = verify }
    func send(_ request: URLRequest, maximumBytes: Int, errorBytes: Int, onBytes: @escaping @Sendable (Int) -> Void) async throws -> ChatGPTHTTPResponse {
        switch request.url?.path {
        case "/api/accounts/oauth/token":
            if failure == .login { return .init(status: 500, data: Data(#"{"error":"fixture"}"#.utf8)) }
            let header: ExactJSON = .object(["alg": .string("ES256"), "kid": .string("fixture")])
            let claims: ExactJSON = .object(["iss": .string("https://auth.openai.com"), "aud": .string("fixture-client"), "sub": .string("fixture-subject"),
                "exp": .integer(Int(Date().timeIntervalSince1970 + 3600)), "nonce": .string(nonce)])
            let input = b64(header.data) + "." + b64(claims.data)
            let token = input + "." + b64(try key.signature(for: Data(input.utf8)).rawRepresentation)
            let result: ExactJSON = .object(["token_type": .string("Bearer"), "access_token": .string("access"), "refresh_token": .string("refresh"),
                "id_token": .string(token), "expires_in": .integer(3600), "scope": .string("chatgpt.tokens.use.direct")])
            return .init(status: 200, data: result.data)
        case "/.well-known/openid-configuration":
            return .init(status: 200, data: Data(#"{"issuer":"https://auth.openai.com","jwks_uri":"https://auth.openai.com/jwks","id_token_signing_alg_values_supported":["ES256"]}"#.utf8))
        case "/jwks":
            let bytes = key.publicKey.x963Representation
            let jwk: ExactJSON = .object(["kty": .string("EC"), "crv": .string("P-256"), "kid": .string("fixture"),
                "x": .string(b64(bytes.subdata(in: 1..<33))), "y": .string(b64(bytes.subdata(in: 33..<65)))])
            return .init(status: 200, data: ExactJSON.object(["keys": .array([jwk])]).data)
        case "/v1/models":
            modelCalls += 1
            if failure == .catalog { throw HostError("chatgpt_transport_unavailable") }
            return .init(status: 200, data: Data(#"{"models":[{"visibility":"list","slug":"offered","display_name":"Offered"}]}"#.utf8))
        case "/v1/responses" where failure == .recoveredDraw || failure == .observedDraw:
            drawingCalls += 1
            let events: [ExactJSON]
            if failure == .recoveredDraw && drawingCalls == 1 {
                events = [.object(["type": .string("response.output_item.added"),
                                   "item": .object(["type": .string("web_search_call"), "id": .string("fixture")])])]
            } else {
                let item: ExactJSON = .object(["type": .string("function_call"), "id": .string("fixture"),
                    "namespace": .string("inku"), "name": .string("submit_pipeline_response"),
                    "arguments": .string(#"{"ddl":"place one red circle at center.","figures":[]}"#)])
                let body = request.httpBody ?? Data()
                let containsImage = String(decoding: body, as: UTF8.self).contains("data:image/png;base64,")
                var response: ExactJSON = .object(["status": .string("completed"), "output": .array([item])])
                if containsImage {
                    try await imageRequestVerifier?(body)
                    response["echo"] = .string(String(decoding: body, as: UTF8.self))
                }
                events = [.object(["type": .string("response.output_item.added"), "item": item]),
                          .object(["type": .string("response.completed"), "response": response])]
                if containsImage { imageExchange = (response: encode(events), request: body) }
            }
            return .init(status: 200, data: encode(events))
        default: otherCalls += 1; throw HostError("unexpected_fixture_route")
        }
    }
    private func encode(_ events: [ExactJSON]) -> Data {
        Data(events.map { "data: " + $0.text + "\n\n" }.joined().utf8)
    }
    private func b64(_ data: Data) -> String { data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
}
