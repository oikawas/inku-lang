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
        let reason = display.webCopy("placeRefused." + state, display.webCopyFormat("placeRefused", "動かせません（%@）", state))
        return name + ": " + reason
    }
    static func label(what: String, unit: ExactJSON, place: String, display: DisplaySettings) -> String {
        what + " → " + CompositionNames.placeName(place, language: display.preferences.language)
            + (unit["places"][place].string == "clamped" ? display.webCopy("placeClamped", "（画面の端で止まる）") : "")
    }
}
