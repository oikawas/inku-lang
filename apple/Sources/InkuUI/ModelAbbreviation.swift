import Foundation
import InkuHost

/// Model display names and history-strip labels come from the shared core.
public struct ModelNaming: Sendable {
    /// Web `DEFAULT_PROVIDER`, the stage default of rule 3.
    public static let defaultProvider = "nvidia"

    private let connections: [ProviderSettings]
    private let stageDefault: String
    /// `ja` or `en`: core names a sign-in connection in it ("ChatGPT でサインイン" / "Sign in with ChatGPT").
    private let language: String
    private static let resolutionCache = ModelResolutionCache()

    public init(providers: [ProviderSettings] = [], stageProvider: String = defaultProvider, language: String = "en") {
        connections = providers
        stageDefault = stageProvider
        self.language = language == "ja" ? "ja" : "en"
    }

    private func displayResolution(_ reference: String, defaultProvider: String? = nil) -> [String: Any] {
        let key = ModelResolutionCache.Key(reference: reference, provider: defaultProvider ?? stageDefault, language: language)
        if let cached = Self.resolutionCache.get(key, connections: connections) { return cached }
        var providers = ProviderModelReference.referenceProviders(connections)
        if let plan = connections.first(where: { $0.kind == .chatGPTPlan && $0.id == "chatgpt" }) {
            // Core resolve_display names the sign-in connection and its abbreviation from its descriptor.
            providers["chatgpt"] = ["id": "chatgpt", "active": true,
                "models": (plan.models ?? []).map { ["id": $0.id, "label": $0.label] }] as [String: Any]
        }
        let resolved = (try? ProviderCoreSettings.call("resolve_display", ["ref": reference,
            "providers": providers, "default_provider": defaultProvider ?? stageDefault, "language": language])) ?? [:]
        Self.resolutionCache.put(resolved, for: key, connections: connections)
        return resolved
    }

    // MARK: models.ts

    /// The provider's own name, falling back to its id when the catalog has none.
    public func providerLabel(_ provider: String) -> String {
        guard !provider.isEmpty else { return "" }
        return displayResolution(provider + ":_", defaultProvider: provider)["provider_label"] as? String ?? provider
    }

    /// Web `resolveModelRefForDisplay`: explicit qualification, sole ownership, retired ownership, then the stage default.
    public func resolve(_ reference: String, stageProvider: String = ModelNaming.defaultProvider) -> (provider: String, model: String) {
        let answer = displayResolution(reference, defaultProvider: stageProvider == Self.defaultProvider ? stageDefault : stageProvider)
        return (answer["provider"] as? String ?? stageProvider, answer["model"] as? String ?? reference)
    }

    /// Core's display name, retaining the provider and API model ID.
    public func displayName(_ reference: String?) -> String {
        let ref = (reference ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !ref.isEmpty else { return "" }
        let answer = displayResolution(ref)
        if let name = answer["display_name"] as? String { return name }
        let (provider, model) = resolve(ref)
        let owner = answer["provider_label"] as? String ?? provider
        return owner.isEmpty ? model : "\(owner) / \(model)"
    }

    /// The model ID, including any vendor prefix.
    public func modelShortName(_ reference: String?) -> String {
        let ref = (reference ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !ref.isEmpty else { return "" }
        return resolve(ref).model
    }

    /// Library cards use the same core display name.
    public func shortModel(_ reference: String?) -> String {
        displayName(reference)
    }

    /// Web `historyModelStage1Short`, the history strip form.
    public func stripModel(_ reference: String?) -> String {
        guard let reference, !reference.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return "-" }
        return displayResolution(reference)["strip_label"] as? String ?? reference
    }

    /// Shared core action used for fixture checks of history-strip labels.
    public static func stripLabel(owner: String, name: String, abbreviation: String? = nil) -> String {
        let answer = try? ProviderCoreSettings.call("strip_label", ["owner": owner, "name": name, "owner_abbreviation": abbreviation as Any? ?? NSNull()])
        return answer?["strip_label"] as? String ?? name
    }

    // MARK: HistoryManager.svelte

    public struct Line: Sendable, Equatable {
        public enum Role: Sendable { case interpretation, drawing }
        public let role: Role?
        /// nil when the stage's model was not recorded.
        public let compact: String?
        public let full: String?
    }

    /// Web `modelLines`: one unlabeled line when both stages used the same model, otherwise one line per stage.
    public func cardLines(stage1: String?, stage2: String?) -> [Line] {
        func recorded(_ value: String?) -> String? {
            guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
            return value
        }
        let interpretation = recorded(stage1), drawing = recorded(stage2)
        if let interpretation, interpretation == drawing {
            return [Line(role: nil, compact: shortModel(interpretation), full: displayName(interpretation))]
        }
        return [Line(role: .interpretation, compact: interpretation.map(shortModel), full: interpretation.map(displayName)),
                Line(role: .drawing, compact: drawing.map(shortModel), full: drawing.map(displayName))]
    }
}

/// A tab change rebuilds the history row, but its saved model names and provider catalog have not changed.
/// Separate provider snapshots so a changed connection cannot reuse stale labels.
private final class ModelResolutionCache: @unchecked Sendable {
    struct Key: Hashable {
        let reference: String
        let provider: String
        let language: String
    }

    private let lock = NSLock()
    private struct Snapshot {
        let connections: [ProviderSettings]
        var resolutions: [Key: [String: Any]] = [:]
    }
    private var snapshots: [Snapshot] = []

    func get(_ key: Key, connections current: [ProviderSettings]) -> [String: Any]? {
        lock.withLock {
            snapshots.first(where: { $0.connections == current })?.resolutions[key]
        }
    }

    func put(_ value: [String: Any], for key: Key, connections current: [ProviderSettings]) {
        lock.withLock {
            if let index = snapshots.firstIndex(where: { $0.connections == current }) {
                if snapshots[index].resolutions.count >= 256 { snapshots[index].resolutions.removeAll(keepingCapacity: true) }
                snapshots[index].resolutions[key] = value
            } else {
                if snapshots.count >= 4 { snapshots.removeFirst() }
                snapshots.append(Snapshot(connections: current, resolutions: [key: value]))
            }
        }
    }
}
