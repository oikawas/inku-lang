import Foundation
import InkuCore

struct PreparedProviderRequest: Sendable {
    let request: URLRequest
    let format: String
    let outputBudget: ExactJSON
    let countTokens: URLRequest?
}

/// The core owns wire rules; the host attaches credentials and sends its unchanged bytes.
public enum ProviderWire {
    public static let responseName = "submit_pipeline_response"

    public static func evaluate(_ input: Data) throws -> ExactJSON {
        let value = try ExactJSON(data: InkuCore.providerWire(input))
        guard value["schema"].string == "inku.provider-wire.v1" else { throw HostError("pipeline_schema_violation") }
        return value
    }

    static func connection(_ provider: ProviderSettings) -> ExactJSON {
        .object(["id": .string(provider.id), "kind": .string(provider.kind.rawValue),
            "api_profile": .string(provider.apiProfile ?? ""), "base_url": .string(provider.baseURL.absoluteString)])
    }

    static func prepare(action: Data, provider: ProviderSettings, model: String, maxTokens: Int, key: String?) throws -> PreparedProviderRequest {
        try provider.validate()
        guard provider.kind != .chatGPTPlan else { throw HostError("chatgpt_session_pin_required") }
        guard !model.isEmpty, maxTokens > 0 else { throw HostError("provider_selection_required") }
        let payload = try ExactJSON.rawMember("payload", in: action)
        let prompt = try ExactJSON.rawMember("prompt", in: payload)
        let envelope: ExactJSON = .object(["action": .string("pipeline_request"), "connection": connection(provider),
            "model": .string(model), "max_tokens": .integer(maxTokens)])
        // Passing the original prompt preserves variant member order as well as propertyOrdering.
        let input = Data((String(envelope.text.dropLast()) + ",\"prompt\":" + String(decoding: prompt, as: UTF8.self) + "}").utf8)
        return try prepared(evaluate(input), provider: provider, key: key)
    }

    static func prepareText(prompt: AuxiliaryPrompt, provider: ProviderSettings, model: String, key: String?) throws -> PreparedProviderRequest {
        try provider.validate()
        guard provider.kind != .chatGPTPlan else { throw HostError("chatgpt_operation_not_supported") }
        guard !model.isEmpty, prompt.maximumTokens > 0, prompt.temperature.isFinite,
              prompt.timeoutSeconds > 0, prompt.timeoutSeconds.isFinite else { throw HostError("invalid_auxiliary_request") }
        let input: ExactJSON = .object(["action": .string("text_request"), "connection": connection(provider),
            "model": .string(model), "system": .string(prompt.system), "text": .string(prompt.message),
            "images": .array(prompt.images.map(ExactJSON.string)),
            "temperature": try ExactJSON(data: JSONEncoder().encode(prompt.temperature)),
            "max_tokens": .integer(prompt.maximumTokens)])
        return try prepared(evaluate(input.data), provider: provider, key: key)
    }

    private static func prepared(_ result: ExactJSON, provider: ProviderSettings, key: String?) throws -> PreparedProviderRequest {
        guard result["outcome"].string == "ok" else { throw HostError(result["reason"].string ?? "provider_rejected") }
        if provider.requiresAPIKey && (key ?? "").isEmpty { throw HostError("credentials_unavailable") }
        var headers = try JSONDecoder().decode([String: String].self, from: result["headers"].data)
        let auth = try result.requiredObject("auth")
        headers[try auth.requiredString("header")] = try auth.requiredString("prefix") +
            ((key ?? "").isEmpty ? auth.requiredString("missing") : key!)
        func request(_ value: ExactJSON) throws -> URLRequest {
            guard let url = URL(string: try value.requiredString("url")) else { throw HostError("provider_base_url_invalid") }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"; request.allHTTPHeaderFields = headers
            request.httpBody = Data(try value.requiredString("body").utf8)
            return request
        }
        return PreparedProviderRequest(request: try request(result), format: try result.requiredString("format"),
            outputBudget: result["output_budget"], countTokens: result["count_tokens"] == .null ? nil : try request(result["count_tokens"]))
    }

    public static func request(action: Data, provider: ProviderSettings, model: String, maxTokens: Int, key: String?) throws -> URLRequest {
        try prepare(action: action, provider: provider, model: model, maxTokens: maxTokens, key: key).request
    }

    static func readResponse(_ data: Data, format: String, status: Int = 200, text: Bool = false) throws -> ExactJSON {
        try evaluate(ExactJSON.object(["action": .string(text ? "text_response" : "pipeline_response"),
            "format": .string(format), "status": .integer(status), "body": .string(String(decoding: data, as: UTF8.self))]).data)
    }

    static func answer(_ result: ExactJSON) throws -> String {
        guard result["outcome"].string == "answer" else {
            throw HostError(result["outcome"].string == "http_error" ? result["failure"].string ?? "provider_rejected" : "malformed_payload")
        }
        return try result.requiredString("text")
    }

    public static func responseText(_ data: Data, format: String) throws -> String {
        try answer(readResponse(data, format: format))
    }

    public static func responseText(_ data: Data, kind: ProviderKind) throws -> String {
        try responseText(data, format: format(kind))
    }

    static func format(_ kind: ProviderKind) throws -> String {
        switch kind {
        case .openAICompatible: "openai_chat"
        case .anthropic: "anthropic"
        case .gemini: "gemini"
        case .chatGPTPlan: throw HostError("chatgpt_operation_not_supported")
        }
    }
}
