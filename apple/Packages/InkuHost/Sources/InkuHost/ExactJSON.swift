import Foundation

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
        // Encoding one string also handles control characters and surrogate pairs.
        let encoder = JSONEncoder(); encoder.outputFormatting = [.withoutEscapingSlashes]
        return String(decoding: try! encoder.encode(value), as: UTF8.self)
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
        while index < bytes.count {
            if take(34) {
                do { return try JSONDecoder().decode(String.self, from: Data(bytes[start..<index])) }
                catch { throw HostError("invalid_json") }
            }
            if take(92) { guard index < bytes.count else { throw HostError("invalid_json") }; index += 1 }
            else { index += 1 }
        }
        throw HostError("invalid_json")
    }
}
