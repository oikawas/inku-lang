import Foundation

/// Presentation vocabulary shared with web/src/lib/draw-route.ts and sketch.ts.
enum DrawPresentation {
    struct Step { let label: String; let kind: String }
    static func flow(route: String, sketch: Bool, composition: Bool, japanese: Bool) -> [Step] {
        func step(_ ja: String, _ en: String, _ kind: String) -> Step { Step(label: japanese ? ja : en, kind: kind) }
        var result = [step("記述", "Description", "end")]
        if sketch { result.append(step("写生", "Sketch", "switch")) }
        if route == "stages" {
            result += [step("型を埋める", "Fill the plan", "fixed"), step("構図と法則", "Composition and laws", "fixed"), step("配色", "Colors", "fixed")]
        } else {
            if composition { result.append(step("構図と法則", "Composition and laws", "switch")) }
            result += [step("言葉で書く", "Write in words", "fixed"), step("見て直す", "Look and correct", "fixed")]
            if composition { result.append(step("配色", "Colors", "switch")) }
        }
        result.append(step("画", "Picture", "end"))
        return result
    }
    static func readingNote(_ state: String?, japanese: Bool) -> String {
        let pair: (String, String)
        switch state {
        case "read": pair = ("記述を読み、その読みで書いた", "The description was read, and written from the reading")
        case "supplied": pair = ("作者が直した読みで書いた", "Written from the author's edited reading")
        case "fallback": pair = ("読みが届かず、記述だけから書いた", "The reading did not answer, so it was written from the description alone")
        case "pending": pair = ("読んでいる途中", "Reading")
        default: pair = ("読まずに記述だけから書いた", "Written from the description alone, without a reading")
        }
        return japanese ? pair.0 : pair.1
    }
    static func sketchShort(_ state: String?, japanese: Bool) -> String {
        let pair: (String, String)
        switch state {
        case "fine", "coarse", "supplemented": pair = ("通した", "On")
        case "not_needed": pair = ("通した（補いなし）", "On, nothing added")
        case "fallback": pair = ("届かず", "No answer")
        case "off": pair = ("通さない", "Off")
        case "not_applicable": pair = ("対象外", "Not applicable")
        default: pair = ("記録なし", "Not recorded")
        }
        return japanese ? pair.0 : pair.1
    }
    static func sketchNote(_ state: String?, japanese: Bool) -> String {
        let pair: (String, String)
        switch state {
        case "fine", "coarse": return sketchShort(state, japanese: japanese)
        case "supplemented": pair = ("記述に足りない場所の広がりや季節・時刻の光を補って描いた", "The layer supplemented the extent of place or the seasonal or time-of-day light the description left out")
        case "not_needed": pair = ("写生を通したが、補うものがなかった", "The layer ran and found nothing to add")
        case "fallback": pair = ("写生を試みたが届かず、記述のまま解釈した", "The layer was tried, did not answer, and the description was read as it stood")
        case "off": pair = ("写生を通さずに描いた", "Drawn without the layer")
        case "not_applicable": pair = ("この経路は写生を通らない", "This path does not go through the layer")
        default: pair = ("写生が記録される前に描かれた（切って描いたのではない）", "Drawn before the layer was recorded, which is not the same as off")
        }
        return japanese ? pair.0 : pair.1
    }
}
