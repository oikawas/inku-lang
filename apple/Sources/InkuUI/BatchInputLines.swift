import Foundation

/// The editor and the journal count physical input lines, including empty lines.
public enum BatchInputLines {
    public static func normalizedText(_ text: String) -> String {
        text.replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
            .replacingOccurrences(of: "\u{0085}", with: "\n")
            .replacingOccurrences(of: "\u{2028}", with: "\n")
            .replacingOccurrences(of: "\u{2029}", with: "\n")
    }

    public static func physicalLines(in text: String) -> [String] {
        normalizedText(text).components(separatedBy: "\n")
    }

    public static func entries(in text: String) -> [(line: Int, text: String)] {
        physicalLines(in: text).enumerated().compactMap { offset, value in
            let value = value.trimmingCharacters(in: .whitespacesAndNewlines)
            return value.isEmpty ? nil : (offset + 1, value)
        }
    }
}
