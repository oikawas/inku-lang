import SwiftUI
import InkuHost

/// The saved read-and-draw record, in CanvasGenerationInfo's order and vocabulary.
struct ReadDrawInfoView: View {
    let record: ExactJSON
    let display: DisplaySettings
    private var ja: Bool { display.preferences.language != "en" }
    private func l(_ jaText: String, _ en: String) -> String { ja ? jaText : en }
    private var sep: String { ja ? "、" : ", " }
    private func label(_ value: String?, _ table: [String: (String, String)]) -> String {
        guard let value else { return "" }
        guard let pair = table[value] else { return value }
        return l(pair.0, pair.1)
    }
    private let forms: [String: (String, String)] = ["one_corner": ("一角", "one corner"), "all_over": ("全面", "all over"), "bands": ("横の帯", "bands"), "dividing_line": ("場を分ける線", "dividing line"), "grid": ("格子", "grid"), "flock_and_stray": ("群れと一つの逸脱", "flock and a stray"), "unequal_triangle": ("不等辺の三角", "unequal triangle")]
    private let roles: [String: (String, String)] = ["field": ("場", "field"), "focal": ("主", "focal"), "secondary": ("従", "secondary"), "scattered": ("散在", "scattered"), "accent": ("添え", "accent")]
    private let kinds: [String: (String, String)] = ["cluster": ("1か所の形", "cluster"), "row": ("列", "row"), "surface": ("面", "surface"), "line": ("線", "line")]
    private let measures: [String: (String, String)] = ["ok": ("合う", "fits"), "off": ("少しずれ", "a little off"), "far": ("大きくずれ", "far off"), "fitted": ("合わせた", "fitted"), "clamped": ("範囲の端に合わせた", "clamped"), "off_canvas": ("画の外", "off the canvas"), "unmeasurable": ("測れない", "unmeasurable"), "not_measured": ("測っていない", "not measured")]
    private let figures: [String: (String, String)] = ["speaker": ("語り手", "speaker"), "speaker_part": ("語り手の体の一部", "part of the speaker's body"), "addressee": ("語りかける相手", "addressee"), "third": ("ほかの人", "someone else")]
    private let changes: [String: (String, String)] = ["color_word": ("色の語を書き換えた", "color word rewritten"), "printed": ("数つきで印字し直した", "printed again with numbers"), "ground": ("背景の文を替えた", "background sentence changed"), "ground_added": ("背景の文を足した", "background sentence added")]
    var reading: String { DrawPresentation.readingNote(record["reading_state"].string, japanese: ja) }
    var dropped: [String] {
        let items = (record["dropped_items"].array ?? []).map { item in
            [item["kind"].string, item["quote"].string.map { "「\($0)」" }, item["image"].string].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " ")
        }
        let quotes = (record["dropped_quotes"].object ?? [:]).keys.sorted().map { "\($0) 「\(record["dropped_quotes"][$0].string ?? "")」" }
        return items + quotes
    }
    func round(_ r: ExactJSON) -> String {
        let name = r["stage"].string == "review_description_ddl" ? l("見比べ", "Review") : l("書く", "Writing")
        let again = r["asked_again"].bool == true ? l("（聞き直し）", " (asked again)") : ""
        let instructions = r["instructions"].number ?? "0", problems = r["problems"].number ?? "0"
        let count = l("指示 \(instructions)・直す行 \(problems)", "\(instructions) instructions, \(problems) lines to fix")
        let list = (r["figures"].array ?? []).map { label($0["who"].string, figures) + ": " + ($0["what"].string ?? "") }.joined(separator: sep)
        return name + again + " · " + count + (list.isEmpty ? "" : " · " + list)
    }
    func compositionState(_ c: ExactJSON) -> String {
        if c["state"].string == "used" { return l("構図と法則を決め、それに沿って書いた", "A composition and laws were decided, and the DDL was written toward them") }
        if c["state"].string == "fallback" {
            let reason = c["fallback"].string == "refused" ? l("答えが決まりに合わなかった", "the answers broke the rules") : (c["fallback"].string ?? "")
            return l("構図と法則を決められず、構図と法則なしで書いた（\(reason)）", "No composition and laws could be decided, so it was written without them (\(reason))")
        }
        return l("構図と法則を決めている途中", "Deciding the composition and laws")
    }
    func counts(_ values: [String], table: [String: (String, String)]) -> String {
        var order: [String] = []; var tally: [String: Int] = [:]
        for value in values { if tally[value] == nil { order.append(value) }; tally[value, default: 0] += 1 }
        return order.map { "\(label($0, table)) \(tally[$0]!)" }.joined(separator: sep)
    }
    @ViewBuilder private func group<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        GroupBox { VStack(alignment: .leading, spacing: 10, content: content).frame(maxWidth: .infinity, alignment: .leading).padding(6) } label: { Text(title).inkuFont(12, weight: .semibold).foregroundStyle(.secondary) }
    }
    private func row(_ title: String, _ value: String, _ hint: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 16) {
            Text(title).foregroundStyle(.secondary).frame(width: 190, alignment: .leading).inkuTooltip(display.tooltip(title, serverKey: hint))
            Text(value.isEmpty ? "-" : value).frame(maxWidth: .infinity, alignment: .leading)
        }.inkuFont(13)
    }
    @ViewBuilder private func list(_ title: String, _ lines: [String], numbered: Bool = false) -> some View {
        if !lines.isEmpty {
            Text(title).inkuFont(12).foregroundStyle(.secondary)
            ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                Text((numbered ? "\(index + 1). " : "• ") + line).inkuFont(13).frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
    private func pre(_ value: String) -> some View {
        Text(value).font(.system(size: 12, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading).padding(8).background(InkuColor.bg2)
    }
    var body: some View {
        let rounds = record["rounds"].array ?? []
        let reviewed = rounds.contains { $0["stage"].string == "review_description_ddl" }
        let labels = record["source_labels"].array?.compactMap(\.string) ?? []
        VStack(alignment: .leading, spacing: 16) {
            group(l("言葉で描く", "In words")) {
                row(l("描き方", "Drawing"), l("言葉で描く", "In words"), "provenanceHintDrawRoute")
                row(l("読み", "Reading"), reading, "provenanceHintReading")
                row(l("見比べ", "Review"), reviewed ? l("描いた画を見て一度直した", "Corrected once beside its drawing") : l("見比べなし", "Not reviewed"), "provenanceHintReadReview")
                if !labels.isEmpty { row(l("札", "Labels"), labels.joined(separator: " / "), "provenanceHintReadLabels") }
                if let text = record["reading_text"].string, !text.isEmpty { pre(text) }
                list(l("記述と札に無いため落とした項目", "Dropped: not in the description or its labels"), dropped)
                list(l("回の記録", "Rounds"), rounds.map(round), numbered: true)
                if let text = record["before_review"].string, !text.isEmpty { DisclosureGroup(l("見比べる前の指示書", "Instructions before the review")) { pre(text) } }
            }
            if record["composition"].object != nil { composition(record["composition"]) }
        }
    }
    @ViewBuilder private func composition(_ c: ExactJSON) -> some View {
        let answer = c["answer"], things = answer["things"].array ?? []
        let last = c["measures"].array?.last?["after"].array ?? []
        let misses = last.filter { !["ok", "fitted", "clamped", "not_measured"].contains($0["state"].string ?? "") }
        let colors = c["colors"], colorChanges = colors["changes"].array ?? []
        group(l("構図と法則", "Composition and laws")) {
            row(l("状態", "State"), compositionState(c), "provenanceHintComposition")
            if answer.object != nil {
                row(l("命題", "Thesis"), answer["thesis"].string ?? "", "provenanceHintComposition")
                row(l("画の型", "Form"), label(answer["form"].string, forms), "provenanceHintComposition")
                row(l("主の法則", "Main law"), answer["main_law"].string ?? "", "provenanceHintComposition")
                row(l("法則", "Laws"), (answer["laws"].object ?? [:]).keys.sorted().joined(separator: sep), "provenanceHintComposition")
            }
            if !last.isEmpty { row(l("最後の測り", "Last measure"), counts(last.map { $0["state"].string ?? "" }, table: measures), "provenanceHintCompositionMeasure") }
            if let reason = answer["reason"].string, !reason.isEmpty { Text(l("理由", "Reason") + ": " + reason).inkuFont(12).foregroundStyle(.secondary) }
            list(l("物", "Things"), things.map { thing in
                (thing["thing"].number ?? "") + " " + (thing["what"].string ?? "") + " · " + label(thing["role"].string, roles) + " · " + label(thing["kind"].string, kinds) + (thing["quote"].string.map { " · 「\($0)」" } ?? "")
            })
            list(l("法則が決めた目標", "Targets the laws set"), c["targets"].array?.compactMap(\.string) ?? [])
            list(l("合わなかった組", "Pairs that did not fit"), misses.map { m in
                let number = m["thing"].number ?? m["thing"].array?.compactMap(\.number).joined(separator: "・") ?? ""
                let thing = things.first { $0["thing"].number == number }.map { number + "（" + ($0["what"].string ?? "") + "）" } ?? number
                return (m["law"].string ?? "") + " · " + l("物", "thing") + " " + thing + " · " + label(m["state"].string, measures)
            })
            list(l("カード", "Cards"), (c["cards"].array ?? []).map { card in
                (card["law"].string ?? "") + " · " + (card["built"].bool == true ? l("作った", "built") : l("作らなかった", "not built") + (card["reason"].string.map { "（\($0)）" } ?? "")) + (card["motif"].string.map { " · \($0)" } ?? "")
            })
            if colors.object != nil {
                Text(l("配色", "Colors")).inkuFont(12).foregroundStyle(.secondary)
                let reason = colors["fallback"].string ?? ""
                row(l("状態", "State"), colors["state"].string == "used" ? l("配色を選び、当てて確定した", "Colors were chosen and applied before the commit") : l("配色を当てられず、配色の前の指示書で確定した（\(reason)）", "No colors could be applied, so the DDL before them was committed (\(reason))"), "provenanceHintCompositionColors")
                if let law = colors["main_law"].string, !law.isEmpty { row(l("主の法則", "Main law"), law, "provenanceHintCompositionColors") }
                if let laws = colors["laws"].array, !laws.isEmpty { row(l("法則", "Laws"), laws.compactMap(\.string).joined(separator: sep), "provenanceHintCompositionColors") }
                if let ground = colors["ground"].string, !ground.isEmpty { row(l("地", "Ground"), label(ground, ["white": ("白", "white"), "black": ("黒", "black"), "blue": ("青", "blue"), "red": ("赤", "red"), "green": ("緑", "green"), "gray": ("灰", "gray"), "yellow": ("黄", "yellow"), "orange": ("橙", "orange"), "purple": ("紫", "purple")]), "provenanceHintCompositionColors") }
                if !colorChanges.isEmpty {
                    row(l("変えた文", "Lines changed"), counts(colorChanges.map { $0["how"].string ?? "" }, table: changes), "provenanceHintCompositionColors")
                    DisclosureGroup(l("配色が変えた文", "The lines the colors changed")) {
                        ForEach(Array(colorChanges.enumerated()), id: \.offset) { _, change in
                            Text("• " + (change["before"].string.map { $0 + " → " } ?? "") + (change["after"].array?.compactMap(\.string).joined(separator: " ") ?? "")).inkuFont(13)
                        }
                    }
                }
            }
            if let known = c["known"].array, !known.isEmpty {
                DisclosureGroup(l("文ごとの物", "The thing each sentence draws")) {
                    ForEach(Array(known.enumerated()), id: \.offset) { index, sentence in
                        let number = sentence["thing"].number ?? ""
                        let thing = things.first { $0["thing"].number == number }.map { number + "（" + ($0["what"].string ?? "") + "）" } ?? number
                        Text("\(index + 1). " + l("物", "thing") + " " + thing + ": " + (sentence["text"].string ?? "")).inkuFont(13)
                    }
                }
            }
        }
    }
}
