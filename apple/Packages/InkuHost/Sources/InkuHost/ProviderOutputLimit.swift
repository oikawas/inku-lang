import Foundation
import OSLog

/// Server anthropic_request, gemini_request and openai_request: the room a request leaves for thinking the model
/// does unasked, and what an answer cut off at its output limit spent its budget on.
enum ProviderOutputLimit {
    private static let logger = Logger(subsystem: "app.inku", category: "provider")

    /// Claude 5 models and Mythos Preview think adaptively when a request sends no `thinking` field, and their
    /// thinking counts toward max_tokens; Claude 4.x does not think unasked.
    static let thinkingRoomTokens = 8192
    static func anthropicMaxTokens(_ model: String, answerTokens: Int) -> Int {
        let thinks = model.range(of: "^claude-(?:(?:opus|sonnet|haiku|fable|mythos)-5(?:-|$)|mythos-preview(?:-|$))",
                                 options: .regularExpression) != nil
        return answerTokens + (thinks ? thinkingRoomTokens : 0)
    }

    /// The fields Server logs for a response stopped at its output limit; nil when it was not cut off.
    static func record(_ value: ExactJSON, kind: ProviderKind, responses: Bool) -> ExactJSON? {
        func number(_ item: ExactJSON) -> ExactJSON { item.number == nil ? .null : item }
        switch kind {
        case .anthropic:
            guard value["stop_reason"].string == "max_tokens" else { return nil }
            let blocks = (value["content"].array ?? []).filter { $0.object != nil }
            return .object([
                "stop_reason": .string("max_tokens"), "output_tokens": number(value["usage"]["output_tokens"]),
                "thinking_blocks": .integer(blocks.filter { ["thinking", "redacted_thinking"].contains($0["type"].string ?? "") }.count),
                "has_text": .bool(blocks.contains { $0["type"].string == "text" && !($0["text"].string ?? "").isEmpty }),
                "has_tool_use": .bool(blocks.contains { $0["type"].string == "tool_use" }),
            ])
        case .gemini:
            let first = value["candidates"].array?.first ?? .null
            guard first["finishReason"].string == "MAX_TOKENS" else { return nil }
            let parts = (first["content"]["parts"].array ?? []).filter { $0.object != nil }
            return .object([
                "finish_reason": .string("MAX_TOKENS"), "output_tokens": number(value["usageMetadata"]["candidatesTokenCount"]),
                "thought_tokens": number(value["usageMetadata"]["thoughtsTokenCount"]),
                "has_text": .bool(parts.contains { !($0["text"].string ?? "").isEmpty && $0["thought"].bool != true }),
                "has_function_call": .bool(parts.contains { $0["functionCall"] != .null }),
            ])
        case .openAICompatible where responses:
            guard value["status"].string == "incomplete", value["incomplete_details"]["reason"].string == "max_output_tokens" else { return nil }
            let output = (value["output"].array ?? []).filter { $0.object != nil }
            return .object([
                "incomplete_reason": .string("max_output_tokens"), "output_tokens": number(value["usage"]["output_tokens"]),
                "reasoning_tokens": number(value["usage"]["output_tokens_details"]["reasoning_tokens"]),
                "has_text": .bool(output.contains { $0["type"].string == "message" }),
                "has_function_call": .bool(output.contains { $0["type"].string == "function_call" }),
            ])
        case .openAICompatible:
            let first = value["choices"].array?.first ?? .null
            guard first["finish_reason"].string == "length" else { return nil }
            let message = first["message"]
            func present(_ item: ExactJSON) -> Bool {
                switch item { case .null: false; case .bool(let flag): flag; case .string(let text): !text.isEmpty
                case .array(let items): !items.isEmpty; case .object(let fields): !fields.isEmpty; case .number: true }
            }
            return .object([
                "finish_reason": .string("length"), "output_tokens": number(value["usage"]["completion_tokens"]),
                "reasoning_tokens": number(value["usage"]["completion_tokens_details"]["reasoning_tokens"]),
                "has_reasoning": .bool(present(message["reasoning"]) || present(message["reasoning_content"])),
                "has_text": .bool(present(message["content"])), "has_tool_call": .bool(present(message["tool_calls"])),
            ])
        case .chatGPTPlan:
            return nil
        }
    }

    /// Server's `provider_output_limit {...}` line: keys in name order, compact separators.
    static func line(action: String, provider: String, model: String, body: ExactJSON, kind: ProviderKind, cut: ExactJSON) -> String {
        let limit = kind == .gemini ? body["generationConfig"]["maxOutputTokens"]
            : [body["max_tokens"], body["max_completion_tokens"], body["max_output_tokens"]].first { $0 != .null } ?? .null
        var fields = cut.object ?? [:]
        fields.merge(["action": .string(action), "provider": .string(provider), "model": .string(model), "max_tokens": limit]) { _, value in value }
        return "provider_output_limit " + ExactJSON.object(fields).text
    }

    /// Writes the line when the response was cut off; returns whether it was.
    @discardableResult
    static func log(_ raw: Data, request: URLRequest, provider: ProviderSettings, model: String, action: String, responses: Bool) -> Bool {
        guard let value = try? ExactJSON(data: raw), let cut = record(value, kind: provider.kind, responses: responses) else { return false }
        let body = request.httpBody.flatMap { try? ExactJSON(data: $0) } ?? .null
        let text = line(action: action, provider: provider.id, model: model, body: body, kind: provider.kind, cut: cut)
        logger.warning("\(text, privacy: .public)")
        return true
    }
}
