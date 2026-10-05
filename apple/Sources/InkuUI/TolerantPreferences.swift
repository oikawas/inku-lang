import Foundation

/// Reads a local preference file key by key so an added, removed or retyped field
/// falls back to its default instead of discarding every other saved choice.
enum TolerantPreferences {
    static func decode<T: Codable>(_ type: T.Type, from data: Data, defaults: T) throws -> T {
        guard let saved = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw CocoaError(.coderReadCorrupt)
        }
        var merged = try JSONSerialization.jsonObject(with: JSONEncoder().encode(defaults)) as? [String: Any] ?? [:]
        for key in saved.keys.sorted() {
            var candidate = merged
            candidate[key] = saved[key]
            if (try? decodeObject(type, candidate)) != nil { merged = candidate }
        }
        return try decodeObject(type, merged)
    }

    /// Keeps an unreadable file beside the new one instead of overwriting it on the next save.
    static func setAside(_ url: URL) {
        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "")
        let target = url.deletingLastPathComponent().appendingPathComponent("\(url.lastPathComponent).unreadable-\(stamp)")
        try? FileManager.default.copyItem(at: url, to: target)
    }

    private static func decodeObject<T: Decodable>(_ type: T.Type, _ object: [String: Any]) throws -> T {
        try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: object))
    }
}
