import Foundation
import OSLog

/// The plan's wire rules live in the shared core (provider_wire): the request bodies, the reading of the whole
/// SSE stream and what an HTTP failure says. The host receives the stream whole, holding it to `wireLimit`; the
/// token, cancellation, the quota pause and the observation record stay with the runtime.
enum ChatGPTWire {
    /// The core's sign-in names (`sign_in_<name>` for the `chatgpt` service).
    private static func evaluate(_ name: String, _ fields: [String: ExactJSON]) throws -> ExactJSON {
        var input = fields
        input["action"] = .string("sign_in_" + name); input["service"] = .string("chatgpt")
        return try ProviderWire.evaluate(ExactJSON.object(input).data)
    }

    struct Request: Sendable {
        let body: Data
        let wireLimit: Int
        let endpoint: Endpoint
    }

    /// Where a request goes and how it is sent, as the core answers it (step 4): the URL, method, headers, the
    /// token's header and prefix, and the limits. The URL is still checked before anything is sent.
    struct Endpoint: Sendable {
        let url: URL
        let method: String
        let headers: [String: String]
        let authHeader: String
        let authPrefix: String
        let errorLimit: Int
        let answerLimit: Int?

        init(_ result: ExactJSON) throws {
            guard let text = result["url"].string, let url = URL(string: text), let method = result["method"].string,
                  let headers = result["headers"].object, let header = result["auth"]["header"].string,
                  let prefix = result["auth"]["prefix"].string, let errorLimit = ChatGPTWire.int(result["error_limit"])
            else { throw HostError("chatgpt_endpoint_invalid") }
            try ChatGPTEndpoints.validate(url)
            self.url = url; self.method = method; authHeader = header; authPrefix = prefix; self.errorLimit = errorLimit
            self.headers = try headers.mapValues { value in
                guard let text = value.string else { throw HostError("chatgpt_endpoint_invalid") }
                return text
            }
            answerLimit = ChatGPTWire.int(result["answer_limit"])
        }

        func request(token: String, body: Data?, deadline: Date) -> URLRequest {
            var request = URLRequest(url: url); request.httpMethod = method; request.httpBody = body
            request.timeoutInterval = max(0.001, deadline.timeIntervalSinceNow)
            for (name, value) in headers { request.setValue(value, forHTTPHeaderField: name) }
            request.setValue(authPrefix + token, forHTTPHeaderField: authHeader)
            return request
        }
    }

    enum Transport: String { case timeout, unavailable, tooLarge = "too_large" }

    /// A time limit, a failed or cut connection, or an answer past its limit, classified by the core
    /// (`sign_in_transport`) with its code, pipeline failure and next action.
    static func transport(_ kind: Transport) -> ChatGPTPlanFailure {
        let fallback: String = switch kind {
        case .timeout: "chatgpt_transport_timeout"
        case .unavailable: "chatgpt_transport_unavailable"
        case .tooLarge: "chatgpt_response_too_large"
        }
        guard let result = try? evaluate("transport", ["kind": .string(kind.rawValue)]),
              result["outcome"].string == "ok" else { return ChatGPTPlanFailure(diagnostic: ChatGPTPlanDiagnostic(code: fallback)) }
        return failure(result)
    }

    struct Stream: Sendable {
        let result: Result<String, ChatGPTPlanFailure>
        /// The last `response` the stream carried, for the observation record.
        let terminal: ExactJSON?
    }

    private static let log = Logger(subsystem: "app.inku", category: "chatgpt")

    /// `prompt` is the effect's original JSON, so the schema keeps its member order.
    static func request(model: String, prompt: Data, answerLimit: Int, images: [String] = []) throws -> Request {
        let envelope: ExactJSON = .object(["action": .string("sign_in_request"), "service": .string("chatgpt"), "model": .string(model),
            "answer_limit": .integer(answerLimit)])
        let imageMember = images.isEmpty ? "" : ",\"images\":" + ExactJSON.array(images.map(ExactJSON.string)).text
        let input = Data((String(envelope.text.dropLast()) + ",\"prompt\":" + String(decoding: prompt, as: UTF8.self) + imageMember + "}").utf8)
        return try prepared(ProviderWire.evaluate(input))
    }

    static func visionRequest(model: String, system: String, text: String, images: [String], answerLimit: Int) throws -> Request {
        try prepared(evaluate("vision_request", ["model": .string(model),
            "system": .string(system), "text": .string(text), "images": .array(images.map(ExactJSON.string)),
            "answer_limit": .integer(answerLimit)]))
    }

    static func read(text: Bool, answerLimit: Int, wire: Data) throws -> Stream {
        let result = try evaluate("stream", ["mode": .string(text ? "text" : "pipeline"),
            "answer_limit": .integer(answerLimit), "wire_base64": .string(wire.base64EncodedString())])
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
            // The core says which: bytes that are not UTF-8 are rejected, a stream it cannot read is asked again for.
            return Stream(result: .failure(failure(result)), terminal: terminal)
        default:
            throw HostError("chatgpt_response_invalid")
        }
    }

    /// An HTTP failure from the backend. The core reads the body's text; one that is not JSON says only what the
    /// status says.
    static func httpFailure(_ response: ChatGPTHTTPResponse) throws -> ChatGPTPlanFailure {
        try httpFailure(body: response.data, status: response.status, requestID: response.requestID)
    }

    static func httpFailure(body: Data, status: Int?, requestID: String?) throws -> ChatGPTPlanFailure {
        try httpFailure(["body": .string(String(decoding: body, as: UTF8.self))], status: status, requestID: requestID)
    }

    private static func httpFailure(_ answer: [String: ExactJSON], status: Int?, requestID: String?) throws -> ChatGPTPlanFailure {
        var input = answer
        input["status"] = status.map { .integer($0) } ?? .null
        input["request_id"] = requestID.map(ExactJSON.string) ?? .null
        let result = try evaluate("error", input)
        guard result["outcome"].string == "failed" else { throw HostError("chatgpt_response_invalid") }
        return failure(result)
    }

    fileprivate static func int(_ value: ExactJSON) -> Int? { value.number.flatMap { Int($0) } }

    private static func prepared(_ result: ExactJSON) throws -> Request {
        // A refused request (an image that is not a data URL, a prompt without a schema) is never sent.
        guard result["outcome"].string == "ok", let limit = int(result["wire_limit"]) else { throw HostError("pipeline_schema_violation") }
        return Request(body: Data(try result.requiredString("body").utf8), wireLimit: limit, endpoint: try Endpoint(result))
    }

    /// The next action and whether the pipeline may retry, from the core's one failure table. A table the core
    /// cannot answer leaves the failure rejected, for the user to diagnose.
    static func classify(code: String, temporary: Bool?) -> (failure: String, action: String) {
        var input: [String: ExactJSON] = ["code": .string(code)]
        if let temporary { input["temporary"] = .bool(temporary) }
        guard let result = try? evaluate("failure", input), result["outcome"].string == "ok",
              let failure = result["failure"].string, let action = result["action"].string else { return ("provider_rejected", "diagnose") }
        return (failure, action)
    }

    /// A failure the core classified while reading: its failure and next action come from the same table.
    private static func failure(_ result: ExactJSON) -> ChatGPTPlanFailure {
        let code = result["code"].string ?? "chatgpt_response_failed"
        let classified = result["failure"].string.flatMap { failure in result["action"].string.map { (failure, $0) } }
            ?? classify(code: code, temporary: nil)
        return ChatGPTPlanFailure(diagnostic: ChatGPTPlanDiagnostic(code: code, status: int(result["status"]),
            requestID: result["request_id"].string, parameter: result["param"].string, failure: classified.0, action: classified.1))
    }
}
