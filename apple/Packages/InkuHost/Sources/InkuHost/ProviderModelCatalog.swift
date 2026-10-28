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
        guard provider.kind != .chatGPTPlan else { throw HostError("personal_plan_model_catalog_requires_runtime") }
        let kind = provider.apiProfile == "mlx" ? "mlx" : provider.kind.rawValue
        let plan = try ProviderCoreSettings.call("model_list_start", ["kind": kind, "base_url": provider.baseURL.absoluteString, "api_key": ""])
        guard let urlText = plan["url"] as? String, let url = URL(string: urlText) else { throw HostError("provider_base_url_invalid") }
        var headers = plan["headers"] as? [String: String] ?? [:]
        if let key, !key.isEmpty {
            switch provider.kind {
            case .anthropic: headers["x-api-key"] = key
            case .gemini: headers["x-goog-api-key"] = key
            case .openAICompatible: headers["Authorization"] = "Bearer " + key
            case .chatGPTPlan: throw HostError("personal_plan_model_catalog_requires_runtime")
            }
        }
        let itemsKey = plan["items_key"] as? String ?? ""
        let firstQuery = plan["query"] as? [String: String] ?? [:]
        var rows: [ExactJSON] = []
        if itemsKey.isEmpty {
            let page = try await get(url, query: [:], headers: headers, send: send)
            guard let items = (page["data"] == .null ? page["models"] : page["data"]).array else { throw HostError("model_catalog_invalid") }
            rows = items
        } else {
            var query = firstQuery, finished = false
            for _ in 0..<pageLimit {
                let page = try await get(url, query: query, headers: headers, send: send)
                guard let items = page[itemsKey].array else { throw HostError("model_catalog_invalid") }
                rows += items
                let pageObject = try JSONSerialization.jsonObject(with: page.data)
                let next = try ProviderCoreSettings.call("model_list_next", ["kind": kind, "page": pageObject])["query"] as? [String: String]
                guard let next else { finished = true; break }
                query = firstQuery.merging(next) { $1 }
            }
            guard finished else { throw HostError("model_catalog_unfinished") }
        }
        let rawRows = try rows.map { try JSONSerialization.jsonObject(with: $0.data) }
        let normalized: [[String: Any]]
        do { normalized = try ProviderCoreSettings.call("model_rows", ["payload": ["data": rawRows]])["models"] as? [[String: Any]] ?? [] }
        catch let error as HostError where error.code == "model list response was empty" { throw HostError("model_catalog_empty") }
        let extra = rows.compactMap { row -> FetchedProviderModel? in
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
        let byID = Dictionary(extra.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let models = normalized.compactMap { row -> FetchedProviderModel? in
            guard let id = row["id"] as? String else { return nil }
            let old = byID[id]
            return FetchedProviderModel(id: id, label: row["label"] as? String ?? id,
                contextLimit: old?.contextLimit, capabilities: old?.capabilities ?? [])
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
                             access: [String: ProviderModelAccess] = [:], today: String, providerID: String = "") throws -> (models: [ProviderModelSettings], enabled: [String: Bool]) {
        let previousRow: [String: Any] = ["models": previous.map(\.coreCatalogRecord), "enabled_models": previousEnabled ?? [:]]
        let fetchedRows = fetched.map { ["id": $0.id, "label": $0.label] }
        let prepared = try ProviderCoreSettings.call("refresh_prepare", ["provider": providerID, "models": fetchedRows, "previous": previousRow])
        if let rows = prepared["models"] as? [[String: Any]] {
            let answers: [[String: Any]] = rows.filter { $0["eol"] as? Bool != true }.map { row in
                switch access[row["id"] as? String ?? ""] {
                case .retired(let date): return ["retired": date]
                case .subscription(let enabled): return ["subscription": enabled]
                case nil: return [:]
                }
            }
            let applied = try ProviderCoreSettings.call("access_apply", ["models": rows, "answers": answers])
            guard let checked = applied["models"] as? [[String: Any]] else { throw HostError("provider_core_invalid") }
            let result = try ProviderCoreSettings.call("refresh_finish", ["models": checked, "previous": previousRow, "today": today])
            guard let returned = result["models"] as? [[String: Any]], let enabled = result["enabled_models"] as? [String: Bool],
                  let normalized = try ProviderCoreSettings.call("normalize_models", ["models": returned])["models"] as? [[String: Any]] else { throw HostError("provider_core_invalid") }
            return (try normalized.map { try ProviderCoreSettings.model($0) }, enabled)
        }
        throw HostError("provider_core_invalid")
    }

    /// Ollama Cloud lists models to anyone, so each model is asked once per fetch with the smallest call:
    /// /api/show answers 410 for a retired model, and a one-token chat 403 for one the plan does not reach.
    public static func probeAccess(provider: ProviderSettings, key: String?, modelIDs: [String], today: String,
                                   send: @escaping @Sendable (URLRequest) async -> (status: Int?, text: String)) async -> [String: ProviderModelAccess] {
        guard (try? ProviderCoreSettings.call("access_enabled", ["provider": provider.id])["enabled"] as? Bool) == true else { return [:] }
        let targets = (try? ProviderCoreSettings.call("access_targets", ["models": modelIDs.map { ["id": $0] }])["models"] as? [[String: Any]]) ?? []
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
                let result = try? ProviderCoreSettings.call("access_probe", ["stage": "show", "status": status ?? 0, "text": text, "today": today])
                if let answer = result?["answer"] as? [String: Any], let date = answer["retired"] as? String { return .retired(date) }
            }
            guard let key, !key.isEmpty, let chat = post(base + "/chat/completions", .object(["model": .string(id),
                "messages": .array([.object(["role": .string("user"), "content": .string(".")])]), "max_tokens": .integer(1)]), bearer: key) else { return nil }
            let response = await send(chat)
            let result = try? ProviderCoreSettings.call("access_probe", ["stage": "call", "status": response.status ?? 0, "text": response.text, "today": today])
            guard let answer = result?["answer"] as? [String: Any], let subscription = answer["subscription"] as? Bool else { return nil }
            return .subscription(subscription)
        }
        // Two at a time: the service refuses by concurrency, and two is its limit.
        var answers: [String: ProviderModelAccess] = [:]
        var pending = targets.compactMap { $0["id"] as? String }[...]
        await withTaskGroup(of: (String, ProviderModelAccess?).self) { group in
            let limit = (try? ProviderCoreSettings.call("provider_concurrency", ["provider": provider.id])["limit"] as? Int) ?? 2
            for _ in 0..<max(1, limit) { if let id = pending.popFirst() { group.addTask { (id, await probe(id)) } } }
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
