import Foundation
import InkuCore

/// A core-owned ordinal. Decimal transport preserves u128 values on macOS 14.
public struct SavedVariantOrdinal: Hashable, Sendable, CustomStringConvertible, ExpressibleByIntegerLiteral {
    public typealias IntegerLiteralType = UInt64
    public let rawValue: String
    public var description: String { rawValue }
    public init(_ value: UInt64) { rawValue = String(value) }
    public init(integerLiteral value: UInt64) { self.init(value) }
    public init?(rawValue: String) {
        guard !rawValue.isEmpty, rawValue.utf8.allSatisfy({ (48...57).contains($0) }) else { return nil }
        self.rawValue = rawValue
    }

    /// A one-based label only; candidate selection and pagination belong to core.
    public var displayNumber: String {
        var digits = Array(rawValue.utf8)
        for index in digits.indices.reversed() {
            if digits[index] < 57 {
                digits[index] += 1
                return String(decoding: digits, as: UTF8.self)
            }
            digits[index] = 48
        }
        return "1" + String(decoding: digits, as: UTF8.self)
    }

    var json: ExactJSON { .string(rawValue) }
    static func read(_ value: ExactJSON) throws -> Self {
        guard let text = value.number ?? value.string, let ordinal = Self(rawValue: text) else {
            throw HostError("invalid_saved_variant_ordinal")
        }
        return ordinal
    }
}

public struct SavedVariantRefusal: Error, LocalizedError, Sendable, Equatable {
    public let reason: String
    public let detail: String
    public var errorDescription: String? { detail }
}

/// The single wire boundary for shared saved-variant rules.
public enum SavedVariants {
    public static func response(_ request: ExactJSON) throws -> ExactJSON {
        let result = try ExactJSON(data: InkuCore.savedVariants(request.data))
        guard result["schema"].string == "inku.saved-variants.v1" else {
            throw HostError("invalid_saved_variant_response")
        }
        switch result["outcome"].string {
        case "ok": return result
        case "refused":
            throw SavedVariantRefusal(reason: try result.requiredString("reason"), detail: try result.requiredString("detail"))
        default: throw HostError("invalid_saved_variant_response")
        }
    }

    public static func groundMaterials() throws -> [GroundMaterial] {
        let result = try response(.object(["action": .string("ground_plan"), "score": .object([:])]))
        return try (result["entries"].array ?? []).map(GroundMaterial.init(coreEntry:))
    }
}
