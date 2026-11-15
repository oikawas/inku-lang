import InkuHost

@MainActor
enum PlacePresentation {
    static func title(unit: ExactJSON, place: String, display: DisplaySettings) -> String {
        let name = CompositionNames.placeName(place, language: display.preferences.language)
        if unit["at"].string == place {
            let now = display.webCopy("compositionTargetNow", "今")
            return name + display.label("（\(now)）", " (\(now))")
        }
        let state = unit["places"][place].string ?? "no_chunk"
        if state == "ok" { return name }
        if state == "clamped" { return name + display.webCopy("placeClamped", "（画面の端で止まる）") }
        let reason: String
        switch state {
        case "unchanged": reason = display.label("今の置き場です", "It is already here")
        case "too_large": reason = display.label("画面より大きい物は動かせません", "A thing larger than the canvas cannot move")
        case "leaves_canvas": reason = display.label("動かすと画面からはみ出します", "Moving it there leaves the canvas")
        case "scene_word": reason = display.label("情景の語は動かせません", "A scene word cannot move")
        case "no_numeric_place": reason = display.label("位置を数で書いていない文があります", "Some of its sentences have no numeric place")
        case "fitted": reason = display.label("紙にはめ込んだ作品では動かせません", "A work fitted onto its paper cannot move things")
        case "no_chunk": reason = display.label("この物は指示書にありません", "The instructions have no such thing")
        case "undrawable": reason = display.label("そこへ動かすと描かれない文が出ます", "Moved there, a sentence would not be drawn")
        default: reason = display.webCopyFormat("placeRefused", "動かせません（%@）", state)
        }
        return name + ": " + reason
    }
    static func label(what: String, unit: ExactJSON, place: String, display: DisplaySettings) -> String {
        what + " → " + CompositionNames.placeName(place, language: display.preferences.language)
            + (unit["places"][place].string == "clamped" ? display.webCopy("placeClamped", "（画面の端で止まる）") : "")
    }
}
