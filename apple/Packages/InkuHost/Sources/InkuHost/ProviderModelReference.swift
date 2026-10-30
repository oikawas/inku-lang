import Foundation

/// Server model_settings.provider_for_model. Three rules, no guessing:
/// 1. a prefix naming a known provider (configured, retired `ovms`, or `chatgpt`) before the first colon;
/// 2. otherwise the only provider whose model list holds the whole reference (`gpt-oss:20b` stays one id);
/// 3. otherwise the stage default provider, which Server reads as `nvidia` for the pipeline and its readers.
public enum ProviderModelReference {
    public static let retiredProviderIDs: Set<String> = Set(((try? ProviderCoreSettings.call("retired_providers"))?["providers"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? String })
    public static let stageDefaultProviderID = "nvidia"

    public static func split(_ reference: String, providers: [ProviderSettings]) -> (providerID: String, model: String)? {
        let result = try? ProviderCoreSettings.call("split_ref", ["ref": reference, "providers": referenceProviders(providers)])
        guard let id = result?["provider"] as? String, let model = result?["model"] as? String else { return nil }
        return (id, model)
    }

    public static func resolve(_ reference: String, providers: [ProviderSettings], defaultProvider: String = stageDefaultProviderID) -> (providerID: String, model: String) {
        let result = try? ProviderCoreSettings.call("resolve_ref", ["ref": reference, "providers": referenceProviders(providers), "default_provider": defaultProvider])
        return (result?["provider"] as? String ?? defaultProvider, result?["model"] as? String ?? reference)
    }
    public static func referenceProviders(_ providers: [ProviderSettings]) -> [String: Any] {
        var result = Dictionary(providers.filter { $0.kind != .chatGPTPlan }.map { provider in
            (provider.id, ["id": provider.id, "label": provider.label ?? provider.id, "active": true,
                           "models": (provider.models ?? []).map(\.coreCatalogRecord)] as [String: Any])
        }, uniquingKeysWith: { first, _ in first })
        // Removed built-ins still exist as inactive rows in the core. They do
        // not own bare models, but remain recognizable as explicit prefixes.
        for definition in ProviderCoreSettings.definitions {
            guard let id = definition["id"] as? String, result[id] == nil else { continue }
            result[id] = ["id": id, "label": definition["label"] as? String ?? id, "active": false, "models": []] as [String: Any]
        }
        return result
    }
}
