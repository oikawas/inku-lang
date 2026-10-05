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

    /// Web `batch.nonEmpty` (`numberedBatchLines` with `paintable`): the lines left with something to draw once the
    /// author's numbers and comments are cut. The count shown under the box; the run itself keeps `entries`.
    public static func paintableCount(in text: String) -> Int {
        text.components(separatedBy: "\n").filter {
            DescriptionLabels.hasDrawableText($0.trimmingCharacters(in: .whitespacesAndNewlines))
        }.count
    }
}
