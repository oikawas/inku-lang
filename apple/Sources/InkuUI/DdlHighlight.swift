import Foundation
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

/// Web `plugin-names.ts`: namespaced plugin references in DDL text, which ones this installation holds,
/// and what a wrong one would have fired as. The pattern is the expansion layer's `_PLUGIN_REFERENCE_RE`.
struct PluginNameIndex: Sendable {
    /// Qualified names and aliases, longest first.
    let names: [String]
    /// Firing phrases, longest first, with the entry word each belongs to.
    let firesOn: [(phrase: String, word: String)]

    struct Reference: Sendable, Equatable {
        let range: NSRange
        let text: String
        let known: Bool
    }

    struct Unknown: Sendable, Equatable {
        let text: String
        let namespace: String
        let firesAs: String?
    }

    private static let reference = try! NSRegularExpression(pattern: "(?<![A-Za-z0-9_])[A-Z][A-Za-z0-9_-]*\\.[^\\s、。,;:]+")

    init(words: [PluginWord]) {
        var names: [String] = []
        var firesOn: [(String, String)] = []
        for word in words {
            names.append(word.id)
            names.append(contentsOf: word.aliases.filter { !$0.isEmpty })
            let local = Self.localPart(word.id)
            for phrase in word.firesOnJapanese + word.firesOnEnglish {
                let trimmed = phrase.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty { firesOn.append((trimmed, local)) }
            }
        }
        self.names = names.sorted { ($0 as NSString).length > ($1 as NSString).length }
        self.firesOn = firesOn.sorted { ($0.0 as NSString).length > ($1.0 as NSString).length }.map { (phrase: $0.0, word: $0.1) }
    }

    static func localPart(_ name: String) -> String {
        guard let dot = name.firstIndex(of: ".") else { return name }
        return String(name[name.index(after: dot)...])
    }

    static func namespacePart(_ name: String) -> String {
        guard let dot = name.firstIndex(of: ".") else { return "" }
        return String(name[..<dot])
    }

    /// `scanPluginReferences`: a known name ends where the name ends, and the rest is scanned again.
    func references(in text: String) -> [Reference] {
        let source = text as NSString
        var found: [Reference] = []
        var at = 0
        while at < source.length,
              let match = Self.reference.firstMatch(in: text, range: NSRange(location: at, length: source.length - at)) {
            let matched = source.substring(with: match.range)
            let known = names.first { matched.hasPrefix($0) }
            let length = known.map { ($0 as NSString).length } ?? match.range.length
            let range = NSRange(location: match.range.location, length: length)
            found.append(Reference(range: range, text: source.substring(with: range), known: known != nil))
            at = NSMaxRange(range)
        }
        return found
    }

    /// `firingWordFor`: the entry word the local part would fire as without its namespace.
    func firingWord(for reference: String) -> String? {
        let local = Self.localPart(reference)
        guard !local.isEmpty else { return nil }
        let lowered = local.lowercased()
        return firesOn.first { local.hasPrefix($0.phrase) || lowered.hasPrefix($0.phrase.lowercased()) }?.word
    }

    /// `unknownPluginNames`: the references this installation does not hold, once each, in first-seen order.
    func unknownNames(in text: String) -> [Unknown] {
        var seen: Set<String> = []
        return references(in: text).compactMap { reference in
            guard !reference.known, seen.insert(reference.text).inserted else { return nil }
            return Unknown(text: reference.text, namespace: Self.namespacePart(reference.text), firesAs: firingWord(for: reference.text))
        }
    }
}

/// Web `annotate`: plugin references first, then saijiki words longest first (an ASCII word only on word
/// boundaries), then emotion words. Returns the painted ranges; plain text is left alone.
struct DdlHighlighter: Sendable {
    private struct Entry: Sendable { let word: String; let lower: String; let length: Int; let token: DdlTokenClass; let ascii: Bool }
    private let buckets: [Character: [Entry]]
    private let plugins: PluginNameIndex
    private static let emotionWords = ["美しい", "美しく", "激しい", "激しく", "静かな", "静かに", "素敵", "きれい", "やさしい",
                                       "切ない", "哀しい", "儚い", "神秘的", "幻想的", "寂しい", "爽やか"]
        .sorted { $0.count > $1.count }

    init(saijiki: [SaijikiCategory], plugins: PluginNameIndex) {
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
        self.plugins = plugins
    }

    func marks(_ text: String) -> [InkuEditorMark] {
        let source = text as NSString
        let references = Dictionary(plugins.references(in: text).map { ($0.range.location, $0) }, uniquingKeysWith: { first, _ in first })
        var marks: [InkuEditorMark] = []
        var index = 0
        while index < source.length {
            if let reference = references[index] {
                marks.append(InkuEditorMark(range: reference.range, style: reference.known ? .token(.plugin) : .unknownName))
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

#if os(macOS)
extension InkuEditorMark.Style {
    /// Web `.label-muted` (fg3 at 22%), the `.ddl-token-*` palette in both themes, and the amber unknown name.
    var attributes: [NSAttributedString.Key: Any] {
        switch self {
        case .muted:
            return [.backgroundColor: NSColor.systemGray.withAlphaComponent(0.22)]
        case .unknownName:
            return [.foregroundColor: Self.dynamic(0x8a5a12, 0xf0c368),
                    .backgroundColor: Self.dynamic(0xbf8820, 0xbf8820, lightAlpha: 0.12, darkAlpha: 0.26),
                    .underlineStyle: NSUnderlineStyle.single.rawValue | NSUnderlineStyle.patternDot.rawValue,
                    .underlineColor: Self.dynamic(0xbf8820, 0xf0c368, lightAlpha: 0.42, darkAlpha: 0.48)]
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
