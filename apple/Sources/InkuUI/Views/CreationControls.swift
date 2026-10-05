import InkuHost
import InkuPersistence
import SwiftUI

extension View {
    func creationPanel() -> some View {
        padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.quaternary))
    }
}

@MainActor
struct CreationModelPicker: View {
    @Bindable var model: AppModel
    var body: some View { BatchModelPickerView(model: model) }
}

/// Every action receives the same work that supplies the canvas image and caption.
/// Web CanvasArtworkWorkspace.svelte:186-395: the marks sit at the work's lower left, the actions at its lower right,
/// as 34pt floating circles 14pt above the bottom and 18pt in from the side.
@MainActor
struct CreationCanvasControls: View {
    enum Corner { case left, right }

    @Bindable var model: AppModel
    var corner = Corner.right
    let work: SavedWork?
    let saved: Bool
    let disabled: Bool
    var browsingDisabled = false
    var generationInfoOpen = false
    let onReplayWork: (SavedWork) -> Void
    let onWorkAction: (SavedWork, String) -> Void
    let onShowSaijiki: () -> Void
    @State private var starTargetID: String?
    @State private var starredOverride: Bool?

    private var caption: String { work?.effectiveSourceText.trimmingCharacters(in: .whitespacesAndNewlines) ?? "" }
    private var verticalCaptionAvailable: Bool { CanvasInteraction.supportsVerticalCaption(caption) }
    private var starred: Bool {
        guard let work else { return false }
        return model.library.works.first(where: { $0.id == work.id })?.starred ?? starredOverride ?? work.starred
    }

    var body: some View {
        Group {
            switch corner {
            case .left: captionAndMarks
            case .right: outputControls
            }
        }
        .buttonStyle(InkuFloatingCircleButtonStyle())
        .onChange(of: work?.id, initial: true) { _, id in
            starTargetID = id; starredOverride = nil
        }
    }

    @ViewBuilder private var captionAndMarks: some View {
      if model.display.visible("work_tools") {
        HStack(spacing: 6) {
            Button { model.display.preferences.captionVisible.toggle() } label: {
                Image(systemName: "text.bubble")
            }
            .buttonStyle(InkuFloatingCircleButtonStyle(active: model.display.preferences.captionVisible))
            .accessibilityLabel(model.display.localized("詞書の表示"))
            .accessibilityValue(model.display.localized(model.display.preferences.captionVisible ? "オン" : "オフ"))
            .help(model.display.tooltip("詞書（入力テキスト）の表示/非表示", serverKey: "tooltipCanvasCaption"))
            .disabled(browsingDisabled || caption.isEmpty)
            if verticalCaptionAvailable {
                // Web `.caption-writing-mode`: a 12px select beside the caption button.
                Picker(model.display.localized("詞書きの書字方向"), selection: Binding(
                    get: { model.display.preferences.captionVertical },
                    set: { model.display.preferences.captionVertical = $0 })) {
                    Text(model.display.localized("横書き")).tag(false)
                    Text(model.display.localized("縦書き")).tag(true)
                }.pickerStyle(.menu).labelsHidden().fixedSize()
                    .inkuFont(12)
                    .padding(.horizontal, 4).padding(.vertical, 2)
                    .background(Capsule().fill(InkuColor.floating))
                    .accessibilityLabel(model.display.localized("詞書きの書字方向"))
                    .help(model.display.tooltip("詞書きの書字方向"))
                    .disabled(browsingDisabled || !model.display.preferences.captionVisible || caption.isEmpty)
            }
            Button { toggleStar() } label: { Text("★") }
                .buttonStyle(InkuFloatingCircleButtonStyle(active: starred, tint: starred ? Color(red: 0.84, green: 0.61, blue: 0.13) : nil))
                .accessibilityLabel(model.display.localized(starred ? "スターを外す" : "スターを付ける"))
                .accessibilityValue(model.display.localized(starred ? "オン" : "オフ"))
                .help(model.display.tooltip(starred ? "スターを外す" : "スターを付ける", serverKey: starred ? "starOn" : "starOff"))
                .disabled(!saved || browsingDisabled || model.library.mutating)
            if let work, saved {
                LibraryAnnotationMarkButton(model: model, work: work, mark: .revision).disabled(disabled)
                LibraryAnnotationMarkButton(model: model, work: work, mark: .share).disabled(disabled)
            } else {
                Button {} label: { Image(systemName: "pencil.circle") }
                    .accessibilityLabel(model.display.localized("推敲の印"))
                    .disabled(true)
            }
        }.fixedSize()
      }
    }

    private var outputControls: some View {
        HStack(spacing: 6) {
            if model.display.visible("detail_status"), let hash = work?.renderHash, !hash.isEmpty {
                Button { perform("copy-hash") } label: { Text("#").fontWeight(.semibold) }
                    .accessibilityLabel(model.display.localized("full hash をコピー"))
                    .help(model.display.tooltip("クリックでfull hashをコピーします"))
                    .disabled(browsingDisabled)
            }
            if model.display.visible("work_tools") {
                Button { if let work { onReplayWork(work) } } label: { Image(systemName: "arrow.clockwise") }
                    .accessibilityLabel(model.display.localized("再現を比較"))
                    .help(model.display.tooltip("保存時のSVGと、同じ保存条件を現行エンジンで描いた結果を比較します。作品・履歴・系譜は変わりません。"))
                    .disabled(!saved || disabled)
            }
            if model.display.visible("detail_status") {
                Button { perform("info") } label: { Image(systemName: "info.circle") }
                    .buttonStyle(InkuFloatingCircleButtonStyle(active: generationInfoOpen))
                    .accessibilityLabel(model.display.localized("生成情報"))
                    .help(model.display.tooltip("選択中作品の生成情報を表示"))
                    .disabled(work == nil || browsingDisabled)
            }
            if model.display.visible("work_tools") {
                Button(action: onShowSaijiki) { Image(systemName: "book") }
                    .disabled(browsingDisabled)
                    .accessibilityLabel(model.display.localized("歳時記を開く"))
                    .help(model.display.tooltip("歳時記の語と説明を参照します。", serverKey: "tooltipSaijikiToggle"))
            }
            Button { perform(model.display.visible("work_tools") ? "export" : "export-card") } label: {
                Image(systemName: "square.and.arrow.down")
            }
            .accessibilityLabel(model.display.localized(model.display.visible("work_tools") ? "書き出す" : "共有カード"))
            .help(model.display.tooltip(saved ? (model.display.visible("work_tools") ? "書き出す" : "表示中の作品を共有カードとして書き出します。版面と刻印は設定に従います。")
                : "書き出すには、先に作品を保存してください。", serverKey: saved && !model.display.visible("work_tools") ? "tooltipCanvasDownloadCard" : nil))
            .disabled(!saved || disabled)
            Button {
                guard let work, !disabled else { return }
                Task { await model.copyImage(work: work) }
            } label: { Image(systemName: "doc.on.clipboard") }
            .accessibilityLabel(model.display.localized("クリップボードにコピー"))
            .help(model.display.tooltip("クリップボードにコピー", serverKey: "canvasCopyToClipboard"))
            .disabled(work?.svg.isEmpty != false || disabled)
            if model.display.visible("work_tools") {
                Button { perform("presentation") } label: { Image(systemName: "arrow.up.left.and.arrow.down.right") }
                    .accessibilityLabel(model.display.localized("プレゼンテーションモードを開く"))
                    .help(model.display.tooltip("プレゼンテーションモード (全画面表示)", serverKey: "tooltipCanvasPresentation"))
                    .disabled(work?.svg.isEmpty != false || browsingDisabled)
            }
        }.fixedSize()
    }

    private func perform(_ action: String) {
        guard let work else { return }
        let allowed = SavedWorkActionState.isBrowsingAction(action) ? !browsingDisabled : !disabled
        guard allowed else { return }
        onWorkAction(work, action)
    }

    private func toggleStar() {
        guard var target = work, saved, !browsingDisabled, !model.library.mutating else { return }
        target.starred = starred
        let pinnedTarget = target
        Task {
            await model.library.toggleStar(pinnedTarget)
            do {
                let value = try await model.auxiliaryDatabase().work(id: pinnedTarget.id)
                guard starTargetID == pinnedTarget.id, !Task.isCancelled else { return }
                starredOverride = value?.starred
            } catch {
                guard starTargetID == pinnedTarget.id, !Task.isCancelled else { return }
                model.errorText = error.localizedDescription
            }
        }
    }
}

/// Saved process text is independent of the model's current authoring session.
@MainActor
struct CreationDisplayedProcess: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let saved: Bool
    let disabled: Bool
    let onWorkAction: (SavedWork, String) -> Void

    private var sketch: String? { work.sketchText.flatMap { $0.isEmpty ? nil : $0 } }
    private var ddl: String { work.ddl ?? "" }
    private var hasDDL: Bool { !ddl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    private var canEditSketch: Bool { saved && model.workActionState(for: work)?.canReadDescription == true }
    private var ddlHeading: String {
        let language: String
        if let recorded = work.instructionLangResolved, ["ja", "en"].contains(recorded) {
            language = recorded
        } else if ddl.unicodeScalars.contains(where: { (0x3040...0x30ff).contains($0.value) || (0x3400...0x9fff).contains($0.value) }) {
            language = "ja"
        } else if ddl.unicodeScalars.contains(where: { (0x41...0x5a).contains($0.value) || (0x61...0x7a).contains($0.value) }) {
            language = "en"
        } else { language = model.display.preferences.language == "en" ? "en" : "ja" }
        return language == "ja" ? "指示書（日本語DDL）" : "指示書（英語DDL）"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // `+page.svelte` `.displayed-work-heading`: 12px semibold under a rule, 16pt above.
            Text(model.display.webCopy("displayedWorkProcess", "表示中作品の写生と指示書")).inkuFont(12, weight: .semibold)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 16)
                .overlay(alignment: .top) { Rectangle().fill(InkuColor.border).frame(height: 1) }
            HStack {
                DisclosureGroup(isExpanded: Binding(
                    get: { model.display.preferences.sketchExpanded ?? true },
                    set: { model.display.preferences.sketchExpanded = $0 })) {
                    VStack(alignment: .leading, spacing: 8) {
                        if !sketchNote.isEmpty {
                            Text(model.display.localized(sketchNote)).inkuFont(12).foregroundStyle(.secondary)
                        }
                        if let sketch { Text(sketch).inkuFont(13).lineSpacing(13 * 0.5).textSelection(.enabled) }
                        if let grain = work.sketchGrain {
                            Text(model.display.localizedFormat("旧写生の区切り: %@（保存記録）", grain))
                                .inkuFont(12).foregroundStyle(.secondary)
                        }
                    }.padding(.top, 6)
                } label: { Text(model.display.localized("写生 (Stage 0.5)")).inkuFont(12, weight: .semibold) }
                .help(model.display.tooltip("写生層が書いた文章を表示します。", serverKey: "tooltipSketchToggle"))
                if sketch != nil {
                    Button(model.display.localized("編集")) {
                        model.display.preferences.sketchExpanded = true
                        onWorkAction(work, "sketch")
                    }.buttonStyle(InkuGhostButtonStyle()).disabled(!canEditSketch || disabled)
                        .help(model.display.tooltip("表示中作品の写生を編集します。"))
                }
            }
            if model.display.visible("ddl_tools"), work.ddl != nil {
                HStack(alignment: .firstTextBaseline) {
                    Text(model.display.localized(ddlHeading)).inkuFont(12, weight: .semibold)
                        .help(model.display.tooltip("指示書はこの言語の文法で読みます。", serverKey: "tooltipDdlLang"))
                    Spacer(minLength: 4)
                    Button(model.display.localized("指示書を編集")) { onWorkAction(work, "ddl") }
                        .buttonStyle(InkuGhostButtonStyle())
                        .disabled(!saved || !hasDDL || disabled)
                        .help(model.display.tooltip("表示中の作品の指示書を編集して、その子として描き直します", serverKey: "tooltipDdlEdit"))
                }
                ScrollView {
                    Text(ddl).inkuFont(12.5, design: .monospaced).lineSpacing(4).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.leading, 10)
                }.frame(minHeight: 100, maxHeight: 220)
                    .overlay(alignment: .leading) { Rectangle().fill(.quaternary).frame(width: 2) }
                HStack {
                    Spacer(minLength: 0)
                    Button(model.display.localized("指示書から描画"), systemImage: "arrow.clockwise") { onWorkAction(work, "draw-ddl") }
                        .buttonStyle(InkuGhostButtonStyle())
                        .disabled(!saved || !hasDDL || disabled)
                        .help(model.display.tooltip("表示中の指示書（正規化DDL）をそのままStage 2へ渡して描き直します。Stage 1は走らないので解釈は変わりません。", serverKey: "tooltipDdlPaint"))
                }
            }
        }
    }

    private var sketchNote: String {
        switch work.sketchState {
        case "fine", "coarse": ""
        case "supplemented": "記述に足りない場所の広がりや季節・時刻の光を補って描いた"
        case "not_needed": "写生を通したが、補うものがなかった"
        case "fallback": "写生を試みたが届かず、記述のまま解釈した"
        case "off": "写生を通さずに描いた"
        case "not_applicable": "この経路は写生を通らない"
        default: "写生が記録される前に描かれた（切って描いたのではない）"
        }
    }
}
