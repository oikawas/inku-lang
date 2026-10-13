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
    @State private var highlighter: DdlHighlighter
    @State private var completionStates: [CompletionRangeState] = []
    @State private var completionSource = ""
    @State private var rangeStatus = RangeEditorStatus()
    /// Web `invalidSource`: an invalid range in the editor, or any unreadable numeric range in the text.
    private var invalidSource: Bool { rangeStatus.invalid || CompositionRanges.scan(text).contains { $0.bounds == nil } }

    init(model: AppModel, work: SavedWork, editable: Bool) {
        self.model = model
        self.work = work
        self.editable = editable
        _highlighter = State(initialValue: DdlHighlighter(saijiki: model.saijiki, plugins: PluginNameIndex(words: model.pluginWords)))
    }

    private var text: String { model.ddlBoxText(for: work) }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            InkuTextEditor(text: Binding(get: { model.ddlBoxText(for: work) }, set: { model.setDdlBoxText($0, for: work) }),
                           isEditable: editable, accessibilityLabel: model.display.webCopy("ddlEditorInstructions", "指示書"),
                           style: .ddlCompact,
                           marks: { [highlighter, completionStates, completionSource] source in
                               highlighter.marks(source) + (source == completionSource ? CompletionRangeStyle.marks(completionStates) : [])
                           },
                           insertion: Binding(get: { model.ddlBoxInsertion }, set: { model.ddlBoxInsertion = $0 }),
                           rangeTable: CompositionRanges.table,
                           onRangeStatus: { status in
                               rangeStatus = status
                               model.rangePreview = status.preview
                           },
                           completions: model.ddlCompletions)
                .frame(minHeight: 100, maxHeight: 220)
                .overlay(alignment: .leading) { Rectangle().fill(.quaternary).frame(width: 2) }
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
            completionStates = model.completionRangeStates(source: text)
            completionSource = text
        }
    }
}
