import Foundation
import InkuHost

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

    /// Web `numberedBatchLines(prompt, paintable)` (batch/resume.ts:48-56, `+page.svelte:513`): the lines a run sends,
    /// numbered over every physical line. A line left with nothing to draw once the author's numbers and comments are
    /// cut is not sent, and its number is skipped, so a work still carries the line it was written on.
    public static func paintableEntries(in text: String) -> [(line: Int, text: String)] {
        entries(in: text).filter { DescriptionLabels.hasDrawableText($0.text) }
    }

    /// Web `batch.nonEmpty`: the count shown under the box, the same lines the run sends.
    public static func paintableCount(in text: String) -> Int { paintableEntries(in: text).count }
}
