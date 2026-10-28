import Foundation
import InkuPersistence
import XCTest
@testable import InkuHost

final class ReadAndDrawTransportChecks: XCTestCase, @unchecked Sendable {
    func testFourActionsUseStageOneAnd8192Tokens() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-read-wire-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
        let http = ReadAndDrawWireHTTP()
        let transport = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("none.json"), http: http, database: db)
        let provider = ProviderSettings(id: "fixture", baseURL: URL(string: "https://fixture.invalid/v1")!, requiresAPIKey: false)
        let models = ModelSelection(stage1Model: "fixture:first", stage2Model: "fixture:second", stage1MaxTokens: 123, holeMaxTokens: 456)
        let cases = [("read_description", "description_read"), ("compose_description", "description_composed"),
                     ("write_description_ddl", "description_ddl_written"), ("review_description_ddl", "description_ddl_reviewed")]
        for (tag, expected) in cases {
            let action: ExactJSON = .object(["tag": .string(tag), "identity": .object(["action_id": .string(tag), "attempt": .integer(1), "request_digest": .string(tag)]),
                "timeout_ms": .string("2000"), "payload": .object(["prompt": .object(["system": .string("system"), "message": .string("message"),
                    "action_name": .string(tag), "response_schema": .object(["type": .string("object")])])])])
            let response = try ExactJSON(data: await transport.perform(action: action.data, models: models, providers: [provider], credentials: ReadAndDrawNoKeys(), onBytes: { _ in }))
            XCTAssertEqual(response["tag"].string, expected)
        }
        let bodies = await http.bodies
        XCTAssertEqual(bodies.count, 4)
        XCTAssertTrue(bodies.allSatisfy { $0["model"].string == "first" && $0["max_tokens"].number == "8192" })
    }
}
private struct ReadAndDrawNoKeys: CredentialStore { func key(for credentialID: String) async throws -> String? { nil } }
private actor ReadAndDrawWireHTTP: ProviderHTTPClient {
    private(set) var bodies: [ExactJSON] = []
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse {
        bodies.append(try ExactJSON(data: request.httpBody!))
        let data = Data(#"{"choices":[{"message":{"content":"{}"}}]}"#.utf8)
        onResponse(.init(status: 200, data: data, sent: true, complete: true, truncated: false))
        return .init(status: 200, data: data)
    }
}
