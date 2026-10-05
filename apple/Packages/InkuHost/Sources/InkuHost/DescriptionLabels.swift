import Foundation

/// Web `lib/description-labels.ts` (Server `pipeline_description`): the ranges of a description the drawing does not read.
/// The author's leading numbers and bracketed comments are painted grey in the editors, left out of the meter,
/// and a description made only of them cannot be drawn. Offsets are UTF-16, as in the Web and in NSTextView.
public enum DescriptionLabels {
    public enum Kind: Sendable, Equatable { case number, comment }

    public struct Span: Sendable, Equatable {
        public let range: NSRange
        public let kind: Kind
    }

    // Digits of either width, then a separator an author types; the ideographic space counts as one.
    private static let leadingNumber = try! NSRegularExpression(pattern: "^[ \\t]*[0-9０-９]+[.．、)）:：　][ \\t　]*")
    // Brackets of either width, closed on the line they were opened on.
    private static let comment = try! NSRegularExpression(pattern: "\\[[^\\[\\]\\n]*\\]|［[^［］\\n]*］")
    private static let spaceRun = try! NSRegularExpression(pattern: "[ \\t　]{2,}")
    private static let edgeSpace = try! NSRegularExpression(pattern: "^[ \\t　]+|[ \\t　]+$")

    /// `excludedSpans`: every range the drawing does not read, in order of appearance.
    public static func excludedSpans(_ text: String) -> [Span] {
        guard !text.isEmpty else { return [] }
        var spans: [Span] = []
        var offset = 0
        for line in (text as NSString).components(separatedBy: "\n") {
            let length = (line as NSString).length
            let whole = NSRange(location: 0, length: length)
            if let number = leadingNumber.firstMatch(in: line, options: .anchored, range: whole), number.range.length > 0 {
                spans.append(Span(range: NSRange(location: offset + number.range.location, length: number.range.length), kind: .number))
            }
            for match in comment.matches(in: line, range: whole) {
                spans.append(Span(range: NSRange(location: offset + match.range.location, length: match.range.length), kind: .comment))
            }
            offset += length + 1
        }
        return spans.sorted { $0.range.location < $1.range.location }
    }

    /// `pipelineDescription`: what the drawing reads once the numbers and comments are cut out.
    public static func pipelineDescription(_ text: String) -> String {
        let spans = excludedSpans(text)
        guard !spans.isEmpty else { return text }
        let source = text as NSString
        var kept = ""
        var at = 0
        for span in spans {
            if span.range.location > at { kept += source.substring(with: NSRange(location: at, length: span.range.location - at)) }
            at = max(at, span.range.location + span.range.length)
        }
        if at < source.length { kept += source.substring(from: at) }
        return kept.components(separatedBy: "\n").map { line in
            let collapsed = spaceRun.stringByReplacingMatches(in: line, range: NSRange(location: 0, length: (line as NSString).length), withTemplate: " ")
            return edgeSpace.stringByReplacingMatches(in: collapsed, range: NSRange(location: 0, length: (collapsed as NSString).length), withTemplate: "")
        }.joined(separator: "\n")
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
