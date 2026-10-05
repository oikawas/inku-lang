import Foundation
import SwiftUI

/// Web +page.svelte `highlightJsonLine` with the OutputTabsContent.svelte `.json-*` colors.
public enum JSONHighlight {
    public enum Kind: String, Equatable { case key, string, number, bool, null }

    private static let token = try! NSRegularExpression(
        pattern: #"("(?:\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)"#)

    /// The tokens of one line in order, classified as the Web classifies them.
    public static func tokens(_ line: String) -> [(range: NSRange, kind: Kind)] {
        let text = line as NSString
        return token.matches(in: line, range: NSRange(location: 0, length: text.length)).map { match in
            let value = text.substring(with: match.range)
            let kind: Kind = match.range(at: 2).location != NSNotFound ? .key
                : value.hasPrefix("\"") ? .string
                : value == "true" || value == "false" ? .bool
                : value == "null" ? .null : .number
            return (match.range, kind)
        }
    }

    static func attributed(_ text: String, dark: Bool) -> AttributedString {
        var result = AttributedString()
        for (index, line) in text.components(separatedBy: "\n").enumerated() {
            if index > 0 { result.append(AttributedString("\n")) }
            var styled = AttributedString(line)
            for (range, kind) in tokens(line) {
                guard let swiftRange = Range(range, in: line), let attributedRange = Range(swiftRange, in: styled) else { continue }
                styled[attributedRange].foregroundColor = color(kind, dark: dark)
                switch kind {
                case .key, .bool: styled[attributedRange].inlinePresentationIntent = .stronglyEmphasized
                case .null: styled[attributedRange].inlinePresentationIntent = .emphasized
                case .string, .number: break
                }
            }
            result.append(styled)
        }
        return result
    }

    static func color(_ kind: Kind, dark: Bool) -> Color {
        let hex: UInt32 = switch kind {
        case .key: dark ? 0xd6c5ff : 0x5b3f99
        case .string: dark ? 0x8ce99a : 0x0f6b2f
        case .number: dark ? 0x91caff : 0x075ca8
        case .bool: dark ? 0xffc078 : 0x9a3f05
        case .null: dark ? 0xb8c0cc : 0x5e6672
        }
        return Color(red: Double(hex >> 16 & 255) / 255, green: Double(hex >> 8 & 255) / 255, blue: Double(hex & 255) / 255)
    }
}
