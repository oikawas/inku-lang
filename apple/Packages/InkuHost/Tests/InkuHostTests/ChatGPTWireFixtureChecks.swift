import Foundation
import XCTest
@testable import InkuHost

/// Failure: the plan's body, stream reading, failure classification or model list differs from the shared core,
/// or a Swift receiver re-encodes or reinterprets what the core answered.
final class ChatGPTWireFixtureChecks: XCTestCase {
    func testEverySharedChatGPTCase() throws {
        let data = try Data(contentsOf: ProviderWireMigrationChecks.casesURL())
        var counts: [String: Int] = [:]
        for rawRow in try ExactJSON.rawElements(in: ExactJSON.rawMember("chatgpt", in: data)) {
            let row = try ExactJSON(data: rawRow)
            let input = try ExactJSON.rawMember("request", in: rawRow)
            let request = row["request"], expected = row["expect"]
            let name = row["why"].string ?? "chatgpt"
            let action = try request.requiredString("action")
            // The 21 authentication/publication rows have their own policy check.
            guard ["sign_in_request", "sign_in_vision_request", "sign_in_stream", "sign_in_error", "sign_in_failure",
                   "sign_in_transport"].contains(action) else { continue }
            counts[action, default: 0] += 1
            // The core itself, field by field.
            let result = try ProviderWire.evaluate(input)
            for (field, value) in expected.object ?? [:] { XCTAssertEqual(result[field], value, name + ": " + field) }
            // The Swift receiver the runtime calls.
            let limit = request["answer_limit"].number.flatMap { Int($0) } ?? 0
            switch action {
            case "sign_in_request":
                let prompt = try ExactJSON.rawMember("prompt", in: input)
                let prepared = try ChatGPTWire.request(model: request.requiredString("model"), prompt: prompt, answerLimit: limit)
                if expected["body"] != .null { XCTAssertEqual(prepared.body, Data(try expected.requiredString("body").utf8), name) }
                XCTAssertEqual(String(prepared.wireLimit), result["wire_limit"].number, name)
                try checkEndpoint(prepared.endpoint, result, name)
            case "sign_in_vision_request":
                let images = request["images"].array?.compactMap(\.string) ?? []
                let prepare = { try ChatGPTWire.visionRequest(model: request.requiredString("model"), system: request.requiredString("system"),
                                                              text: request.requiredString("text"), images: images, answerLimit: limit) }
                if expected["outcome"].string == "refused" {
                    XCTAssertThrowsError(try prepare(), name) { XCTAssertEqual(($0 as? HostError)?.code, "pipeline_schema_violation", name) }
                } else {
                    let prepared = try prepare()
                    if expected["body"] != .null { XCTAssertEqual(prepared.body, Data(try expected.requiredString("body").utf8), name) }
                    try checkEndpoint(prepared.endpoint, result, name)
                }
            case "sign_in_stream":
                let wire = try XCTUnwrap(Data(base64Encoded: request.requiredString("wire_base64")), name)
                let stream = try ChatGPTWire.read(text: request["mode"].string == "text", answerLimit: limit, wire: wire)
                XCTAssertEqual(stream.terminal ?? .null, expected["terminal"], name)
                switch (stream.result, expected["outcome"].string) {
                case (.success(let text), "answer"): XCTAssertEqual(text, expected["text"].string, name)
                case (.failure(let failure), "failed"):
                    XCTAssertEqual(failure.diagnostic.code, expected["code"].string, name)
                    XCTAssertEqual(failure.diagnostic.pipelineFailure, expected["failure"].string, name)
                    XCTAssertEqual(failure.diagnostic.action, expected["action"].string, name)
                case (.failure(let failure), "malformed"):
                    // Step 4: the core's code, failure and action (a stream it cannot read is asked again for).
                    XCTAssertEqual(failure.diagnostic.code, result["code"].string, name)
                    XCTAssertEqual(failure.diagnostic.pipelineFailure, result["failure"].string, name)
                    XCTAssertEqual(failure.diagnostic.action, result["action"].string, name)
                default: XCTFail(name + ": the Swift receiver answered differently")
                }
            case "sign_in_error":
                // The runtime hands the core the answer's text; a row given as a value is sent as that value's text.
                let status = request["status"].number.flatMap { Int($0) }
                let body = request["body"].string.map { Data($0.utf8) } ?? request["value"].data
                let failure = try ChatGPTWire.httpFailure(body: body, status: status, requestID: request["request_id"].string).diagnostic
                XCTAssertEqual(failure.code, expected["code"].string, name)
                XCTAssertEqual(failure.pipelineFailure, expected["failure"].string, name)
                XCTAssertEqual(failure.action, expected["action"].string, name)
                XCTAssertEqual(failure.status.map { String($0) }, expected["status"].number, name)
                XCTAssertEqual(failure.requestID, expected["request_id"].string, name)
                XCTAssertEqual(failure.parameter, expected["param"].string, name)
            case "sign_in_failure":
                let diagnostic = ChatGPTPlanDiagnostic(code: try request.requiredString("code"), temporary: request["temporary"].bool)
                XCTAssertEqual(diagnostic.pipelineFailure, expected["failure"].string, name)
                XCTAssertEqual(diagnostic.action, expected["action"].string, name)
            case "sign_in_transport":
                let kind = try XCTUnwrap(ChatGPTWire.Transport(rawValue: request.requiredString("kind")), name)
                let diagnostic = ChatGPTWire.transport(kind).diagnostic
                XCTAssertEqual(diagnostic.code, expected["code"].string, name)
                XCTAssertEqual(diagnostic.pipelineFailure, expected["failure"].string, name)
                XCTAssertEqual(diagnostic.action, expected["action"].string, name)
            default: XCTFail(name + ": unknown action")
            }
        }
        XCTAssertEqual(counts, ["sign_in_request": 9, "sign_in_vision_request": 9, "sign_in_stream": 59, "sign_in_error": 11,
                                "sign_in_failure": 75, "sign_in_transport": 3])
        print("Shared ChatGPT rows checked: \(counts.values.reduce(0, +)) (requests=9, vision=9, streams=59, errors=11, failures=75, transport=3) through core and the Swift receivers; HTTP=0")
    }

    /// Step 6: the host's own guard on where anything is sent (kept by the author's choice) names the same places as
    /// the core's descriptor — the sign-in issuer's host and the resource's host and paths.
    func testHostSendGuardAgreesWithTheCoreDescriptor() throws {
        let constants = try ChatGPTPolicy.call("sign_in_auth_constants")
        let issuer = try XCTUnwrap(URL(string: try constants.requiredString("issuer")))
        let resource = try XCTUnwrap(URL(string: try constants.requiredString("resource")))
        XCTAssertEqual(issuer.host, ChatGPTEndpoints.authenticationHost)
        XCTAssertEqual(resource.host, ChatGPTEndpoints.apiHost)
        XCTAssertEqual(Set(ChatGPTEndpoints.apiPaths), [resource.path + "/models", resource.path + "/responses"])
        for suffix in ["/models", "/responses"] {
            XCTAssertNoThrow(try ChatGPTEndpoints.validate(try XCTUnwrap(URL(string: resource.absoluteString + suffix))), suffix)
        }
        // Every sign-in address goes to the core, which accepts the issuer's own.
        for name in ["token", "authorize"] {
            XCTAssertNoThrow(try ChatGPTEndpoints.validate(try XCTUnwrap(URL(string: try constants.requiredString(name))), authenticationOnly: true), name)
        }
    }

    /// Step 4: the request Swift sends goes where the core says, with its headers and token.
    private func checkEndpoint(_ endpoint: ChatGPTWire.Endpoint, _ result: ExactJSON, _ name: String) throws {
        let request = endpoint.request(token: "token-a", body: Data("{}".utf8), deadline: Date().addingTimeInterval(60))
        XCTAssertEqual(request.url?.absoluteString, result["url"].string, name)
        XCTAssertEqual(request.httpMethod, result["method"].string, name)
        var headers = (result["headers"].object ?? [:]).compactMapValues(\.string)
        headers[try result["auth"].requiredString("header")] = try result["auth"].requiredString("prefix") + "token-a"
        XCTAssertEqual(request.allHTTPHeaderFields, headers, name)
    }
}
