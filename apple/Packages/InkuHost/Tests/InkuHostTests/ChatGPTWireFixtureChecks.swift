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
            // The 59 authentication/publication rows have their own policy check.
            guard ["chatgpt_request", "chatgpt_vision_request", "chatgpt_stream", "chatgpt_error", "chatgpt_catalog", "chatgpt_failure",
                   "chatgpt_models_request", "chatgpt_transport"].contains(action) else { continue }
            counts[action, default: 0] += 1
            // The core itself, field by field.
            let result = try ProviderWire.evaluate(input)
            for (field, value) in expected.object ?? [:] { XCTAssertEqual(result[field], value, name + ": " + field) }
            // The Swift receiver the runtime calls.
            let limit = request["answer_limit"].number.flatMap { Int($0) } ?? 0
            switch action {
            case "chatgpt_request":
                let effect = Data(("{\"payload\":{\"prompt\":" + String(decoding: try ExactJSON.rawMember("prompt", in: input), as: UTF8.self) + "}}").utf8)
                let prepared = try ChatGPTPlanRuntime.request(action: effect, model: request.requiredString("model"), argumentLimit: limit)
                if expected["body"] != .null { XCTAssertEqual(prepared.body, Data(try expected.requiredString("body").utf8), name) }
                XCTAssertEqual(String(prepared.wireLimit), result["wire_limit"].number, name)
                try checkEndpoint(prepared.endpoint, result, name)
            case "chatgpt_vision_request":
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
            case "chatgpt_stream":
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
            case "chatgpt_error":
                let status = request["status"].number.flatMap { Int($0) }
                let failure = try (request["body"].string.map {
                    try ChatGPTWire.httpFailure(body: Data($0.utf8), status: status, requestID: request["request_id"].string)
                } ?? ChatGPTWire.httpFailure(value: request["value"], status: status, requestID: request["request_id"].string)).diagnostic
                XCTAssertEqual(failure.code, expected["code"].string, name)
                XCTAssertEqual(failure.pipelineFailure, expected["failure"].string, name)
                XCTAssertEqual(failure.action, expected["action"].string, name)
                XCTAssertEqual(failure.status.map { String($0) }, expected["status"].number, name)
                XCTAssertEqual(failure.requestID, expected["request_id"].string, name)
                XCTAssertEqual(failure.parameter, expected["param"].string, name)
            case "chatgpt_catalog":
                let read = { try request["body"].string.map { try ChatGPTWire.catalog(body: Data($0.utf8)) } ?? ChatGPTWire.catalog(request["value"]) }
                guard expected["outcome"].string == "ok" else {
                    XCTAssertThrowsError(try read(), name) { error in
                        guard expected["outcome"].string == "malformed" else { return }
                        let diagnostic = ChatGPTPlanRuntime.diagnostic(error)
                        XCTAssertEqual(diagnostic.code, result["code"].string, name)
                        XCTAssertEqual(diagnostic.pipelineFailure, result["failure"].string, name)
                        XCTAssertEqual(diagnostic.action, result["action"].string, name)
                    }
                    continue
                }
                let models = try read()
                XCTAssertEqual(models.map(\.id), expected["models"].array?.compactMap { $0["id"].string }, name)
                XCTAssertEqual(models.map(\.label), expected["models"].array?.compactMap { $0["label"].string }, name)
            case "chatgpt_failure":
                let diagnostic = ChatGPTPlanDiagnostic(code: try request.requiredString("code"), temporary: request["temporary"].bool)
                XCTAssertEqual(diagnostic.pipelineFailure, expected["failure"].string, name)
                XCTAssertEqual(diagnostic.action, expected["action"].string, name)
            case "chatgpt_models_request":
                let endpoint = try ChatGPTWire.modelsEndpoint()
                try checkEndpoint(endpoint, result, name)
                XCTAssertEqual(endpoint.answerLimit.map { String($0) }, result["answer_limit"].number, name)
            case "chatgpt_transport":
                let kind = try XCTUnwrap(ChatGPTWire.Transport(rawValue: request.requiredString("kind")), name)
                let diagnostic = ChatGPTWire.transport(kind).diagnostic
                XCTAssertEqual(diagnostic.code, expected["code"].string, name)
                XCTAssertEqual(diagnostic.pipelineFailure, expected["failure"].string, name)
                XCTAssertEqual(diagnostic.action, expected["action"].string, name)
            default: XCTFail(name + ": unknown action")
            }
        }
        XCTAssertEqual(counts, ["chatgpt_request": 9, "chatgpt_vision_request": 9, "chatgpt_stream": 59, "chatgpt_error": 11, "chatgpt_catalog": 8,
                                "chatgpt_failure": 75, "chatgpt_models_request": 1, "chatgpt_transport": 3])
        print("Shared ChatGPT rows checked: \(counts.values.reduce(0, +)) (requests=9, vision=9, streams=59, errors=11, catalogs=8, failures=75, models request=1, transport=3) through core and the Swift receivers; HTTP=0")
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
