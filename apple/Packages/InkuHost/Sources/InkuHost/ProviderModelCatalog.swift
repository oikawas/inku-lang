import Foundation

/// One row of a provider's live model list.
public struct FetchedProviderModel: Sendable, Equatable {
    public let id: String
    public let label: String
    public let contextLimit: Int?
    public let capabilities: [String]
    public init(id: String, label: String, contextLimit: Int? = nil, capabilities: [String] = []) {
        self.id = id; self.label = label; self.contextLimit = contextLimit; self.capabilities = capabilities
    }
}

/// Server api_core/routers/settings.py: reading a provider's model list and folding it into the saved catalog.
public enum ProviderModelCatalog {
    public typealias Send = @Sendable (URLRequest) async throws -> (status: Int, data: Data)
    /// The largest page each API allows, so one request is the usual case.
    public static let pageSize = 1000
    /// Stops a provider that never says it is done; a list cut short there would retire real models.
    public static let pageLimit = 20
    public static let timeout: TimeInterval = 20

    /// Every page of the list (Anthropic `limit`/`after_id`, Gemini `pageSize`/`pageToken`, one page otherwise).
    /// Server sends the key header only when a key exists, and refuses an empty list.
    public static func fetch(provider: ProviderSettings, firstURL: URL, key: String?, send: Send) async throws -> [FetchedProviderModel] {
        var headers = ["Accept": "application/json"]
        if let key, !key.isEmpty {
            switch provider.kind {
            case .anthropic: headers["x-api-key"] = key
            case .gemini: headers["x-goog-api-key"] = key
            case .openAICompatible: headers["Authorization"] = "Bearer " + key
            case .chatGPTPlan: throw HostError("personal_plan_model_catalog_requires_runtime")
            }
        }
        if provider.kind == .anthropic { headers["anthropic-version"] = "2023-06-01" }
        let itemsKey: String, firstQuery: [String: String]
        switch provider.kind {
        case .anthropic: itemsKey = "data"; firstQuery = ["limit": String(pageSize)]
        case .gemini: itemsKey = "models"; firstQuery = ["pageSize": String(pageSize)]
        default: itemsKey = ""; firstQuery = [:]
        }
        var rows: [ExactJSON] = []
        if itemsKey.isEmpty {
            let page = try await get(firstURL, query: [:], headers: headers, send: send)
            guard let items = (page["data"] == .null ? page["models"] : page["data"]).array else { throw HostError("model_catalog_invalid") }
            rows = items
        } else {
            var query = firstQuery, finished = false
            for _ in 0..<pageLimit {
                let page = try await get(firstURL, query: query, headers: headers, send: send)
                guard let items = page[itemsKey].array else { throw HostError("model_catalog_invalid") }
                rows += items
                let next: [String: String]?
                if provider.kind == .anthropic {
                    next = page["has_more"].bool == true ? page["last_id"].string.flatMap { $0.isEmpty ? nil : ["after_id": $0] } : nil
                } else {
                    next = page["nextPageToken"].string.flatMap { $0.isEmpty ? nil : ["pageToken": $0] }
                }
                guard let next else { finished = true; break }
                query = firstQuery.merging(next) { $1 }
            }
            guard finished else { throw HostError("model_catalog_unfinished") }
        }
        let models = rows.compactMap { row -> FetchedProviderModel? in
            guard row.object != nil else { return nil }
            var id = (row["id"].string.flatMap { $0.isEmpty ? nil : $0 } ?? row["name"].string ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if id.hasPrefix("models/") { id = String(id.dropFirst(7)) }
            guard !id.isEmpty else { return nil }
            let named = row["display_name"].string.flatMap { $0.isEmpty ? nil : $0 } ?? row["displayName"].string ?? id
            let label = named.trimmingCharacters(in: .whitespacesAndNewlines)
            return FetchedProviderModel(id: id, label: label.isEmpty ? id : label,
                                        contextLimit: row["inputTokenLimit"].number.flatMap(Int.init),
                                        capabilities: row["supportedGenerationMethods"].array?.compactMap(\.string) ?? [])
        }
        guard !models.isEmpty else { throw HostError("model_catalog_empty") }
        return models
    }

    private static func get(_ url: URL, query: [String: String], headers: [String: String], send: Send) async throws -> ExactJSON {
        guard var parts = URLComponents(url: url, resolvingAgainstBaseURL: false) else { throw HostError("provider_base_url_invalid") }
        var items = (parts.queryItems ?? []).filter { query[$0.name] == nil }
        items += query.keys.sorted().map { URLQueryItem(name: $0, value: query[$0]) }
        parts.queryItems = items.isEmpty ? nil : items
        guard let pageURL = parts.url else { throw HostError("provider_base_url_invalid") }
        var request = URLRequest(url: pageURL)
        request.timeoutInterval = timeout
        request.allHTTPHeaderFields = headers
        let (status, data) = try await send(request)
        guard (200...299).contains(status) else { throw HostError("model_catalog_http_failure") }
        return try ExactJSON(data: data)
    }

    /// Server api_settings_fetch_provider_models: the live list replaces the saved one. A known model keeps its
    /// metadata, its EOL/subscription marks and a hand-made label the provider does not replace; a re-offered model
    /// loses its EOL mark. A model that disappeared stays at the end as EOL. A new model is saved switched off; a
    /// known model keeps its switch unless it is EOL or needs a subscription.
    public static func merge(fetched: [FetchedProviderModel], previous: [ProviderModelSettings], previousEnabled: [String: Bool]?,
                             access: [String: ProviderModelAccess] = [:], today: String) -> (models: [ProviderModelSettings], enabled: [String: Bool]) {
        var seen = Set<String>()
        let byID = Dictionary(previous.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        var models: [ProviderModelSettings] = fetched.compactMap { row in
            guard seen.insert(row.id).inserted else { return nil }
            guard var model = byID[row.id] else {
                return ProviderModelSettings(id: row.id, label: row.label, purposes: row.id.lowercased().contains("vision") ? ["vision"] : ["llm"])
            }
            if !(row.label == row.id && !model.label.isEmpty && model.label != model.id) { model.label = row.label }
            model.eol = nil; model.eolDate = nil
            return model
        }
        for index in models.indices {
            switch access[models[index].id] {
            case .retired(let date): models[index].eol = true; models[index].eolDate = date
            case .subscription(true): models[index].requiresSubscription = true
            case .subscription(false): models[index].requiresSubscription = nil
            case nil: break
            }
        }
        let retired = previous.filter { !seen.contains($0.id) }.reduce(into: [ProviderModelSettings]()) { list, model in
            guard !list.contains(where: { $0.id == model.id }) else { return }
            var kept = model; kept.eol = true; kept.eolDate = kept.eolDate ?? today
            list.append(kept)
        }.sorted { $0.id < $1.id }
        models += retired
        let enabled = Dictionary(models.map { model in
            (model.id, model.isSelectable && byID[model.id] != nil && previousEnabled?[model.id] != false)
        }, uniquingKeysWith: { first, _ in first })
        return (models, enabled)
    }

    /// Ollama Cloud lists models to anyone, so each model is asked once per fetch with the smallest call:
    /// /api/show answers 410 for a retired model, and a one-token chat 403 for one the plan does not reach.
    public static let accessProbeProviderIDs: Set<String> = ["ollama-cloud"]

    public static func probeAccess(provider: ProviderSettings, key: String?, modelIDs: [String], today: String,
                                   send: @escaping @Sendable (URLRequest) async -> (status: Int?, text: String)) async -> [String: ProviderModelAccess] {
        guard accessProbeProviderIDs.contains(provider.id) else { return [:] }
        let base = provider.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let origin = base.hasSuffix("/v1") ? String(base.dropLast(3)) : base
        @Sendable func post(_ url: String, _ body: ExactJSON, bearer: String? = nil) -> URLRequest? {
            guard let url = URL(string: url) else { return nil }
            var request = URLRequest(url: url); request.httpMethod = "POST"; request.timeoutInterval = timeout
            request.httpBody = body.data
            request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.setValue("application/json", forHTTPHeaderField: "Accept")
            if let bearer { request.setValue("Bearer " + bearer, forHTTPHeaderField: "Authorization") }
            return request
        }
        @Sendable func probe(_ id: String) async -> ProviderModelAccess? {
            if let show = post(origin + "/api/show", .object(["model": .string(id)])) {
                let (status, text) = await send(show)
                if status == 410 {
                    let date = text.range(of: "retired at \\d{4}-\\d{2}-\\d{2}", options: .regularExpression).map { String(text[$0].suffix(10)) }
                    return .retired(date ?? today)
                }
            }
            guard let key, !key.isEmpty, let chat = post(base + "/chat/completions", .object(["model": .string(id),
                "messages": .array([.object(["role": .string("user"), "content": .string(".")])]), "max_tokens": .integer(1)]), bearer: key) else { return nil }
            switch await send(chat).status {
            case 403: return .subscription(true)
            case 200: return .subscription(false)
            default: return nil
            }
        }
        // Two at a time: the service refuses by concurrency, and two is its limit.
        var answers: [String: ProviderModelAccess] = [:]
        var pending = modelIDs[...]
        await withTaskGroup(of: (String, ProviderModelAccess?).self) { group in
            for _ in 0..<2 { if let id = pending.popFirst() { group.addTask { (id, await probe(id)) } } }
            while let (id, answer) = await group.next() {
                if let answer { answers[id] = answer }
                if let next = pending.popFirst() { group.addTask { (next, await probe(next)) } }
            }
        }
        return answers
    }

    public static func utcDay(_ date: Date = Date()) -> String {
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year!, parts.month!, parts.day!)
    }
}

public enum ProviderModelAccess: Sendable, Equatable {
    case retired(String)
    case subscription(Bool)
}
