import Foundation
import InkuHost

public enum ProviderModelFilter: String, CaseIterable, Sendable, Identifiable {
    case all, enabled, disabled, llm, vision
    public var id: String { rawValue }
}

/// The drawing picker preserves the ChatGPT publication order and otherwise uses core sort keys.
public enum ProviderModelOrdering {
    public static func picker(_ models: [ProviderModelSettings], purpose: String, chatGPT: Bool) -> [ProviderModelSettings] {
        if chatGPT { return models }
        let stage = purpose == "vision" ? "none" : "both"
        return models.enumerated().sorted { first, second in
            let left = first.element.catalogSortKey(purpose: purpose, stage: stage)
            let right = second.element.catalogSortKey(purpose: purpose, stage: stage)
            return left == right ? first.offset < second.offset : left < right
        }.map(\.element)
    }
}

/// A sheet-local draft never changes persisted settings until its owner saves it.
public struct ProviderModelsDraft: Sendable, Equatable {
    public var models: [ProviderModelSettings]
    public var enabled: [String: Bool]
    private let initialModels: [ProviderModelSettings]
    private let initialEnabled: [String: Bool]

    public init(models: [ProviderModelSettings], enabled: [String: Bool]) {
        self.models = models
        self.enabled = enabled
        initialModels = models
        initialEnabled = enabled
    }

    public var isDirty: Bool { models != initialModels || enabled != initialEnabled }
    public var enabledCount: Int { models.filter { isEnabled(modelID: $0.id) }.count }

    public func model(modelID: String) -> ProviderModelSettings? {
        models.first { $0.id == modelID }
    }

    public func isEnabled(modelID: String) -> Bool {
        guard let model = model(modelID: modelID), model.isPublishable else { return false }
        let row: [String: Any] = ["id": "draft", "active": true, "models": [model.coreCatalogRecord], "enabled_models": enabled]
        let answer = try? ProviderCoreSettings.call("model_offered", ["settings": ["providers": ["draft": row]], "order": ["draft"],
            "provider": "draft", "model": modelID])
        return answer?["offered"] as? Bool ?? false
    }

    public func filteredModels(search: String, filter: ProviderModelFilter) -> [ProviderModelSettings] {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        return models.enumerated().filter { _, model in
            let text = [model.id, model.label, model.speedLabel ?? "",
                        model.commentJA ?? "", model.commentEN ?? ""].joined(separator: " ")
            guard query.isEmpty || text.localizedCaseInsensitiveContains(query) else { return false }
            switch filter {
            case .all: return true
            case .enabled: return isEnabled(modelID: model.id)
            case .disabled: return !isEnabled(modelID: model.id)
            case .llm: return model.purposes.contains("llm")
            case .vision: return model.purposes.contains("vision")
            }
        }.sorted { lhs, rhs in
            let left = lhs.element.catalogSortKey(), right = rhs.element.catalogSortKey()
            return left == right ? lhs.offset < rhs.offset : left < right
        }.map(\.element)
    }

    public mutating func setEnabled(modelID: String, enabled value: Bool) {
        guard let model = model(modelID: modelID), !value || model.isPublishable else { return }
        enabled[modelID] = value
    }

    /// A purpose measured without a response can be chosen too, as not recommended (the author, 2026-10-26);
    /// the model keeps it in `allowedUnsupportedPurposes`, as the Server does.
    public mutating func togglePurpose(modelID: String, purpose: String) {
        guard ["llm", "vision"].contains(purpose),
              let index = models.firstIndex(where: { $0.id == modelID }),
              Self.canEditPurposes(models[index]) else { return }
        if models[index].purposes.contains(purpose) {
            models[index].purposes.removeAll { $0 == purpose }
        } else {
            models[index].purposes.append(purpose)
        }
        let allowed = models[index].purposes.filter(models[index].isNotRecommended(for:))
        models[index].allowedUnsupportedPurposes = allowed.isEmpty ? nil : allowed
        enabled[modelID] = !models[index].purposes.isEmpty
    }

    /// An author can restore a locally cleared purpose without publishing a blocked model.
    public static func canEditPurposes(_ model: ProviderModelSettings) -> Bool {
        model.resolvedLabels.allSatisfy { $0.publishable || ($0.id == "no_response" && !model.labels.contains("no_response")) }
    }

    public mutating func setVisible(models visible: [ProviderModelSettings], enabled value: Bool) {
        for model in visible { setEnabled(modelID: model.id, enabled: value) }
    }

    public mutating func updateModel(_ model: ProviderModelSettings) {
        guard let index = models.firstIndex(where: { $0.id == model.id }) else { return }
        models[index] = model
    }

}
