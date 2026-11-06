import Foundation
import InkuCore

/// Core title rules; display callers fall back to unmodified text if core cannot read it.
public enum DdlTitles {
    private static func rows(_ text: String) throws -> [(NSRange, String)] {
        let json = try ExactJSON(data: Data(InkuCore.ddlTitleLines(text).utf8))
        guard let rows = json.array else { throw HostError("provider_core_invalid") }
        let offsets = text.unicodeScalars.reduce(into: [0]) { values, scalar in
            values.append(values.last! + (scalar.value > 0xFFFF ? 2 : 1))
        }
        return try rows.map { row in
            guard let values = row.array, values.count == 3,
                  let start = values[0].number.flatMap(Int.init), let end = values[1].number.flatMap(Int.init),
                  start >= 0, end >= start, end < offsets.count, let name = values[2].string else {
                throw HostError("provider_core_invalid")
            }
            return (NSRange(location: offsets[start], length: offsets[end] - offsets[start]), name)
        }
    }

    public static func name(_ line: String) -> String? {
        guard let rows = try? rows(line), rows.count == 1,
              rows[0].0 == NSRange(location: 0, length: (line as NSString).length) else { return nil }
        return rows[0].1
    }

    public static func lineRanges(_ text: String) -> [NSRange] { (try? rows(text).map(\.0)) ?? [] }

    public static func firstSentenceLine(_ text: String) -> String? {
        let ranges = lineRanges(text)
        var offset = 0
        for line in text.components(separatedBy: "\n") {
            let content = line.hasSuffix("\r") ? String(line.dropLast()) : line
            let range = NSRange(location: offset, length: (content as NSString).length)
            if !ranges.contains(range), !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return content }
            offset += (line as NSString).length + 1
        }
        return nil
    }

    public static func withoutTitleLines(_ text: String) -> String {
        (try? InkuCore.withoutDdlTitleLines(text)) ?? text
    }

    public static func withoutTitleLinesForDrawing(_ text: String) throws -> String {
        try InkuCore.withoutDdlTitleLines(text)
    }
}
