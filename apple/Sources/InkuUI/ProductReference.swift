import Foundation
import InkuHost

public struct CanvasDisplayMetadata: Decodable, Sendable {
    public let label: String
    public let category: String
    public let intentJa: String
    public let intentEn: String
}

public struct SaijikiPreview: Decodable, Sendable {
    public let svg: String
    public let effectJa: String
    public let effectEn: String
    public let exampleJa: String
    public let exampleEn: String

    public func effect(language: String) -> String { language == "ja" ? effectJa : effectEn }
    public func example(language: String) -> String { language == "ja" ? exampleJa : exampleEn }
}

public struct ReferenceVocabulary: Decodable, Sendable {
    public let term: String
    public let meaning: String
}

public struct ProductReferenceCopy: Decodable, Sendable {
    public let texts: [String: String]
    public let vocabulary: [ReferenceVocabulary]
    public let limitLabels: [String: String]
    public let limitHints: [String: String]
    public let limitGroups: [String: String]
    public let limitGroupSummaries: [String: String]
    public let limitGroupTooltips: [String: String]
    public let limitUnits: [String: String]
    public func text(_ key: String) -> String { texts[key] ?? key }
}

public struct ProductReference: Decodable, Sendable {
    public let schema: String
    public let version: String
    public let build: String
    public let buildDate: String
    public let versions: [String: String]
    public let canvasMetadata: [String: CanvasDisplayMetadata]
    public let copy: [String: ProductReferenceCopy]
    public let saijikiPreviews: [String: SaijikiPreview]

    public func localized(language: String) -> ProductReferenceCopy? { copy[language] ?? copy["ja"] }
}

public struct DrawingLimitGroup: Decodable, Sendable {
    public let id: String
    public let fields: [String]
}

public struct DrawingLimitRule: Decodable, Sendable {
    public let target: String
    public let ceiling: String
}

/// Host setting selections from the same versioned rules the Server uses.
public struct DrawingLimitDefinition: Decodable, Sendable {
    public let defaults: [String: UInt32]
    public let absoluteMaximum: UInt32
    public let groups: [DrawingLimitGroup]
    public let normalization: [DrawingLimitRule]
    public let budgetMapping: [String: String]
    public let bytesPerMark: [String: UInt32]

    public func normalized(_ selected: [String: UInt32]?) -> [String: UInt32] {
        var result = defaults
        for (key, value) in selected ?? [:] where defaults[key] != nil {
            result[key] = min(absoluteMaximum, max(1, value))
        }
        for rule in normalization {
            if let value = result[rule.target], let ceiling = result[rule.ceiling] {
                result[rule.target] = min(value, ceiling)
            }
        }
        return result
    }

    public func parsedDraft(_ draft: [String: String]) throws -> [String: UInt32] {
        var parsed: [String: UInt32] = [:]
        for key in defaults.keys {
            let text = (draft[key] ?? "").replacingOccurrences(of: ",", with: "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty, let value = Int64(text) else { throw HostError("invalid_drawing_limit_value") }
            parsed[key] = UInt32(min(Int64(absoluteMaximum), max(1, value)))
        }
        return normalized(parsed)
    }
}
