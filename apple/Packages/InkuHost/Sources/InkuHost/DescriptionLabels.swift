import Foundation
import InkuCore

/// Shared core label rules, adapted only from scalar offsets to the editor's UTF-16 offsets.
/// The author's leading numbers and bracketed comments are painted grey in the editors, left out of the meter,
/// and a description made only of them cannot be drawn. Offsets are UTF-16, as in the Web and in NSTextView.
public enum DescriptionLabels {
    public enum Kind: String, Sendable, Equatable { case number, comment }

    public struct Span: Sendable, Equatable {
        public let range: NSRange
        public let kind: Kind
    }

    /// `excludedSpans`: every range the drawing does not read, in order of appearance.
    public static func excludedSpans(_ text: String) -> [Span] {
        let document = try! ExactJSON(data: InkuCore.descriptionLabelSpans(text))
        guard let rows = document.array else { preconditionFailure("Invalid core label spans") }
        let utf16Offsets = text.unicodeScalars.reduce(into: [0]) { offsets, scalar in
            offsets.append(offsets.last! + (scalar.value > 0xFFFF ? 2 : 1))
        }
        return rows.map { row in
            guard let fields = row.array, fields.count == 3,
                  let start = fields[0].number.flatMap(Int.init), let end = fields[1].number.flatMap(Int.init),
                  start >= 0, start <= end, end < utf16Offsets.count,
                  let name = fields[2].string, let kind = Kind(rawValue: name) else {
                preconditionFailure("Invalid core label span")
            }
            return Span(range: NSRange(location: utf16Offsets[start], length: utf16Offsets[end] - utf16Offsets[start]), kind: kind)
        }
    }

    /// `pipelineDescription`: what the drawing reads once the numbers and comments are cut out.
    public static func pipelineDescription(_ text: String) -> String {
        InkuCore.descriptionWithoutLabels(text)
    }

    /// Web `canSubmit` (state.svelte.ts:363): a description is drawable when something is left to read.
    public static func hasDrawableText(_ text: String) -> Bool {
        !pipelineDescription(text).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Server `_rewords` (pipeline_api.py:59-64): whether the words read differ, labels and spacing aside.
    /// A held work refuses a description that rewords it; its own description may still start a new work.
    public static func rewords(_ text: String, _ description: String) -> Bool {
        func read(_ value: String) -> String {
            pipelineDescription(value).split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
        }
        return read(text) != read(description)
    }
}
