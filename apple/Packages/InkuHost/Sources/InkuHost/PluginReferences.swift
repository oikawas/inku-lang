import Foundation

public struct PluginFiringPhrase: Sendable {
    public let phrase: String
    public let word: String
    public init(phrase: String, word: String) { self.phrase = phrase; self.word = word }
}

public struct PluginReferenceState: Sendable, Identifiable {
    public let text: String
    public let known: Bool
    public let firesAs: String?
    public let offset: Int
    public var id: Int { offset }
}

/// Same namespace pattern and known-prefix rule as Web plugin-names.ts.
public enum PluginReferences {
    public static func scan(text: String, names: Set<String>, firesOn: [PluginFiringPhrase] = []) -> [PluginReferenceState] {
        let pattern = try! NSRegularExpression(pattern: "(?<![A-Za-z0-9_])[A-Z][A-Za-z0-9_-]*\\.[^\\s、。,;:]+")
        let names = names.sorted { $0.utf16.count > $1.utf16.count }
        let firesOn = firesOn.sorted { $0.phrase.utf16.count > $1.phrase.utf16.count }
        let source = text as NSString
        var at = 0
        var states: [PluginReferenceState] = []
        while at < source.length,
              let match = pattern.firstMatch(in: text, options: [.withTransparentBounds], range: NSRange(location: at, length: source.length - at)) {
            let written = source.substring(with: match.range)
            let known = names.first { written.hasPrefix($0) }
            let reference = known ?? written
            let local = String(reference.dropFirst((reference.firstIndex(of: ".").map { reference.distance(from: reference.startIndex, to: $0) + 1 }) ?? 0))
            let hint = known == nil ? firesOn.first { local.hasPrefix($0.phrase) || local.lowercased().hasPrefix($0.phrase.lowercased()) }?.word : nil
            states.append(PluginReferenceState(text: reference, known: known != nil, firesAs: hint, offset: match.range.location))
            at = match.range.location + reference.utf16.count
        }
        return states
    }
}
