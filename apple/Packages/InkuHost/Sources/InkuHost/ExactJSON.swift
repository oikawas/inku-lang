import Foundation
import InkuCore

private final class ExactJSONStringCodec: @unchecked Sendable {
    static let shared = ExactJSONStringCodec()
    private let lock = NSLock()
    private let encoder: JSONEncoder = {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.withoutEscapingSlashes]; return encoder
    }()
    private let decoder = JSONDecoder()
    func encode(_ value: String) -> String {
        lock.withLock { String(decoding: try! encoder.encode(value), as: UTF8.self) }
    }
    func decode(_ bytes: Data) throws -> String {
        try lock.withLock { try decoder.decode(String.self, from: bytes) }
    }
}

/// JSON transport values retain number lexemes instead of rounding through Double.
public indirect enum ExactJSON: Sendable, Equatable {
    case object([String: ExactJSON])
    case array([ExactJSON])
    case string(String)
    case number(String)
    case bool(Bool)
    case null

    public init(data: Data) throws {
        var parser = JSONParser(bytes: Array(data))
        self = try parser.value(depth: 0)
        parser.whitespace()
        guard parser.index == parser.bytes.count else { throw HostError("invalid_json") }
    }

    public var data: Data { Data(text.utf8) }
    /// Indent without changing numeric lexemes, and sort object keys as in `text`.
    public var prettyText: String { prettyText(depth: 0) }

    private func prettyText(depth: Int) -> String {
        let current = String(repeating: "  ", count: depth)
        let next = String(repeating: "  ", count: depth + 1)
        switch self {
        case .object(let fields) where !fields.isEmpty:
            let rows = fields.keys.sorted().map { next + Self.quote($0) + " : " + fields[$0]!.prettyText(depth: depth + 1) }
            return "{\n" + rows.joined(separator: ",\n") + "\n" + current + "}"
        case .array(let values) where !values.isEmpty:
            return "[\n" + values.map { next + $0.prettyText(depth: depth + 1) }.joined(separator: ",\n") + "\n" + current + "]"
        default: return text
        }
    }
    /// Select transport bytes without changing object member order or number spelling.
    public static func rawMember(_ key: String, in data: Data) throws -> Data {
        _ = try Self(data: data)
        var parser = JSONParser(bytes: Array(data)); parser.whitespace()
        guard parser.take(123) else { throw HostError("pipeline_schema_violation") }
        parser.whitespace()
        if !parser.take(125) {
            while true {
                parser.whitespace(); let name = try parser.string()
                parser.whitespace(); guard parser.take(58) else { throw HostError("invalid_json") }
                parser.whitespace(); let start = parser.index
                _ = try parser.value(depth: 1)
                if name == key { return Data(parser.bytes[start..<parser.index]) }
                parser.whitespace()
                if parser.take(125) { break }
                guard parser.take(44) else { throw HostError("invalid_json") }
            }
        }
        throw HostError("pipeline_schema_violation")
    }

    /// The caller has already parsed the whole document. Scan without decoding large skipped values.
    static func rawMemberValidated(_ key: String, in data: Data) throws -> Data {
        var parser = JSONParser(bytes: Array(data)); parser.whitespace()
        guard parser.take(123) else { throw HostError("pipeline_schema_violation") }
        parser.whitespace()
        if !parser.take(125) {
            while true {
                parser.whitespace(); let name = try parser.string()
                parser.whitespace(); guard parser.take(58) else { throw HostError("invalid_json") }
                parser.whitespace(); let start = parser.index
                try parser.skipValidatedValue()
                if name == key { return Data(parser.bytes[start..<parser.index]) }
                parser.whitespace()
                if parser.take(125) { break }
                guard parser.take(44) else { throw HostError("invalid_json") }
            }
        }
        throw HostError("pipeline_schema_violation")
    }

    /// Split a validated JSON array into its unchanged element bytes.
    public static func rawElements(in data: Data) throws -> [Data] {
        _ = try Self(data: data)
        var parser = JSONParser(bytes: Array(data)); parser.whitespace()
        guard parser.take(91) else { throw HostError("pipeline_schema_violation") }
        parser.whitespace(); if parser.take(93) { return [] }
        var elements: [Data] = []
        while true {
            parser.whitespace(); let start = parser.index
            _ = try parser.value(depth: 1)
            elements.append(Data(parser.bytes[start..<parser.index]))
            parser.whitespace(); if parser.take(93) { return elements }
            guard parser.take(44) else { throw HostError("invalid_json") }
        }
    }
    /// Shared identity serialization; `text` remains the exact-lexeme transport representation.
    public var canonicalText: String? { InkuCore.canonicalJSON(text) }
    public var text: String {
        switch self {
        case .object(let fields):
            return "{" + fields.keys.sorted().map { Self.quote($0) + ":" + fields[$0]!.text }.joined(separator: ",") + "}"
        case .array(let values): return "[" + values.map(\.text).joined(separator: ",") + "]"
        case .string(let value): return Self.quote(value)
        case .number(let value): return value
        case .bool(let value): return value ? "true" : "false"
        case .null: return "null"
        }
    }

    /// `text`, except that a schema object naming `propertyOrdering` writes its `properties` in that order
    /// (the rest sorted after them), as Server's Gemini projection does. Gemini generates in this order.
    public var orderedText: String {
        switch self {
        case .object(let fields):
            return "{" + fields.keys.sorted().map { key in
                let value = fields[key]!
                if key == "properties", let names = fields["propertyOrdering"]?.array?.compactMap(\.string),
                   case .object(let properties) = value {
                    let named = names.reduce(into: [String]()) { if properties[$1] != nil && !$0.contains($1) { $0.append($1) } }
                    let order = named + properties.keys.sorted().filter { !named.contains($0) }
                    return Self.quote(key) + ":{" + order.map { Self.quote($0) + ":" + properties[$0]!.orderedText }.joined(separator: ",") + "}"
                }
                return Self.quote(key) + ":" + value.orderedText
            }.joined(separator: ",") + "}"
        case .array(let values): return "[" + values.map(\.orderedText).joined(separator: ",") + "]"
        default: return text
        }
    }

    /// Python `json.dumps(value, ensure_ascii=False, sort_keys=True)`: ", " and ": " separators, keys in
    /// code point order, and only quotes, backslashes and control characters escaped. Server writes the
    /// auxiliary prompts' context in this form.
    public var pythonText: String {
        switch self {
        case .object(let fields):
            let keys = fields.keys.sorted { $0.unicodeScalars.map(\.value).lexicographicallyPrecedes($1.unicodeScalars.map(\.value)) }
            return "{" + keys.map { Self.pythonQuote($0) + ": " + fields[$0]!.pythonText }.joined(separator: ", ") + "}"
        case .array(let values): return "[" + values.map(\.pythonText).joined(separator: ", ") + "]"
        case .string(let value): return Self.pythonQuote(value)
        default: return text
        }
    }
    private static func pythonQuote(_ value: String) -> String {
        var result = "\""
        for scalar in value.unicodeScalars {
            switch scalar {
            case "\"": result += "\\\""
            case "\\": result += "\\\\"
            case "\n": result += "\\n"
            case "\r": result += "\\r"
            case "\t": result += "\\t"
            case "\u{08}": result += "\\b"
            case "\u{0C}": result += "\\f"
            default:
                if scalar.value < 0x20 { result += String(format: "\\u%04x", scalar.value) }
                else { result.unicodeScalars.append(scalar) }
            }
        }
        return result + "\""
    }

    public subscript(_ key: String) -> ExactJSON {
        get { if case .object(let fields) = self { fields[key] ?? .null } else { .null } }
        set { if case .object(var fields) = self { fields[key] = newValue; self = .object(fields) } }
    }
    public var string: String? { if case .string(let value) = self { value } else { nil } }
    public var number: String? { if case .number(let value) = self { value } else { nil } }
    public var bool: Bool? { if case .bool(let value) = self { value } else { nil } }
    public var array: [ExactJSON]? { if case .array(let value) = self { value } else { nil } }
    public var object: [String: ExactJSON]? { if case .object(let value) = self { value } else { nil } }
    public func requiredString(_ key: String) throws -> String {
        guard let value = self[key].string else { throw HostError("pipeline_schema_violation") }
        return value
    }
    public func requiredObject(_ key: String) throws -> ExactJSON {
        guard self[key].object != nil else { throw HostError("pipeline_schema_violation") }
        return self[key]
    }
    public static func optional(_ value: String?) -> ExactJSON { value.map(Self.string) ?? .null }
    public static func integer(_ value: some BinaryInteger) -> ExactJSON { .number(String(value)) }
    private static func quote(_ value: String) -> String {
        // Restrict the fast path to unambiguous ASCII; the encoder handles all other cases.
        if value.utf8.allSatisfy({ $0 >= 0x20 && $0 < 0x7f && $0 != 34 && $0 != 92 }) {
            return "\"" + value + "\""
        }
        return ExactJSONStringCodec.shared.encode(value)
    }
}

private struct JSONParser {
    let bytes: [UInt8]
    var index = 0
    mutating func whitespace() {
        while index < bytes.count && [9, 10, 13, 32].contains(bytes[index]) { index += 1 }
    }
    mutating func value(depth: Int) throws -> ExactJSON {
        whitespace()
        guard depth < 256, index < bytes.count else { throw HostError("invalid_json") }
        switch bytes[index] {
        case 123:
            index += 1; whitespace()
            var fields: [String: ExactJSON] = [:]
            if take(125) { return .object(fields) }
            while true {
                whitespace()
                let key = try string()
                guard fields[key] == nil else { throw HostError("duplicate_json_key") }
                whitespace(); guard take(58) else { throw HostError("invalid_json") }
                fields[key] = try value(depth: depth + 1)
                whitespace()
                if take(125) { return .object(fields) }
                guard take(44) else { throw HostError("invalid_json") }
            }
        case 91:
            index += 1; whitespace()
            var values: [ExactJSON] = []
            if take(93) { return .array(values) }
            while true {
                values.append(try value(depth: depth + 1)); whitespace()
                if take(93) { return .array(values) }
                guard take(44) else { throw HostError("invalid_json") }
            }
        case 34: return .string(try string())
        case 116: try literal("true"); return .bool(true)
        case 102: try literal("false"); return .bool(false)
        case 110: try literal("null"); return .null
        default:
            let start = index
            _ = take(45)
            if !take(48) {
                guard index < bytes.count, (49...57).contains(bytes[index]) else { throw HostError("invalid_json") }
                digits()
            }
            if take(46) {
                let before = index; digits()
                guard index > before else { throw HostError("invalid_json") }
            }
            if take(101) || take(69) {
                if !take(43) { _ = take(45) }
                let before = index; digits()
                guard index > before else { throw HostError("invalid_json") }
            }
            return .number(String(decoding: bytes[start..<index], as: UTF8.self))
        }
    }
    mutating func skipValidatedValue() throws {
        guard index < bytes.count else { throw HostError("invalid_json") }
        var nesting = 0
        var inString = false
        var escaped = false
        while index < bytes.count {
            let byte = bytes[index]
            if inString {
                index += 1
                if escaped { escaped = false }
                else if byte == 92 { escaped = true }
                else if byte == 34 { inString = false; if nesting == 0 { return } }
                continue
            }
            if byte == 34 { inString = true; index += 1; continue }
            if byte == 123 || byte == 91 { nesting += 1; index += 1; continue }
            if byte == 125 || byte == 93 {
                if nesting == 0 { return }
                nesting -= 1; index += 1
                if nesting == 0 { return }
                continue
            }
            if nesting == 0 && (byte == 44 || byte == 32 || byte == 9 || byte == 10 || byte == 13) { return }
            index += 1
        }
        guard !inString, nesting == 0 else { throw HostError("invalid_json") }
    }
    mutating func digits() { while index < bytes.count && (48...57).contains(bytes[index]) { index += 1 } }
    mutating func take(_ byte: UInt8) -> Bool {
        guard index < bytes.count, bytes[index] == byte else { return false }
        index += 1; return true
    }
    mutating func literal(_ text: String) throws {
        let expected = Array(text.utf8)
        guard index + expected.count <= bytes.count,
              Array(bytes[index..<(index + expected.count)]) == expected else { throw HostError("invalid_json") }
        index += expected.count
    }
    mutating func string() throws -> String {
        let start = index
        guard take(34) else { throw HostError("invalid_json") }
        var plainASCII = true
        while index < bytes.count {
            if take(34) {
                if plainASCII { return String(decoding: bytes[(start + 1)..<(index - 1)], as: UTF8.self) }
                do { return try ExactJSONStringCodec.shared.decode(Data(bytes[start..<index])) }
                catch { throw HostError("invalid_json") }
            }
            if bytes[index] < 0x20 || bytes[index] >= 0x7f { plainASCII = false }
            if take(92) { plainASCII = false; guard index < bytes.count else { throw HostError("invalid_json") }; index += 1 }
            else { index += 1 }
        }
        throw HostError("invalid_json")
    }
}
