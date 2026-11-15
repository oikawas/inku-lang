import InkuHost
import InkuPersistence
import SwiftUI

/// The saved composition between the sketch and instructions, following the Web's folded section.
@MainActor
struct CompositionSection: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let snapshot: CompositionRecordSnapshot?
    let saved: Bool
    let disabled: Bool
    let onAction: (SavedWork, String) -> Void
    private var display: DisplaySettings { model.display }
    private var language: String { display.preferences.language }
    private var inherited: Bool { snapshot?.own == nil && snapshot?.inherited != nil }
    private var record: ExactJSON? { snapshot?.own ?? snapshot?.inherited }
    private var answer: ExactJSON? { record?["answer"].object == nil ? nil : record?["answer"] }
    private var fallback: Bool { record?["state"].string == "fallback" }
    private var open: Binding<Bool> { Binding(get: { display.preferences.compositionExpanded ?? false }, set: { display.preferences.compositionExpanded = $0 }) }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            DisclosureGroup(isExpanded: open) {
                if let answer {
                    if model.workActionState(for: work) != .userDDL {
                      HStack {
                        if model.workActionState(for: work)?.showsDescriptionActions == true {
                            Button(display.webCopy("workActionComposition", "構図と法則を変える")) { onAction(work, "composition-form") }
                                .disabled(disabled || model.workActionState(for: work)?.canReadDescription != true)
                        }
                        Button(display.webCopy("canvasVaryComposition", "配置を変える")) { onAction(work, "layout") }.disabled(disabled)
                      }.buttonStyle(InkuGhostButtonStyle())
                    }
                    details(answer).padding(.top, 6)
                } else {
                    Text(display.webCopy(fallback ? "compositionFallback" : "compositionNoRecordNote", fallback ? "構図なし" : "構図の記録がありません。"))
                        .inkuFont(12).foregroundStyle(.secondary).padding(.top, 6)
                }
            } label: {
                HStack(spacing: 6) {
                    Text(display.webCopy("compositionSectionTitle", "構図と法則")).inkuFont(12, weight: .semibold)
                    Spacer(minLength: 0)
                    if inherited { Text(display.webCopy("compositionInheritedMark", "親の構図")).inkuFont(10) }
                    if let answer {
                        if let form = answer["form"].string { namedFigure(form, name: CompositionNames.formName(form, language: language)) }
                        if let law = answer["main_law"].string { namedFigure(law, name: CompositionNames.lawName(law, language: language)) }
                    } else { Text(display.webCopy(fallback ? "compositionFallback" : "compositionNoRecord", fallback ? "構図なし" : "記録なし")).inkuFont(12) }
                }.foregroundStyle(.secondary)
            }
            if let thesis = answer?["thesis"].string, !thesis.isEmpty {
                Text(thesis).inkuFont(13).lineLimit(open.wrappedValue ? nil : 2).textSelection(.enabled)
            }
        }
        .task(id: [work.id, work.ddl ?? "", open.wrappedValue ? "open" : "closed", answer?.text ?? ""]) {
            guard open.wrappedValue, saved else { model.clearCompositionBoxes(workID: work.id); return }
            await model.loadCompositionBoxes(work: work)
            guard !Task.isCancelled, model.compositionBoxWorkID == work.id else { return }
            var quotes: [String: String] = [:]
            for thing in answer?["things"].array ?? [] {
                if let number = thing["thing"].number, let quote = thing["quote"].string { quotes[number] = quote }
            }
            model.compositionQuotes = quotes
        }
        .onDisappear { model.clearCompositionBoxes(workID: work.id) }
    }

    private func namedFigure(_ id: String, name: String) -> some View {
        HStack(spacing: 3) { CompositionFigure(id: id).frame(width: 20, height: 20); Text(name).inkuFont(12) }
    }

    @ViewBuilder private func details(_ answer: ExactJSON) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if inherited, let source = snapshot?.inherited {
                let kind = compositionDerivationName(source["via"].array?.first?.string ?? "", display: display)
                let date = source["at"].number.flatMap(Double.init).map { Date(timeIntervalSince1970: $0 / 1000).formatted(date: .abbreviated, time: .shortened) } ?? "—"
                Text(display.webCopyFormat("compositionInheritedNote", "この作品は『%@』の子です。下は、親の作品（%@）の構図と法則です。", kind, date))
                    .inkuFont(11).foregroundStyle(.secondary)
            }
            if let form = answer["form"].string { row(display.webCopy("compositionFormTerm", "画の型"), CompositionNames.formName(form, language: language), figure: form) }
            if let law = answer["main_law"].string { row(display.webCopy("compositionMainLawTerm", "主の法則"), CompositionNames.lawName(law, language: language), figure: law) }
            let laws = (answer["laws"].object ?? [:]).keys.sorted().filter { $0 != answer["main_law"].string }
            if !laws.isEmpty { row(display.webCopy("compositionLawsTerm", "法則"), laws.map { CompositionNames.lawName($0, language: language) }.joined(separator: "・")) }
            let colors = record?["colors"]["laws"].array?.compactMap(\.string) ?? []
            if !colors.isEmpty { row(display.webCopy("compositionColorsTerm", "配色"), colors.map { CompositionNames.colorLawName($0, language: language) }.joined(separator: "・")) }
            if let reason = answer["reason"].string, !reason.isEmpty { row(display.webCopy("compositionReasonTerm", "理由"), reason) }
            let things = answer["things"].array ?? []
            if !things.isEmpty {
                Text(display.webCopy("compositionThingsHead", "物")).inkuFont(11).foregroundStyle(.secondary)
                ForEach(Array(things.enumerated()), id: \.offset) { _, thing in
                    let unit = unitFor(thing)
                    let number = thing["thing"].number
                    Button {
                        model.activeCompositionThing = number
                        if let line = unit?["lines"].array?.first?.number.flatMap(Int.init) { model.revealCompositionLine = InkuEditorReveal(line: line) }
                    } label: { HStack(alignment: .top, spacing: 8) {
                        Text(thing["thing"].number ?? "").inkuFont(11)
                        Text(CompositionNames.roleName(thing["role"].string ?? "", language: language)).inkuFont(11).foregroundStyle(.secondary)
                        VStack(alignment: .leading) {
                            Text(thing["what"].string ?? "").inkuFont(12)
                            if let number = thing["thing"].number, let moved = snapshot?.places.first(where: { $0["thing"].number == number }), let at = moved["at"].string {
                                Text(CompositionNames.placeName(at, language: language) + display.webCopy("compositionMovedNote", "（配置を変えて移した）"))
                                    .inkuFont(11).foregroundStyle(.secondary)
                            }
                            if let quote = thing["quote"].string {
                                HStack(spacing: 4) {
                                    Text("「\(quote)」")
                                    if plain(quote).isEmpty || !plain(work.effectiveSourceText).contains(plain(quote)) {
                                        Text(display.webCopy("compositionFromReading", "読みから"))
                                    }
                                }.inkuFont(11).foregroundStyle(.secondary)
                            }
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle()) }
                    .buttonStyle(.plain).onHover { inside in model.activeCompositionThing = inside ? number : nil }
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func plain(_ value: String) -> String { value.filter { !$0.isWhitespace && $0 != "　" } }

    private func unitFor(_ thing: ExactJSON) -> ExactJSON? {
        guard model.compositionBoxWorkID == work.id else { return nil }
        let number = thing["thing"].number
        let quote = thing["quote"].string
        return model.compositionUnits.first { unit in
            (number != nil && unit["thing"].number == number) || (quote != nil && unit["title"].string == quote)
        }
    }

    private func row(_ title: String, _ value: String, figure: String? = nil) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(title).inkuFont(11).foregroundStyle(.secondary).frame(width: 70, alignment: .leading)
            if let figure { CompositionFigure(id: figure).frame(width: 22, height: 22) }
            Text(value).inkuFont(12).frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
