import Foundation

/// This adapter changes HTTP shape only. The core owns prompt, schema and response validation.
public enum ProviderWire {
    public static let responseName = "submit_pipeline_response"

    public static func request(action: Data, provider: ProviderSettings, model: String, maxTokens: Int, key: String?) throws -> URLRequest {
        try provider.validate()
        guard !model.isEmpty, maxTokens > 0 else { throw HostError("provider_selection_required") }
        if provider.requiresAPIKey && (key ?? "").isEmpty { throw HostError("credentials_unavailable") }
        let effect = try ExactJSON(data: action)
        let prompt = try effect.requiredObject("payload").requiredObject("prompt")
        let system = try prompt.requiredString("system")
        let message = try prompt.requiredString("message")
        let schema = try prompt.requiredObject("response_schema")
        let actionName = try prompt.requiredString("action_name")
        let base = provider.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let function: ExactJSON = .object(["name": .string(responseName), "description": .string("Submit the requested pipeline response."), "parameters": schema])
        var body: ExactJSON
        var endpoint: String
        var headers = ["Content-Type": "application/json"]
        switch provider.kind {
        case .chatGPTPlan: throw HostError("chatgpt_session_pin_required")
        case .openAICompatible:
            endpoint = base + "/chat/completions"
            headers["Authorization"] = "Bearer " + ((key ?? "").isEmpty ? "none" : key!)
            body = .object(["model": .string(model), "stream": .bool(false),
                            "messages": .array([.object(["role": .string("system"), "content": .string(system)]),
                                                 .object(["role": .string("user"), "content": .string(message)])])])
            let temperature = ["generate_normalized_ddl", "read_composition"].contains(actionName) ? "0.3" : "0.0"
            if provider.baseURL.host?.lowercased() == "api.openai.com" {
                body["max_completion_tokens"] = .integer(maxTokens)
                if !(model.hasPrefix("gpt-5") || model.range(of: "^o[0-9]", options: .regularExpression) != nil) { body["temperature"] = .number(temperature) }
                if model.range(of: "^gpt-5\\.[0-9]", options: .regularExpression) != nil { body["reasoning_effort"] = .string("none") }
            } else {
                body["max_tokens"] = .integer(maxTokens); body["temperature"] = .number(temperature)
                if provider.apiProfile == "mlx" {
                    body["enable_thinking"] = .bool(false)
                    let name = model.split(separator: "/").last.map(String.init) ?? model
                    if name.range(of: "^gemma[-_]?4(?:[-_]|$)", options: [.regularExpression, .caseInsensitive]) != nil {
                        body["temperature"] = .number("1.0"); body["top_p"] = .number("0.95"); body["top_k"] = .integer(64)
                    }
                }
            }
            if provider.id == "ollama" || provider.apiProfile == "mlx" {
                body["response_format"] = .object(["type": .string("json_schema"), "json_schema": .object(["name": .string(responseName), "schema": schema, "strict": .bool(true)])])
            } else {
                body["tools"] = .array([.object(["type": .string("function"), "function": function])])
                body["tool_choice"] = .object(["type": .string("function"), "function": .object(["name": .string(responseName)])])
            }
            if ["ollama", "ollama-cloud"].contains(provider.id) { body["reasoning_effort"] = .string("none") }
        case .anthropic:
            endpoint = base + "/v1/messages"
            headers["x-api-key"] = key ?? ""; headers["anthropic-version"] = "2023-06-01"
            body = .object(["model": .string(model), "max_tokens": .integer(maxTokens), "system": .string(system),
                            "messages": .array([.object(["role": .string("user"), "content": .string(message)])]),
                            "tools": .array([.object(["name": .string(responseName), "description": function["description"], "input_schema": schema])]),
                            "tool_choice": .object(["type": .string("auto")])])
        case .gemini:
            let encoded = model.addingPercentEncoding(withAllowedCharacters: CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"))!
            endpoint = base + "/v1beta/models/" + encoded + ":generateContent"
            headers["x-goog-api-key"] = key ?? ""
            body = .object(["systemInstruction": .object(["parts": .array([.object(["text": .string(system)])])]),
                            "contents": .array([.object(["role": .string("user"), "parts": .array([.object(["text": .string(message)])])])]),
                            "generationConfig": .object(["maxOutputTokens": .integer(maxTokens), "thinkingConfig": .object(["thinkingLevel": .string("minimal")])]),
                            "tools": .array([.object(["functionDeclarations": .array([.object(["name": .string(responseName), "description": function["description"], "parametersJsonSchema": try geminiSchema(schema, compactHoleEdits: actionName == "complete_visible_ddl_holes")])])])]),
                            "toolConfig": .object(["functionCallingConfig": .object(["mode": .string("ANY"), "allowedFunctionNames": .array([.string(responseName)])])])])
        }
        guard let url = URL(string: endpoint) else { throw HostError("provider_base_url_invalid") }
        var request = URLRequest(url: url)
        // Gemini reads property order from the wire; the other dialects receive the core's sorted schema as Server sends it.
        request.httpMethod = "POST"; request.httpBody = provider.kind == .gemini ? Data(body.orderedText.utf8) : body.data
        request.allHTTPHeaderFields = headers
        return request
    }

    public static func responseText(_ data: Data, kind: ProviderKind) throws -> String {
        let value = try ExactJSON(data: data)
        var text: String?
        switch kind {
        case .chatGPTPlan: throw HostError("chatgpt_operation_not_supported")
        case .openAICompatible:
            guard let message = value["choices"].array?.first?["message"] else { throw HostError("malformed_payload") }
            let calls = message["tool_calls"].array ?? []
            if calls.isEmpty { text = message["content"].string }
            else {
                guard calls.count == 1, calls[0]["function"]["name"].string == responseName else { throw HostError("malformed_payload") }
                text = calls[0]["function"]["arguments"].string
            }
        case .anthropic:
            guard let content = value["content"].array else { throw HostError("malformed_payload") }
            let calls = content.filter { $0["type"].string == "tool_use" }
            if !calls.isEmpty {
                guard calls.count == 1, calls[0]["name"].string == responseName, calls[0]["input"].object != nil else { throw HostError("malformed_payload") }
                text = calls[0]["input"].text
            } else {
                let answer = content.filter { $0["type"].string == "text" }.compactMap { $0["text"].string }.joined(separator: "\n")
                guard let first = answer.firstIndex(of: "{"), let last = answer.lastIndex(of: "}"), first < last else { throw HostError("malformed_payload") }
                let parsed = try ExactJSON(data: Data(answer[first...last].utf8))
                guard parsed.object != nil else { throw HostError("malformed_payload") }
                text = parsed.text
            }
        case .gemini:
            guard let parts = value["candidates"].array?.first?["content"]["parts"].array else { throw HostError("malformed_payload") }
            let calls = parts.map { $0["functionCall"] }.filter { $0.object != nil }
            guard calls.count == 1, calls[0]["name"].string == responseName, calls[0]["args"].object != nil else { throw HostError("malformed_payload") }
            text = calls[0]["args"].text
        }
        guard let text, !text.isEmpty else { throw HostError("malformed_payload") }
        return text
    }

    public static func geminiSchema(_ schema: ExactJSON, compactHoleEdits: Bool = false) throws -> ExactJSON {
        let keys: Set<String> = ["$anchor", "$defs", "$id", "$ref", "additionalProperties", "anyOf", "description", "enum", "format", "items", "maxItems", "maximum", "minItems", "minimum", "oneOf", "prefixItems", "properties", "propertyOrdering", "required", "title", "type"]
        func project(_ value: ExactJSON, named: Bool = false) -> ExactJSON {
            if let values = value.array { return .array(values.map { project($0) }) }
            guard let fields = value.object else { return value }
            var output: [String: ExactJSON] = [:]
            for (key, item) in fields {
                if named { output[key] = project(item) }
                else if key == "const" { output["enum"] = .array([item]) }
                else if keys.contains(key) { output[key] = project(item, named: key == "$defs" || key == "properties") }
            }
            return .object(output)
        }
        func merge(_ values: [ExactJSON]) -> ExactJSON? {
            guard let first = values.first else { return nil }
            if values.allSatisfy({ $0 == first }) { return first }
            guard let fields = first.object, values.allSatisfy({ $0.object.map { Set($0.keys) } == Set(fields.keys) }) else { return nil }
            if Set(fields.keys) == ["enum"], values.allSatisfy({ $0["enum"].array?.count == 1 }) { return .object(["enum": .array(values.map { $0["enum"].array![0] })]) }
            var merged: [String: ExactJSON] = [:]
            for key in fields.keys { guard let item = merge(values.map { $0[key] }) else { return nil }; merged[key] = item }
            return .object(merged)
        }
        var result = project(schema)
        guard result["type"].string == "object" else { throw HostError("malformed_payload") }
        if compactHoleEdits {
            var properties = result["properties"]
            let name = properties["results"].object != nil ? "results" : "edits"
            var collection = properties[name]
            if let variants = collection["items"]["oneOf"].array, !variants.isEmpty {
                if let merged = merge(variants), merged["type"].string == "object" { collection["items"] = merged }
                else if variants.allSatisfy({ $0["properties"].object != nil }) {
                    var required = Set(variants[0]["required"].array?.compactMap(\.string) ?? [])
                    for variant in variants.dropFirst() { required.formIntersection(variant["required"].array?.compactMap(\.string) ?? []) }
                    let allNames = Set(variants.flatMap { Array($0["properties"].object!.keys) })
                    var mergedProperties: [String: ExactJSON] = [:]
                    for key in allNames {
                        let candidates = variants.compactMap { $0["properties"].object?[key] }
                        guard let value = merge(candidates) else { return result }
                        mergedProperties[key] = value
                    }
                    collection["items"] = .object(["type": .string("object"), "additionalProperties": .bool(false), "required": .array(required.sorted().map(ExactJSON.string)), "properties": .object(mergedProperties)])
                }
                properties[name] = collection; result["properties"] = properties
            }
        }
        return result
    }
}
