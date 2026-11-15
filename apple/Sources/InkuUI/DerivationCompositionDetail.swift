import Foundation
import InkuHost
import InkuPersistence

@MainActor
func compositionDerivationName(_ kind: String, display: DisplaySettings) -> String {
    switch kind {
    case "replay": return display.label("再描画", "Replay")
    case "tool_change": return display.label("てざわり", "Touches")
    case "ground_change": return display.label("支持体", "Ground")
    case "catalog_change": return display.label("色", "Color")
    case "color_arrangement_change": return display.label("配色", "Color arrangement")
    case "canvas_fit": return display.label("はめ込み", "Fit")
    case "layout_change": return display.label("配置", "Layout")
    case "composition_form_change": return display.label("構図と法則", "Composition and laws")
    default: return kind
    }
}

@MainActor
func compositionDerivationDetail(_ edge: LineageEdge?, display: DisplaySettings) -> String? {
    guard let edge, let metadata = try? ExactJSON(data: Data(edge.metadataJSON.utf8)) else { return nil }
    let language = display.preferences.language
    if edge.derivationKind == "layout_change" {
        let place = metadata["place"]
        guard let title = place["title"].string, !title.isEmpty, let to = place["at"].string, !to.isEmpty else { return nil }
        let from = place["at_from"].string.flatMap { $0.isEmpty ? nil : CompositionNames.placeName($0, language: language) }
            ?? display.label("置き場の外", "off the places")
        return "\(title): \(from) → \(CompositionNames.placeName(to, language: language))"
    }
    guard edge.derivationKind == "composition_form_change" else { return nil }
    if let to = metadata["thesis_to"].string, !to.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        func head(_ s: String) -> String { let t = s.trimmingCharacters(in: .whitespacesAndNewlines); return t.unicodeScalars.count > 14 ? String(String.UnicodeScalarView(t.unicodeScalars.prefix(14))) + "…" : t }
        let from = metadata["thesis_from"].string.flatMap { $0.isEmpty ? nil : head($0) } ?? "—"
        return "\(display.webCopy("compositionThesisLabel", "命題")): \(from) → \(head(to))"
    }
    if let from = metadata["main_law_from"].string, !from.isEmpty, let to = metadata["main_law_to"].string, !to.isEmpty {
        return "\(display.webCopy("compositionMainLawTerm", "主の法則")): \(CompositionNames.lawName(from, language: language)) → \(CompositionNames.lawName(to, language: language))"
    }
    if let from = metadata["form_from"].string, !from.isEmpty, let to = metadata["form_to"].string, !to.isEmpty {
        return "\(display.webCopy("compositionFormTerm", "画の型")): \(CompositionNames.formName(from, language: language)) → \(CompositionNames.formName(to, language: language))"
    }
    return nil
}
