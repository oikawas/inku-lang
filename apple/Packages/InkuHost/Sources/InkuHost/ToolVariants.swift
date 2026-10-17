import Foundation

public enum ToolChangeMode: String, CaseIterable, Sendable {
    case uniform, perSentence = "per_sentence"
}

public struct ToolChange: Decodable, Sendable, Equatable {
    public let index: Int
    public let from: String
    public let to: String
}

public struct TouchTool: Decodable, Sendable {
    public let value: String
    public let ja: String
    public let en: String
    public func name(language: String) -> String { language == "ja" ? ja : en }
}

/// A host-owned plan: no mutable Score, source or parent can be supplied by a view.
public struct ToolVariantPlan: Sendable {
    public let mode: ToolChangeMode
    public let tools: [String: String]
    public let changes: [ToolChange]
    public let source: String
    public let labels: [TouchTool]
    let replay: SavedScoreReplayPlan

    public func toolName(_ value: String, language: String) -> String {
        labels.first(where: { $0.value == value })?.name(language: language) ?? value
    }
}
