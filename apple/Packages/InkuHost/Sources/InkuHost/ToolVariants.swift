import Foundation
import InkuCore

public enum ToolChangeMode: String, CaseIterable, Sendable {
    case uniform, perSentence = "per_sentence"
}

public struct ToolChange: Sendable, Equatable {
    public let index: Int
    public let from: String
    public let to: String
}

public struct TouchTool: Sendable {
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

enum ToolVariants {
    static func read(configuration: ExactJSON, source: String, tools: [String: String] = [:]) throws -> ExactJSON {
        let request: ExactJSON = .object(["config": configuration, "source": .string(source),
            "tools": .object(tools.mapValues(ExactJSON.string))])
        let result = try ExactJSON(data: InkuCore.retouch(request.data))
        guard result["schema"].string == "inku.touch-change.v1" else { throw HostError("touch_change_unavailable") }
        return result
    }

    static func ownerIndex(_ instruction: ExactJSON) -> Int? {
        let owner = instruction["arrangement"]["resolved"]["owner"]
        guard owner["kind"].string == "source_instruction", let value = owner["instruction_index"].number else { return nil }
        return Int(value)
    }

    /// Server tool_variants.drawn_tools: the first drawn instruction of each changeable source sentence.
    static func drawnTools(score: ExactJSON, sentences: [Int], known: Set<String>) -> [Int: String] {
        var drawn: [Int: String] = [:]
        let included = Set(sentences)
        for instruction in score["instructions"].array ?? [] {
            guard let index = ownerIndex(instruction), included.contains(index), drawn[index] == nil else { continue }
            let weight = instruction["weight"].string ?? "pen"
            drawn[index] = known.contains(weight) ? weight : "pen"
        }
        return Dictionary(uniqueKeysWithValues: sentences.map { ($0, drawn[$0] ?? "pen") })
    }

    static func options(drawn: [Int: String], mode: ToolChangeMode, tools: [String]) -> [[String: String]] {
        let sentences = drawn.keys.sorted()
        guard !sentences.isEmpty else { return [] }
        if mode == .uniform {
            let offered = tools.filter { tool in sentences.contains { drawn[$0] != tool } }
            return offered.shuffled().prefix(4).map { tool in
                Dictionary(uniqueKeysWithValues: sentences.map { (String($0), tool) })
            }
        }
        var options: [[String: String]] = []
        for _ in 0..<32 {
            var option: [String: String] = [:]
            for index in sentences {
                guard let tool = tools.filter({ $0 != drawn[index] }).randomElement() else { return options }
                option[String(index)] = tool
            }
            if !options.contains(option) { options.append(option) }
            if options.count == 4 { break }
        }
        return options
    }

    static func scoreWithTools(_ score: ExactJSON, tools: [String: String]) -> ExactJSON {
        var changed = score
        changed["instructions"] = .array((score["instructions"].array ?? []).map { instruction in
            var instruction = instruction
            if let index = ownerIndex(instruction), let tool = tools[String(index)] { instruction["weight"] = .string(tool) }
            return instruction
        })
        return changed
    }
}
