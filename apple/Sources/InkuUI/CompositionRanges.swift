import Foundation
import InkuCore

/// Web `composition-ranges.ts`: numeric places written as `name (horizontal a to b, vertical c to d)`, read as the
/// shared core's named ranges (`inku.composition-ranges.v1`). Positions are UTF-16 offsets, as in the Web.
public enum CompositionRanges {
    /// An exact rational in [0, 1]; denominators stay at most 10^6, so cross products fit in 64 bits.
    public struct Rational: Equatable, Sendable {
        public let numerator: Int64
        public let denominator: Int64
        public init(_ numerator: Int64, _ denominator: Int64) { self.numerator = numerator; self.denominator = denominator }
        var value: Double { Double(numerator) / Double(denominator) }
        static func < (a: Self, b: Self) -> Bool { a.numerator * b.denominator < b.numerator * a.denominator }
        static func same(_ a: Self, _ b: Self) -> Bool { a.numerator * b.denominator == b.numerator * a.denominator }
    }
    /// left, top, right, bottom.
    public typealias Bounds = [Rational]
    public struct Preview: Equatable, Sendable {
        public let bounds: [Double]
        public let invalid: Bool
    }
    public struct Entry: Equatable, Sendable {
        public let key: String
        public let words: [String: String]
        public let bounds: Bounds
        public let corner: Bool
    }
    public struct NumericRange: Equatable, Sendable {
        public var start: Int, end: Int, nameStart: Int, nameEnd: Int, bodyStart: Int, bodyEnd: Int
        public var name: String
        public var body: String
        public let lang: String
        public var bounds: Bounds?
    }

    /// The core's table, read once.
    public static let table: [Entry] = read(InkuCore.compositionRanges())

    public static func parseNumber(_ source: String, lang: String) -> Rational? {
        var text = source
        if lang == "ja" {
            text = String(String.UnicodeScalarView(text.unicodeScalars.map { scalar in
                (0xFF10...0xFF19).contains(scalar.value) ? Unicode.Scalar(scalar.value - 0xFEE0)! : scalar
            })).replacingOccurrences(of: "．", with: ".").replacingOccurrences(of: "／", with: "/")
        }
        text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.utf16.count <= 32 else { return nil }
        let ascii = CharacterSet(charactersIn: "0123456789")
        func digits(_ part: Substring) -> Bool { !part.isEmpty && part.unicodeScalars.allSatisfy { ascii.contains($0) } }
        var numerator: Int64, denominator: Int64
        let fraction = text.split(separator: "/", omittingEmptySubsequences: false)
        if fraction.count == 2, digits(fraction[0]), digits(fraction[1]) {
            guard let n = Int64(fraction[0]), let d = Int64(fraction[1]), d >= 1, d <= 1_000_000 else { return nil }
            numerator = n; denominator = d
        } else {
            let decimal = text.split(separator: ".", omittingEmptySubsequences: false)
            guard (decimal.count == 1 && digits(decimal[0])) || (decimal.count == 2 && digits(decimal[0]) && digits(decimal[1]) && decimal[1].count <= 6),
                  let whole = Int64(decimal[0]) else { return nil }
            let places = decimal.count == 2 ? decimal[1] : ""
            denominator = Int64(pow(10.0, Double(places.count)))
            let (scaled, overflow) = whole.multipliedReportingOverflow(by: denominator)
            guard !overflow else { return nil }
            numerator = scaled + (Int64(places) ?? 0)
        }
        guard numerator <= denominator else { return nil }
        var a = numerator, b = denominator
        while b != 0 { (a, b) = (b, a % b) }
        let divisor = max(a, 1)
        return Rational(numerator / divisor, denominator / divisor)
    }

    private static let jaBody = try! NSRegularExpression(pattern: "^\\s*横\\s*(.*?)\\s*[〜～~－-]\\s*(.*?)\\s*[、，,]\\s*縦\\s*(.*?)\\s*[〜～~－-]\\s*(.*?)\\s*$")
    private static let enBody = try! NSRegularExpression(pattern: "^\\s*horizontal\\s+(.+?)(?:\\s+to\\s+|\\s*[-–]\\s*)(.+?)\\s*,\\s*vertical\\s+(.+?)(?:\\s+to\\s+|\\s*[-–]\\s*)(.+?)\\s*$",
                                                         options: [.caseInsensitive])

    public static func parseBody(_ body: String, lang: String) -> Bounds? {
        let pattern = lang == "ja" ? jaBody : enBody
        let ns = body as NSString
        guard let match = pattern.firstMatch(in: body, range: NSRange(location: 0, length: ns.length)) else { return nil }
        let values = (1...4).map { parseNumber(ns.substring(with: match.range(at: $0)), lang: lang) }
        guard values.allSatisfy({ $0 != nil }) else { return nil }
        let left = values[0]!, right = values[1]!, top = values[2]!, bottom = values[3]!
        guard left < right, top < bottom else { return nil }
        return [left, top, right, bottom]
    }

    public static func sameBounds(_ a: Bounds, _ b: Bounds) -> Bool { a.count == 4 && b.count == 4 && zip(a, b).allSatisfy { Rational.same($0, $1) } }

    public static func preview(_ bounds: Bounds, invalid: Bool = false) -> Preview { Preview(bounds: bounds.map(\.value), invalid: invalid) }

    public static func read(_ payload: Data) -> [Entry] {
        guard let value = try? JSONSerialization.jsonObject(with: payload) as? [String: Any],
              value["schema"] as? String == "inku.composition-ranges.v1", let items = value["ranges"] as? [Any] else { return [] }
        var result: [Entry] = []
        for item in items {
            guard let row = item as? [String: Any], let key = row["key"] as? String, let words = row["words"] as? [String: Any],
                  let ja = words["ja"] as? String, !ja.isEmpty, let en = words["en"] as? String, !en.isEmpty,
                  let corner = row["corner"] as? Bool, let bounds = row["bounds"] as? [[Any]], bounds.count == 4 else { return [] }
            var exact: Bounds = []
            for pair in bounds {
                guard pair.count == 2, let n = (pair[0] as? NSNumber)?.int64Value, let d = (pair[1] as? NSNumber)?.int64Value,
                      n >= 0, d > 0, n <= d else { return [] }
                exact.append(Rational(n, d))
            }
            guard exact[0] < exact[2], exact[1] < exact[3] else { return [] }
            result.append(Entry(key: key, words: ["ja": ja, "en": en], bounds: exact, corner: corner))
        }
        return result
    }

    private static let jaScan = try! NSRegularExpression(pattern: "(?:^|[\\n。！？、，,を])([\\t 　]*)([^\\n。！？、，,を（）()]+?)([\\t 　]*[（(])(横[^）)\\n]*)([）)])(?=\\s*に)")
    private static let enScan = try! NSRegularExpression(pattern: "\\b(?:at|in|on)\\s+((?:\\[composition\\]\\s*)?(?:the\\s+)?[^()\\n.,;]+?)(\\s*\\()(horizontal\\s+[^)\\n]*)(\\))",
                                                         options: [.caseInsensitive])
    private static let jaMark = try! NSRegularExpression(pattern: "^［構図］\\s*")
    private static let enMark = try! NSRegularExpression(pattern: "^\\[composition\\]\\s*")
    private static let enThe = try! NSRegularExpression(pattern: "^the\\s+")

    public static func scan(_ text: String) -> [NumericRange] {
        let ns = text as NSString
        var result: [NumericRange] = []
        for (lang, pattern) in [("ja", jaScan), ("en", enScan)] {
            for match in pattern.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
                let rawName = ns.substring(with: match.range(at: lang == "ja" ? 2 : 1))
                let opening = ns.substring(with: match.range(at: lang == "ja" ? 3 : 2))
                let body = ns.substring(with: match.range(at: lang == "ja" ? 4 : 3))
                let raw = rawName as NSString, open = opening as NSString, bodyNS = body as NSString
                let nameStart = NSMaxRange(match.range) - raw.length - open.length - bodyNS.length - 1
                let nameEnd = nameStart + raw.length
                let bodyStart = nameEnd + open.length
                var name = (lang == "ja" ? jaMark : enMark).stringByReplacingMatches(in: rawName, range: NSRange(location: 0, length: raw.length), withTemplate: "")
                if lang == "en" { name = enThe.stringByReplacingMatches(in: name, range: NSRange(location: 0, length: (name as NSString).length), withTemplate: "") }
                result.append(NumericRange(start: nameStart, end: bodyStart + bodyNS.length + 1, nameStart: nameStart, nameEnd: nameEnd,
                    bodyStart: bodyStart, bodyEnd: bodyStart + bodyNS.length, name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                    body: body, lang: lang, bounds: parseBody(body, lang: lang)))
            }
        }
        // Web: `filter((range, i, all) => !i || range.start >= all[i - 1].end)` on the sorted list.
        let sorted = result.sorted { $0.start < $1.start }
        return sorted.enumerated().filter { index, range in index == 0 || range.start >= sorted[index - 1].end }.map(\.element)
    }

    public static func matching(_ range: NumericRange, _ table: [Entry]) -> Entry? {
        guard let bounds = range.bounds else { return nil }
        return table.first { $0.words[range.lang] == range.name && sameBounds($0.bounds, bounds) }
    }

    public static func followedName(_ bounds: Bounds?, current: String, opened: String, lang: String, table: [Entry]) -> String {
        guard let bounds else { return current }
        if let match = table.first(where: { sameBounds($0.bounds, bounds) }) { return match.words[lang] ?? current }
        let chosen = lang == "ja" ? "指定の範囲" : "chosen place"
        return opened == chosen || table.contains(where: { $0.words[lang] == opened }) ? chosen : opened
    }

    public static func edit(_ source: String, range: NumericRange, body: String, table: [Entry], opened: String? = nil) -> (source: String, range: NumericRange) {
        let ns = source as NSString
        let bounds = parseBody(body, lang: range.lang)
        let rawName = ns.substring(with: NSRange(location: range.nameStart, length: range.nameEnd - range.nameStart))
        let name = followedName(bounds, current: range.name, opened: opened ?? range.name, lang: range.lang, table: table)
        let nextName = rawName.range(of: range.name).map { rawName.replacingCharacters(in: $0, with: name) } ?? rawName
        let next = ns.substring(to: range.nameStart) + nextName
            + ns.substring(with: NSRange(location: range.nameEnd, length: range.bodyStart - range.nameEnd)) + body + ns.substring(from: range.bodyEnd)
        let shift = (nextName as NSString).length - (rawName as NSString).length
        let bodyLength = (body as NSString).length
        var edited = range
        edited.name = name; edited.nameEnd = range.nameEnd + shift; edited.bodyStart = range.bodyStart + shift
        edited.bodyEnd = range.bodyStart + shift + bodyLength; edited.end = edited.bodyEnd + 1; edited.body = body; edited.bounds = bounds
        return (next, edited)
    }
}

/// Web `codemirror-ranges.ts`: which ranges an editor folds, which one is open, the frame it shows, and whether
/// leaving an edited range should rename it. Pure, so the rules are checked without a text view.
public struct RangeEditorState: Equatable, Sendable {
    public var ranges: [CompositionRanges.NumericRange] = []
    public var active: CompositionRanges.NumericRange?
    public var pendingName = false
    public var hover: Int?
    public var focused = false
    public var preview: CompositionRanges.Preview?
    public var invalid = false
    /// Folded text: the numbers after a matching name, and an old composition mark.
    public var hidden: [NSRange] = []
    /// The place word of each matching range, shown with a dotted underline.
    public var names: [NSRange] = []

    public init() {}

    static func contains(_ range: CompositionRanges.NumericRange, _ selection: NSRange) -> Bool {
        selection.length == 0
            ? selection.location > range.start && selection.location < range.end
            : selection.location < range.end && NSMaxRange(selection) > range.start
    }

    public static func derive(text: String, selection: NSRange, focused: Bool, hover: Int?, previous: RangeEditorState?,
                              table: [CompositionRanges.Entry]) -> RangeEditorState {
        let ns = text as NSString
        var state = RangeEditorState()
        state.ranges = CompositionRanges.scan(text)
        state.focused = focused; state.hover = hover
        state.active = focused ? state.ranges.first { contains($0, selection) } : nil
        state.pendingName = state.active != nil && previous?.active?.start == state.active?.start && previous?.pendingName == true
        let shown = state.active ?? state.ranges.first { $0.start == hover }
        if let bounds = shown?.bounds { state.preview = CompositionRanges.preview(bounds) }
        else if let shown, previous?.active?.start == shown.start, let last = previous?.preview {
            state.preview = .init(bounds: last.bounds, invalid: true)
        }
        state.invalid = state.ranges.contains { $0.bounds == nil }
        for range in state.ranges where CompositionRanges.matching(range, table) != nil {
            let rawName = ns.substring(with: NSRange(location: range.nameStart, length: range.nameEnd - range.nameStart)) as NSString
            let label = rawName.range(of: range.name, options: .backwards)
            if label.location != NSNotFound { state.names.append(NSRange(location: range.nameStart + label.location, length: label.length)) }
            if focused && contains(range, selection) { continue }
            state.hidden.append(NSRange(location: range.nameEnd, length: range.end - range.nameEnd))
            let legacy = rawName.range(of: "^(?:［構図］|\\[composition\\])\\s*", options: .regularExpression)
            if legacy.location != NSNotFound { state.hidden.append(NSRange(location: range.nameStart, length: legacy.length)) }
        }
        // A temporarily broken axis or parenthesis stays an invalid edit until the caret leaves it:
        // keep the last valid frame, never invent bounds.
        if state.active == nil, let last = previous?.active, focused, last.end > last.start, contains(last, selection) {
            var broken = last; broken.bounds = nil
            state.active = broken; state.pendingName = previous?.pendingName ?? false; state.invalid = true
            state.preview = previous?.preview.map { .init(bounds: $0.bounds, invalid: true) }
        }
        return state
    }

    /// Web `pendingNameAfter`: editing the numbers asks for the name to follow on leaving; editing the words cancels it.
    public func pendingName(afterEditing edit: NSRange) -> Bool {
        guard let range = active else { return false }
        let from = edit.location, to = NSMaxRange(edit)
        func touches(_ start: Int, _ end: Int, includeEnd: Bool = false) -> Bool {
            from == to ? from >= start && (from < end || (includeEnd && from == end)) : from < end && to > start
        }
        if touches(range.nameStart, range.nameEnd) { return false }
        return pendingName || touches(range.bodyStart, range.bodyEnd, includeEnd: true)
    }

    /// This state with its open range moved by an edit made before or inside it.
    public func mapped(edit: NSRange, replacementLength: Int) -> RangeEditorState {
        guard var range = active else { return self }
        let delta = replacementLength - edit.length
        func map(_ position: Int, side: Int) -> Int {
            if position < edit.location || (position == edit.location && side < 0) { return position }
            if position >= NSMaxRange(edit) { return position + delta }
            return edit.location + (side < 0 ? 0 : replacementLength)
        }
        range.start = map(range.start, side: -1); range.end = map(range.end, side: 1)
        range.nameStart = map(range.nameStart, side: -1); range.nameEnd = map(range.nameEnd, side: 1)
        range.bodyStart = map(range.bodyStart, side: -1); range.bodyEnd = map(range.bodyEnd, side: 1)
        var next = self; next.active = range
        return next
    }

    /// Web `followNameOnLeaving`: when the caret leaves a range whose numbers were edited, its name follows them.
    /// Returns the name's span and the new name, or nil when nothing should change.
    public func followedName(text: String, selection: NSRange, focused: Bool, table: [CompositionRanges.Entry]) -> (range: NSRange, name: String)? {
        guard let previous = active, pendingName else { return nil }
        guard let range = CompositionRanges.scan(text).first(where: { $0.start == previous.start }), range.bounds != nil,
              !(focused && Self.contains(range, selection)) else { return nil }
        let edited = CompositionRanges.edit(text, range: range, body: range.body, table: table)
        let ns = text as NSString, nextNS = edited.source as NSString
        let current = ns.substring(with: NSRange(location: range.nameStart, length: range.nameEnd - range.nameStart))
        let name = nextNS.substring(with: NSRange(location: edited.range.nameStart, length: edited.range.nameEnd - edited.range.nameStart))
        return name == current ? nil : (NSRange(location: range.nameStart, length: range.nameEnd - range.nameStart), name)
    }
}
