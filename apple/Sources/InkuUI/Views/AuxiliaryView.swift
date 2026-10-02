import InkuHost
import SwiftUI

@MainActor
public struct AuxiliaryView: View {
    @Bindable var model: AppModel
    public var mode: AuxiliaryMode
    @State private var auxiliary = AuxiliaryModel()
    @State private var deleteRecordID: String?
    @Environment(\.dismiss) private var dismiss

    public init(model: AppModel, mode: AuxiliaryMode = .advice) { self.model = model; self.mode = mode }

    public var body: some View {
        @Bindable var auxiliary = auxiliary
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text(model.display.localized(mode == .colophon ? "系譜の奥書" : "AI の助言・自律推敲")).font(.title2.weight(.semibold))
                    Spacer()
                    Button(model.display.localized("閉じる")) {
                        Task {
                            await auxiliary.stop(app: model)
                            guard !model.isBusy else { return }
                            dismiss()
                        }
                    }.disabled(auxiliary.stopping || (model.isBusy && !auxiliary.running))
                }
                if let work = model.selectedWork {
                    HStack(spacing: 14) {
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(width: 110, height: 95)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(work.effectiveSourceText).lineLimit(3)
                            Text(model.display.localized("元の作品は保持し、新しい子を系譜に保存します。")).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                } else {
                    ContentUnavailableView(model.display.localized("保存作品を選択"), systemImage: "photo", description: Text(model.display.localized("ライブラリか制作画面で元の作品を選択してください。")))
                }
                VStack(alignment: .leading, spacing: 10) {
                    TextField(model.display.localized("補助モデル（サービスID:モデルID）"), text: $auxiliary.modelReference)
                        .textFieldStyle(.roundedBorder).help(model.display.preferences.showTooltips ? model.display.localized("空欄では制作の Stage 1 モデルを使います。画像を扱えるモデルを指定してください。") : "")
                    Picker(model.display.localized("応答の言語"), selection: $auxiliary.language) { Text(model.display.localized("日本語")).tag("ja"); Text("English").tag("en") }
                        .pickerStyle(.segmented).frame(maxWidth: 220)
                }.disabled(auxiliary.running || model.isBusy)
                if mode == .colophon { colophonControls }
                else { adviceControls; refinementControls }
                if auxiliary.running {
                    HStack {
                        ProgressView().controlSize(.small)
                        Text(model.display.message(auxiliary.status))
                        Spacer()
                        Button(model.display.localized(auxiliary.stopping ? "停止中" : "停止"), role: .destructive) { Task { await auxiliary.stop(app: model) } }
                            .disabled(auxiliary.stopping)
                    }
                } else if !auxiliary.status.isEmpty { Text(model.display.message(auxiliary.status)).font(.callout).foregroundStyle(.secondary) }
                if let error = auxiliary.errorText { Text(error).foregroundStyle(.red).textSelection(.enabled) }
                if !auxiliary.draftText.isEmpty { draftEditor }
                if !auxiliary.generatedWorks.isEmpty { generations }
                if mode == .colophon { savedColophons }
            }.padding(20)
        }
        .frame(minWidth: 460, idealWidth: 700, minHeight: 520)
        .task(id: model.selectedWorkID) { await auxiliary.initialize(app: model) }
        .onDisappear { Task { await auxiliary.stop(app: model) } }
        .interactiveDismissDisabled(auxiliary.running || model.isBusy)
        .alert(model.display.localized("この奥書を削除しますか？"), isPresented: Binding(get: { deleteRecordID != nil }, set: { if !$0 { deleteRecordID = nil } })) {
            Button(model.display.localized("削除"), role: .destructive) { if let id = deleteRecordID { Task { await auxiliary.deleteColophon(id, app: model) } }; deleteRecordID = nil }
            Button(model.display.localized("キャンセル"), role: .cancel) { deleteRecordID = nil }
        }
    }

    private var adviceControls: some View {
        @Bindable var auxiliary = auxiliary
        return GroupBox(model.display.localized("モデルから画像の助言を受ける")) {
            VStack(alignment: .leading, spacing: 10) {
                Text(model.display.localized("画像に見える事実と次に試す方向を受け取ります。採点や順位付けは行いません。")).font(.caption).foregroundStyle(.secondary)
                TextField(model.display.localized("AI に伝える方向性"), text: $auxiliary.direction, axis: .vertical).lineLimit(2...4)
                Button(model.display.localized("画像から助言を読む"), systemImage: "eye") { Task { await auxiliary.requestAdvice(app: model) } }
                    .disabled(auxiliary.sourceIsLocked || model.selectedWork == nil || auxiliary.running || model.isBusy)
                if auxiliary.sourceIsLocked {
                    Text(model.display.localized("DDL を編集した作品は記述を読み直しません。色・配置・タッチ・変奏を元の DDL から描けます。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let advice = auxiliary.advice {
                    Text(model.display.localized("観察")).font(.caption.weight(.semibold))
                    Text(advice.observation).textSelection(.enabled)
                    Text(model.display.localizedFormat("次の操作: %@ · 読み手: %@", model.display.localized(AuxiliaryModel.kindLabel(advice.suggestedKind)), advice.model))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
        }
    }

    private var refinementControls: some View {
        @Bindable var auxiliary = auxiliary
        return GroupBox(model.display.localized("世代を限定した自律推敲")) {
            VStack(alignment: .leading, spacing: 12) {
                Picker(model.display.localized("方式"), selection: $auxiliary.visionMode) {
                    Text(model.display.localized("ランダム")).tag(false)
                    Text("AI Vision").tag(true)
                }.pickerStyle(.segmented).frame(maxWidth: 300).disabled(auxiliary.sourceIsLocked)
                Text(model.display.localized(auxiliary.visionMode ? "上のモデルが観察し、同じモデルで各世代を描きます。" : "制作のモデルで描きます。方向性は読み取りを変える世代にだけ渡します。"))
                    .font(.caption).foregroundStyle(.secondary)
                Stepper(model.display.localizedFormat("生成する世代数: %ld", auxiliary.generations), value: $auxiliary.generations, in: 1...10)
                HStack {
                    ForEach(AuxiliaryProvider.allowedKinds, id: \.self) { kind in
                        Toggle(model.display.localized(AuxiliaryModel.kindLabel(kind)), isOn: Binding(
                            get: { auxiliary.enabledKinds.contains(kind) },
                            set: { if $0 { auxiliary.enabledKinds.insert(kind) } else { auxiliary.enabledKinds.remove(kind) } }))
                            .toggleStyle(.button).disabled(kind == "reinterpretation" && auxiliary.sourceIsLocked)
                    }
                }
                if auxiliary.enabledKinds.contains("variation") {
                    Picker(model.display.localized("変奏の強度"), selection: $auxiliary.amplitude) {
                        Text(model.display.localized("小")).tag("small"); Text(model.display.localized("中")).tag("medium"); Text(model.display.localized("大")).tag("large")
                    }.pickerStyle(.segmented).frame(maxWidth: 260)
                }
                HStack {
                    Toggle(model.display.localized("元のワイルド設定を引き継ぐ"), isOn: $auxiliary.inheritWild)
                    if !auxiliary.inheritWild { Toggle(model.display.localized("ワイルド"), isOn: $auxiliary.wildOverride) }
                }
                Button(model.display.localizedFormat("%ld 世代の推敲を開始", auxiliary.generations), systemImage: "play") { Task { await auxiliary.startRefinement(app: model) } }
                    .disabled(model.selectedWork == nil || auxiliary.enabledKinds.isEmpty)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
        }.disabled(auxiliary.running || model.isBusy)
    }

    private var colophonControls: some View {
        GroupBox(model.display.localized("起点から現在の作品までを読む")) {
            VStack(alignment: .leading, spacing: 10) {
                Text(model.display.localized("各世代の見える差を順に読み、機械抽出した不変量で結びます。詞書を物語化せず、評価や作者の意図は付けません。"))
                    .font(.caption).foregroundStyle(.secondary)
                Button(model.display.localized("奥書の草稿を生成"), systemImage: "text.book.closed") { Task { await auxiliary.generateColophon(app: model) } }
                    .disabled(auxiliary.running || model.isBusy || model.selectedWork?.lineageNodeID == nil)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
        }
    }

    private var draftEditor: some View {
        @Bindable var auxiliary = auxiliary
        return GroupBox(model.display.localized(mode == .colophon ? "編集して採用する奥書" : "編集して採用する次の方針")) {
            VStack(alignment: .leading, spacing: 10) {
                TextEditor(text: $auxiliary.draftText).font(.body).frame(minHeight: mode == .colophon ? 230 : 100)
                    .disabled(auxiliary.running)
                if let draft = auxiliary.colophonDraft, !draft.warnings.isEmpty {
                    Text(model.display.localized("確認が必要な表現: ") + draft.warnings.joined(separator: model.display.preferences.language == "en" ? ", " : "、")).font(.caption).foregroundStyle(.orange)
                }
                HStack {
                    Button(model.display.localized("コピー"), systemImage: "doc.on.doc") { auxiliary.copyDraft() }
                    Spacer()
                    if mode == .colophon {
                        Button(model.display.localized("編集した奥書を保存")) { Task { await auxiliary.saveColophon(app: model) } }
                    } else {
                        Button(model.display.localized("この方針で子を描く")) { Task { await auxiliary.adoptAdvice(app: model) } }
                            .disabled(auxiliary.sourceIsLocked)
                    }
                }.disabled(auxiliary.running || model.isBusy)
            }.padding(6)
        }
    }

    private var generations: some View {
        GroupBox(model.display.localizedFormat("保存した世代 (%ld)", auxiliary.completedGenerations)) {
            ScrollView(.horizontal) {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(auxiliary.generatedWorks, id: \.id) { work in
                        Button { Task { await model.selectWork(work) } } label: {
                            VStack {
                                ArtworkThumbnail(work: work, renderer: model.renderer).frame(width: 130, height: 115)
                                Text(work.effectiveSourceText).font(.caption).lineLimit(2).frame(width: 130)
                            }
                        }.buttonStyle(.plain).disabled(auxiliary.running || model.isBusy)
                    }
                }.padding(6)
            }
        }
    }

    private var savedColophons: some View {
        GroupBox(model.display.localized("保存した奥書")) {
            VStack(alignment: .leading, spacing: 14) {
                if auxiliary.storedColophons.isEmpty { Text(model.display.localized("この系譜の奥書はまだありません。")).foregroundStyle(.secondary) }
                ForEach(auxiliary.storedColophons) { record in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(record.signature).font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Button(model.display.localized("編集")) { auxiliary.editColophon(record) }
                            Button(model.display.localized("削除"), role: .destructive) { deleteRecordID = record.id }
                        }
                        Text(record.adoptedBody ?? record.generatedBody).textSelection(.enabled)
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
        }.disabled(auxiliary.running)
    }
}
