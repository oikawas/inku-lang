import Foundation
import InkuHost

/// Evaluations are refreshed from the canonical catalog; local registration stays author-owned.
public struct ModelGuidanceCatalog: Decodable, Sendable {
    public let schema: String
    public let version: String
    public let updated: String
    public let labelDefinitions: [ModelCatalogLabelDefinition]
    private let providers: [String: GuidanceProvider]
    private var providerDefinitions: [GuidanceProviderDefinition] = []

    public static let bundled: ModelGuidanceCatalog? = try? loadBundled()

    public static func bundledManifestData() throws -> Data {
        guard let url = Bundle.module.url(forResource: "server-defaults", withExtension: "json") else {
            throw HostError("bundled_resources_unavailable")
        }
        return try Data(contentsOf: url)
    }

    public static func loadBundled() throws -> ModelGuidanceCatalog {
        let envelope = try JSONDecoder().decode(GuidanceManifest.self, from: bundledManifestData())
        var catalog = envelope.modelCatalog
        guard catalog.schema == "inku.model-catalog.v2", catalog.labelDefinitions == ModelCatalogLabels.definitions else {
            throw HostError("model_catalog_schema_invalid")
        }
        catalog.providerDefinitions = envelope.providerDefaults.providers
        return catalog
    }

    /// Decode the shared Server record format, including absent purposes and measurement keys.
    public static func modelSettings(recordData: Data) throws -> ProviderModelSettings {
        try JSONDecoder().decode(GuidanceModel.self, from: recordData).settings
    }

    private func knownProvider(_ id: String, kind: ProviderKind) -> GuidanceProvider? {
        if id == "chatgpt", kind == .chatGPTPlan { return providers[id] }
        guard providerDefinitions.contains(where: { $0.id == id && $0.kind == kind.rawValue }) else { return nil }
        return providers[id]
    }

    public func applyingCatalog(to model: ProviderModelSettings, providerID: String, kind: ProviderKind) -> ProviderModelSettings {
        guard let source = knownProvider(providerID, kind: kind)?.models.first(where: { $0.id == model.id })?.settings else { return model }
        var result = source
        result.label = model.label
        result.purposes = model.purposes.filter { !(source.unsupportedPurposes ?? []).contains($0) }
        result.eol = model.eol
        result.requiresSubscription = model.requiresSubscription
        result.eolDate = model.eol == false ? nil : model.eolDate ?? source.eolDate
        return result
    }

    public func contains(modelID: String, providerID: String, kind: ProviderKind) -> Bool {
        knownProvider(providerID, kind: kind)?.models.contains { $0.id == modelID } == true
    }

    public func registeredModels(for connection: ProviderSettings) -> [ProviderModelInfo] {
        registeredModelSettings(for: connection).filter {
            $0.isSelectable && $0.purposes.contains("llm") && connection.enabledModels?[$0.id] != false
        }.map {
            ProviderModelInfo(id: connection.id + ":" + $0.id, name: $0.label, contextLimit: nil, capabilities: [])
        }
    }

    public func registeredModelSettings(for connection: ProviderSettings) -> [ProviderModelSettings] {
        if let models = connection.models {
            return models.map { applyingCatalog(to: $0, providerID: connection.id, kind: connection.kind) }
        }
        guard let provider = knownProvider(connection.id, kind: connection.kind) else { return [] }
        let byID = Dictionary(provider.models.map { ($0.id, $0.settings) }, uniquingKeysWith: { first, _ in first })
        return provider.defaults.compactMap { byID[$0] }
    }

    /// Naming an old saved reference never registers or enables it for another drawing.
    func savedModelLabel(providerID: String, modelID: String) -> String? {
        providers[providerID]?.models.first { $0.id == modelID }?.settings.label
    }

    public func guidance(for reference: String, providers configured: [ProviderSettings]) -> ModelGuidance? {
        guard let separator = reference.firstIndex(of: ":") else { return nil }
        let providerID = String(reference[..<separator])
        let modelID = String(reference[reference.index(after: separator)...])
        guard !modelID.isEmpty,
              let connection = configured.first(where: { $0.id == providerID }),
              let model = registeredModelSettings(for: connection).first(where: { $0.id == modelID })
                ?? knownProvider(providerID, kind: connection.kind)?.models.first(where: { $0.id == modelID })?.settings else { return nil }
        let speedHidden = providerDefinitions.first(where: { $0.id == providerID && $0.kind == connection.kind.rawValue })?.speedHidden ?? false
        return ModelGuidance(providerID: providerID, model: model, speedHidden: speedHidden)
    }

    private enum CodingKeys: String, CodingKey {
        case schema, version, updated, providers
        case labelDefinitions = "labels"
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
    public let resolvedLabels: [ModelCatalogLabelDefinition]
    public let modelFold: String?
    public let unsupportedPurposes: [String]?
    public let speedLLMSeconds: Double?
    public let speedVisionSeconds: Double?
    public let costUSDLLM: Double?
    public let costUSDVision: Double?
    public let hasEvaluation: Bool

    fileprivate init(providerID: String, model: ProviderModelSettings, speedHidden: Bool) {
        self.providerID = providerID; self.modelID = model.id; self.label = model.label; self.purposes = model.purposes
        self.stage1 = model.recommendationStage1; self.stage2 = model.recommendationStage2
        self.llm = model.recommendationLLM ?? model.recommendationLevel
        self.vision = model.recommendationVision ?? model.recommendationLevel
        self.speedLabel = speedHidden ? nil : model.speedLabel; self.speedClass = speedHidden ? nil : model.speedClass
        self.speedHidden = speedHidden; self.japaneseComment = model.commentJA; self.englishComment = model.commentEN
        self.resolvedLabels = model.resolvedLabels; self.modelFold = model.modelFold
        self.endOfLife = model.resolvedLabels.contains { $0.id == "eol" }; self.endOfLifeDate = model.eolDate
        self.requiresSubscription = model.resolvedLabels.contains { $0.id == "subscription" }
        self.unsupportedPurposes = model.unsupportedPurposes
        self.speedLLMSeconds = model.speedLLMSeconds; self.speedVisionSeconds = model.speedVisionSeconds
        self.costUSDLLM = model.costUSDLLM; self.costUSDVision = model.costUSDVision
        self.hasEvaluation = model.hasCatalogMeasurement
    }

    public var hasStageRecommendations: Bool { stage1 != nil || stage2 != nil }
    public var stage1Level: Int? { Self.level(stage1 ?? llm) }
    public var stage2Level: Int? { Self.level(stage2 ?? llm) }
    // A two-stage selection uses the weaker measured stage; Vision never raises it.
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
    let modelCatalog: ModelGuidanceCatalog
    let providerDefaults: GuidanceProviderDefaults
    enum CodingKeys: String, CodingKey {
        case modelCatalog = "model_catalog", providerDefaults = "provider_defaults"
    }
}

private struct GuidanceProviderDefaults: Decodable { let providers: [GuidanceProviderDefinition] }
private struct GuidanceProviderDefinition: Decodable, Sendable {
    let id: String
    let kind: String
    let speedHidden: Bool
}
private struct GuidanceProvider: Decodable, Sendable {
    let defaults: [String]
    let models: [GuidanceModel]
}

private struct GuidanceModel: Decodable, Sendable {
    let id: String
    let label: String
    let purposes: [String]?
    let labels: [String]
    let recommendationLLM: Int?
    let recommendationVision: Int?
    let recommendationStage1: Int?
    let recommendationStage2: Int?
    let recommendationLevel: Int?
    let speedLabel: String?
    let speedClass: String?
    let commentJA: String?
    let commentEN: String?
    let eolDate: String?
    let unsupportedPurposes: [String]?
    let speedLLMSeconds: Double?
    let speedVisionSeconds: Double?
    let costUSDLLM: Double?
    let costUSDVision: Double?
    let measurementPresent: Bool

    var settings: ProviderModelSettings {
        .init(id: id, label: label, purposes: (purposes ?? ["llm"]).filter { !(unsupportedPurposes ?? []).contains($0) },
              recommendationLevel: recommendationLevel, recommendationLLM: recommendationLLM,
              recommendationVision: recommendationVision, recommendationStage1: recommendationStage1,
              recommendationStage2: recommendationStage2, speedClass: speedClass, speedLabel: speedLabel,
              commentJA: commentJA, commentEN: commentEN, eolDate: eolDate,
              labels: labels, unsupportedPurposes: unsupportedPurposes,
              speedLLMSeconds: speedLLMSeconds, speedVisionSeconds: speedVisionSeconds,
              costUSDLLM: costUSDLLM, costUSDVision: costUSDVision, catalogMeasurementPresent: measurementPresent)
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeIfPresent(String.self, forKey: .id) ?? "catalog-case"
        label = try values.decodeIfPresent(String.self, forKey: .label) ?? id
        purposes = try values.decodeIfPresent([String].self, forKey: .purposes)
        labels = try values.decodeIfPresent([String].self, forKey: .labels) ?? []
        recommendationLLM = try values.decodeIfPresent(Int.self, forKey: .recommendationLLM)
        recommendationVision = try values.decodeIfPresent(Int.self, forKey: .recommendationVision)
        recommendationStage1 = try values.decodeIfPresent(Int.self, forKey: .recommendationStage1)
        recommendationStage2 = try values.decodeIfPresent(Int.self, forKey: .recommendationStage2)
        recommendationLevel = try values.decodeIfPresent(Int.self, forKey: .recommendationLevel)
        speedLabel = try values.decodeIfPresent(String.self, forKey: .speedLabel)
        speedClass = try values.decodeIfPresent(String.self, forKey: .speedClass)
        commentJA = try values.decodeIfPresent(String.self, forKey: .commentJA)
        commentEN = try values.decodeIfPresent(String.self, forKey: .commentEN)
        eolDate = try values.decodeIfPresent(String.self, forKey: .eolDate)
        unsupportedPurposes = try values.decodeIfPresent([String].self, forKey: .unsupportedPurposes)
        speedLLMSeconds = try values.decodeIfPresent(Double.self, forKey: .speedLLMSeconds)
        speedVisionSeconds = try values.decodeIfPresent(Double.self, forKey: .speedVisionSeconds)
        costUSDLLM = try values.decodeIfPresent(Double.self, forKey: .costUSDLLM)
        costUSDVision = try values.decodeIfPresent(Double.self, forKey: .costUSDVision)
        measurementPresent = [CodingKeys.recommendationLLM, .recommendationVision, .recommendationStage1,
                              .recommendationStage2, .recommendationLevel, .speedLabel, .speedClass,
                              .commentJA, .commentEN, .unsupportedPurposes, .speedLLMSeconds, .speedVisionSeconds,
                              .costUSDLLM, .costUSDVision].contains { values.contains($0) }
    }

    private enum CodingKeys: String, CodingKey {
        case id, label, purposes, labels
        case recommendationLLM = "recommendation_llm", recommendationVision = "recommendation_vision"
        case recommendationStage1 = "recommendation_stage1", recommendationStage2 = "recommendation_stage2"
        case recommendationLevel = "recommendation_level", speedLabel = "speed_label", speedClass = "speed_class"
        case commentJA = "comment_ja", commentEN = "comment_en", eolDate = "eol_date"
        case unsupportedPurposes = "unsupported_purposes", speedLLMSeconds = "speed_llm_seconds", speedVisionSeconds = "speed_vision_seconds"
        case costUSDLLM = "cost_usd_llm", costUSDVision = "cost_usd_vision"
    }
}
