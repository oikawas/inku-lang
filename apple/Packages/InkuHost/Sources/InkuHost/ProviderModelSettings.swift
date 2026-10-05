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

    public init(id: String, label: String? = nil, purposes: [String] = ["llm"],
                recommendationLevel: Int? = nil, recommendationLLM: Int? = nil,
                recommendationVision: Int? = nil, recommendationStage1: Int? = nil,
                recommendationStage2: Int? = nil, speedClass: String? = nil,
                speedLabel: String? = nil, commentJA: String? = nil, commentEN: String? = nil,
                eol: Bool? = nil, eolDate: String? = nil, requiresSubscription: Bool? = nil) {
        self.id = id; self.label = label ?? id; self.purposes = purposes
        self.recommendationLevel = recommendationLevel; self.recommendationLLM = recommendationLLM
        self.recommendationVision = recommendationVision; self.recommendationStage1 = recommendationStage1
        self.recommendationStage2 = recommendationStage2; self.speedClass = speedClass
        self.speedLabel = speedLabel; self.commentJA = commentJA; self.commentEN = commentEN
        self.eol = eol; self.eolDate = eolDate; self.requiresSubscription = requiresSubscription
    }

    public var isSelectable: Bool { eol != true && requiresSubscription != true }

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
    }
}
