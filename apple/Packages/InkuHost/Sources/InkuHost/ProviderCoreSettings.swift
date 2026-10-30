import Foundation
import InkuCore

/// The single boundary between the macOS persisted representation and shared provider settings.
/// Credentials and the personal plan remain in the host and never enter this conversion.
public enum ProviderCoreSettings {
    public static func call(_ action: String, _ fields: [String: Any] = [:]) throws -> [String: Any] {
        var request = fields
        request["schema"] = "inku.model-catalog-request.v1"; request["action"] = action
        let data = try JSONSerialization.data(withJSONObject: request, options: [.sortedKeys])
        guard let response = try JSONSerialization.jsonObject(with: InkuCore.modelCatalog(data)) as? [String: Any] else {
            throw HostError("provider_core_invalid")
        }
        if let error = response["error"] as? String { throw HostError(error) }
        return response
    }

    public static var definitions: [[String: Any]] {
        (try? call("providers", ["host": "macos"])["providers"] as? [[String: Any]]) ?? []
    }
    private static var catalogProviders: [String: [String: Any]] {
        (try? JSONSerialization.jsonObject(with: SharedModelCatalog.catalogData) as? [String: Any])?["providers"] as? [String: [String: Any]] ?? [:]
    }
    private static func catalogRows(_ id: String) -> [[String: Any]] {
        catalogProviders[id]?["models"] as? [[String: Any]] ?? []
    }
    private static func defaultRows(_ id: String) -> [[String: Any]] {
        let defaults = (try? call("catalog"))?["defaults"] as? [String: [[String: Any]]] ?? [:]
        return defaults[id] ?? []
    }

    public static func model(_ row: [String: Any]) throws -> ProviderModelSettings {
        let names: [String: String] = ["recommendation_level":"recommendationLevel", "recommendation_llm":"recommendationLLM",
            "recommendation_vision":"recommendationVision", "recommendation_stage1":"recommendationStage1", "recommendation_stage2":"recommendationStage2",
            "speed_class":"speedClass", "speed_label":"speedLabel", "comment_ja":"commentJA", "comment_en":"commentEN",
            "eol_date":"eolDate", "requires_subscription":"requiresSubscription", "unsupported_purposes":"unsupportedPurposes",
            "allowed_unsupported_purposes":"allowedUnsupportedPurposes", "speed_llm_seconds":"speedLLMSeconds", "speed_vision_seconds":"speedVisionSeconds",
            "cost_usd_llm":"costUSDLLM", "cost_usd_vision":"costUSDVision"]
        var mapped = row
        for (key, destination) in names { if let value = row[key] { mapped[destination] = value } }
        var labels = Set(row["labels"] as? [String] ?? [])
        for (key, label) in [("legacy", "legacy"), ("not_supported", "not_supported"), ("requires_subscription", "subscription"), ("eol", "eol")] {
            if row[key] as? Bool == true { labels.insert(label) }
        }
        mapped["labels"] = labels.sorted()
        mapped["catalogMeasurementPresent"] = !SharedModelCatalog.measurementKeys.isDisjoint(with: row.keys)
        return try JSONDecoder().decode(ProviderModelSettings.self, from: JSONSerialization.data(withJSONObject: mapped))
    }

    public static func providerRecord(_ provider: ProviderSettings, migrating: Bool = false) -> [String: Any] {
        let rows = provider.models?.map(\.coreCatalogRecord) ?? defaultRows(provider.id)
        let activeIDs = Set(rows.compactMap { row -> String? in
            guard let id = row["id"] as? String, let value = try? model(row) else { return nil }
            var evaluated = value
            if migrating, provider.models != nil,
               definitions.contains(where: { $0["id"] as? String == provider.id && $0["kind"] as? String == provider.kind.rawValue }),
               let source = catalogRows(provider.id).first(where: { $0["id"] as? String == id }),
               let internalRow = (try? call("internal", ["model": source]))?["model"] as? [String: Any],
               var catalogModel = try? model(internalRow) {
                // Before migration the UI overlaid catalog measurements while
                // preserving the author's local access and purpose choices.
                let allowed = value.allowedUnsupportedPurposes ?? []
                let purposes = value.purposes.filter { !catalogModel.isNotRecommended(for: $0) || allowed.contains($0) }
                catalogModel.purposes = purposes
                catalogModel.allowedUnsupportedPurposes = allowed
                catalogModel.eol = value.eol
                catalogModel.requiresSubscription = value.requiresSubscription
                evaluated = catalogModel
            }
            guard evaluated.isPublishable else { return nil }
            return id
        })
        let definition = definitions.first { $0["id"] as? String == provider.id }
        let definitionRows = definition?["models"] as? [[String: Any]] ?? []
        let all = rows + catalogRows(provider.id) + definitionRows
        var enabled: [String: Bool] = [:]
        for row in all {
            guard let id = row["id"] as? String, !id.isEmpty else { continue }
            enabled[id] = activeIDs.contains(id) && provider.enabledModels?[id] != false
        }
        let limits = provider.rateLimits
        var result: [String: Any] = ["id": provider.id, "label": provider.label ?? provider.id,
            "kind": provider.apiProfile == "mlx" ? "mlx" : provider.kind.rawValue,
            "base_url": provider.baseURL.absoluteString, "requires_api_key": provider.requiresAPIKey,
            "api_key": "", "active": true, "models": rows, "enabled_models": enabled, "memo": provider.memo ?? ""]
        result["default_base_url"] = definition?["default_base_url"] as? String ?? provider.baseURL.absoluteString
        result["builtin"] = definition != nil
        var rate: [String: Int] = [:]
        if let value = limits?.requestsPerMinute { rate["rpm"] = value }
        if let value = limits?.tokensPerMinute { rate["tpm"] = value }
        if let value = limits?.requestsPerDay { rate["rpd"] = value }
        if limits != nil { result["rate_limits"] = rate }
        return result
    }

    public static func coreInput(_ host: HostSettings) -> (settings: [String: Any], order: [String]) {
        var providers: [String: Any] = [:]
        let regular = host.providers.filter { $0.kind != .chatGPTPlan }
        for provider in regular { providers[provider.id] = providerRecord(provider, migrating: host.inactiveBuiltinProviderIDs == nil) }
        if host.providerDefaultsInstalled == true {
            for definition in definitions {
                guard let id = definition["id"] as? String, providers[id] == nil else { continue }
                providers[id] = ["id": id, "active": false]
            }
        }
        for id in host.inactiveBuiltinProviderIDs ?? [] { providers[id] = ["id": id, "active": false] }
        let regularOrder = regular.map(\.id)
        let catalogVersion = (try? call("catalog"))?["version"] as? String ?? ""
        // The inactive-ID field is introduced by this migration. On the first
        // read let core refresh catalog metadata; subsequent reads retain the
        // already-normalized observations instead of overlaying them again.
        return (["providers": providers, "model_catalog_version": host.inactiveBuiltinProviderIDs == nil ? "" : catalogVersion],
                regularOrder + providers.keys.filter { !regularOrder.contains($0) }.sorted())
    }

    public static func normalize(_ host: HostSettings) throws -> HostSettings {
        let input = coreInput(host)
        let result = try call("normalize_settings", ["host":"macos", "settings":input.settings, "order":input.order, "env":[:]])
        return try fromCore(result, preserving: host)
    }
    public static func update(_ previous: HostSettings, to host: HostSettings) throws -> HostSettings {
        let before = coreInput(previous), after = coreInput(host)
        let beforeRows = before.settings["providers"] as? [String: Any] ?? [:]
        // Normalize first: core can add built-in rows (notably NVIDIA). Supply a
        // switch for every resulting row in the patch, including the added ones.
        let normalized = try call("normalize_settings", ["host": "macos", "settings": after.settings, "order": after.order, "env": [:]])
        guard let normalizedSettings = normalized["settings"] as? [String: Any],
              let afterRows = normalizedSettings["providers"] as? [String: Any] else { throw HostError("provider_core_invalid") }
        var patch = afterRows
        for id in beforeRows.keys where afterRows[id] == nil { patch[id] = ["delete": true] }
        let result = try call("update_settings", ["host": "macos", "settings": before.settings, "order": before.order,
            "patch": ["providers": patch], "patch_order": after.order + patch.keys.filter { !after.order.contains($0) }.sorted(), "env": [:]])
        return try fromCore(result, preserving: host)
    }
    public static func catalogModels(_ provider: ProviderSettings, purpose: String? = nil, includeDisabled: Bool = false) -> [ProviderModelSettings] {
        guard provider.kind != .chatGPTPlan else { return provider.models ?? [] }
        let row = providerRecord(provider)
        let response = try? call("provider_catalog", ["settings": ["providers": [provider.id: row]], "order": [provider.id],
            "include_disabled": includeDisabled, "include_developer": true, "purpose": purpose ?? ""])
        let groups = response?["providers"] as? [[String: Any]] ?? []
        let rows = groups.first?["models"] as? [[String: Any]] ?? []
        return rows.compactMap { try? model($0) }
    }
    public static func isOffered(_ model: String, provider: ProviderSettings, purpose: String) -> Bool {
        let response = try? call("model_offered", ["settings": ["providers": [provider.id: providerRecord(provider)]],
            "order": [provider.id], "provider": provider.id, "model": model, "purpose": purpose])
        return response?["offered"] as? Bool ?? false
    }
    public static func connection(_ provider: ProviderSettings) throws -> ProviderSettings {
        guard provider.kind != .chatGPTPlan else { return provider }
        let response = try call("connection", ["provider": provider.id, "settings": ["providers": [provider.id: providerRecord(provider)]]])
        guard let row = response["connection"] as? [String: Any], let kind = row["kind"] as? String,
              let resolvedKind = ProviderKind(rawValue: kind), let base = row["base_url"] as? String,
              let url = URL(string: base) else { throw HostError("provider_core_invalid") }
        var result = provider
        result.kind = resolvedKind; result.baseURL = url
        result.apiProfile = (row["api_profile"] as? String) == "mlx" ? "mlx" : provider.apiProfile
        result.requiresAPIKey = row["requires_api_key"] as? Bool ?? provider.requiresAPIKey
        return result
    }
    public static func fromCore(_ result: [String: Any], preserving original: HostSettings) throws -> HostSettings {
        guard let settings = result["settings"] as? [String: Any], let providers = settings["providers"] as? [String: [String: Any]],
              let order = result["order"] as? [String] else { throw HostError("provider_core_invalid") }
        var host = original
        let old = Dictionary(original.providers.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        var converted: [ProviderSettings] = []
        var inactive: [String] = []
        for id in order {
            guard let row = providers[id] else { continue }
            if row["active"] as? Bool == false { if row["builtin"] as? Bool == true { inactive.append(id) }; continue }
            guard let base = row["base_url"] as? String, let url = URL(string: base) else { throw HostError("provider_base_url_invalid") }
            let kindName = row["kind"] as? String ?? "openai_compatible"
            let kind = ProviderKind(rawValue: kindName == "mlx" ? "openai_compatible" : kindName) ?? .openAICompatible
            let rate = row["rate_limits"] as? [String: Int] ?? [:]
            let models = try (row["models"] as? [[String: Any]] ?? []).map(model)
            var enabled = row["enabled_models"] as? [String: Bool] ?? [:]
            for model in models where !model.isPublishable { enabled[model.id] = false }
            converted.append(ProviderSettings(id: id, kind: kind, baseURL: url, apiProfile: kindName == "mlx" ? "mlx" : old[id]?.apiProfile,
                requiresAPIKey: row["requires_api_key"] as? Bool ?? true, credentialID: old[id]?.credentialID ?? id,
                rateLimits: .init(requestsPerMinute: rate["rpm"], tokensPerMinute: rate["tpm"], requestsPerDay: rate["rpd"]),
                label: row["label"] as? String, models: models, enabledModels: enabled, memo: row["memo"] as? String))
        }
        host.providers = converted + original.providers.filter { $0.kind == .chatGPTPlan }
        host.inactiveBuiltinProviderIDs = inactive.sorted()
        host.providerDefaultsInstalled = true
        return host
    }
}
