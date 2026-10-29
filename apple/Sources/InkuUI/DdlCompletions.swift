import Foundation
import InkuHost

/// Web `ddlCompletions`: the saijiki words of the instruction language and the macro names as they are shown
/// (`pluginDisplayName`: the Japanese alias for Japanese DDL, the qualified name otherwise).
public struct DdlCompletions {
    public let japanese: [String]
    public let english: [String]
    private let plugins: [PluginWord]
    private let uiLanguage: String
    /// The instruction language of the whole text (`AppModel.instructionLanguage(for:)`).
    public let language: @MainActor (String) -> String

    public init(saijiki: [SaijikiCategory], plugins: [PluginWord], uiLanguage: String = "ja", language: @escaping @MainActor (String) -> String) {
        func unique(_ words: [String]) -> [String] {
            var seen = Set<String>()
            return words.filter { !$0.isEmpty && seen.insert($0).inserted }
        }
        let words = saijiki.flatMap(\.words).filter { !$0.referenceOnly }
        japanese = unique(words.map(\.japanese) + plugins.map { $0.displayName(language: "ja") })
        english = unique(words.compactMap(\.english) + plugins.map { $0.displayName(language: "en") })
        self.plugins = plugins
        self.uiLanguage = uiLanguage
        self.language = language
    }

    @MainActor public func words(for text: String) -> [String] { language(text) == "ja" ? japanese : english }

    @MainActor func presentation(for completion: String, text: String) -> String {
        let lang = language(text)
        guard let word = plugins.first(where: { $0.displayName(language: lang) == completion }) else { return completion }
        let others = Array(word.japanese.dropFirst()) + Array(word.english.dropFirst())
        let kind = uiLanguage != "en" ? (word.kind == "object" ? "物の語" : "情景の語") : (word.kind == "object" ? "object" : "scene")
        let note = uiLanguage != "en" ? word.note : word.englishNote ?? word.note
        let example = lang == "ja" ? word.exampleJapanese : word.exampleEnglish
        return ([completion, others.joined(separator: " / "), kind, note, example ?? ""]
            .filter { !$0.isEmpty }).joined(separator: " — ")
    }

    public struct Match: Equatable, Sendable {
        public let range: NSRange
        public let items: [String]
    }

    @MainActor public func match(text: String, caret: Int, excluded: NSRange? = nil) -> Match? {
        let source = text as NSString
        guard caret > 0, caret <= source.length else { return nil }
        if let excluded, caret >= excluded.location, caret <= NSMaxRange(excluded) { return nil }
        if DdlTitles.lineRanges(text).contains(where: { caret >= $0.location && caret <= NSMaxRange($0) }) { return nil }
        var opening = caret
        while opening > 0 {
            let unit = source.character(at: opening - 1)
            if unit == 0x7b || unit == 0xff5b { opening -= 1; break }
            if unit == 0x7d || unit == 0xff5d || unit == 0x0a || unit == 0x3002 || unit == 0x2e { opening = caret; break }
            opening -= 1
        }
        if opening < caret, [0x7b, 0xff5b].contains(Int(source.character(at: opening))) {
            let prefix = source.substring(with: NSRange(location: opening + 1, length: caret - opening - 1))
            let lang = language(text)
            var seen = Set<String>()
            let items = plugins.filter { word in
                prefix.isEmpty || (word.japanese + word.english).contains { $0.range(of: prefix, options: [.caseInsensitive, .anchored]) != nil }
            }.map { $0.displayName(language: lang) }.filter { seen.insert($0).inserted }
            guard !items.isEmpty else { return nil }
            let hasClose = caret < source.length && [0x7d, 0xff5d].contains(Int(source.character(at: caret)))
            return Match(range: NSRange(location: opening, length: caret - opening + (hasClose ? 1 : 0)), items: items)
        }
        return Self.match(text: text, caret: caret, words: words(for: text), excluded: excluded)
    }

    /// The word being typed before the caret: the longest run that ends at the caret, holds no space or
    /// punctuation, does not start inside a Latin word, and starts some candidate (ignoring case). Nil inside
    /// `excluded` (an open range's numbers, Web), on a title line, or when nothing starts with it.
    public static func match(text: String, caret: Int, words: [String], excluded: NSRange? = nil) -> Match? {
        let ns = text as NSString
        guard caret > 0, caret <= ns.length else { return nil }
        if let excluded, caret >= excluded.location, caret <= NSMaxRange(excluded) { return nil }
        // A title line names a chunk and draws nothing, so it offers no word (DDL 27).
        if DdlTitles.lineRanges(text).contains(where: { caret >= $0.location && caret <= NSMaxRange($0) }) { return nil }
        let longest = words.map { ($0 as NSString).length }.max() ?? 0
        let stops = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters).union(.symbols)
        var start = caret
        while start > 0, caret - start < longest {
            let unit = ns.character(at: start - 1)
            if UTF16.isTrailSurrogate(unit) || UTF16.isLeadSurrogate(unit) { start -= 1; continue }
            guard let scalar = Unicode.Scalar(unit), !stops.contains(scalar) else { break }
            start -= 1
        }
        func latin(_ index: Int) -> Bool {
            guard index >= 0, index < ns.length, let scalar = Unicode.Scalar(ns.character(at: index)) else { return false }
            return scalar.isASCII && CharacterSet.alphanumerics.contains(scalar)
        }
        for location in start..<caret {
            if latin(location), latin(location - 1) { continue }
            let typed = ns.substring(with: NSRange(location: location, length: caret - location))
            let items = words.filter { $0.range(of: typed, options: [.caseInsensitive, .anchored]) != nil }
            if !items.isEmpty { return Match(range: NSRange(location: location, length: caret - location), items: items) }
        }
        return nil
    }
}
