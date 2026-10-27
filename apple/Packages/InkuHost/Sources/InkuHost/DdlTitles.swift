import Foundation

/// Chunk titles (DDL 27), the rule of the shared core's `chunk_title.rs` as Web `ddl-titles.ts` ports it:
/// a line that is only a bracketed name, 「灯台」 or "lighthouse" (or “lighthouse”), names the chunk of
/// sentences after it. A title draws nothing, so a DDL view shows it as a heading and colours no word in
/// it, and the words a work read leave it out.
public enum DdlTitles {
    private static let brackets: [(open: Character, close: Character)] = [("「", "」"), ("\"", "\""), ("“", "”")]

    /// The name a line gives when the whole line, without the spaces around it, is a title (empty for a
    /// title that ends a chunk); nil for any other line. A name leaves out its own pair's characters only.
    public static func name(_ line: String) -> String? {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        for (open, close) in brackets {
            guard trimmed.count >= 2, trimmed.first == open, trimmed.last == close else { continue }
            let inner = trimmed.dropFirst().dropLast()
            if !inner.contains(open) && !inner.contains(close) && !inner.contains("\n") {
                return inner.trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return nil
    }

    /// Where each title line stands in `text` (UTF-16, as NSString counts), without its line break.
    public static func lineRanges(_ text: String) -> [NSRange] {
        var ranges: [NSRange] = []
        var start = 0
        for line in text.components(separatedBy: "\n") {
            let length = (line as NSString).length
            let content = line.hasSuffix("\r") ? String(line.dropLast()) : line
            if name(content) != nil { ranges.append(NSRange(location: start, length: (content as NSString).length)) }
            start += length + 1
        }
        return ranges
    }

    /// The first line that is neither blank nor a title (nor an empty 「」 that ends a chunk): what names a
    /// work that has only its DDL.
    public static func firstSentenceLine(_ text: String) -> String? {
        text.split(whereSeparator: \.isNewline)
            .first { !$0.trimmingCharacters(in: .whitespaces).isEmpty && name(String($0)) == nil }
            .map(String.init)
    }

    /// `text` without its title lines.
    public static func withoutTitleLines(_ text: String) -> String {
        text.components(separatedBy: "\n").filter { name($0) == nil }.joined(separator: "\n")
    }
}
