import SwiftUI
import InkuHost
import InkuPersistence

/// Web DdlViewer: the displayed work's instructions in a compact editor (no line numbers). The author edits a
/// draft; drawing happens only through "Draw from instructions". Read-only while drawing or without a saved work.
@MainActor
struct DdlBoxEditor: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let editable: Bool
    @State private var pluginCalls: [PluginCall] = []
    @State private var pluginCallsRevision = 0
    @State private var pluginSource = ""
    @State private var hoverIndex: Int?
    @Environment(\.inkuTooltipsCovered) private var tooltipsCovered
    private var highlighter: DdlHighlighter { model.ddlHighlighter.withCalls(pluginSource == text ? pluginCalls : []) }
    @State private var completionStates: [CompletionRangeState] = []
    @State private var completionSource = ""
    @State private var rangeStatus = RangeEditorStatus()
    /// Web `invalidSource`: an invalid range in the editor, or any unreadable numeric range in the text.
    private var invalidSource: Bool { rangeStatus.invalid || CompositionRanges.scan(text).contains { $0.bounds == nil } }

    init(model: AppModel, work: SavedWork, editable: Bool) {
        self.model = model
        self.work = work
        self.editable = editable
    }

    private var text: String { model.ddlBoxText(for: work) }
    private var activeLines: [Int] {
        guard model.compositionBoxWorkID == work.id, text == model.compositionBoxSource,
              let title = model.activeCompositionThing,
              let unit = model.compositionUnits.first(where: { $0["title"].string == title }) else { return [] }
        return (unit["lines"].array ?? []).compactMap { $0.number.flatMap(Int.init) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            InkuTextEditor(text: Binding(get: { model.ddlBoxText(for: work) }, set: { model.setDdlBoxText($0, for: work) }),
                           isEditable: editable, accessibilityLabel: model.display.webCopy("ddlEditorInstructions", "指示書"),
                           style: .ddlCompact,
                           marks: { [highlighter, completionStates, completionSource, activeLines] source in
                               let lineIndex = BatchEditorLineIndex(source)
                               let length = (source as NSString).length
                               let marks = activeLines.compactMap { line -> InkuEditorMark? in
                                   guard lineIndex.starts.indices.contains(line) else { return nil }
                                   let start = lineIndex.starts[line]
                                   let end = line + 1 < lineIndex.starts.count ? lineIndex.starts[line + 1] : length
                                   return InkuEditorMark(range: NSRange(location: start, length: max(0, end - start)), style: .compositionThing)
                               }
                               return highlighter.marks(source) + (source == completionSource ? CompletionRangeStyle.marks(completionStates) : []) + marks
                           },
                           marksKey: .ddlComposition(model.saijikiRevision, pluginCallsRevision, pluginSource == text, completionStates, completionSource, model.activeCompositionThing),
                           insertion: Binding(get: { model.ddlBoxInsertion }, set: { model.ddlBoxInsertion = $0 }),
                           reveal: Binding(get: { model.revealCompositionLine }, set: { model.revealCompositionLine = $0 }),
                           rangeTable: CompositionRanges.table,
                           onRangeStatus: { status in
                               rangeStatus = status
                               model.rangePreview = status.preview
                           },
                           completions: model.ddlCompletions, onCharacterHover: { index in
                               hoverIndex = index
                               guard model.compositionBoxWorkID == work.id, text == model.compositionBoxSource, let index else {
                                   model.activeCompositionThing = nil; return
                               }
                               let line = BatchEditorLineIndex(text).line(containing: index)
                               model.activeCompositionThing = model.compositionUnits.first { unit in
                                   (unit["lines"].array ?? []).contains { $0.number.flatMap(Int.init) == line }
                               }?["title"].string
                           })
                .frame(minHeight: 100, maxHeight: 220)
                .overlay(alignment: .leading) { Rectangle().fill(.quaternary).frame(width: 2) }
                .overlay(alignment: .topTrailing) {
                    if !tooltipsCovered, model.display.preferences.showTooltips, pluginSource == text,
                       let hoverIndex, let call = pluginCalls.first(where: { NSLocationInRange(hoverIndex, $0.range) }) {
                        PluginCallPreview(call: call, model: model, language: model.instructionLanguage(for: text))
                            .allowsHitTesting(false).padding(8)
                    }
                }
            if completionSource == text { CompletionRangeSummary(display: model.display, states: completionStates) }
            if invalidSource {
                Text(model.display.localized("横1/3〜2/3、縦2/3〜1 の形で、0〜1の数を、始まりを終わりより小さく書いてください。「-」「－」も使えます。枠は最後の有効な範囲です"))
                    .inkuFont(12).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true)
            }
        }
        // Web DdlViewer `paintBlocked`: an invalid range or an IME composition holds drawing back.
        .onChange(of: invalidSource || rangeStatus.composing, initial: true) { _, blocked in model.ddlBoxRangeBlocked = blocked }
        .onDisappear { model.rangePreview = nil; model.ddlBoxRangeBlocked = false }
        // Web DdlEditor: completion states are asked 180 ms after the text settles.
        .task(id: [work.id, text, model.completionRecordKey]) {
            try? await Task.sleep(for: .milliseconds(180))
            guard !Task.isCancelled else { return }
            let source = text
            let calls = await model.pluginCalls(source: source, workID: work.id)
            guard !Task.isCancelled, text == source else { return }
            pluginCalls = calls; pluginCallsRevision &+= 1; pluginSource = source
            completionStates = model.completionRangeStates(source: source)
            completionSource = source
        }
    }
}
