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
            VStack(alignment: .leading, spacing: 8) {
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
                    .inkuFont(13).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    parentCard
                    editControls.workEditPanel()
                }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider()
            footer.padding(20).background(.bar)
        }
        #if os(macOS)
        .frame(minWidth: 640, idealWidth: 680, minHeight: 550, idealHeight: 680)
        #endif
        .task { await editor.initialize(app: model) }
        .interactiveDismissDisabled(editor.running || model.isBusy)
        .onDisappear { Task { await editor.stop(app: model) } }
    }

    private var parentCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.display.localized("元の作品")).inkuFont(14, weight: .semibold)
            HStack(alignment: .top, spacing: 14) {
                ArtworkThumbnail(work: editor.work, renderer: model.renderer)
                    .frame(width: 120, height: 120).clipped()
                    .accessibilityLabel(model.display.localized("元の作品"))
                Text(editor.work.effectiveSourceText).inkuFont(13).lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                    .help(model.display.preferences.showTooltips ? editor.work.effectiveSourceText : "")
                    .frame(maxWidth: .infinity, minHeight: 72, alignment: .topLeading)
            }.frame(minHeight: 120, alignment: .top)
        }.workEditPanel()
    }

    private var editControls: some View {
        @Bindable var editor = editor
        return VStack(alignment: .leading, spacing: 14) {
            if editor.mode == .description {
                Text(model.display.localized("記述")).inkuFont(14, weight: .semibold)
                TextEditor(text: $editor.draftText).frame(minHeight: 190).border(Color.secondary.opacity(0.25))
                    .accessibilityLabel(model.display.localized("記述"))
                    .disabled(editor.running)
                DescriptionMeterView(model: model, text: editor.draftText)
                HStack {
                    Text(model.display.localized(editor.inheritWild ? "筆致制限（継承）" : "筆致制限")).inkuFont(12).foregroundStyle(.secondary)
                    Button(model.display.localized("暴れる") + " " + model.display.localized((editor.inheritWild ? editor.work.renderWild ?? false : editor.wildOverride) ? "入" : "切")) {
                        editor.wildOverride = !(editor.inheritWild ? editor.work.renderWild ?? false : editor.wildOverride)
                        editor.inheritWild = false
                    }.buttonStyle(.bordered).tint((editor.inheritWild ? editor.work.renderWild ?? false : editor.wildOverride) ? Color.accentColor : Color.secondary)
                }.disabled(editor.running || model.isBusy)
            } else {
                HStack(spacing: 8) {
                    Text(model.display.localized("写生")).inkuFont(12).foregroundStyle(.secondary)
                    InkuSegmentedButtons(options: [("off", model.display.localized("なし")), ("on", model.display.localized("あり"))],
                                         selection: $editor.sketchMode)
                }.disabled(editor.running)
                    .help(model.display.tooltip(editor.sketchMode == "on"
                        ? "記述の横に、場所の広がりや季節・時刻の光を補って描く" : "写生を通さず、記述だけで描く"))
                Text(model.display.localized("親の写生")).inkuFont(14, weight: .semibold)
                if let prose = editor.work.sketchText, !prose.isEmpty {
                    Text(prose).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                } else {
                    Text(model.display.localized(sketchStateNote)).foregroundStyle(.secondary)
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
            Button(model.display.localized("取消")) { dismiss() }
                .disabled(editor.running || model.isBusy).keyboardShortcut(.cancelAction)
        }
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

private extension View {
    func workEditPanel() -> some View {
        padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary))
    }
}
