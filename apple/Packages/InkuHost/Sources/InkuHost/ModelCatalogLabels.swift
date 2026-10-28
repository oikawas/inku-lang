import Foundation

public struct ModelCatalogLabelDefinition: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public let ja: String
    public let en: String
    public let publishable: Bool

    public func name(language: String) -> String { language == "en" ? en : ja }
}

/// The shared core supplies ordering, names and publication policy.
public enum ModelCatalogLabels {
    public static let definitions = SharedModelCatalog.labels

    public static func resolve(for model: ProviderModelSettings) -> [ModelCatalogLabelDefinition] {
        let ids = SharedModelCatalog.decision(for: model).labels
        return ids.compactMap { id in definitions.first { $0.id == id } }
    }
}
