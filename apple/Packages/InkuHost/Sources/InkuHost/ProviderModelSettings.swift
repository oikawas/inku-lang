import Foundation

/// A service's saved model catalog, using the provider's unmodified model ID.
public struct ProviderModelSettings: Codable, Sendable, Equatable, Identifiable {
    public var id: String
    public var label: String
    public var purposes: [String]
    public var recommendationLevel: Int?
    public var recommendationLLM: Int?
    public var recommendationVision: Int?
    public var recommendationStage1: Int?
    public var recommendationStage2: Int?
    public var speedClass: String?
    public var speedLabel: String?
    public var commentJA: String?
    public var commentEN: String?
    public var eol: Bool?
    public var eolDate: String?
    public var requiresSubscription: Bool?
    public var labels: [String]
    public var unsupportedPurposes: [String]?
    /// Purposes chosen knowing the measurement found no response (the author, 2026-10-26).
    public var allowedUnsupportedPurposes: [String]?
    public var speedLLMSeconds: Double?
    public var speedVisionSeconds: Double?
    public var costUSDLLM: Double?
    public var costUSDVision: Double?
    public var catalogMeasurementPresent: Bool?

    public init(id: String, label: String? = nil, purposes: [String] = ["llm"],
                recommendationLevel: Int? = nil, recommendationLLM: Int? = nil,
                recommendationVision: Int? = nil, recommendationStage1: Int? = nil,
                recommendationStage2: Int? = nil, speedClass: String? = nil,
                speedLabel: String? = nil, commentJA: String? = nil, commentEN: String? = nil,
                eol: Bool? = nil, eolDate: String? = nil, requiresSubscription: Bool? = nil,
                labels: [String] = [], unsupportedPurposes: [String]? = nil,
                allowedUnsupportedPurposes: [String]? = nil,
                speedLLMSeconds: Double? = nil, speedVisionSeconds: Double? = nil,
                costUSDLLM: Double? = nil, costUSDVision: Double? = nil,
                catalogMeasurementPresent: Bool? = nil) {
        self.id = id; self.label = label ?? id; self.purposes = purposes
        self.recommendationLevel = recommendationLevel; self.recommendationLLM = recommendationLLM
        self.recommendationVision = recommendationVision; self.recommendationStage1 = recommendationStage1
        self.recommendationStage2 = recommendationStage2; self.speedClass = speedClass
        self.speedLabel = speedLabel; self.commentJA = commentJA; self.commentEN = commentEN
        self.eol = eol; self.eolDate = eolDate; self.requiresSubscription = requiresSubscription
        self.labels = labels; self.unsupportedPurposes = unsupportedPurposes
        self.allowedUnsupportedPurposes = allowedUnsupportedPurposes
        self.speedLLMSeconds = speedLLMSeconds; self.speedVisionSeconds = speedVisionSeconds
        self.costUSDLLM = costUSDLLM; self.costUSDVision = costUSDVision
        self.catalogMeasurementPresent = catalogMeasurementPresent
    }

    public var resolvedLabels: [ModelCatalogLabelDefinition] { ModelCatalogLabels.resolve(for: self) }
    public var modelFold: String? { resolvedLabels.last?.id }
    public var isSelectable: Bool { resolvedLabels.allSatisfy(\.publishable) }
    /// A model offered for no purpose is never published, nor turned on by "select all".
    public var isPublishable: Bool { isSelectable && !purposes.isEmpty }

    /// Measured without a response for this purpose: it can be chosen, but is not recommended.
    public func isNotRecommended(for purpose: String) -> Bool { (unsupportedPurposes ?? []).contains(purpose) }

    /// Offered for the purpose: a purpose measured without a response only when it was chosen for it.
    public func offers(_ purpose: String) -> Bool {
        purposes.contains(purpose) && (!isNotRecommended(for: purpose) || (allowedUnsupportedPurposes ?? []).contains(purpose))
    }
    public var hasCatalogMeasurement: Bool {
        catalogMeasurementPresent == true
            || [recommendationLevel, recommendationLLM, recommendationVision, recommendationStage1, recommendationStage2].contains { $0 != nil }
            || speedClass != nil || speedLabel != nil || commentJA != nil || commentEN != nil
            || speedLLMSeconds != nil || speedVisionSeconds != nil || costUSDLLM != nil || costUSDVision != nil
            || unsupportedPurposes != nil
    }

    public func validate() throws {
        guard !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              Set(purposes).count == purposes.count,
              purposes.allSatisfy({ $0 == "llm" || $0 == "vision" }),
              [recommendationLevel, recommendationLLM, recommendationVision,
               recommendationStage1, recommendationStage2].compactMap({ $0 }).allSatisfy({ (1...5).contains($0) })
        else { throw HostError("provider_model_settings_invalid") }
    }

    private enum CodingKeys: String, CodingKey {
        case id, label, purposes, recommendationLevel, recommendationLLM, recommendationVision
        case recommendationStage1, recommendationStage2, speedClass, speedLabel, commentJA, commentEN
        case eol, eolDate, requiresSubscription
        case labels, unsupportedPurposes, allowedUnsupportedPurposes, speedLLMSeconds, speedVisionSeconds, costUSDLLM, costUSDVision
        case catalogMeasurementPresent
    }

    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(String.self, forKey: .id)
        label = try values.decodeIfPresent(String.self, forKey: .label) ?? id
        purposes = try values.decodeIfPresent([String].self, forKey: .purposes) ?? ["llm"]
        recommendationLevel = try values.decodeIfPresent(Int.self, forKey: .recommendationLevel)
        recommendationLLM = try values.decodeIfPresent(Int.self, forKey: .recommendationLLM)
        recommendationVision = try values.decodeIfPresent(Int.self, forKey: .recommendationVision)
        recommendationStage1 = try values.decodeIfPresent(Int.self, forKey: .recommendationStage1)
        recommendationStage2 = try values.decodeIfPresent(Int.self, forKey: .recommendationStage2)
        speedClass = try values.decodeIfPresent(String.self, forKey: .speedClass)
        speedLabel = try values.decodeIfPresent(String.self, forKey: .speedLabel)
        commentJA = try values.decodeIfPresent(String.self, forKey: .commentJA)
        commentEN = try values.decodeIfPresent(String.self, forKey: .commentEN)
        eol = try values.decodeIfPresent(Bool.self, forKey: .eol)
        eolDate = try values.decodeIfPresent(String.self, forKey: .eolDate)
        requiresSubscription = try values.decodeIfPresent(Bool.self, forKey: .requiresSubscription)
        labels = try values.decodeIfPresent([String].self, forKey: .labels) ?? []
        unsupportedPurposes = try values.decodeIfPresent([String].self, forKey: .unsupportedPurposes)
        allowedUnsupportedPurposes = try values.decodeIfPresent([String].self, forKey: .allowedUnsupportedPurposes)
        speedLLMSeconds = try values.decodeIfPresent(Double.self, forKey: .speedLLMSeconds)
        speedVisionSeconds = try values.decodeIfPresent(Double.self, forKey: .speedVisionSeconds)
        costUSDLLM = try values.decodeIfPresent(Double.self, forKey: .costUSDLLM)
        costUSDVision = try values.decodeIfPresent(Double.self, forKey: .costUSDVision)
        catalogMeasurementPresent = try values.decodeIfPresent(Bool.self, forKey: .catalogMeasurementPresent)
    }
}
