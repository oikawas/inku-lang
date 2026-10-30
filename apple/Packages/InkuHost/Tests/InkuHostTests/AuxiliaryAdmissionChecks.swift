import Foundation
import InkuPersistence
import XCTest
@testable import InkuHost

final class AuxiliaryAdmissionChecks: XCTestCase, @unchecked Sendable {
    func testTextAdmissionSettlementAnd429() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-aux-rate-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let database = try InkuDatabase(url: folder.appendingPathComponent("test.sqlite"))
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let environment = ProviderRateEnvironment(clock: { now }, sleep: { _ in try Task.checkCancellation() })
        let absent = folder.appendingPathComponent("absent.json")
        let prompt = AuxiliaryPrompt(system: "system", message: "message", temperature: 0.9, maximumTokens: 16, timeoutSeconds: 10, purpose: .demo)
        for mode in AuxiliaryAdmissionHTTP.Mode.allCases {
            let gemini = mode != .unlimited
            let provider = ProviderSettings(id: "fixture-\(mode)", kind: gemini ? .gemini : .openAICompatible,
                baseURL: URL(string: "https://fixture.invalid/v1")!, requiresAPIKey: false,
                rateLimits: .init(requestsPerMinute: 0, tokensPerMinute: gemini ? 1000 : 0, requestsPerDay: mode == .success ? 1 : 0))
            let http = AuxiliaryAdmissionHTTP(mode: mode, database: database, providerID: provider.id)
            let transport = URLSessionProviderTransport(usageURL: absent, http: http, database: database, environment: environment)
            do {
                let answer = try await transport.performAuxiliary(prompt: prompt, modelReference: provider.id + ":fixture",
                    settings: HostSettings(providers: [provider]), credentials: AuxiliaryAdmissionCredentials(), onBytes: { _ in })
                XCTAssertEqual(answer, "answer")
                XCTAssertTrue(mode == .success || mode == .missingUsage || mode == .unlimited)
            } catch {
                XCTAssertTrue(mode == .generation429 || mode == .count429, "Unexpected \(mode): \(error)")
                XCTAssertEqual((error as? HostError)?.code, "rate_limited")
            }
            let counts = await http.counts
            let generations = await http.generations
            XCTAssertEqual(counts, gemini ? 1 : 0)
            XCTAssertEqual(generations, mode == .count429 ? 0 : 1)
            let saved = try await database.providerRateState(providerID: provider.id)
            let state = try XCTUnwrap(saved)
            XCTAssertEqual(state.daily, mode == .count429 ? 0 : 1)
            if mode == .success {
                XCTAssertEqual(state.events.first?.tokens, 85)
                let pipelineBudget = ProviderRateBudget(database: database, legacyURL: absent, environment: environment)
                do {
                    _ = try await pipelineBudget.reserve(provider: provider, inputTokens: 1, deadline: now.addingTimeInterval(1))
                    XCTFail("Text and drawing must share the daily budget")
                } catch { XCTAssertEqual((error as? HostError)?.code, "rate_limited") }
            }
            if mode == .missingUsage { XCTAssertEqual(state.events.first?.tokens, 110); XCTAssertEqual(state.notBefore, now.timeIntervalSince1970 + 62) }
            if mode == .generation429 || mode == .count429 { XCTAssertEqual(state.notBefore, now.timeIntervalSince1970 + 99) }
        }
    }
}
private struct AuxiliaryAdmissionCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}
private actor AuxiliaryAdmissionHTTP: ProviderHTTPClient {
    enum Mode: CaseIterable, Sendable { case success, missingUsage, generation429, count429, unlimited }
    let mode: Mode
    let database: InkuDatabase
    let providerID: String
    private(set) var counts = 0
    private(set) var generations = 0
    private var countBody: ExactJSON?
    init(mode: Mode, database: InkuDatabase, providerID: String) { self.mode = mode; self.database = database; self.providerID = providerID }
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse {
        let body = try ExactJSON(data: request.httpBody!)
        let count = request.url!.path.hasSuffix(":countTokens")
        if count { counts += 1; countBody = body["generateContentRequest"] }
        else {
            generations += 1
            guard let state = try await database.providerRateState(providerID: providerID), state.daily == 1 else { throw HostError("missing_reservation") }
            if let countBody {
                var fields = countBody.object!; fields.removeValue(forKey: "model")
                guard ExactJSON.object(fields) == body, state.events.first?.tokens == 110 else { throw HostError("wrong_count_request") }
            }
        }
        let status = (count && mode == .count429) || (!count && mode == .generation429) ? 429 : 200
        let value: ExactJSON
        if status == 429 {
            value = .object(["error": .object(["details": .array([.object(["@type": .string("type.googleapis.com/google.rpc.RetryInfo"), "retryDelay": .string("99s")])])])])
        } else if count { value = .object(["totalTokens": .integer(100)]) }
        else if mode == .unlimited { value = .object(["choices": .array([.object(["message": .object(["content": .string("answer")])])])]) }
        else {
            var fields: [String: ExactJSON] = ["candidates": .array([.object(["content": .object(["parts": .array([.object(["text": .string("answer")])])])])])]
            if mode == .success { fields["usageMetadata"] = .object(["promptTokenCount": .integer(85)]) }
            value = .object(fields)
        }
        onResponse(.init(status: status, data: value.data, sent: true, complete: true, truncated: false))
        return .init(status: status, data: value.data, retryAfter: 1)
    }
}
