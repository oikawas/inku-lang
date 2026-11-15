import Foundation
import InkuCore

/// Composition vocabulary comes from the same core as the saved records.
@MainActor public enum CompositionNames {
    private static let table = (try? JSONSerialization.jsonObject(with: InkuCore.compositionNames())) as? [String: Any] ?? [:]

    public static var formIDs: [String] {
        (table["forms"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? String }
    }

    public static var mainLawIDs: [String] {
        (table["laws"] as? [[String: Any]] ?? []).filter { $0["main"] as? Bool == true }.compactMap { $0["code"] as? String }
    }

    private static func value(_ section: String, _ key: String, _ field: String, language: String, fallback: String) -> String {
        let rows = table[section] as? [[String: Any]] ?? []
        guard let row = rows.first(where: { ($0["id"] as? String ?? $0["code"] as? String) == key }),
              let text = row[field] as? [String: String] else { return fallback }
        return text[language == "ja" ? "ja" : "en"] ?? fallback
    }

    public static func formName(_ id: String, language: String) -> String { value("forms", id, "name", language: language, fallback: id) }
    public static func formDescription(_ id: String, language: String) -> String { value("forms", id, "description", language: language, fallback: id) }
    public static func lawName(_ id: String, language: String) -> String { value("laws", id, "name", language: language, fallback: id) }
    public static func lawFamily(_ id: String, language: String) -> String { value("laws", id, "family", language: language, fallback: id) }
    public static func lawSummary(_ id: String, language: String) -> String { value("laws", id, "summary", language: language, fallback: id) }
    public static func colorLawName(_ id: String, language: String) -> String { value("color_laws", id, "name", language: language, fallback: id) }
    public static func roleName(_ id: String, language: String) -> String { value("roles", id, "name", language: language, fallback: id) }
    public static func kindName(_ id: String, language: String) -> String { value("kinds", id, "name", language: language, fallback: id) }
    public static func atName(_ id: String, language: String) -> String { value("at", id, "name", language: language, fallback: id) }
    public static func placeName(_ id: String, language: String) -> String { value("places", id, "name", language: language, fallback: id) }
}
