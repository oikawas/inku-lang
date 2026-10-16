import InkuPersistence
import SwiftUI

@MainActor
public struct WorkEditView: View {
    @Bindable private var model: AppModel
    @State private var editor: WorkEditModel
    @Environment(\.dismiss) private var dismiss
    private let onCommitted: @MainActor () -> Void

    public init(model: AppModel, work: SavedWork, mode: WorkEditMode, onCommitted: @escaping @MainActor () -> Void = {}) {
        self.model = model
        self.onCommitted = onCommitted
        _editor = State(initialValue: WorkEditModel(work: work, mode: mode))
    }

    public var body: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                Text(model.display.localized(editor.mode == .description ? "記述を変える" : "写生なし／ありで描き直す"))
                    .inkuFont(16, weight: .semibold)
                    Spacer()
                    Button { dismiss() } label: { Image(systemName: "xmark") }
                        .accessibilityLabel(model.display.localized("閉じる")).disabled(editor.running || model.isBusy)
                }
                Text(model.display.localized(editor.mode == .description
                    ? "変更した記述から、選択した作品の子を描画します。"
                    : "写生を外すか付けるかを選んで描き直し、選択した作品の子として系譜へ保存します。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }.frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 20).padding(.top, 18).padding(.bottom, 14)
            Divider()
            ScrollView {
                editControls.padding(.horizontal, 20).padding(.vertical, 18)
            }
            Divider()
            footer.padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 16)
        }
        #if os(macOS)
        .frame(minWidth: 560, idealWidth: 780,
               minHeight: editor.mode == .description ? 380 : 260,
               idealHeight: editor.mode == .description ? 450 : 360)
        #endif
        .task { await editor.initialize(app: model) }
        .interactiveDismissDisabled(editor.running || model.isBusy)
        .onDisappear { Task { await editor.stop(app: model) } }
    }

    private var editControls: some View {
        @Bindable var editor = editor
        return VStack(alignment: .leading, spacing: 8) {
            if editor.mode == .description {
                Text(model.display.webCopy("inputSectionLabel", "記述")).inkuFont(12, weight: .semibold).foregroundStyle(.secondary)
                TextEditor(text: $editor.draftText).padding(.horizontal, 10).padding(.vertical, 8).frame(height: 200)
                    .scrollContentBackground(.hidden)
                    .background(InkuColor.bg, in: RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(InkuColor.border2))
                    .accessibilityLabel(model.display.localized("記述"))
                    .disabled(editor.running)
                DescriptionMeterView(model: model, text: editor.draftText)
            } else {
                HStack(spacing: 8) {
                    Text(model.display.localized("写生")).inkuFont(12).foregroundStyle(.secondary)
                    // SketchSelect.svelte:47: each choice names what it does (`sketchModeHint`).
                    InkuSegmentedButtons(options: [("off", model.display.localized("なし")), ("on", model.display.localized("あり"))],
                                         selection: $editor.sketchMode,
                                         tooltips: [model.display.tooltip("写生を通さず、記述だけで描く"),
                                                    model.display.tooltip("記述の横に、場所の広がりや季節・時刻の光を補って描く")])
                }.disabled(editor.running)
                if let prose = editor.work.sketchText, !prose.isEmpty {
                    Text(prose).inkuFont(12).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                } else {
                    Text(model.display.webCopy("workEditNoSketch", "この作品は写生を通していません。"))
                        .inkuFont(12).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if !model.hasNextDrawingModel {
                Text(model.display.localized("描画モデルが未設定です。設定でAIサービスとモデルを選択してください。"))
                    .inkuFont(13).foregroundStyle(.secondary)
            }
            if let error = editor.errorText { Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled) }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private var footer: some View {
        HStack {
            if editor.running {
                // WorkEditDialog.svelte:118: the drawing indicator at the end of the footer row.
                Spacer()
                RunStatusView(display: model.display, label: model.isBusy ? model.status : "生成の準備中", variant: .inline,
                              stopping: editor.stopping, onStop: { Task { await editor.stop(app: model) } })
            } else {
                if editor.mode == .description {
                    wildControl
                } else {
                    Text(model.display.webCopy("workEditParentGrain", "親の写生") + ": "
                        + model.display.localized(editor.work.sketchText?.isEmpty == false ? "あり" : sketchStateNote))
                        .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                Button(model.display.webCopy("pipelineCancel", "キャンセル")) { dismiss() }
                    .disabled(model.isBusy).keyboardShortcut(.cancelAction)
                Button(model.display.webCopy(editor.mode == .description ? "submitBtn" : "pipelinePerform",
                                             editor.mode == .description ? "描画する" : "演奏する")) {
                    Task { if await editor.draw(app: model) { onCommitted(); dismiss() } }
                }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(!editor.canDraw || model.isBusy || model.isPreview || !model.hasNextDrawingModel)
            }
        }
    }

    private var wildControl: some View {
        let wild = editor.inheritWild ? editor.work.renderWild ?? false : editor.wildOverride
        return HStack(spacing: 4) {
            Text(model.display.localized(editor.inheritWild ? "筆致制限（継承）" : "筆致制限") + ":")
                .inkuFont(11).foregroundStyle(.secondary)
            Button(model.display.localized("暴れる")) {
                editor.wildOverride = !wild; editor.inheritWild = false
            }.buttonStyle(.bordered).tint(wild ? Color.accentColor : Color.secondary)
                .accessibilityValue(model.display.localized(wild ? "入" : "切"))
        }.disabled(model.isBusy)
    }

    private var sketchStateNote: String {
        switch editor.work.sketchState {
        case nil: "写生が記録される前に描かれた（切って描いたのではない）"
        case "off": "写生を通さずに描いた"
        case "not_needed": "写生を通したが、補うものがなかった"
        case "fallback": "写生を試みたが届かず、記述のまま解釈した"
        case "not_applicable": "この経路は写生を通らない"
        case "supplemented": "記述に足りない場所の広がりや季節・時刻の光を補って描いた"
        case "fine": "過去の写生: 細かく"
        case "coarse": "過去の写生: 大きく"
        default: "この作品には保存された写生がありません。"
        }
    }
}
