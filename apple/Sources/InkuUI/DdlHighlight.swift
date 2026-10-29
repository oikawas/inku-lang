import Foundation
import InkuHost
#if os(macOS)
import AppKit
#endif

/// Web `highlight.ts` token classes: a saijiki word by its category, an emotion word, or a plugin name.
enum DdlTokenClass: String, Sendable, Equatable {
    case shape, touch, line, color, motion, place, action, angle, ratio, plugin, word, emotion

    /// Web `saijikiCategoryClassByKey`.
    init(categoryKey key: String) {
        if key.hasPrefix("plugin-") { self = .plugin; return }
        switch key {
        case "katachi": self = .shape
        case "tezawari": self = .touch
        case "tsuranari": self = .line
        case "iro": self = .color
        case "yuragi": self = .motion
        case "basho": self = .place
        case "ugoki": self = .action
        case "katamuki": self = .angle
        case "wariai": self = .ratio
        default: self = .word
        }
    }
}

struct PluginCall: Sendable, Equatable {
    let range: NSRange
    let text: String
    let status: String
    let qualifiedName: String?
    let writtenJapanese: String?
    let writtenEnglish: String?
    let noteJapanese: String?
    let noteEnglish: String?
    let exampleJapanese: String?
    let exampleEnglish: String?
    let suggestion: String?
    let candidates: [String]

    init?(_ value: ExactJSON, source: String, entries: [ExactJSON] = []) {
        guard let start = value["start_utf16"].number.flatMap(Int.init),
              let end = value["end_utf16"].number.flatMap(Int.init),
              start >= 0, end > start, end <= (source as NSString).length,
              let text = value["text"].string, let status = value["status"].string,
              (source as NSString).substring(with: NSRange(location: start, length: end - start)) == text else { return nil }
        range = NSRange(location: start, length: end - start)
        self.text = text
        self.status = status
        let id = value["qualified_name"].string
        qualifiedName = id
        let entry = entries.first { $0["qualified_name"].string == id }
        writtenJapanese = entry?["written_ja"].string
        writtenEnglish = entry?["written_en"].string
        noteJapanese = entry?["note_ja"].string
        noteEnglish = entry?["note_en"].string
        exampleJapanese = entry?["example_ja"].string
        exampleEnglish = entry?["example_en"].string
        suggestion = value["suggestion"].string
        candidates = (value["candidates"].array ?? []).compactMap(\.string)
    }
}

/// Web `annotate` for a DDL: a title line (DDL 27) whole, then plugin references, then saijiki words longest
/// first (an ASCII word only on word boundaries), then emotion words. Returns the painted ranges; plain text
/// is left alone.
struct DdlHighlighter: Sendable {
    private struct Entry: Sendable { let word: String; let lower: String; let length: Int; let token: DdlTokenClass; let ascii: Bool }
    private let buckets: [Character: [Entry]]
    private let calls: [PluginCall]
    private static let emotionWords = ["美しい", "美しく", "激しい", "激しく", "静かな", "静かに", "素敵", "きれい", "やさしい",
                                       "切ない", "哀しい", "儚い", "神秘的", "幻想的", "寂しい", "爽やか"]
        .sorted { $0.count > $1.count }

    init(saijiki: [SaijikiCategory], calls: [PluginCall] = []) {
        var entries: [Entry] = []
        for category in saijiki {
            let token = DdlTokenClass(categoryKey: category.id)
            for word in category.words {
                for surface in [word.japanese, word.english].compactMap({ $0 }) where !surface.isEmpty {
                    let ascii = surface.unicodeScalars.allSatisfy { (0x20...0x7e).contains($0.value) }
                    entries.append(Entry(word: surface, lower: surface.lowercased(), length: (surface as NSString).length,
                                         token: token, ascii: ascii))
                }
            }
        }
        entries.sort { $0.length > $1.length }
        var buckets: [Character: [Entry]] = [:]
        for entry in entries {
            guard let first = (entry.ascii ? entry.lower : entry.word).first else { continue }
            buckets[first, default: []].append(entry)
        }
        self.buckets = buckets
        self.calls = calls
    }

    func marks(_ text: String) -> [InkuEditorMark] {
        let source = text as NSString
        let references = Dictionary(calls.map { ($0.range.location, $0) }, uniquingKeysWith: { first, _ in first })
        let titles = Dictionary(DdlTitles.lineRanges(text).map { ($0.location, $0) }, uniquingKeysWith: { first, _ in first })
        var marks: [InkuEditorMark] = []
        var index = 0
        while index < source.length {
            // A title draws nothing, so no word in it is coloured.
            if let title = titles[index], title.length > 0 {
                marks.append(InkuEditorMark(range: title, style: .title))
                index = NSMaxRange(title)
                continue
            }
            if let reference = references[index] {
                marks.append(InkuEditorMark(range: reference.range, style: reference.status == "resolved" ? .token(.plugin) : .unknownName))
                index = NSMaxRange(reference.range)
                continue
            }
            let character = source.substring(with: source.rangeOfComposedCharacterSequence(at: index))
            var matched = false
            for entry in character.lowercased().first.flatMap({ buckets[$0] }) ?? [] where matches(source, at: index, entry) {
                marks.append(InkuEditorMark(range: NSRange(location: index, length: entry.length), style: .token(entry.token)))
                index += entry.length
                matched = true
                break
            }
            if matched { continue }
            if let emotion = Self.emotionWords.first(where: { source.length - index >= ($0 as NSString).length
                && source.substring(with: NSRange(location: index, length: ($0 as NSString).length)) == $0 }) {
                let length = (emotion as NSString).length
                marks.append(InkuEditorMark(range: NSRange(location: index, length: length), style: .token(.emotion)))
                index += length
                continue
            }
            index += 1
        }
        return marks
    }

    private func matches(_ source: NSString, at index: Int, _ entry: Entry) -> Bool {
        guard source.length - index >= entry.length else { return false }
        let candidate = source.substring(with: NSRange(location: index, length: entry.length))
        guard entry.ascii else { return candidate == entry.word }
        guard candidate.lowercased() == entry.lower else { return false }
        func wordCharacter(_ offset: Int) -> Bool {
            guard offset >= 0, offset < source.length, let scalar = UnicodeScalar(source.character(at: offset)) else { return false }
            return CharacterSet.alphanumerics.contains(scalar) && scalar.isASCII || scalar == "-"
        }
        return !wordCharacter(index - 1) && !wordCharacter(index + entry.length)
    }
}

/// InkuAppCheck `--ddl-title-only`: the highlighter's marks as plain values, with no plugin words.
public enum DdlHighlightProbe {
    public static func marks(_ text: String, saijiki: [SaijikiCategory]) -> [(range: NSRange, style: String)] {
        DdlHighlighter(saijiki: saijiki).marks(text).map { mark in
            let style = switch mark.style {
            case .title: "title"
            case .token(let token): token.rawValue
            default: "other"
            }
            return (mark.range, style)
        }
    }
}

#if os(macOS)
extension InkuEditorMark.Style {
    /// Web `.label-muted` (fg3 at 22%), the `.ddl-token-*` palette in both themes, and the amber unknown name.
    var attributes: [NSAttributedString.Key: Any] {
        switch self {
        case .muted:
            return [.backgroundColor: NSColor.systemGray.withAlphaComponent(0.22)]
        case .completion(let state):
            let color: NSColor = switch state { case .completed: .systemBlue; case .numbersChanged: .systemGreen; case .wordsChanged: .systemOrange }
            return [.underlineStyle: NSUnderlineStyle.thick.rawValue | NSUnderlineStyle.patternDot.rawValue, .underlineColor: color]
        case .unknownName:
            return [.foregroundColor: Self.dynamic(0x8a5a12, 0xf0c368),
                    .backgroundColor: Self.dynamic(0xbf8820, 0xbf8820, lightAlpha: 0.12, darkAlpha: 0.26),
                    .underlineStyle: NSUnderlineStyle.single.rawValue | NSUnderlineStyle.patternDot.rawValue,
                    .underlineColor: Self.dynamic(0xbf8820, 0xf0c368, lightAlpha: 0.42, darkAlpha: 0.48)]
        case .title:
            // Web `.ddl-title` (weight 600 in that colour). Temporary attributes cannot change the font, so the
            // heading is the colour with a line under it.
            return [.foregroundColor: Self.dynamic(0x3d4650, 0xd6dde4),
                    .underlineStyle: NSUnderlineStyle.single.rawValue,
                    .underlineColor: Self.dynamic(0x3d4650, 0xd6dde4, lightAlpha: 0.45, darkAlpha: 0.45)]
        case .token(let token):
            let palette = Self.palette[token] ?? Self.palette[.word]!
            var attributes: [NSAttributedString.Key: Any] = [.foregroundColor: Self.dynamic(palette.light, palette.dark)]
            if let background = palette.background {
                attributes[.backgroundColor] = Self.dynamic(background.light, background.dark,
                                                            lightAlpha: background.lightAlpha, darkAlpha: background.darkAlpha)
            }
            return attributes
        }
    }

    private struct Palette {
        let light: Int
        let dark: Int
        let background: (light: Int, dark: Int, lightAlpha: CGFloat, darkAlpha: CGFloat)?
    }

    // `+page.svelte:3658-3690`.
    private static let palette: [DdlTokenClass: Palette] = [
        .shape: Palette(light: 0x2c5fb8, dark: 0x9cc4ff, background: (0x2c5fb8, 0x5c8fdc, 0.08, 0.26)),
        .touch: Palette(light: 0x7a5b2f, dark: 0xe2bf82, background: (0x7a5b2f, 0xbc8b3e, 0.10, 0.24)),
        .line: Palette(light: 0x53606b, dark: 0xc4ccd5, background: (0x53606b, 0x93a0b0, 0.10, 0.22)),
        .color: Palette(light: 0xb12a6b, dark: 0xff91c7, background: (0xb12a6b, 0xd75095, 0.09, 0.24)),
        .motion: Palette(light: 0x197a74, dark: 0x7ce1d4, background: (0x197a74, 0x329d93, 0.10, 0.24)),
        .place: Palette(light: 0x6b4cb3, dark: 0xc2a9ff, background: (0x6b4cb3, 0x8563d6, 0.09, 0.26)),
        .action: Palette(light: 0x9a4a1d, dark: 0xf0aa73, background: (0x9a4a1d, 0xc5692d, 0.10, 0.24)),
        .angle: Palette(light: 0x3d6f2c, dark: 0xa7d88e, background: (0x3d6f2c, 0x598e41, 0.10, 0.25)),
        .ratio: Palette(light: 0x9a3d3d, dark: 0xf0a0a0, background: (0x9a3d3d, 0xc44e4e, 0.09, 0.24)),
        .plugin: Palette(light: 0x9f4b3b, dark: 0xf0a58f, background: (0xb95845, 0xb95845, 0.10, 0.26)),
        .word: Palette(light: 0x2c3e91, dark: 0xb8c7ff, background: (0x2c3e91, 0x5c6fcd, 0.08, 0.26)),
        .emotion: Palette(light: 0x9b7a66, dark: 0xd8b8a6, background: nil),
    ]

    private static func dynamic(_ light: Int, _ dark: Int, lightAlpha: CGFloat = 1, darkAlpha: CGFloat = 1) -> NSColor {
        NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            let value = isDark ? dark : light
            return NSColor(srgbRed: CGFloat((value >> 16) & 0xff) / 255, green: CGFloat((value >> 8) & 0xff) / 255,
                           blue: CGFloat(value & 0xff) / 255, alpha: isDark ? darkAlpha : lightAlpha)
        }
    }
}
#endif
