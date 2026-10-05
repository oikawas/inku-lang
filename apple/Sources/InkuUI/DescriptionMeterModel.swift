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
        DescriptionLabels.pipelineDescription(text)
    }

    /// Web `japaneseForm`: by the phrases when they are a form, otherwise by the total.
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
            guard gaps.allSatisfy({ $0 <= 2 }), abs(phrases.reduce(0, +) - target) <= 2 else { continue }
            let distance = gaps.reduce(0, +)
            if best == nil || distance < best!.1 { best = (NamedVerseForm(name: name, length: target), distance) }
        }
        return best?.0 ?? japaneseForm(total: total)
    }

    /// Web `formByTotal`: the form whose length the total is within two sounds of, nearest first, the shorter on a tie.
    public static func japaneseForm(total: Int) -> NamedVerseForm? {
        var totals = [("俳句/川柳",17), ("片歌",19), ("都々逸",26), ("短歌",31), ("旋頭歌・仏足石歌",38)]
        if total + 2 >= 43 { for pairs in 3...((total + 2 - 7) / 12) { totals.append(("長歌", 12 * pairs + 7)) } }
        var best: (NamedVerseForm, Int)?
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

    /// Web `englishSyllables`: vowel groups less a silent final e, the page's estimate until the dictionary answers.
    public static func englishSyllables(_ text: String) -> Int {
        let word = try! NSRegularExpression(pattern: "[a-z]+(?:'[a-z]+)*")
        let vowels = try! NSRegularExpression(pattern: "[aeiouy]+")
        let source = text.lowercased()
        var total = 0
        for match in word.matches(in: source, range: NSRange(location: 0, length: (source as NSString).length)) {
            var value = (source as NSString).substring(with: match.range).replacingOccurrences(of: "'", with: "")
            if (value as NSString).length > 2, value.hasSuffix("e"), value.range(of: "[^aeiouy]le$", options: .regularExpression) == nil {
                value.removeLast()
            }
            total += max(1, vowels.numberOfMatches(in: value, range: NSRange(location: 0, length: (value as NSString).length)))
        }
        return total
    }

    /// Web `METER_TEXT_LIMIT`, counted in UTF-16 as `text.length`: a longer description is judged on the page.
    public static let dictionaryTextLimit = 4000

    /// Web `describeLength`: what the meter says, from the dictionary's last answers when they have come.
    /// The Japanese answer is kept while the author types; the English one only while the line count still matches.
    public static func describe(_ text: String, uiLanguage: String, japaneseEnabled: Bool, englishEnabled: Bool,
                                mora: DescriptionMoraAnswer? = nil, syllableLines: [Int]? = nil) -> DescriptionMeterReading {
        let source = pipelineDescription(text).trimmingCharacters(in: .whitespacesAndNewlines)
        if !readsAsJapanese(text, uiLanguage: uiLanguage) {
            let lines = source.components(separatedBy: "\n").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
            guard englishEnabled else { return DescriptionMeterReading(unit: .lines, count: lines.count, form: nil) }
            let syllables = syllableLines?.count == lines.count ? syllableLines! : lines.map(englishSyllables)
            return DescriptionMeterReading(unit: .lines, count: lines.count, form: englishForm(lines: syllables))
        }
        let characters = source.unicodeScalars.filter { !CharacterSet.whitespacesAndNewlines.contains($0) }.count
        guard japaneseEnabled else { return DescriptionMeterReading(unit: .characters, count: characters, form: nil) }
        if let mora {
            return DescriptionMeterReading(unit: .mora(approximate: !mora.unread.isEmpty), count: mora.total,
                                           form: japaneseForm(total: mora.total, phrases: mora.phrases))
        }
        return DescriptionMeterReading(unit: .characters, count: characters, form: japaneseForm(total: characters))
    }
}

/// The dictionary's count of a Japanese description (Web `MoraCount`).
public struct DescriptionMoraAnswer: Sendable, Equatable {
    public let total: Int
    public let phrases: [Int]
    public let unread: [String]
    public init(total: Int, phrases: [Int], unread: [String]) { self.total = total; self.phrases = phrases; self.unread = unread }
}

/// Web `DescriptionMeter` and its label (ja.ts:214-218, en.ts:214-217).
public struct DescriptionMeterReading: Sendable, Equatable {
    public enum Unit: Sendable, Equatable { case mora(approximate: Bool), characters, lines }
    public let unit: Unit
    public let count: Int
    public let form: NamedVerseForm?

    public func label(language: String) -> String {
        let english = language == "en"
        let name = form.map { english ? Self.englishNames[$0.name] ?? $0.name : $0.name }
        switch unit {
        case .lines:
            guard let form, let name else { return english ? "Lines \(count)" : "行数 \(count)" }
            return english ? "Lines \(count)/\(form.length) (\(name))" : "行数 \(count)/\(form.length)（\(name)）"
        case .characters:
            guard let form, let name else { return english ? "Characters \(count)" : "文字数 \(count)" }
            return english ? "Characters \(count)/\(form.length) (\(name))" : "文字数 \(count)/\(form.length)（\(name)）"
        case .mora(let approximate):
            let about = approximate ? (english ? "about " : "約") : ""
            let tail = form.map { english ? "/\($0.length) (\(name ?? $0.name))" : "/\($0.length)（\(name ?? $0.name)）" } ?? ""
            return (english ? "Sounds " : "音数 ") + about + "\(count)" + tail
        }
    }

    /// Web en.ts `verseFormName` / `englishFormName`, keyed by the Japanese names the forms carry here.
    private static let englishNames: [String: String] = [
        "俳句/川柳": "haiku or senryū", "片歌": "katauta", "都々逸": "dodoitsu", "短歌": "tanka",
        "旋頭歌": "sedōka", "仏足石歌": "bussokuseki-ka", "旋頭歌・仏足石歌": "sedōka or bussokuseki-ka", "長歌": "chōka",
        "カプレット": "couplet", "ハイク": "haiku", "ターセット": "tercet", "クワトレイン": "quatrain",
        "シンクェイン": "cinquain", "ソネット": "sonnet", "ヴィラネル": "villanelle", "セスティーナ": "sestina",
    ]
}
