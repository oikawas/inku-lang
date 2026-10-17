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
                XCTAssertEqual(prepared.body, Data(try expected.requiredString("body").utf8), name)
                XCTAssertEqual(String(prepared.wireLimit), result["wire_limit"].number, name)
            case "chatgpt_vision_request":
                let images = request["images"].array?.compactMap(\.string) ?? []
                let prepare = { try ChatGPTWire.visionRequest(model: request.requiredString("model"), system: request.requiredString("system"),
                                                              text: request.requiredString("text"), images: images, answerLimit: limit) }
                if expected["outcome"].string == "refused" {
                    XCTAssertThrowsError(try prepare(), name) { XCTAssertEqual(($0 as? HostError)?.code, "pipeline_schema_violation", name) }
                } else { XCTAssertEqual(try prepare().body, Data(try expected.requiredString("body").utf8), name) }
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
                case (.failure(let failure), "malformed"): XCTAssertEqual(failure.diagnostic.code, "chatgpt_response_invalid", name)
                default: XCTFail(name + ": the Swift receiver answered differently")
                }
            case "chatgpt_error":
                let failure = try ChatGPTWire.httpFailure(value: request["value"], status: request["status"].number.flatMap { Int($0) },
                                                          requestID: request["request_id"].string).diagnostic
                XCTAssertEqual(failure.code, expected["code"].string, name)
                XCTAssertEqual(failure.pipelineFailure, expected["failure"].string, name)
                XCTAssertEqual(failure.action, expected["action"].string, name)
                XCTAssertEqual(failure.status.map { String($0) }, expected["status"].number, name)
                XCTAssertEqual(failure.requestID, expected["request_id"].string, name)
                XCTAssertEqual(failure.parameter, expected["param"].string, name)
            case "chatgpt_catalog":
                guard expected["outcome"].string == "ok" else {
                    XCTAssertThrowsError(try ChatGPTWire.catalog(request["value"]), name); continue
                }
                let models = try ChatGPTWire.catalog(request["value"])
                XCTAssertEqual(models.map(\.id), expected["models"].array?.compactMap { $0["id"].string }, name)
                XCTAssertEqual(models.map(\.label), expected["models"].array?.compactMap { $0["label"].string }, name)
            case "chatgpt_failure":
                let diagnostic = ChatGPTPlanDiagnostic(code: try request.requiredString("code"), temporary: request["temporary"].bool)
                XCTAssertEqual(diagnostic.pipelineFailure, expected["failure"].string, name)
                XCTAssertEqual(diagnostic.action, expected["action"].string, name)
            default: XCTFail(name + ": unknown action")
            }
        }
        XCTAssertEqual(counts, ["chatgpt_request": 8, "chatgpt_vision_request": 8, "chatgpt_stream": 57, "chatgpt_error": 9, "chatgpt_catalog": 5,
                                "chatgpt_failure": 75])
        print("Shared ChatGPT rows checked: \(counts.values.reduce(0, +)) (requests=8, vision=8, streams=57, errors=9, catalogs=5, failures=75) through core and the Swift receivers; HTTP=0")
    }
}
