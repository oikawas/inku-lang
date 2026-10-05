import Foundation
import InkuHost

public enum ProviderModelFilter: String, CaseIterable, Sendable, Identifiable {
    case all, enabled, disabled, llm, vision
    public var id: String { rawValue }
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
        guard let model = model(modelID: modelID), model.isSelectable else { return false }
        return enabled[modelID] ?? true
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
            if lhs.element.isSelectable != rhs.element.isSelectable { return lhs.element.isSelectable }
            let leftLevel = Self.recommendationLevel(lhs.element)
            let rightLevel = Self.recommendationLevel(rhs.element)
            if leftLevel != rightLevel { return leftLevel > rightLevel }
            let order = lhs.element.label.localizedStandardCompare(rhs.element.label)
            return order == .orderedSame ? lhs.offset < rhs.offset : order == .orderedAscending
        }.map(\.element)
    }

    public mutating func setEnabled(modelID: String, enabled value: Bool) {
        guard let model = model(modelID: modelID), !value || model.isSelectable else { return }
        enabled[modelID] = value
    }

    public mutating func togglePurpose(modelID: String, purpose: String) {
        guard ["llm", "vision"].contains(purpose),
              let index = models.firstIndex(where: { $0.id == modelID }),
              models[index].isSelectable else { return }
        if models[index].purposes.contains(purpose) {
            models[index].purposes.removeAll { $0 == purpose }
        } else {
            models[index].purposes.append(purpose)
        }
        enabled[modelID] = !models[index].purposes.isEmpty
    }

    public mutating func setVisible(models visible: [ProviderModelSettings], enabled value: Bool) {
        for model in visible { setEnabled(modelID: model.id, enabled: value) }
    }

    public mutating func updateModel(_ model: ProviderModelSettings) {
        guard let index = models.firstIndex(where: { $0.id == model.id }) else { return }
        models[index] = model
    }

    private static func recommendationLevel(_ model: ProviderModelSettings) -> Int {
        let llm = model.purposes.contains("llm") ? model.recommendationLLM ?? model.recommendationLevel ?? 0 : 0
        let vision = model.purposes.contains("vision") ? model.recommendationVision ?? model.recommendationLevel ?? 0 : 0
        return min(5, max(0, max(llm, vision)))
    }
}
