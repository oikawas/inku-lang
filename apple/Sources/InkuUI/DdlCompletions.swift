import Foundation

/// Web `ddlCompletions`: the saijiki words of the instruction language and the macro names as they are shown
/// (`pluginDisplayName`: the Japanese alias for Japanese DDL, the qualified name otherwise).
public struct DdlCompletions {
    public let japanese: [String]
    public let english: [String]
    /// The instruction language of the whole text (`AppModel.instructionLanguage(for:)`).
    public let language: @MainActor (String) -> String

    public init(saijiki: [SaijikiCategory], plugins: [PluginWord], language: @escaping @MainActor (String) -> String) {
        func unique(_ words: [String]) -> [String] {
            var seen = Set<String>()
            return words.filter { !$0.isEmpty && seen.insert($0).inserted }
        }
        let words = saijiki.flatMap(\.words).filter { !$0.referenceOnly }
        japanese = unique(words.map(\.japanese) + plugins.map { $0.displayName(language: "ja") })
        english = unique(words.compactMap(\.english) + plugins.map { $0.displayName(language: "en") })
        self.language = language
    }

    @MainActor public func words(for text: String) -> [String] { language(text) == "ja" ? japanese : english }

    public struct Match: Equatable, Sendable {
        public let range: NSRange
        public let items: [String]
    }

    /// The word being typed before the caret: the longest run that ends at the caret, holds no space or
    /// punctuation, does not start inside a Latin word, and starts some candidate (ignoring case). Nil inside
    /// `excluded` (an open range's numbers, Web) or when nothing starts with it.
    public static func match(text: String, caret: Int, words: [String], excluded: NSRange? = nil) -> Match? {
        let ns = text as NSString
        guard caret > 0, caret <= ns.length else { return nil }
        if let excluded, caret >= excluded.location, caret <= NSMaxRange(excluded) { return nil }
        let longest = words.map { ($0 as NSString).length }.max() ?? 0
        // `.` and `_` stay inside a word: macro names are qualified (`Nature.wakaba`).
        let stops = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters).union(.symbols).subtracting(CharacterSet(charactersIn: "._"))
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
