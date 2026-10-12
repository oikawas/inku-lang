import Foundation

/// Generation admission is separate from compile identity and consumer envelopes.
public enum SVGGenerationLimit {
    public static let recommendedMiB = 12
    public static let range = 1...32

    public static func bytes(_ miB: Int?) throws -> UInt64 {
        let value = miB ?? recommendedMiB
        guard range.contains(value) else { throw HostError("invalid_svg_limit") }
        return UInt64(value) * 1_024 * 1_024
    }

    public static func parse(_ text: String) throws -> Int {
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, value.utf8.allSatisfy({ (48...57).contains($0) }),
              let miB = Int(value), range.contains(miB) else { throw HostError("invalid_svg_limit") }
        return miB
    }

    static func validate(_ svg: String, maximumBytes: UInt64) throws {
        guard UInt64(svg.utf8.count) <= maximumBytes else {
            throw HostError("svg_too_large", svgLimitMiB: Int(maximumBytes / (1_024 * 1_024)))
        }
    }
}
