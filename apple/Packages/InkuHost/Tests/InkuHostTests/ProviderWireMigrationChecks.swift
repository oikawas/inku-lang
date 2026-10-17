import Foundation
import XCTest
@testable import InkuHost

/// Failure: a wire-rule migration changes an existing Swift request or answer without accounting for it.
final class ProviderWireMigrationChecks: XCTestCase {
    static func casesURL() throws -> URL {
        var parent = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        while parent.path != "/" {
            let candidate = parent.appendingPathComponent("server/tests/data/provider-wire-cases.json")
            if FileManager.default.fileExists(atPath: candidate.path) { return candidate }
            parent.deleteLastPathComponent()
        }
        throw HostError("missing_shared_provider_wire_cases")
    }

    static func provider(_ request: ExactJSON) -> ProviderSettings? {
        let value = request["connection"]
        guard let kind = value["kind"].string.flatMap(ProviderKind.init(rawValue:)),
              let url = value["base_url"].string.flatMap(URL.init(string:)) else { return nil }
        return ProviderSettings(id: value["id"].string!, kind: kind, baseURL: url,
            apiProfile: value["api_profile"].string, requiresAPIKey: false)
    }

    static func effect(_ rawRequest: Data) throws -> Data {
        let prompt = try ExactJSON.rawMember("prompt", in: rawRequest)
        return Data(("{\"payload\":{\"prompt\":" + String(decoding: prompt, as: UTF8.self) + "}}").utf8)
    }

    // Failure: core bytes are re-encoded, auth is added in core, a raw schema loses its
    // order, or one host interprets an answer differently from the shared fixture.
    func testEverySharedProviderWireCase() throws {
        let data = try Data(contentsOf: Self.casesURL())
        var counts: [String: Int] = [:]
        for category in ["requests", "text_requests", "responses"] {
            for rawRow in try ExactJSON.rawElements(in: ExactJSON.rawMember(category, in: data)) {
                let row = try ExactJSON(data: rawRow)
                let input = try ExactJSON.rawMember("request", in: rawRow)
                let request = try ExactJSON(data: input), expected = row["expect"]
                let result = try ProviderWire.evaluate(input)
                let name = row["why"].string ?? category
                counts[category, default: 0] += 1
                if category == "responses" || expected["outcome"].string != "ok" {
                    for (field, value) in expected.object ?? [:] { XCTAssertEqual(result[field], value, name + ": " + field) }
                    continue
                }
                XCTAssertEqual(result["outcome"], expected["outcome"], name)
                XCTAssertEqual(result["body"], expected["body"], name)
                XCTAssertEqual(result["url"], expected["url"], name)
                var headers = try JSONDecoder().decode([String: String].self, from: result["headers"].data)
                let auth = result["auth"]
                headers[try auth.requiredString("header")] = try auth.requiredString("prefix") + "KEY"
                XCTAssertEqual(.object(Dictionary(uniqueKeysWithValues: headers.map { ($0.key.lowercased(), ExactJSON.string($0.value)) })), expected["headers"], name)
                let expectedBody = try ExactJSON(data: Data(expected["body"].string!.utf8))
                let expectedBudget = result["format"].string == "gemini" ? expectedBody["generationConfig"]["maxOutputTokens"]
                    : [expectedBody["max_tokens"], expectedBody["max_completion_tokens"], expectedBody["max_output_tokens"]].first { $0 != .null } ?? .null
                XCTAssertEqual(result["output_budget"], expectedBudget, name)
                if result["count_tokens"].object != nil {
                    let expectedCount = "{\"generateContentRequest\":{\"model\":" + ExactJSON.string("models/" + request["model"].string!).text + "," + String(expected["body"].string!.dropFirst()) + "}"
                    XCTAssertEqual(result["count_tokens"]["body"].string, expectedCount, name)
                    XCTAssertEqual(result["count_tokens"]["url"].string, expected["url"].string!.replacingOccurrences(of: ":generateContent", with: ":countTokens"), name)
                }
                if let provider = Self.provider(request), (try? provider.validate()) != nil {
                    let actual: URLRequest
                    if category == "requests" {
                        actual = try ProviderWire.request(action: Self.effect(input), provider: provider,
                            model: request["model"].string!, maxTokens: Int(request["max_tokens"].number!)!, key: "KEY")
                    } else {
                        let prompt = AuxiliaryPrompt(system: request["system"].string!, message: request["text"].string!,
                            images: request["images"].array?.compactMap(\.string) ?? [],
                            temperature: Double(request["temperature"].number!)!, maximumTokens: Int(request["max_tokens"].number!)!)
                        actual = try AuxiliaryWire.request(prompt: prompt, provider: provider, model: request["model"].string!, key: "KEY")
                    }
                    XCTAssertEqual(actual.httpBody, Data(expected["body"].string!.utf8), name)
                    XCTAssertEqual(actual.url?.absoluteString, expected["url"].string, name)
                }
            }
        }
        XCTAssertEqual(counts, ["requests": 246, "text_requests": 81, "responses": 97])
        print("Shared provider wire rows checked: requests=246, text=81, responses=97, body/auth/budget/countTokens; synthetic KEY only, HTTP=0")
    }

    func testCaptureSwiftWireInventory() throws {
        guard let destination = ProcessInfo.processInfo.environment["INKU_WIRE_AUDIT_OUTPUT"] else {
            throw XCTSkip("Set a fresh audit output to compare the existing Swift boundary")
        }
        let url = URL(fileURLWithPath: destination)
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
        let data = try Data(contentsOf: Self.casesURL())
        var rows: [ExactJSON] = []
        for category in ["requests", "text_requests"] {
            for (index, rawRow) in try ExactJSON.rawElements(in: ExactJSON.rawMember(category, in: data)).enumerated() {
                let raw = try ExactJSON.rawMember("request", in: rawRow), input = try ExactJSON(data: raw)
                var row: ExactJSON = .object(["category": .string(category), "index": .integer(index)])
                guard let provider = Self.provider(input) else {
                    row["outcome"] = .string("unrepresentable_host_kind"); rows.append(row); continue
                }
                do {
                    let request: URLRequest
                    if category == "requests" {
                        request = try ProviderWire.request(action: Self.effect(raw), provider: provider,
                            model: input["model"].string!, maxTokens: Int(input["max_tokens"].number!)!, key: "KEY")
                    } else {
                        let prompt = AuxiliaryPrompt(system: input["system"].string!, message: input["text"].string!,
                            images: input["images"].array?.compactMap(\.string) ?? [],
                            temperature: Double(input["temperature"].number!)!, maximumTokens: Int(input["max_tokens"].number!)!)
                        request = try AuxiliaryWire.request(prompt: prompt, provider: provider, model: input["model"].string!, key: "KEY")
                    }
                    row["outcome"] = .string("ok"); row["url"] = .string(request.url!.absoluteString)
                    row["body"] = .string(String(decoding: request.httpBody!, as: UTF8.self))
                    row["headers"] = .object(Dictionary(uniqueKeysWithValues: (request.allHTTPHeaderFields ?? [:]).map { ($0.key.lowercased(), ExactJSON.string($0.value)) }))
                } catch { row["outcome"] = .string("refused"); row["host_error"] = .string((error as? HostError)?.code ?? String(describing: type(of: error))) }
                rows.append(row)
            }
        }
        for (index, rawRow) in try ExactJSON.rawElements(in: ExactJSON.rawMember("responses", in: data)).enumerated() {
            let input = try ExactJSON(data: ExactJSON.rawMember("request", in: rawRow))
            let format = input["format"].string!, status = Int(input["status"].number!)!, body = input["body"].string!
            let kind: ProviderKind = format == "gemini" ? .gemini : format == "anthropic" ? .anthropic : .openAICompatible
            var row: ExactJSON = .object(["category": .string("responses"), "index": .integer(index)])
            if !(200...299).contains(status) {
                let diagnostic = ProviderDiagnosticSanitizer.diagnostic(error: HTTPFailure(status: status, retryAfter: 60),
                    endpoint: nil, secrets: ["KEY"], httpStatus: status, httpBody: Data(body.utf8))
                var refusal: [String: ExactJSON] = [:]
                for (name, value) in [("code", diagnostic.providerCode), ("type", diagnostic.providerType),
                                      ("param", diagnostic.providerParameter), ("status", diagnostic.providerStatus), ("message", diagnostic.providerMessage)] {
                    if let value { refusal[name] = .string(value) }
                }
                row["outcome"] = .string("http_error"); row["refusal"] = .object(refusal)
                row["failure"] = .string(status == 429 ? "rate_limited" : status >= 500 ? "transport_unavailable" : "provider_rejected")
            } else {
                let value = try? ExactJSON(data: Data(body.utf8))
                let cut = value.flatMap { ProviderOutputLimit.record($0, kind: kind, responses: format == "openai_responses") }
                if let cut { row["cut"] = cut }
                do {
                    let text: String
                    if input["action"].string == "text_response" { text = try AuxiliaryWire.responseText(Data(body.utf8), kind: kind) }
                    else if format == "openai_responses" {
                        text = try ProviderWire.responseText(Data(body.utf8), format: "openai_responses")
                    } else { text = try ProviderWire.responseText(Data(body.utf8), kind: kind) }
                    row["outcome"] = .string("answer"); row["text"] = .string(text)
                } catch { row["outcome"] = .string(cut != nil ? "cut" : "malformed") }
            }
            rows.append(row)
        }
        try ExactJSON.array(rows).data.write(to: url, options: .withoutOverwriting)
        print("Swift provider wire inventory: \(rows.count) rows, synthetic KEY only, HTTP=0")
    }

    // Failure: a host-side JSON pre-parser rejects a response before the shared reader sees it.
    func testPipelineResponsesThroughHTTPBoundary() async throws {
        let data = try Data(contentsOf: Self.casesURL())
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-wire-http-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        var checked = 0
        for (index, rawRow) in try ExactJSON.rawElements(in: ExactJSON.rawMember("responses", in: data)).enumerated() {
            let row = try ExactJSON(data: rawRow), input = row["request"], expected = row["expect"]
            guard input["action"].string == "pipeline_response" else { continue }
            let format = input["format"].string!, status = Int(input["status"].number!)!
            let kind: ProviderKind = format == "gemini" ? .gemini : format == "anthropic" ? .anthropic : .openAICompatible
            let provider = ProviderSettings(id: "wire-\(index)", kind: kind,
                baseURL: URL(string: format == "openai_responses" ? "https://api.openai.com/v1" : "https://fixture.invalid/v1")!,
                requiresAPIKey: false, rateLimits: .init(requestsPerMinute: 0, tokensPerMinute: 0, requestsPerDay: 0))
            let transport = URLSessionProviderTransport(usageURL: folder.appendingPathComponent("\(index).json"),
                http: WireFixtureHTTP(status: status, body: Data(input["body"].string!.utf8)))
            let models = ModelSelection(stage1Model: provider.id + ":fixture", stage2Model: provider.id + ":fixture")
            let result = try ExactJSON(data: await transport.perform(action: SchemaOrderFixture.action(SchemaOrderFixture.unordered),
                models: models, providers: [provider], credentials: WireFixtureCredentials(), onBytes: { _ in }))
            if expected["outcome"].string == "answer" {
                XCTAssertEqual(result["tag"].string, "composition_read", row["why"].string ?? "")
                XCTAssertEqual(result["response"], expected["text"], row["why"].string ?? "")
            } else {
                XCTAssertEqual(result["tag"].string, "provider_failed")
                XCTAssertEqual(result["failure"], expected["outcome"].string == "http_error" ? expected["failure"] : .string("malformed_payload"))
            }
            checked += 1
        }
        XCTAssertEqual(checked, 78)
    }
}

private struct WireFixtureCredentials: CredentialStore {
    func key(for credentialID: String) async throws -> String? { nil }
}

private struct WireFixtureHTTP: ProviderHTTPClient {
    let status: Int
    let body: Data
    func send(_ request: URLRequest, maximumBytes: Int, onBytes: @escaping @Sendable (Int) -> Void,
              onResponse: @escaping ProviderHTTPReadHandler) async throws -> ProviderHTTPResponse {
        onBytes(body.count)
        onResponse(.init(status: status, data: body, sent: true, complete: true, truncated: false))
        return .init(status: status, data: body)
    }
}
