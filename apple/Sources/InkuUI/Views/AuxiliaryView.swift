import InkuHost
import InkuPersistence
import SwiftUI

@MainActor
public struct AuxiliaryView: View {
    @Bindable var model: AppModel
    public var mode: AuxiliaryMode
    public let work: SavedWork?
    @State private var auxiliary = AuxiliaryModel()
    @State private var deleteRecordID: String?
    @State private var showModels = false
    @Environment(\.dismiss) private var dismiss

    public init(model: AppModel, mode: AuxiliaryMode = .advice, work: SavedWork? = nil) { self.model = model; self.mode = mode; self.work = work }

    public var body: some View {
        if mode == .advice { AutonomousRefinementView(model: model, work: work) }
        else { colophonBody }
    }

    private var colophonBody: some View {
        @Bindable var auxiliary = auxiliary
        return ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text(model.display.localized(mode == .colophon ? "系譜の奥書" : "AI自動推敲プロセス")).inkuFont(16, weight: .semibold)
                    Spacer()
                    Button(model.display.localized("閉じる")) {
                        Task {
                            await auxiliary.stop(app: model)
                            guard !model.isBusy else { return }
                            dismiss()
                        }
                    }.disabled(auxiliary.stopping || auxiliary.selectingSource || (model.isBusy && !auxiliary.running))
                }
                if let work = auxiliary.sourceWork ?? work {
                    HStack(spacing: 14) {
                        ArtworkThumbnail(work: work, thumbnails: model.thumbnails).frame(width: 110, height: 95)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(work.effectiveSourceText).lineLimit(3)
                            Text(model.display.localized("元の作品は保持し、新しい子を系譜に保存します。")).inkuFont(12).foregroundStyle(.secondary)
                        }
                    }
                } else {
                    ContentUnavailableView(model.display.localized("保存作品を選択"), systemImage: "photo", description: Text(model.display.localized("ライブラリか制作画面で元の作品を選択してください。")))
                }
                visionSelection
                colophonControls
                if auxiliary.running {
                    HStack {
                        ProgressView().controlSize(.small)
                        Text(model.display.message(auxiliary.status))
                        Spacer()
                        Button(model.display.localized(auxiliary.stopping ? "停止中" : "停止"), role: .destructive) { Task { await auxiliary.stop(app: model) } }
                            .disabled(auxiliary.stopping)
                    }
                } else if !auxiliary.status.isEmpty { Text(model.display.message(auxiliary.status)).inkuFont(13).foregroundStyle(.secondary) }
                if let error = auxiliary.errorText { Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled) }
                if !auxiliary.draftText.isEmpty { draftEditor }
                if mode == .colophon { savedColophons }
            }.padding(20)
        }
        .frame(minWidth: 460, idealWidth: 700, minHeight: 520)
        .task(id: work?.id ?? model.selectedWorkID) {
            await auxiliary.initialize(app: model, work: work, mode: mode)
        }
        .sheet(isPresented: $showModels) {
            BatchModelPickerView(model: model, initialReference: auxiliary.modelReference, immediateSelection: true,
                                 title: model.display.localized("Visionモデルを選択"), purpose: "vision",
                                 onSelection: { reference in try await auxiliary.selectModel(reference, app: model, mode: mode) })
        }
        .onDisappear { Task { await auxiliary.stop(app: model) } }
        .interactiveDismissDisabled(auxiliary.running || auxiliary.selectingSource || model.isBusy)
        .alert(model.display.localized("この奥書を削除しますか？"), isPresented: Binding(get: { deleteRecordID != nil }, set: { if !$0 { deleteRecordID = nil } })) {
            Button(model.display.localized("削除"), role: .destructive) { if let id = deleteRecordID { Task { await auxiliary.deleteColophon(id, app: model) } }; deleteRecordID = nil }
            Button(model.display.localized("キャンセル"), role: .cancel) { deleteRecordID = nil }
        }
    }

    private var visionSelection: some View {
        @Bindable var auxiliary = auxiliary
        return VStack(alignment: .leading, spacing: 10) {
            Button { showModels = true } label: {
                Label(auxiliary.modelReference.isEmpty ? model.display.localized("Visionモデルを選択") : auxiliary.modelReference, systemImage: "eye")
            }.inkuTooltip(model.display.tooltip("画像を扱える登録モデルから選択します。", serverKey: "modelSelectionVisionHint"))
            HStack(spacing: 8) {
                Text(model.display.localized("応答の言語")).inkuFont(12).foregroundStyle(.secondary)
                InkuSegmentedButtons(options: [("ja", model.display.localized("日本語")), ("en", "English")], selection: $auxiliary.language)
            }.accessibilityElement(children: .contain).accessibilityLabel(model.display.localized("応答の言語"))
        }.disabled(auxiliary.running || auxiliary.selectingSource || model.isBusy)
    }

    private var colophonControls: some View {
        GroupBox(model.display.localized("起点から現在の作品までを読む")) {
            VStack(alignment: .leading, spacing: 10) {
                Text(model.display.localized("各世代の見える差を順に読み、機械抽出した不変量で結びます。詞書を物語化せず、評価や作者の意図は付けません。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                if auxiliary.loadingColophonPath {
                    ProgressView(model.display.localized("読み込み中"))
                } else if let count = auxiliary.colophonPathCount {
                    let template = ServerTips.text("okugakiBranchConfirm", language: model.display.preferences.language)
                        ?? model.display.localized("起点から表示作品まで {count} 世代の枝を読みます。")
                    Text(template.replacingOccurrences(of: "{count}", with: count.formatted()))
                        .inkuFont(13)
                } else {
                    Button(model.display.localized("再読込")) { Task { await auxiliary.refreshColophonPath() } }
                        .disabled(auxiliary.running || model.isBusy)
                }
                Button(model.display.localized("奥書を追記"), systemImage: "text.book.closed") { Task { await auxiliary.generateColophon(app: model) } }
                    .disabled(auxiliary.running || model.isBusy || auxiliary.loadingColophonPath || auxiliary.colophonPathCount == nil || auxiliary.modelReference.isEmpty)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
        }
    }

    private var draftEditor: some View {
        @Bindable var auxiliary = auxiliary
        return GroupBox(model.display.localized(mode == .colophon ? "生成した奥書" : "編集して採用する次の方針")) {
            VStack(alignment: .leading, spacing: 10) {
                if mode == .colophon {
                    Text(auxiliary.draftText).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    TextEditor(text: $auxiliary.draftText).inkuFont(14).frame(minHeight: 100).disabled(auxiliary.running || auxiliary.selectingSource)
                }
                if let draft = auxiliary.colophonDraft, !draft.warnings.isEmpty {
                    Text(model.display.localized("確認が必要な表現: ") + draft.warnings.joined(separator: model.display.preferences.language == "en" ? ", " : "、")).inkuFont(12).foregroundStyle(.orange)
                }
                HStack {
                    Button(model.display.localized("コピー"), systemImage: "doc.on.doc") { auxiliary.copyDraft() }
                    Spacer()
                    if mode != .colophon {
                        Button(model.display.localized("この方針で子を描く")) { Task { await auxiliary.adoptAdvice(app: model) } }
                            .disabled(auxiliary.sourceIsLocked)
                    }
                }.disabled(auxiliary.running || auxiliary.selectingSource || model.isBusy)
            }.padding(6)
        }
    }

    private var savedColophons: some View {
        GroupBox(model.display.localized("保存した奥書")) {
            VStack(alignment: .leading, spacing: 14) {
                if auxiliary.storedColophons.isEmpty { Text(model.display.localized("この系譜の奥書はまだありません。")).foregroundStyle(.secondary) }
                ForEach(auxiliary.storedColophons) { record in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(record.signature).inkuFont(12).foregroundStyle(.secondary)
                            Spacer()
                            Button(model.display.localized("コピー")) { auxiliary.draftText = record.adoptedBody ?? record.generatedBody; auxiliary.copyDraft() }
                            Button(model.display.localized("削除"), role: .destructive) { deleteRecordID = record.id }
                                .inkuTooltip(model.display.tooltip("この奥書を削除", serverKey: "okugakiDelete"))
                        }
                        Text(record.adoptedBody ?? record.generatedBody).textSelection(.enabled)
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
        }.disabled(auxiliary.running)
    }
}
