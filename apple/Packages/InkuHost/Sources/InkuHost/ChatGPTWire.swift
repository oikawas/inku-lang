import Foundation
import OSLog

/// The plan's wire rules live in the shared core (provider_wire): the request bodies, the reading of the whole
/// SSE stream, what an HTTP failure says and the model list. The host receives the stream whole, holding it to
/// `wireLimit`; the token, cancellation, the quota pause and the observation record stay with the runtime.
enum ChatGPTWire {
    struct Request: Sendable {
        let body: Data
        let wireLimit: Int
    }

    struct Stream: Sendable {
        let result: Result<String, ChatGPTPlanFailure>
        /// The last `response` the stream carried, for the observation record.
        let terminal: ExactJSON?
    }

    private static let log = Logger(subsystem: "app.inku", category: "chatgpt")

    /// `prompt` is the effect's original JSON, so the schema keeps its member order.
    static func request(model: String, prompt: Data, answerLimit: Int) throws -> Request {
        let envelope: ExactJSON = .object(["action": .string("chatgpt_request"), "model": .string(model), "answer_limit": .integer(answerLimit)])
        let input = Data((String(envelope.text.dropLast()) + ",\"prompt\":" + String(decoding: prompt, as: UTF8.self) + "}").utf8)
        return try prepared(ProviderWire.evaluate(input))
    }

    static func visionRequest(model: String, system: String, text: String, images: [String], answerLimit: Int) throws -> Request {
        try prepared(ProviderWire.evaluate(ExactJSON.object(["action": .string("chatgpt_vision_request"), "model": .string(model),
            "system": .string(system), "text": .string(text), "images": .array(images.map(ExactJSON.string)),
            "answer_limit": .integer(answerLimit)]).data))
    }

    static func wireLimit(answerLimit: Int) throws -> Int {
        let result = try ProviderWire.evaluate(ExactJSON.object(["action": .string("chatgpt_limits"), "answer_limit": .integer(answerLimit)]).data)
        guard let limit = int(result["wire_limit"]) else { throw HostError("chatgpt_response_invalid") }
        return limit
    }

    static func read(text: Bool, answerLimit: Int, wire: Data) throws -> Stream {
        let result = try ProviderWire.evaluate(ExactJSON.object(["action": .string("chatgpt_stream"), "mode": .string(text ? "text" : "pipeline"),
            "answer_limit": .integer(answerLimit), "wire_base64": .string(wire.base64EncodedString())]).data)
        let terminal = result["terminal"] == .null ? nil : result["terminal"]
        switch result["outcome"].string {
        case "answer":
            return Stream(result: .success(try result.requiredString("text")), terminal: terminal)
        case "failed":
            if let shapes = result["tool_shapes"].array {
                // Tool metadata explains protocol failures without logging text or arguments.
                log.warning("chatgpt_tool_shape \(ExactJSON.array(shapes).text, privacy: .public) streamed_calls=\(int(result["streamed_calls"]) ?? 0) finalized_calls=\(int(result["finalized_calls"]) ?? 0)")
            }
            return Stream(result: .failure(failure(result)), terminal: terminal)
        case "malformed":
            return Stream(result: .failure(ChatGPTPlanFailure(diagnostic: .init(code: "chatgpt_response_invalid"))), terminal: terminal)
        default:
            throw HostError("chatgpt_response_invalid")
        }
    }

    /// An HTTP failure from the backend; a body that is not JSON says only what the status says.
    static func httpFailure(_ response: ChatGPTHTTPResponse) throws -> ChatGPTPlanFailure {
        try httpFailure(value: (try? ExactJSON(data: response.data)) ?? .null, status: response.status, requestID: response.requestID)
    }

    static func httpFailure(value: ExactJSON, status: Int?, requestID: String?) throws -> ChatGPTPlanFailure {
        let result = try ProviderWire.evaluate(ExactJSON.object(["action": .string("chatgpt_error"), "value": value,
            "status": status.map { .integer($0) } ?? .null, "request_id": requestID.map(ExactJSON.string) ?? .null]).data)
        guard result["outcome"].string == "failed" else { throw HostError("chatgpt_response_invalid") }
        return failure(result)
    }

    static func catalog(_ value: ExactJSON) throws -> [ChatGPTPlanModel] {
        let result = try ProviderWire.evaluate(ExactJSON.object(["action": .string("chatgpt_catalog"), "value": value]).data)
        guard result["outcome"].string == "ok", let models = result["models"].array else { throw HostError("chatgpt_response_invalid") }
        return try models.map { ChatGPTPlanModel(id: try $0.requiredString("id"), label: try $0.requiredString("label")) }
    }

    private static func int(_ value: ExactJSON) -> Int? { value.number.flatMap { Int($0) } }

    private static func prepared(_ result: ExactJSON) throws -> Request {
        // A refused request (an image that is not a data URL, a prompt without a schema) is never sent.
        guard result["outcome"].string == "ok", let limit = int(result["wire_limit"]) else { throw HostError("pipeline_schema_violation") }
        return Request(body: Data(try result.requiredString("body").utf8), wireLimit: limit)
    }

    /// The core decides whether a failure is temporary; the next action shown stays the runtime's own table.
    private static func failure(_ result: ExactJSON) -> ChatGPTPlanFailure {
        ChatGPTPlanFailure(diagnostic: .init(code: result["code"].string ?? "chatgpt_response_failed", status: int(result["status"]),
            requestID: result["request_id"].string, parameter: result["param"].string,
            temporary: result["failure"].string == "transport_unavailable"))
    }
}
