import Foundation
import InkuHost
import Observation

public struct NamedVerseForm: Sendable, Equatable {
    public let name: String
    public let length: Int
}

@MainActor @Observable
public final class DescriptionMeterModel {
    public var japaneseEnabled = true { didSet { save() } }
    public var englishEnabled = true { didSet { save() } }
    public private(set) var settingsError: String?
    @ObservationIgnored private var fileURL: URL?
    public init() {}

    public func connect(directory: URL?) {
        guard let directory else { return }
        let file = directory.appendingPathComponent("description-meter.json")
        do {
            if FileManager.default.fileExists(atPath: file.path) {
                let data = try ExactJSON(data: Data(contentsOf: file))
                japaneseEnabled = data["japanese"].bool ?? true
                englishEnabled = data["english"].bool ?? true
            }
            fileURL = file; settingsError = nil
        } catch { settingsError = "形式判定の設定を読み込めませんでした: " + error.localizedDescription }
    }

    private func save() {
        guard let fileURL else { return }
        do {
            let data = try JSONSerialization.data(withJSONObject: ["japanese": japaneseEnabled, "english": englishEnabled], options: [.sortedKeys])
            try data.write(to: fileURL, options: .atomic); settingsError = nil
        } catch { settingsError = "形式判定の設定を保存できませんでした: " + error.localizedDescription }
    }

    /// Exact Web language discriminator; a plain ASCII description is English.
    public static func readsAsJapanese(_ text: String, uiLanguage: String) -> Bool {
        let source = pipelineDescription(text).trimmingCharacters(in: .whitespacesAndNewlines)
        if source.range(of: "[぀-ヿ㐀-鿿]", options: .regularExpression) != nil { return true }
        let ascii = !source.isEmpty && source.unicodeScalars.allSatisfy { $0.value <= 127 || CharacterSet.whitespacesAndNewlines.contains($0) }
        return !ascii && !(source.isEmpty && uiLanguage == "en")
    }

    public static func pipelineDescription(_ text: String) -> String {
        let number = try! NSRegularExpression(pattern: "(?m)^[ \\t]*[0-9０-９]+[.．、)）:：　][ \\t　]*")
        let comment = try! NSRegularExpression(pattern: "\\[[^\\[\\]\\n]*\\]|［[^［］\\n]*］")
        let source = text as NSString
        let range = NSRange(location: 0, length: source.length)
        let spans = (number.matches(in: text, range: range) + comment.matches(in: text, range: range)).map(\.range).sorted { $0.location < $1.location }
        guard !spans.isEmpty else { return text }
        var result = text
        for span in spans.reversed() { result = (result as NSString).replacingCharacters(in: span, with: "") }
        let spaces = try! NSRegularExpression(pattern: "[ \\t　]{2,}")
        return result.components(separatedBy: "\n").map { line in
            spaces.stringByReplacingMatches(in: line, range: NSRange(line.startIndex..., in: line), withTemplate: " ")
                .trimmingCharacters(in: CharacterSet(charactersIn: " \t　"))
        }.joined(separator: "\n")
    }

    public static func japaneseForm(total: Int, phrases: [Int]) -> NamedVerseForm? {
        var patterns: [(String, [Int])] = [
            ("俳句/川柳", [5,7,5]), ("片歌", [5,7,7]), ("都々逸", [7,7,7,5]),
            ("短歌", [5,7,5,7,7]), ("旋頭歌", [5,7,7,5,7,7]), ("仏足石歌", [5,7,5,7,7,7]),
        ]
        if phrases.count >= 7 && phrases.count % 2 == 1 {
            patterns.append(("長歌", Array(repeating: [5,7], count: (phrases.count - 1) / 2).flatMap { $0 } + [7]))
        }
        var best: (NamedVerseForm, Int)?
        for (name, expected) in patterns where expected.count == phrases.count && phrases.count >= 2 {
            let gaps = zip(phrases, expected).map { abs($0 - $1) }
            let target = expected.reduce(0, +)
            guard gaps.allSatisfy({ $0 <= 2 }), abs(total - target) <= 2 else { continue }
            let distance = gaps.reduce(0, +)
            if best == nil || distance < best!.1 { best = (NamedVerseForm(name: name, length: target), distance) }
        }
        if let best { return best.0 }
        var totals = [("俳句/川柳",17), ("片歌",19), ("都々逸",26), ("短歌",31), ("旋頭歌・仏足石歌",38)]
        if total + 2 >= 43 { for pairs in 3...((total + 2 - 7) / 12) { totals.append(("長歌", 12 * pairs + 7)) } }
        for (name, target) in totals where abs(total - target) <= 2 {
            let distance = abs(total - target)
            if best == nil || distance < best!.1 { best = (NamedVerseForm(name: name, length: target), distance) }
        }
        return best?.0
    }

    public static func englishForm(lines: [Int]) -> NamedVerseForm? {
        switch lines.count {
        case 2: return NamedVerseForm(name: "カプレット", length: 2)
        case 3: return NamedVerseForm(name: lines.reduce(0, +) <= 17 ? "ハイク" : "ターセット", length: 3)
        case 4: return NamedVerseForm(name: "クワトレイン", length: 4)
        case 5: return zip(lines, [2,4,6,8,2]).allSatisfy { abs($0 - $1) <= 1 } ? NamedVerseForm(name: "シンクェイン", length: 5) : nil
        default: return [("ソネット",14), ("ヴィラネル",19), ("セスティーナ",39)].first { abs(lines.count - $0.1) <= 1 }.map { NamedVerseForm(name: $0.0, length: $0.1) }
        }
    }
}
