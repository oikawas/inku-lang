import Foundation

/// Server model_settings.provider_for_model. Three rules, no guessing:
/// 1. a prefix naming a known provider (configured, retired `ovms`, or `chatgpt`) before the first colon;
/// 2. otherwise the only provider whose model list holds the whole reference (`gpt-oss:20b` stays one id);
/// 3. otherwise the stage default provider, which Server reads as `nvidia` for the pipeline and its readers.
public enum ProviderModelReference {
    public static let retiredProviderIDs: Set<String> = ["ovms"]
    public static let stageDefaultProviderID = "nvidia"

    public static func split(_ reference: String, providers: [ProviderSettings]) -> (providerID: String, model: String)? {
        guard let colon = reference.firstIndex(of: ":"), colon > reference.startIndex else { return nil }
        let head = String(reference[..<colon]), rest = String(reference[reference.index(after: colon)...])
        let known = Set(providers.map(\.id)).union(retiredProviderIDs).union(["chatgpt"])
        return !rest.isEmpty && known.contains(head) ? (head, rest) : nil
    }

    public static func resolve(_ reference: String, providers: [ProviderSettings]) -> (providerID: String, model: String) {
        if let qualified = split(reference, providers: providers) { return qualified }
        // The personal plan never owns a bare reference: Server keeps it out of the provider catalog.
        let owners = providers.filter { $0.kind != .chatGPTPlan && ($0.models ?? []).contains { $0.id == reference } }
        if owners.count == 1 { return (owners[0].id, reference) }
        return (stageDefaultProviderID, reference)
    }
}
