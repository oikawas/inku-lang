import Foundation
import InkuHost

/// Versioned Server evaluations provide defaults until a service saves its own catalog.
public struct ModelGuidanceCatalog: Decodable, Sendable {
    public let schema: String
    public let version: String
    public let updated: String
    private let providers: [GuidanceProvider]

    public static let bundled: ModelGuidanceCatalog? = try? loadBundled()

    public static func loadBundled() throws -> ModelGuidanceCatalog {
        guard let url = Bundle.module.url(forResource: "server-defaults", withExtension: "json") else {
            throw HostError("bundled_resources_unavailable")
        }
        let envelope = try JSONDecoder().decode(GuidanceManifest.self, from: Data(contentsOf: url))
        guard envelope.modelGuidance.schema == "inku.model-guidance.v1" else {
            throw HostError("model_guidance_schema_invalid")
        }
        return envelope.modelGuidance
    }

    public func registeredModels(for connection: ProviderSettings) -> [ProviderModelInfo] {
        registeredModelSettings(for: connection).filter {
            $0.isSelectable && $0.purposes.contains("llm") && connection.enabledModels?[$0.id] != false
        }.map {
            ProviderModelInfo(id: connection.id + ":" + $0.id, name: $0.label, contextLimit: nil, capabilities: [])
        }
    }

    public func registeredModelSettings(for connection: ProviderSettings) -> [ProviderModelSettings] {
        if let models = connection.models { return models }
        guard let provider = providers.first(where: { $0.id == connection.id && $0.kind == connection.kind.rawValue }) else { return [] }
        return provider.models.map(\.settings)
    }

    public func guidance(for reference: String, providers configured: [ProviderSettings]) -> ModelGuidance? {
        guard let separator = reference.firstIndex(of: ":") else { return nil }
        let providerID = String(reference[..<separator])
        let modelID = String(reference[reference.index(after: separator)...])
        guard !modelID.isEmpty,
              let connection = configured.first(where: { $0.id == providerID }),
              let model = registeredModelSettings(for: connection).first(where: { $0.id == modelID }) else { return nil }
        let speedHidden = providers.first(where: { $0.id == providerID && $0.kind == connection.kind.rawValue })?.speedHidden ?? false
        return ModelGuidance(providerID: providerID, modelID: modelID, label: model.label,
                             purposes: model.purposes,
                             stage1: model.recommendationStage1, stage2: model.recommendationStage2,
                             llm: model.recommendationLLM ?? model.recommendationLevel,
                             vision: model.recommendationVision ?? model.recommendationLevel,
                             speedLabel: speedHidden ? nil : model.speedLabel,
                             speedClass: speedHidden ? nil : model.speedClass,
                             speedHidden: speedHidden,
                             japaneseComment: model.commentJA, englishComment: model.commentEN,
                             endOfLife: model.eol ?? false, endOfLifeDate: model.eolDate,
                             requiresSubscription: model.requiresSubscription ?? false)
    }
}

public struct ModelGuidance: Sendable {
    public let providerID: String
    public let modelID: String
    public let label: String
    public let purposes: [String]
    private let stage1: Int?
    private let stage2: Int?
    private let llm: Int?
    private let vision: Int?
    public let speedLabel: String?
    public let speedClass: String?
    public let speedHidden: Bool
    public let japaneseComment: String?
    public let englishComment: String?
    public let endOfLife: Bool
    public let endOfLifeDate: String?
    public let requiresSubscription: Bool

    fileprivate init(providerID: String, modelID: String, label: String, purposes: [String],
                     stage1: Int?, stage2: Int?, llm: Int?, vision: Int?, speedLabel: String?,
                     speedClass: String?, speedHidden: Bool, japaneseComment: String?, englishComment: String?,
                     endOfLife: Bool, endOfLifeDate: String?, requiresSubscription: Bool) {
        self.providerID = providerID; self.modelID = modelID; self.label = label; self.purposes = purposes
        self.stage1 = stage1; self.stage2 = stage2; self.llm = llm; self.vision = vision
        self.speedLabel = speedLabel; self.speedClass = speedClass; self.speedHidden = speedHidden
        self.japaneseComment = japaneseComment; self.englishComment = englishComment
        self.endOfLife = endOfLife; self.endOfLifeDate = endOfLifeDate; self.requiresSubscription = requiresSubscription
    }

    public var hasStageRecommendations: Bool { stage1 != nil || stage2 != nil }
    public var hasEvaluation: Bool {
        hasStageRecommendations || llm != nil || vision != nil || speedLabel != nil
            || comment(language: "ja") != nil
    }
    public var stage1Level: Int? { Self.level(stage1 ?? llm) }
    public var stage2Level: Int? { Self.level(stage2 ?? llm) }
    // Server/Web's 'both' selection uses the weaker measured stage, while an
    // end-to-end evaluation has one LLM number. Vision never raises this value.
    public var bothStagesLevel: Int? { Self.level([stage1, stage2].compactMap { $0 }.min() ?? llm) }
    public var visionLevel: Int? { Self.level(vision) }

    public func comment(language: String) -> String? {
        let preferred = language == "en" ? englishComment : japaneseComment
        let fallback = language == "en" ? japaneseComment : englishComment
        return [preferred, fallback].compactMap { $0 }.first { !$0.isEmpty }
    }

    public static func recommendation(_ level: Int?) -> String {
        guard let level = Self.level(level) else { return "—" }
        return String(repeating: "★", count: level) + String(repeating: "☆", count: 5 - level) + " (\(level)/5)"
    }

    private static func level(_ value: Int?) -> Int? {
        guard let value, value > 0 else { return nil }
        return min(5, value)
    }
}

private struct GuidanceManifest: Decodable {
    let modelGuidance: ModelGuidanceCatalog
    enum CodingKeys: String, CodingKey { case modelGuidance = "model_guidance" }
}

private struct GuidanceProvider: Decodable, Sendable {
    let id: String
    let kind: String
    let speedHidden: Bool
    let models: [GuidanceModel]
    enum CodingKeys: String, CodingKey { case id, kind, models; case speedHidden = "speed_hidden" }
}

private struct GuidanceModel: Decodable, Sendable {
    let id: String
    let label: String
    let purposes: [String]?
    let recommendationLLM: Int?
    let recommendationVision: Int?
    let recommendationStage1: Int?
    let recommendationStage2: Int?
    let recommendationLevel: Int?
    let speedLabel: String?
    let speedClass: String?
    let commentJA: String?
    let commentEN: String?
    let eol: Bool?
    let eolDate: String?
    let requiresSubscription: Bool?
    var settings: ProviderModelSettings {
        .init(id: id, label: label, purposes: purposes ?? ["llm"],
              recommendationLevel: recommendationLevel, recommendationLLM: recommendationLLM,
              recommendationVision: recommendationVision, recommendationStage1: recommendationStage1,
              recommendationStage2: recommendationStage2, speedClass: speedClass, speedLabel: speedLabel,
              commentJA: commentJA, commentEN: commentEN, eol: eol, eolDate: eolDate,
              requiresSubscription: requiresSubscription)
    }
    enum CodingKeys: String, CodingKey {
        case id, label, purposes, eol
        case recommendationLLM = "recommendation_llm", recommendationVision = "recommendation_vision"
        case recommendationStage1 = "recommendation_stage1", recommendationStage2 = "recommendation_stage2"
        case recommendationLevel = "recommendation_level", speedLabel = "speed_label", speedClass = "speed_class"
        case commentJA = "comment_ja", commentEN = "comment_en", eolDate = "eol_date"
        case requiresSubscription = "requires_subscription"
    }
}
