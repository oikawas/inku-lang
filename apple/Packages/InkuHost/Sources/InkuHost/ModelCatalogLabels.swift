import Foundation

public struct ModelCatalogLabelDefinition: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public let ja: String
    public let en: String
    public let publishable: Bool

    public func name(language: String) -> String { language == "en" ? en : ja }
}

/// The Server label table supplies ordering, names and publication policy.
public enum ModelCatalogLabels {
    public static let definitions: [ModelCatalogLabelDefinition] = {
        do { return try loadBundled() }
        catch { preconditionFailure("Bundled model label table unavailable: \(error)") }
    }()

    public static func loadBundled() throws -> [ModelCatalogLabelDefinition] {
        guard let url = Bundle.module.url(forResource: "model-labels", withExtension: "json") else {
            throw HostError("model_catalog_labels_unavailable")
        }
        let table = try JSONDecoder().decode(LabelTable.self, from: Data(contentsOf: url))
        guard table.schema == "inku.model-catalog.v2", !table.labels.isEmpty,
              Set(table.labels.map(\.id)).count == table.labels.count else {
            throw HostError("model_catalog_labels_invalid")
        }
        return table.labels
    }

    public static func resolve(for model: ProviderModelSettings) -> [ModelCatalogLabelDefinition] {
        var labels = Set(model.labels)
        if let subscription = model.requiresSubscription {
            if subscription { labels.insert("subscription") } else { labels.remove("subscription") }
        }
        if let eol = model.eol {
            if eol { labels.insert("eol") } else { labels.remove("eol") }
        }
        // A purpose chosen against the measurement (2026-10-26) does not make the model answer it.
        if model.purposes.allSatisfy(model.isNotRecommended(for:)) { labels.insert("no_response") }
        if !model.hasCatalogMeasurement && definitions.filter({ labels.contains($0.id) }).allSatisfy(\.publishable) {
            labels.insert("unmeasured")
        }
        return definitions.filter { labels.contains($0.id) }
    }

    private struct LabelTable: Decodable {
        let schema: String
        let labels: [ModelCatalogLabelDefinition]
    }
}
