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
    @State private var observedGeneration: SavedWork?
    @State private var refineChoicesRestored = false
    @Environment(\.dismiss) private var dismiss

    public init(model: AppModel, mode: AuxiliaryMode = .advice, work: SavedWork? = nil) { self.model = model; self.mode = mode; self.work = work }

    public var body: some View {
        @Bindable var auxiliary = auxiliary
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text(model.display.localized(mode == .colophon ? "系譜の奥書" : "AI の助言・自律推敲")).inkuFont(16, weight: .semibold)
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
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(width: 110, height: 95)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(work.effectiveSourceText).lineLimit(3)
                            Text(model.display.localized("元の作品は保持し、新しい子を系譜に保存します。")).inkuFont(12).foregroundStyle(.secondary)
                        }
                    }
                } else {
                    ContentUnavailableView(model.display.localized("保存作品を選択"), systemImage: "photo", description: Text(model.display.localized("ライブラリか制作画面で元の作品を選択してください。")))
                }
                VStack(alignment: .leading, spacing: 10) {
                    Button { showModels = true } label: {
                        Label(auxiliary.modelReference.isEmpty ? model.display.localized("Visionモデルを選択") : auxiliary.modelReference, systemImage: "eye")
                    }.inkuTooltip(model.display.tooltip("画像を扱える登録モデルから選択します。", serverKey: "modelSelectionVisionHint"))
                    HStack(spacing: 8) {
                        Text(model.display.localized("応答の言語")).inkuFont(12).foregroundStyle(.secondary)
                        InkuSegmentedButtons(options: [("ja", model.display.localized("日本語")), ("en", "English")], selection: $auxiliary.language)
                    }.accessibilityElement(children: .contain).accessibilityLabel(model.display.localized("応答の言語"))
                }.disabled(auxiliary.running || auxiliary.selectingSource || model.isBusy)
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
                } else if !auxiliary.status.isEmpty { Text(model.display.message(auxiliary.status)).inkuFont(13).foregroundStyle(.secondary) }
                if let error = auxiliary.errorText { Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled) }
                if !auxiliary.draftText.isEmpty { draftEditor }
                if !auxiliary.generatedWorks.isEmpty { generations }
                if mode == .colophon { savedColophons }
            }.padding(20)
        }
        .frame(minWidth: 460, idealWidth: 700, minHeight: 520)
        .task(id: work?.id ?? model.selectedWorkID) {
            if mode == .advice && !refineChoicesRestored { restoreRefineChoices() }
            await auxiliary.initialize(app: model, work: work, mode: mode)
        }
        // A held work turns Vision and reading off for itself; that is not the author's choice, so it is not kept.
        .onChange(of: refineChoices) { _, choices in
            if mode == .advice, refineChoicesRestored, !auxiliary.sourceIsLocked { model.display.preferences.aiRefine = choices }
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

    private var adviceControls: some View {
        @Bindable var auxiliary = auxiliary
        return GroupBox(model.display.localized("モデルから画像の助言を受ける")) {
            VStack(alignment: .leading, spacing: 10) {
                Text(model.display.localized("画像に見える事実と次に試す方向を受け取ります。採点や順位付けは行いません。")).inkuFont(12).foregroundStyle(.secondary)
                TextField(model.display.localized("AI に伝える方向性"), text: $auxiliary.direction, axis: .vertical).lineLimit(2...4)
                    .disabled(auxiliary.sourceIsLocked || auxiliary.running || auxiliary.selectingSource || model.isBusy)
                    .inkuTooltip(model.display.tooltip("AIへ伝える方針は160文字までです。"))
                Text("\(auxiliary.direction.utf16.count) / \(AuxiliaryModel.directionLimit)")
                    .inkuFont(12).monospacedDigit().foregroundStyle(.secondary)
                Button(model.display.localized("画像から助言を読む"), systemImage: "eye") { Task { await auxiliary.requestAdvice(app: model) } }
                    .disabled(auxiliary.sourceIsLocked || auxiliary.sourceWork == nil || auxiliary.modelReference.isEmpty || auxiliary.running || model.isBusy)
                if auxiliary.sourceIsLocked {
                    Text(model.display.localized("DDL を編集した作品は記述を読み直しません。色・配置・タッチを元の DDL から描けます。"))
                        .inkuFont(12).foregroundStyle(.secondary)
                }
                if let advice = auxiliary.advice {
                    Text(model.display.localized("観察")).inkuFont(12, weight: .semibold)
                    Text(advice.observation).textSelection(.enabled)
                    Text(model.display.localizedFormat("次の操作: %@ · 読み手: %@", model.display.localized(AuxiliaryModel.kindLabel(advice.suggestedKind)), advice.model))
                        .inkuFont(12).foregroundStyle(.secondary)
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
        }
    }

    /// Web `inku-ai-refine-settings`: mode, generations, the four dimensions and the direction, not the wild switch.
    private var refineChoices: AIRefineChoices {
        AIRefineChoices(visionMode: auxiliary.visionMode, generations: auxiliary.generations,
                        kinds: AuxiliaryProvider.allowedKinds.filter(auxiliary.enabledKinds.contains), direction: auxiliary.direction)
    }
    private func restoreRefineChoices() {
        refineChoicesRestored = true
        guard let saved = model.display.preferences.aiRefine else { return }
        auxiliary.visionMode = saved.visionMode
        if (1...10).contains(saved.generations) { auxiliary.generations = saved.generations }
        auxiliary.enabledKinds = Set(saved.kinds.filter(AuxiliaryProvider.allowedKinds.contains))
        auxiliary.direction = saved.direction
    }

    private var refinementControls: some View {
        @Bindable var auxiliary = auxiliary
        return GroupBox(model.display.localized("世代を限定した自律推敲")) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    Text(model.display.localized("方式")).inkuFont(12).foregroundStyle(.secondary)
                    InkuSegmentedButtons(options: [(false, model.display.localized("ランダム")), (true, "AI Vision")], selection: $auxiliary.visionMode)
                }.disabled(auxiliary.sourceIsLocked)
                    // AIRefineModal.svelte:251: a held work names why Vision is off.
                    .inkuTooltip(auxiliary.sourceIsLocked ? lockedReason : "")
                Text(model.display.localized(auxiliary.visionMode ? "上のモデルが観察し、同じモデルで各世代を描きます。" : "制作のモデルで描きます。方向性は読み取りを変える世代にだけ渡します。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                Stepper(model.display.localizedFormat("生成する世代数: %ld", auxiliary.generations), value: $auxiliary.generations, in: 1...10)
                HStack {
                    ForEach(AuxiliaryProvider.allowedKinds, id: \.self) { kind in
                        Toggle(model.display.localized(AuxiliaryModel.kindLabel(kind)), isOn: Binding(
                            get: { auxiliary.enabledKinds.contains(kind) },
                            set: { if $0 { auxiliary.enabledKinds.insert(kind) } else { auxiliary.enabledKinds.remove(kind) } }))
                            .toggleStyle(.button).disabled(kind == "reinterpretation" && auxiliary.sourceIsLocked)
                            .inkuTooltip(kindTooltip(kind), placement: .bottom)
                    }
                }
                HStack {
                    Toggle(model.display.localized("元のワイルド設定を引き継ぐ"), isOn: $auxiliary.inheritWild)
                    if !auxiliary.inheritWild { Toggle(model.display.localized("ワイルド"), isOn: $auxiliary.wildOverride) }
                }
                Button(model.display.localizedFormat("%ld 世代の推敲を開始", auxiliary.generations), systemImage: "play") { Task { await auxiliary.startRefinement(app: model) } }
                    .disabled(auxiliary.sourceWork == nil || auxiliary.enabledKinds.isEmpty || (auxiliary.visionMode && auxiliary.modelReference.isEmpty))
            }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
        }.disabled(auxiliary.running || auxiliary.selectingSource || model.isBusy)
    }

    private var lockedReason: String {
        model.display.tooltip("編集した指示書で確定した作品です。記述を読み直す操作は使えません。", serverKey: "descriptionLockedReason")
    }

    /// AIRefineModal.svelte:255: what each element costs; reading names the lock on a held work.
    private func kindTooltip(_ kind: String) -> String {
        switch kind {
        case "reinterpretation":
            return auxiliary.sourceIsLocked ? lockedReason : model.display.tooltip("低速（LLM・API使用）", serverKey: "refineCostReading")
        case "catalog_change": return model.display.tooltip("超高速（LLM不要）", serverKey: "refineCostColor")
        case "layout_change": return model.display.tooltip("高速（補完の穴があるときだけLLM）", serverKey: "refineCostLayout")
        default: return model.display.tooltip("超高速（LLM不要）", serverKey: "refineCostTouch")
        }
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

    private var generations: some View {
        GroupBox(model.display.localizedFormat("保存した世代 (%ld)", auxiliary.completedGenerations)) {
            VStack(alignment: .leading, spacing: 12) {
                ScrollView(.horizontal) {
                    HStack(alignment: .top, spacing: 12) {
                        ForEach(auxiliary.generatedWorks, id: \.id) { work in
                            Button { observedGeneration = work } label: {
                                VStack {
                                    ArtworkThumbnail(work: work, renderer: model.renderer).frame(width: 130, height: 115)
                                    Text(work.effectiveSourceText).inkuFont(12).lineLimit(2).frame(width: 130)
                                }.padding(6)
                                    .background(observedGeneration?.id == work.id ? Color.accentColor.opacity(0.12) : Color.clear,
                                                in: RoundedRectangle(cornerRadius: 6))
                            }.buttonStyle(.plain).disabled(auxiliary.running || auxiliary.selectingSource || model.isBusy)
                        }
                    }
                }
                if let work = observedGeneration, auxiliary.generatedWorks.contains(where: { $0.id == work.id }) {
                    Text(model.display.localized("観察する作品")).inkuFont(12, weight: .semibold)
                    ArtworkCanvas(svg: work.svg, renderer: model.renderer, caption: work.effectiveSourceText)
                        .frame(height: 260)
                    HStack {
                        Button(model.display.localized("観察を閉じる")) { observedGeneration = nil }
                        Spacer()
                        if auxiliary.selectingSource {
                            ProgressView(model.display.localized("保存された世代の読込中")).controlSize(.small)
                        }
                        Button(model.display.localized("この作品から再開")) {
                            Task { if await auxiliary.selectRefinementSource(work, app: model) { observedGeneration = nil } }
                        }.disabled(auxiliary.running || auxiliary.stopping || auxiliary.selectingSource || model.isBusy || work.trashed)
                    }
                }
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
