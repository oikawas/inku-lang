import CryptoKit
import Foundation
import XCTest
@testable import InkuHost
@testable import InkuUI

@MainActor final class ChatGPTReauthCatalogTests: XCTestCase {
    func testAuthorizationRefreshesOnceAndPreservesPublication() async throws {
        for mode in ["new", "reauth", "consent"] {
            let fixture = try ReauthFixture(existing: mode != "new", failure: .none)
            defer { fixture.remove() }
            await fixture.app.initialize()
            let model = ChatGPTPlanSettingsModel()
            await model.load(app: fixture.app)
            let before = await fixture.http.modelCalls
            XCTAssertEqual(before, 0, "Opening settings must not fetch the catalog")
            await model.authorize(profileID: mode == "new" ? nil : fixture.profileID, consent: mode == "consent", app: fixture.app) { url in
                fixture.accept(url)
            }
            XCTAssertTrue(model.connected, mode)
            XCTAssertEqual(model.status, "")
            XCTAssertNil(model.errorText)
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
        await model.authorize(profileID: fixture.profileID, app: fixture.app) { fixture.accept($0) }
        XCTAssertTrue(model.connected)
        XCTAssertEqual(model.status, "")
        XCTAssertEqual(model.errorText, ChatGPTStatusCopy.text("chatgpt_transport_unavailable", language: fixture.app.display.preferences.language))
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
            await model.authorize(profileID: fixture.profileID, app: fixture.app) { url in
                if cancelled { Task { @MainActor in await model.cancel(app: fixture.app) } }
                else { fixture.accept(url) }
            }
            let calls = await fixture.http.modelCalls
            XCTAssertEqual(calls, 0)
            let saved = try XCTUnwrap(fixture.store.load().profiles[fixture.profileID])
            XCTAssertEqual(saved.generation, 1)
            if !cancelled { XCTAssertNotNil(model.errorText) }
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

private actor ReauthHTTP: ChatGPTHTTPClient {
    enum Failure { case none, login, catalog }
    let failure: Failure
    let key: P256.Signing.PrivateKey
    var nonce = ""
    private(set) var modelCalls = 0
    init(failure: Failure) throws { self.failure = failure; key = try P256.Signing.PrivateKey(rawRepresentation: Data(repeating: 0, count: 31) + Data([1])) }
    func setNonce(_ value: String) { nonce = value }
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void) async throws -> ChatGPTHTTPResponse {
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
        default: throw HostError("unexpected_fixture_route")
        }
    }
    private func b64(_ data: Data) -> String { data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
}
