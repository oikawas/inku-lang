import InkuHost
import InkuPersistence
import SwiftUI

/// BatchPanel.svelte keeps the completed line's instructions and sketch separate from the next active line.
@MainActor
struct BatchObservationCards: View {
    @Bindable var model: AppModel
    @Bindable var automation: AutomationModel
    @State private var metrics: [ProviderAttemptMetric] = []
    @State private var highlighter: DdlHighlighter

    init(model: AppModel, automation: AutomationModel) {
        self.model = model
        self.automation = automation
        _highlighter = State(initialValue: DdlHighlighter(saijiki: model.saijiki, plugins: PluginNameIndex(words: model.pluginWords)))
    }

    private var work: SavedWork? { automation.observedWork }
    private var display: DisplaySettings { model.display }
    private var lineLabel: String {
        automation.observedRow.map { display.webCopyFormat("batchActiveLine", "%@", $0.line) } ?? ""
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let sketch = work?.sketchText, !sketch.isEmpty {
                block(title: display.webCopy("sketchLabel", "写生（Stage 0.5）"),
                      metadata: [lineLabel, sketchModeLabel].filter { !$0.isEmpty }.joined(separator: " · ")) {
                    ScrollView {
                        Text(sketch).inkuFont(12).lineSpacing(5).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(10)
                    }.frame(height: 100)
                }
            }
            block(title: display.webCopy("batchActiveDdlLabel", "処理中の指示書"),
                  metadata: [lineLabel, display.webCopy("statsTokens", "トークン") + " " + tokenPair].filter { !$0.isEmpty }.joined(separator: " · ")) {
                if let ddl = work?.ddl, !ddl.isEmpty {
                    InkuTextEditor(text: .constant(ddl), isEditable: false,
                        accessibilityLabel: display.webCopy("batchActiveDdlLabel", "処理中の指示書"),
                        style: InkuEditorStyle(fontSize: 12, monospaced: false, lineHeightMultiple: 1.55,
                                               wraps: true, lineNumbers: false, inset: CGSize(width: 10, height: 9), drawsBackground: false),
                        marks: { [highlighter] in highlighter.marks($0) })
                        .frame(height: 132)
                } else {
                    Text(display.webCopy("batchActiveDdlPending", "指示書を待機中…"))
                        .inkuFont(12).foregroundStyle(.secondary).padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
        .task(id: work?.id) {
            metrics = []
            guard let work else { return }
            let information = try? await model.savedGenerationInformation(work: work)
            guard !Task.isCancelled else { return }
            metrics = information?.metrics ?? []
        }
    }

    private var tokenPair: String {
        let inputs = metrics.compactMap { $0.usage?.inputTokens }
        let outputs = metrics.compactMap { $0.usage?.outputTokens }
        return (inputs.isEmpty ? "-" : String(inputs.reduce(0, +))) + "→"
            + (outputs.isEmpty ? "-" : String(outputs.reduce(0, +))) + "tok"
    }

    private var sketchModeLabel: String {
        guard let grain = work?.sketchGrain else { return "" }
        let on = ["on", "fine", "coarse"].contains(grain)
        let value = display.label(on ? "あり" : "なし", on ? "On" : "Off")
        return display.webCopy("sketchGrainLabel", "区切り") + ": " + value
    }

    private func block<Body: View>(title: String, metadata: String, @ViewBuilder content: () -> Body) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(title).inkuFont(11, weight: .semibold)
                    Spacer(minLength: 0)
                    Text(metadata).inkuFont(11).foregroundStyle(.secondary).monospacedDigit()
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).inkuFont(11, weight: .semibold)
                    Text(metadata).inkuFont(11).foregroundStyle(.secondary).monospacedDigit()
                }
            }.padding(.horizontal, 9).padding(.vertical, 6)
            Divider()
            content()
        }.frame(maxWidth: .infinity, alignment: .leading)
            .background(InkuColor.panel, in: RoundedRectangle(cornerRadius: 4))
            .clipShape(RoundedRectangle(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
    }
}
