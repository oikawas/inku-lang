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
        @Bindable var editor = editor
        VStack(alignment: .leading, spacing: 16) {
            Text(model.display.localized(editor.mode == .description ? "記述を変える" : "写生なし／ありで描き直す"))
                .font(.title2.weight(.semibold))
            Text(model.display.localized(editor.mode == .description
                ? "変更した記述から、選択した作品の子を描画します。"
                : "写生を外すか付けるかを選んで描き直し、選択した作品の子として系譜へ保存します。"))
                .font(.callout).foregroundStyle(.secondary)
            HStack(alignment: .top, spacing: 14) {
                ArtworkThumbnail(work: editor.work, renderer: model.renderer).frame(width: 120, height: 100)
                Text(editor.work.effectiveSourceText).font(.callout).lineLimit(4).textSelection(.enabled)
                    .help(model.display.preferences.showTooltips ? editor.work.effectiveSourceText : "")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }.frame(height: 100, alignment: .top).layoutPriority(1)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if editor.mode == .description {
                        Text(model.display.localized("記述")).font(.headline)
                        TextEditor(text: $editor.draftText).frame(minHeight: 190).border(Color.secondary.opacity(0.25))
                            .accessibilityLabel(model.display.localized("記述"))
                            .disabled(editor.running)
                        DescriptionMeterView(model: model, text: editor.draftText)
                        HStack {
                            Toggle(model.display.localized("元のワイルド設定を引き継ぐ"), isOn: $editor.inheritWild)
                            if !editor.inheritWild { Toggle(model.display.localized("ワイルド"), isOn: $editor.wildOverride) }
                        }.disabled(editor.running)
                    } else {
                        Picker(model.display.localized("写生"), selection: $editor.sketchMode) {
                            Text(model.display.localized("なし")).tag("off")
                            Text(model.display.localized("あり")).tag("on")
                        }.pickerStyle(.segmented).frame(maxWidth: 280).disabled(editor.running)
                        Text(model.display.localized("親の写生")).font(.headline)
                        if let prose = editor.work.sketchText, !prose.isEmpty {
                            Text(prose).textSelection(.enabled)
                        } else {
                            Text(model.display.localized(sketchStateNote)).foregroundStyle(.secondary)
                        }
                    }
                    if !model.hasNextDrawingModel {
                        Text(model.display.localized("描画モデルが未設定です。設定でAIサービスとモデルを選択してください。"))
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    if let error = editor.errorText { Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled) }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider()
            HStack {
                if editor.running {
                    ProgressView().controlSize(.small)
                    Text(model.display.message(model.isBusy ? model.status : "生成の準備中"))
                    Spacer()
                    Button(model.display.localized(editor.stopping ? "停止中" : "停止")) { Task { await editor.stop(app: model) } }
                        .disabled(editor.stopping)
                } else {
                    Spacer()
                    Button(model.display.localized("描く")) {
                        Task { if await editor.draw(app: model) { onCommitted(); dismiss() } }
                    }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                        .disabled(!editor.canDraw || model.isBusy || model.isPreview || !model.hasNextDrawingModel)
                }
                Button(model.display.localized("閉じる")) {
                    Task {
                        await editor.stop(app: model)
                        guard !editor.running, !model.isBusy else { return }
                        dismiss()
                    }
                }.disabled(editor.stopping || (model.isBusy && !editor.running)).keyboardShortcut(.cancelAction)
            }
        }.padding(20).frame(minWidth: 440, idealWidth: 680, minHeight: 440, idealHeight: 590)
            .task { await editor.initialize(app: model) }
            .interactiveDismissDisabled(editor.running || model.isBusy)
            .onDisappear { Task { await editor.stop(app: model) } }
    }

    private var sketchStateNote: String {
        switch editor.work.sketchState {
        case nil: "写生が記録される前に描かれた（切って描いたのではない）"
        case "off": "写生を通さずに描いた"
        case "not_needed": "写生を通したが、補うものがなかった"
        case "fallback": "写生を試みたが届かず、記述のまま解釈した"
        case "not_applicable": "この経路は写生を通らない"
        case "fine": "過去の写生: 細かく"
        case "coarse": "過去の写生: 大きく"
        default: "この作品には保存された写生がありません。"
        }
    }
}
