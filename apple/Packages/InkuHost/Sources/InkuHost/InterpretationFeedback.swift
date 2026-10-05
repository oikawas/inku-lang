import Foundation

public struct FeedbackLexeme: Sendable {
    public let surface: String
    public let category: String
    public init(surface: String, category: String) { self.surface = surface; self.category = category }
}

public enum FeedbackTone: String, Sendable { case strong, medium, weak }

public struct FeedbackPart: Sendable, Identifiable {
    public let text: String
    public let tone: FeedbackTone
    public let offset: Int
    public var id: Int { offset }
}

/// Exact greedy matching and weak-part extraction from Web highlight/current-work.
public enum InterpretationFeedback {
    private static let emotions = ["美しい", "美しく", "激しい", "激しく", "静かな", "静かに", "素敵", "きれい", "やさしい", "切ない", "哀しい", "儚い", "神秘的", "幻想的", "寂しい", "爽やか"]

    public static func parts(description: String, ddl: String, vocabulary: [FeedbackLexeme]) -> [FeedbackPart] {
        guard !description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !ddl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return [] }
        let entries = vocabulary.enumerated().sorted {
            $0.element.surface.utf16.count == $1.element.surface.utf16.count ? $0.offset < $1.offset
                : $0.element.surface.utf16.count > $1.element.surface.utf16.count
        }.map(\.element)
        let emotions = emotions.sorted { $0.utf16.count > $1.utf16.count }
        let source = description as NSString
        let lowered = ddl.lowercased()
        var result: [FeedbackPart] = []
        var position = 0
        var plainStart = 0
        func includes(_ needle: String) -> Bool {
            let needle = needle.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return !needle.isEmpty && lowered.contains(needle)
        }
        func plain(to end: Int) {
            guard end > plainStart else { return }
            let text = source.substring(with: NSRange(location: plainStart, length: end - plainStart))
            let tone: FeedbackTone = text.trimmingCharacters(in: .whitespacesAndNewlines).utf16.count >= 2 && includes(text) ? .medium : .weak
            result.append(FeedbackPart(text: text, tone: tone, offset: plainStart))
        }
        func match(_ surface: String, at index: Int, boundary: Bool) -> Bool {
            let length = surface.utf16.count
            guard length > 0, index + length <= source.length else { return false }
            let piece = source.substring(with: NSRange(location: index, length: length))
            guard boundary ? piece.lowercased() == surface.lowercased() : piece == surface else { return false }
            if boundary {
                func word(_ value: unichar) -> Bool { (65...90).contains(value) || (97...122).contains(value) || (48...57).contains(value) || value == 45 }
                if index > 0 && word(source.character(at: index - 1)) { return false }
                if index + length < source.length && word(source.character(at: index + length)) { return false }
            }
            return true
        }
        while position < source.length {
            if let entry = entries.first(where: { match($0.surface, at: position, boundary: $0.surface.utf8.allSatisfy { (32...126).contains($0) }) }) {
                plain(to: position)
                let text = source.substring(with: NSRange(location: position, length: entry.surface.utf16.count))
                result.append(FeedbackPart(text: text, tone: includes(text) || includes(entry.category) ? .strong : .medium, offset: position))
                position += entry.surface.utf16.count; plainStart = position
            } else if let word = emotions.first(where: { match($0, at: position, boundary: false) }) {
                plain(to: position)
                result.append(FeedbackPart(text: word, tone: .medium, offset: position))
                position += word.utf16.count; plainStart = position
            } else { position += 1 }
        }
        plain(to: source.length)
        return result
    }

    public static func unreadWords(description: String, ddl: String, vocabulary: [FeedbackLexeme]) -> [String] {
        let pattern = try! NSRegularExpression(pattern: "[一-龯々ぁ-んァ-ヶー]{2,}|[A-Za-z][A-Za-z'-]+")
        return parts(description: description, ddl: ddl, vocabulary: vocabulary).filter { $0.tone == .weak }.flatMap { part in
            pattern.matches(in: part.text, range: NSRange(part.text.startIndex..., in: part.text)).map { (part.text as NSString).substring(with: $0.range) }
        }
    }
}
