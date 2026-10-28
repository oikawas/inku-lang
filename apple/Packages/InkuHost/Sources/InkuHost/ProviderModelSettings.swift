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
    public var modelFold: String? { SharedModelCatalog.decision(for: self).fold }
    public var isSelectable: Bool { !SharedModelCatalog.decision(for: self).selection.unselectable }
    /// A model offered for no purpose is never published, nor turned on by "select all".
    public var isPublishable: Bool { isSelectable && !purposes.isEmpty }

    /// Measured without a response for this purpose: it can be chosen, but is not recommended.
    public func isNotRecommended(for purpose: String) -> Bool { SharedModelCatalog.decision(for: self).selection.unsupported[purpose] ?? false }

    /// Offered for the purpose: a purpose measured without a response only when it was chosen for it.
    public func offers(_ purpose: String) -> Bool {
        purposes.contains(purpose) && (!isNotRecommended(for: purpose) || (allowedUnsupportedPurposes ?? []).contains(purpose))
    }
    public var hasCatalogMeasurement: Bool { !SharedModelCatalog.measurementKeys.isDisjoint(with: coreCatalogRecord.keys) }

    /// Translate stored labels and local observations into the Server-shaped core input.
    public var coreCatalogRecord: [String: Any] {
        var record: [String: Any] = ["id": id, "label": label, "purposes": purposes]
        var stored = Set(labels)
        if let requiresSubscription { if requiresSubscription { stored.insert("subscription") } else { stored.remove("subscription") } }
        if let eol { if eol { stored.insert("eol") } else { stored.remove("eol") } }
        for (label, key) in [("legacy", "legacy"), ("subscription", "requires_subscription"),
                             ("not_supported", "not_supported"), ("eol", "eol")] where stored.contains(label) { record[key] = true }
        let measurements: [(String, Any?)] = [
            ("recommendation_level", recommendationLevel), ("recommendation_llm", recommendationLLM),
            ("recommendation_vision", recommendationVision), ("recommendation_stage1", recommendationStage1),
            ("recommendation_stage2", recommendationStage2), ("speed_class", speedClass), ("speed_label", speedLabel),
            ("comment_ja", commentJA), ("comment_en", commentEN), ("unsupported_purposes", unsupportedPurposes),
            ("speed_llm_seconds", speedLLMSeconds), ("speed_vision_seconds", speedVisionSeconds),
            ("cost_usd_llm", costUSDLLM), ("cost_usd_vision", costUSDVision)]
        for (key, value) in measurements { if let value { record[key] = value } }
        if let allowedUnsupportedPurposes { record["allowed_unsupported_purposes"] = allowedUnsupportedPurposes }
        if let eolDate { record["eol_date"] = eolDate }
        if let eol { record["eol"] = eol }
        if let requiresSubscription { record["requires_subscription"] = requiresSubscription }
        if catalogMeasurementPresent == true && measurements.allSatisfy({ $0.1 == nil }) { record["recommendation_level"] = NSNull() }
        return record
    }

    public func catalogLevel(purpose: String, stage: String = "none") -> Int? {
        guard let value = SharedModelCatalog.decision(for: self).selection.levels[purpose]?[stage], value > 0 else { return nil }
        return Int(value)
    }
    public func catalogSortKey(purpose: String = "none", stage: String = "none") -> String {
        guard let key = SharedModelCatalog.decision(for: self).selection.sortKeys[purpose]?[stage] else {
            preconditionFailure("Core model catalog sort key unavailable")
        }
        return key
    }

    public func validate() throws {
        let response = try ProviderCoreSettings.call("normalize_models", ["models": [coreCatalogRecord]])
        guard !(response["models"] as? [[String: Any]] ?? []).isEmpty else { throw HostError("provider_model_settings_invalid") }
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
