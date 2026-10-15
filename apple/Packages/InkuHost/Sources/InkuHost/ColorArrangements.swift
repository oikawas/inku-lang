import CryptoKit
import Foundation
#if canImport(FoundationXML)
import FoundationXML
#endif

/// Server color_arrangements.py: distinct visible assignments, spread across the whole permutation space.
public struct ColorArrangementIndex: Sendable {
    public let palette: [String]
    public let used: [String]
    public let total: UInt64
    private let identityRank: UInt64
    private let start: UInt64

    public init(svg: String, colorMap: Data, workID: String) throws {
        let map = try ExactJSON(data: colorMap)
        let colors = try (map.object ?? [:]).filter { $0.key.hasPrefix("palette:") }.map { _, value in
            guard let color = Self.hex(value.string) else { throw HostError("saved_color_catalog_unavailable") }
            return color
        }
        palette = Array(Set(colors)).sorted()
        guard !palette.isEmpty else { throw HostError("saved_color_catalog_unavailable") }
        let reader = PaintReader(palette: Set(palette))
        let parser = XMLParser(data: Data(svg.utf8)); parser.delegate = reader
        parser.shouldResolveExternalEntities = false
        guard parser.parse() else { throw HostError("saved_svg_unavailable") }
        used = reader.paints.sorted()
        total = try Self.permutations(palette.count, used.count) - 1
        var remaining = palette
        var rank: UInt64 = 0
        for (position, color) in used.enumerated() {
            let digit = remaining.firstIndex(of: color)!
            rank += UInt64(digit) * (try Self.permutations(remaining.count - 1, used.count - position - 1))
            remaining.remove(at: digit)
        }
        identityRank = rank
        start = SHA256.hash(data: Data(workID.utf8)).prefix(8).reduce(UInt64(0)) { ($0 << 8) | UInt64($1) }
    }

    public func substitution(at index: UInt64) throws -> [String: String] {
        guard index < total else { throw HostError("color_arrangement_exhausted") }
        var stride = max(1, UInt64((Double(total) * ((sqrt(5) - 1) / 2)).rounded(.toNearestOrEven)))
        while Self.gcd(stride, total) != 1 { stride += 1 }
        let product = index.multipliedFullWidth(by: stride)
        let step = total.dividingFullWidth(product).remainder
        let spread = Self.addModulo(start % total, step, total)
        var rank = spread + (spread >= identityRank ? 1 : 0)
        var remaining = palette
        var result: [String: String] = [:]
        for (position, color) in used.enumerated() {
            let block = try Self.permutations(remaining.count - 1, used.count - position - 1)
            let digit = Int(rank / block); rank %= block
            result[color] = remaining.remove(at: digit)
        }
        return result
    }

    public func colorMap(_ parent: Data, at index: UInt64) throws -> Data {
        let substitution = try substitution(at: index)
        let parent = try ExactJSON(data: parent)
        var result: [String: ExactJSON] = [:]
        var previous: [String: String] = [:]
        for (key, value) in parent.object ?? [:] {
            if key.hasPrefix("recolor:") {
                guard let from = Self.hex(String(key.dropFirst(8))), let to = Self.hex(value.string) else {
                    throw HostError("saved_color_arrangement_invalid")
                }
                previous[from] = to
            } else { result[key] = value }
        }
        let originals = Set(result.values.compactMap { Self.hex($0.string) }).union(previous.keys)
        for original in originals {
            let current = previous[original] ?? original
            let target = substitution[current] ?? current
            if target != original { result["recolor:" + original] = .string(target) }
        }
        return ExactJSON.object(result).data
    }

    private static func hex(_ text: String?) -> String? {
        guard var text = text?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), text.first == "#" else { return nil }
        let body = text.dropFirst()
        guard [3, 6].contains(body.count), body.allSatisfy({ "0123456789abcdef".contains($0) }) else { return nil }
        if body.count == 3 { text = "#" + body.map { "\($0)\($0)" }.joined() }
        return text
    }

    private static func permutations(_ n: Int, _ k: Int) throws -> UInt64 {
        guard k >= 0, k <= n else { throw HostError("saved_color_catalog_invalid") }
        var result: UInt64 = 1
        for position in 0..<k {
            let next = result.multipliedReportingOverflow(by: UInt64(n - position))
            guard !next.overflow else { throw HostError("color_arrangement_space_too_large") }
            result = next.partialValue
        }
        return result
    }

    private static func gcd(_ a: UInt64, _ b: UInt64) -> UInt64 {
        var a = a; var b = b
        while b != 0 { (a, b) = (b, a % b) }
        return a
    }

    private static func addModulo(_ a: UInt64, _ b: UInt64, _ modulus: UInt64) -> UInt64 {
        a >= modulus - b ? a - (modulus - b) : a + b
    }

    private final class PaintReader: NSObject, XMLParserDelegate {
        let palette: Set<String>
        var paints: Set<String> = []
        init(palette: Set<String>) { self.palette = palette }
        func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?,
                    qualifiedName qName: String?, attributes attributeDict: [String: String]) {
            var attributes = attributeDict
            for declaration in (attributes["style"] ?? "").split(separator: ";") {
                let pair = declaration.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
                if pair.count == 2 { attributes[pair[0].trimmingCharacters(in: .whitespaces)] = pair[1].trimmingCharacters(in: .whitespaces) }
            }
            for key in ["fill", "stroke", "stop-color", "flood-color", "lighting-color", "color"] {
                if let color = ColorArrangementIndex.hex(attributes[key]), palette.contains(color) { paints.insert(color) }
            }
        }
    }
}
