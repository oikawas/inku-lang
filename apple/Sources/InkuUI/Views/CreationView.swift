import InkuPersistence
import SwiftUI

struct BatchWorkspaceSelection {
    private enum Display { case history, latest, row(SavedWork, String) }
    private var display = Display.history
    var revision = UUID()
    init() {}

    var followsLatest: Bool { if case .latest = display { true } else { false } }
    var pinnedWork: SavedWork? { if case .row(let work, _) = display { work } else { nil } }
    var rowID: String? { if case .row(_, let id) = display { id } else { nil } }

    mutating func showHistory() { display = .history; revision = UUID() }
    mutating func followLatest() { display = .latest; revision = UUID() }
    mutating func pin(_ work: SavedWork, rowID: String) { display = .row(work, rowID); revision = UUID() }
    mutating func invalidateReads() { revision = UUID() }
}

/// Web `.main-shell`: the input panel, its 18pt toggle, the canvas panel, and the history strip under both.
@MainActor
struct CreationView: View {
    @Bindable var model: AppModel
    @Bindable var history: HistoryModel
    @Bindable var automation: AutomationModel
    @Bindable var maintenance: LocalMaintenance
    @Bindable var ui: WorkspaceUIState
    @Binding var batchWorkspace: BatchWorkspaceSelection
    /// The refine workspace, shown in place of the canvas while it is open.
    var inlinePanel: AnyView? = nil
    let onEditWork: (SavedWork, WorkEditMode) -> Void
    let onAdjustWork: (SavedWork) -> Void
    let onReplayWork: (SavedWork) -> Void
    let onWorkAction: (SavedWork, String) -> Void
    let onLineageExport: (String) -> Void
    var onPresentWork: () -> Void = {}
    var onWorkspaceWorkChange: (SavedWork?) -> Void = { _ in }
    private var controlsDisabled: Bool { model.isBusy || automation.isOccupied }
    private var browsingDisabled: Bool { model.isBrowsingLocked }
    @State private var showColorCatalogs = false
    @State private var showModelPicker = false
    @State private var showConditionDetails = false
    @State private var showPaperPicker = false
    @State private var showSketchMenu = false
    @State private var showNewDDL = false
    @State private var rightPanelWidth: CGFloat = 0
    @Environment(\.inkuWindowSize) private var windowSize
    private var isBatch: Bool { automation.workspaceInputMode == "batch" }
    private var batchWork: SavedWork? { batchWorkspace.pinnedWork ?? (batchWorkspace.followsLatest ? automation.observedWork : nil) }
    private var usesBatchWork: Bool { isBatch && batchWork != nil }
    private var workspaceWork: SavedWork? { usesBatchWork ? batchWork : model.displayedWork }
    private var workspaceIsPreview: Bool { !usesBatchWork && model.isPreview }
    private var hasSavedWorkspaceWork: Bool { workspaceWork?.trashed == false && !workspaceIsPreview }
    private var display: DisplaySettings { model.display }
    #if os(macOS)
    @Environment(DDLImportController.self) private var importer
    #endif

    /// `+page.svelte:3738-3779`: 440pt, and `min(400px, 42vw)` at 1180 or narrower.
    private var compactWindow: Bool { (windowSize?.width ?? 1320) <= 1180 }
    private var leftPanelWidth: CGFloat {
        let width = windowSize?.width ?? 1320
        return compactWindow ? min(400, width * 0.42) : 440
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                if !ui.leftPanelCollapsed {
                    leftPanel.frame(width: leftPanelWidth).disabled(inlinePanel != nil)
                }
                leftPanelToggle
                rightPanel
            }
            if display.visible("history") {
                Rectangle().fill(InkuColor.border).frame(height: 1)
                HistoryStripView(model: model, history: history, displayedWorkID: workspaceWork?.id,
                                 onSelectWork: { _ in batchWorkspace.showHistory() })
                    .disabled(inlinePanel != nil)
            }
        }
        .overlay(alignment: .trailing) {
            if ui.saijikiOpen { saijikiDrawer.transition(.move(edge: .trailing)) }
        }
        .animation(.easeOut(duration: 0.2), value: ui.saijikiOpen)
        .sheet(isPresented: $showColorCatalogs) {
            ColorCatalogView(model: model, descriptionOnly: true)
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.colorCatalog)
        }
        .sheet(isPresented: $showModelPicker) {
            BatchModelPickerView(model: model)
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.modelSelection)
        }
        .sheet(isPresented: $showNewDDL) {
            NewDdlAuthoringSheet(model: model)
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.ddlEditor)
        }
        .onChange(of: automation.workspaceInputMode) { _, _ in batchWorkspace.invalidateReads() }
        .onChange(of: ui.workspaceTab) { _, tab in
            batchWorkspace.invalidateReads()
            if tab == "lineage", isBatch, batchWorkspace.followsLatest,
               let work = batchWork, let rowID = automation.observedRow?.id {
                batchWorkspace.pin(work, rowID: rowID)
            }
        }
        .onDisappear { batchWorkspace.invalidateReads() }
        .onChange(of: workspaceWork?.id) { _, _ in
            onWorkspaceWorkChange(workspaceWork)
            // CanvasGenerationInfo follows the chosen work only when the setting says so.
            if !display.preferences.keepGenerationInfo { ui.generationInfoOpen = false }
        }
        .onAppear {
            model.inputMode = "description"
            if !["off", "on"].contains(model.sketchMode) { model.sketchMode = "off" }
            if !["auto", "fixed"].contains(model.catalogMode) { model.catalogMode = "fixed" }
            onWorkspaceWorkChange(workspaceWork)
        }
    }

    // MARK: - Left panel

    /// Web `.left-panel` / `.panel-scroll`: padding 14×16 (12 at 1180 or narrower), 14 between sections.
    private var leftPanel: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if automation.running && automation.mode == "demo" { demoBanner }
                if display.visible("input_modes") { inputTabs }
                inputContents
                if !isBatch && display.visible("ddl_tools") {
                    HStack {
                        Spacer(minLength: 0)
                        Button(display.webCopy("ddlNewButton", "指示書の新規作成")) { showNewDDL = true }
                            .buttonStyle(InkuGhostButtonStyle())
                            .disabled(controlsDisabled)
                            .inkuTooltip(display.tooltip("記述を介さず、指示書を直接書いて独立した作品として描画します", serverKey: "tooltipDdlNew"))
                    }.padding(.top, -6)
                }
                if !isBatch, let work = workspaceWork {
                    CreationDisplayedProcess(model: model, work: work, saved: hasSavedWorkspaceWork,
                                             disabled: controlsDisabled, onWorkAction: onWorkAction)
                }
                if !isBatch, display.visible("detail_status"), let work = workspaceWork {
                    CreationResultLog(model: model, work: work)
                }
                statusFooter
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 14).padding(.horizontal, compactWindow ? 12 : 16)
        }
        .background(InkuColor.bg)
    }

    /// InputPanel.svelte:180-198: two equal underline tabs; a running tab carries a dot and `(n/N ↻r)`.
    private var inputTabs: some View {
        HStack(spacing: 0) {
            InkuPanelTab(title: display.webCopy("modeSingle", "記述"), selected: !isBatch,
                         running: model.isBusy && !automation.isOccupied) {
                automation.workspaceInputMode = "description"
            }
            .inkuTooltip(display.tooltip("自由な自然言語で記述を入力して1枚ずつ描画します", serverKey: "tooltipInputTabSingle"))
            InkuPanelTab(title: display.webCopy("modeBatch", "バッチ"), selected: isBatch,
                         running: automation.running && automation.mode == "batch", progress: batchProgress) {
                automation.workspaceInputMode = "batch"
            }
            .inkuTooltip(display.tooltip("改行区切りで複数の記述を入力し、順次連続して描画します", serverKey: "tooltipInputTabBatch"))
        }
        .overlay(alignment: .bottom) { Rectangle().fill(InkuColor.border).frame(height: 1).allowsHitTesting(false) }
        .disabled(browsingDisabled)
    }

    private var batchProgress: String {
        guard automation.running, automation.mode == "batch", !automation.rows.isEmpty else { return "" }
        let current = automation.completedCount + (automation.activeRow == nil ? 0 : 1)
        guard current > 0 else { return "" }
        let retry = automation.currentRetryRound > 0 ? " ↻\(automation.currentRetryRound)" : ""
        return "(\(current)/\(automation.rows.count)\(retry))"
    }

    /// `+page.svelte` `.demo-running-banner`: a way back to the demo settings and the run status.
    private var demoBanner: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button(display.webCopy("demoOpenSettings", "デモの設定・進行状況")) {
                ui.settingsSection = .demo; ui.settingsOpen = true
            }.buttonStyle(InkuGhostButtonStyle())
            runStatus(label: automation.status, onStop: { Task { await automation.stop(app: model) } },
                      stopping: automation.stopping)
        }
        .padding(.vertical, 10)
        .overlay(alignment: .bottom) { Rectangle().fill(InkuColor.border).frame(height: 1) }
    }

    private var inputContents: some View {
        VStack(alignment: .leading, spacing: 6) {
            if isBatch {
                BatchPanelView(model: model, automation: automation, inputOnly: true,
                               onObserveWork: { work, rowID in batchWorkspace.pin(work, rowID: rowID) },
                               followsLatestWork: batchWorkspace.followsLatest,
                               selectedRowID: batchWorkspace.rowID, observationRevision: $batchWorkspace.revision, ui: ui)
            } else {
                input
                if display.visible("drawing_settings") { nextConditions }
                generationAction.padding(.top, 8)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private var descriptionLocked: Bool { model.sourceLocked && model.selectedWork != nil }

    /// InputPanel.svelte:271-305: a 14px heading with a 12px hint, the box (14px, line 1.65), then the meter row.
    private var input: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 8) {
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 8) {
                        Text(display.webCopy("inputSectionLabel", "記述")).inkuFont(14, weight: .semibold)
                        if descriptionLocked {
                            Label(display.webCopy("descriptionLockedMark", "ロック"), systemImage: "lock").inkuFont(11, weight: .medium).foregroundStyle(.secondary)
                        }
                    }
                    Text(display.webCopy("inputSectionHint", "短い文章で、表現したいものを入力。")).inkuFont(12).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                Button(display.webCopy("clearInputBtn", "新規")) {
                    batchWorkspace.showHistory()
                    #if os(macOS)
                    importer.clearMessage()
                    #endif
                    model.newWork()
                }
                .buttonStyle(InkuGhostButtonStyle())
                .disabled(controlsDisabled)
                .inkuTooltip(display.tooltip("入力をクリアする", serverKey: "tooltipInputClear"))
            }
            editor(text: $model.descriptionText, readOnly: descriptionLocked)
            if descriptionLocked {
                Text(display.webCopy("pipelineDescriptionLocked", "この作品はDDLを編集しているため、記述は固定しています。"))
                    .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            // InputPanel.svelte:308-311 `.input-meta-row`: the comment hint at the left, the meter at the right.
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(display.webCopy("inputCommentHint", "[括弧内文字列はコメント扱い]")).inkuFont(12).foregroundStyle(.tertiary)
                Spacer(minLength: 0)
                DescriptionMeterView(model: model, text: model.descriptionText)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// InputPanel.svelte:201-262,445-503: "次に描く条件", two rows with a 変更 button, then the compact row.
    private var nextConditions: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(display.webCopy("nextWorkConditions", "次の生成条件")).inkuFont(12, weight: .medium).foregroundStyle(.secondary)
                .padding(.top, 8).padding(.bottom, 2)
            conditionRow(display.webCopy("modelButton", "モデル"),
                         value: model.nextBatchDrawingModelReference.isEmpty ? display.localized("選択してください") : model.nextBatchDrawingModelReference,
                         help: tip("次の作品の描画モデルを選びます。")) { showModelPicker = true }
                .disabled(controlsDisabled)
            Rectangle().fill(InkuColor.border).frame(height: 1)
            conditionRow(display.webCopy("colorCatalogButton", "色カタログ"), value: catalogSummary,
                         help: tip("次の作品の配色を選びます。")) { showColorCatalogs = true }
                .disabled(controlsDisabled || model.catalogs.isEmpty)
                .accessibilityLabel(display.localized("色カタログを開く"))
                .accessibilityValue(catalogSummary)
            Rectangle().fill(InkuColor.border).frame(height: 1)
            WrappingHStack(spacing: 6) { compactConditionControls }
                .padding(.top, 2)
                .disabled(controlsDisabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var catalogSummary: String {
        model.catalogMode == "auto" ? display.localized("記述から選択")
            : model.catalogs.first { $0.id == model.catalogID }?.name ?? model.catalogID
    }

    private func conditionRow(_ label: String, value: String, help: String, action: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 8) {
                Text(label).inkuFont(12, weight: .medium).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Button(display.webCopy("editButton", "変更"), action: action)
                    .buttonStyle(InkuGhostButtonStyle())
                    .inkuTooltip(help)
            }
            Text(value).inkuFont(14).lineLimit(2).truncationMode(.middle)
                .frame(maxWidth: .infinity, alignment: .leading)
                .inkuTooltip(display.tooltipValue(value))
        }
        .padding(.vertical, 7)
    }

    @ViewBuilder private var compactConditionControls: some View {
        Button(display.localized("写生") + ": " + display.localized(model.sketchMode == "on" ? "あり" : "なし")) { showSketchMenu.toggle() }
            .buttonStyle(InkuGhostButtonStyle())
            .inkuTooltip(display.tooltip("次の作品で写生を使うかを選びます。", serverKey: "tooltipInputSketch"))
            .popover(isPresented: $showSketchMenu, arrowEdge: .bottom) { sketchMenu }
        Button(display.webCopy("wildButton", "暴れる") + " " + display.webCopy(model.wild ? "wildEnabled" : "wildDisabled", model.wild ? "入" : "切")) {
            model.wild.toggle()
        }
        .buttonStyle(InkuGhostButtonStyle(active: model.wild))
        .accessibilityValue(display.localized(model.wild ? "オン" : "オフ"))
        .inkuTooltip(tip("次の作品の筆致を規則から外します。"))
        Button { showPaperPicker = true } label: {
            Label(display.localized("用紙") + ": " + (model.canvases.first { $0.id == model.canvasID }?.label ?? model.canvasID),
                  systemImage: "rectangle.portrait")
        }
        .buttonStyle(InkuGhostButtonStyle())
        .inkuTooltip(tip("用紙の形と意図を見て、次の作品の用紙を選びます。"))
        .popover(isPresented: $showPaperPicker) {
            CreationPaperPicker(model: model) { showPaperPicker = false }.environment(display)
        }
        .accessibilityValue(model.canvases.first { $0.id == model.canvasID }?.name ?? model.canvasID)
        // Native: language, seed and catalog choice, which the Web keeps in other places.
        Button(display.localized("生成条件の詳細")) { showConditionDetails = true }
            .buttonStyle(InkuGhostButtonStyle())
            .inkuTooltip(tip("言語・シード・配色の選び方を確認して変更します。"))
            .popover(isPresented: $showConditionDetails) { conditionDetails }
    }

    /// Web SketchSelect: the two choices with what each does.
    private var sketchMenu: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach([("off", "なし", "写生を通さず、記述だけで描く"), ("on", "あり", "記述の横に、場所の広がりや季節・時刻の光を補って描く")], id: \.0) { option in
                Button {
                    model.sketchMode = option.0; showSketchMenu = false
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Image(systemName: "checkmark").opacity(model.sketchMode == option.0 ? 1 : 0)
                            Text(display.localized(option.1)).inkuFont(13, weight: .medium)
                        }
                        Text(display.localized(option.2)).inkuFont(12).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true).padding(.leading, 20)
                    }
                    .padding(.vertical, 6).padding(.horizontal, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }.buttonStyle(.plain)
            }
        }.padding(6).frame(width: 310)
    }

    private var conditionDetails: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(display.localized("生成条件の詳細")).inkuFont(14, weight: .semibold)
            Picker(display.localized("配色の選び方"), selection: $model.catalogMode) {
                Text(display.localized("指定")).tag("fixed")
                Text(display.localized("記述から選択")).tag("auto")
            }.inkuTooltip(tip("次の作品の配色を選びます。"))
            TextField(display.localized("シード（空欄で新規）"), text: $model.seedText).textFieldStyle(.roundedBorder)
                .inkuTooltip(tip("空欄なら次の描画で新しいシードを使います。"))
        }.padding(16).frame(width: 360).disabled(controlsDisabled)
    }

    /// InputPanel.svelte:308-337: the paint button, or the run status while drawing.
    private var generationAction: some View {
        VStack(alignment: .leading, spacing: 10) {
            if model.inputMode == "description" && !model.hasNextDrawingModel {
                Button {
                    ui.settingsSection = .models; ui.settingsOpen = true
                } label: {
                    Label(display.localized("記述から生成するには、設定で接続先とモデルを指定してください。"), systemImage: "gearshape")
                        .inkuFont(13).multilineTextAlignment(.leading)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .disabled(browsingDisabled)
            }
            if model.inputMode == "description" && model.hasNextDrawingModel && ui.drawingKeyMissing {
                // R6: the Web has no first-run guide (its keys live on the Server); this points to the connection page.
                VStack(alignment: .leading, spacing: 6) {
                    Text(display.localizedFormat("描画モデル（%@）の接続先にAPIキーがありません。設定の「モデル設定」でAPIキーを入力すると描けます。",
                                                 model.nextDrawingModelReference))
                        .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    Button(display.localized("接続設定を開く")) { ui.settingsSection = .models; ui.settingsOpen = true }
                        .buttonStyle(InkuGhostButtonStyle(prominent: true))
                        .disabled(browsingDisabled)
                }
                .padding(.vertical, 8).padding(.horizontal, 10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 4).fill(InkuColor.panel))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
            }
            if automation.isOccupied {
                Button { Task { await automation.stop(app: model) } } label: {
                    Label(display.localized(automation.stopping ? "停止中" : "停止"), systemImage: "stop.fill")
                }
                .buttonStyle(InkuPaintButtonStyle())
                .disabled(!automation.running || automation.stopping)
            } else if model.isBusy {
                runStatus(label: model.status, onStop: { Task { await model.cancel() } }, stopping: false)
            } else if descriptionLocked {
                // InputPanel.svelte:326-334: a held work is drawn from its description only as a new work, named as such.
                Button { batchWorkspace.showHistory(); Task { await model.forkDescription() } } label: {
                    Text(display.webCopy("pipelineForkDescription", "この記述から新しい作品を作る"))
                }
                .buttonStyle(InkuPaintButtonStyle())
                .keyboardShortcut(.return, modifiers: .command)
                .disabled(!model.canForkDescription || automation.isOccupied)
                .inkuTooltip(display.tooltip("この記述をそのまま使って、新しい作品として描き直します。", serverKey: "tooltipForkDescription"))
            } else {
                Button { batchWorkspace.showHistory(); Task { await model.generateDescription() } } label: {
                    Text(display.webCopy("submitBtn", "生成"))
                }
                .buttonStyle(InkuPaintButtonStyle())
                .keyboardShortcut(.return, modifiers: .command)
                .disabled(!model.canGenerateDescription || automation.isOccupied)
                .inkuTooltip(tip("入力と次の生成条件から作品を描きます。"))
            }
        }
    }

    /// Web RunStatus.svelte: mascot, the stage and its provider facts, and the stop button, in one bordered box.
    private func runStatus(label: String, onStop: @escaping () -> Void, stopping: Bool) -> some View {
        HStack(alignment: .center, spacing: 10) {
            NativeMascot(kind: display.preferences.mascot).frame(width: 28, height: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text(display.message(label)).inkuFont(12, weight: .medium).lineLimit(2)
                ProviderProgressView(model: model)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Button(display.localized(stopping ? "停止中" : "停止"), action: onStop)
                .buttonStyle(InkuGhostButtonStyle())
                .keyboardShortcut(.escape, modifiers: [])
                .disabled(stopping)
                .inkuTooltip(tip("実行中の描画を停止します。"))
        }
        .padding(.vertical, 6).padding(.horizontal, 8)
        .frame(minHeight: 46)
        .background(RoundedRectangle(cornerRadius: 4).fill(InkuColor.panel))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2))
    }

    /// The native status line and the backup and result-log reports, which the Web has no place for.
    @ViewBuilder private var statusFooter: some View {
        let status = automation.running ? automation.status : model.status
        if !status.isEmpty || !maintenance.backupStatus.isEmpty || !maintenance.logStatus.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                if !status.isEmpty && !model.isBusy { Text(display.message(status)).inkuFont(12).lineLimit(2) }
                if !maintenance.backupStatus.isEmpty { Text(display.message(maintenance.backupStatus)).inkuFont(11) }
                if !maintenance.logStatus.isEmpty { Text(display.message(maintenance.logStatus)).inkuFont(11) }
            }
            .foregroundStyle(.secondary)
            .textSelection(.enabled)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// InputPanel.svelte:292-304: the textarea over LabelHighlight, which paints the numbers and comments grey.
    private func editor(text: Binding<String>, readOnly: Bool = false) -> some View {
        let scale = display.preferences.textScale
        return ZStack(alignment: .topLeading) {
            InkuTextEditor(text: text, isEditable: !readOnly, accessibilityLabel: display.localized("記述"), style: .description)
                .disabled(controlsDisabled)
            if text.wrappedValue.isEmpty {
                Text(display.webCopy("inputPlaceholder", "山の向こうに月が昇る")).inkuFont(14).foregroundStyle(.tertiary)
                    .padding(.vertical, 9).padding(.horizontal, 10).allowsHitTesting(false)
            }
        }
        // Five rows at 14px with line height 1.65, as `rows="5"`.
        .frame(height: (5 * 14 * 1.65 + 18) * scale)
        .background(readOnly ? InkuColor.bg2 : InkuColor.panel, in: RoundedRectangle(cornerRadius: 4))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(InkuColor.border2, style: StrokeStyle(lineWidth: 1, dash: readOnly ? [4, 3] : [])))
    }

    private var leftPanelToggle: some View {
        let title = display.localized(ui.leftPanelCollapsed ? "記述エリアを開く" : "記述エリアを畳む")
        return Button { ui.leftPanelCollapsed.toggle() } label: {
            Text(ui.leftPanelCollapsed ? "›" : "‹").inkuFont(13).foregroundStyle(.secondary)
                .frame(width: 18).frame(maxHeight: .infinity)
                .background(InkuColor.bg2)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .overlay(alignment: .trailing) { Rectangle().fill(InkuColor.border).frame(width: 1) }
        .accessibilityLabel(title)
        .inkuTooltip(display.preferences.showTooltips ? title : "")
    }

    // MARK: - Canvas panel

    private var rightPanel: some View {
        VStack(spacing: 0) {
            if display.visible("work_tools") && inlinePanel == nil { tabsRow }
            canvasArea
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { rightPanelWidth = $0 }
        .task(id: workspaceWork?.id) {
            guard let work = workspaceWork, hasSavedWorkspaceWork, !Task.isCancelled else { return }
            await history.locate(app: model, workID: work.id)
            guard !Task.isCancelled, workspaceWork?.id == work.id else { return }
            await model.loadWorkActionState(work)
        }
    }

    /// CanvasPanel.svelte:687-756,1025-1053: 作品／系譜 text tabs and the displayed work's conditions.
    /// Below 880pt (67.69em at 13px) the conditions take a second row, as the Web's container query does.
    private var tabsRow: some View {
        let wide = rightPanelWidth >= 880 * display.preferences.textScale
        let showsMeta = workspaceWork != nil && display.visible("detail_status")
        return VStack(spacing: 0) {
            HStack(spacing: 0) {
                InkuTextTab(title: display.webCopy("tabCanvas", "作品"), selected: ui.workspaceTab != "lineage", compact: !wide) {
                    ui.workspaceTab = "artwork"
                }
                .inkuTooltip(display.tooltip("描画された作品のキャンバスを表示します", serverKey: "tooltipCanvasTabCanvas"), placement: .bottom)
                InkuTextTab(title: display.localized("系譜"), selected: ui.workspaceTab == "lineage", compact: !wide) {
                    ui.workspaceTab = "lineage"
                }
                .disabled(workspaceWork == nil || browsingDisabled)
                .inkuTooltip(display.tooltip("作品の派生関係を表示"), placement: .bottom)
                if wide && showsMeta, let work = workspaceWork {
                    Spacer(minLength: 12)
                    metaStrip(work)
                } else {
                    Spacer(minLength: 8)
                }
                workActionMenu.padding(.leading, 8)
            }
            if !wide && showsMeta, let work = workspaceWork {
                metaStrip(work).frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            }
        }
        .padding(.horizontal, wide ? 16 : 10)
        .background(InkuColor.bg)
        .overlay(alignment: .bottom) { Rectangle().fill(InkuColor.border).frame(height: 1) }
    }

    private func metaStrip(_ work: SavedWork) -> some View {
        let stage1 = work.stage1Model ?? "DDL"
        let stage2 = work.stage2Model ?? stage1
        let catalog = work.renderColorCatalogName ?? work.renderColorCatalogID ?? work.catalogID ?? "—"
        let canvasID = work.renderCanvasAspectID ?? ""
        let canvas = model.canvases.first { $0.id == canvasID }?.label ?? work.renderCanvasAspect ?? (canvasID.isEmpty ? "—" : canvasID)
        let size = ByteCountFormatter.string(fromByteCount: Int64(work.svg.utf8.count), countStyle: .file)
        let created = Date(timeIntervalSince1970: Double(work.at) / 1000).formatted(.dateTime.year().month(.twoDigits).day(.twoDigits).hour().minute())
        return HStack(spacing: 0) {
            Text(display.webCopy("displayedWorkConditions", "表示中作品の描画条件")).inkuFont(12, weight: .medium)
                .foregroundStyle(.secondary).lineLimit(1).fixedSize()
                .padding(.trailing, 12)
            // CanvasPanel.svelte:707,726,730: each value carries its own title, the models as "解釈 / 描画".
            metaItem(display.localized("モデル"), maxWidth: 280, title: stage1 + " / " + stage2) {
                if stage1 == stage2 {
                    Text(stage1)
                } else {
                    VStack(alignment: .leading, spacing: 1) {
                        HStack(spacing: 4) { Text(display.localized("解釈")).foregroundStyle(.tertiary); Text(stage1) }
                        HStack(spacing: 4) { Text(display.localized("描画")).foregroundStyle(.tertiary); Text(stage2) }
                    }
                }
            }
            metaItem(display.localized("色カタログ"), maxWidth: 130, title: catalog) { Text(catalog) }
            metaItem(display.localized("キャンバス"), maxWidth: 100, title: canvas) { Text(canvas) }
            metaItem(display.localized("サイズ"), maxWidth: nil) { Text(size).monospacedDigit() }
            metaItem(display.localized("作成"), maxWidth: nil) { Text(created).monospacedDigit() }
        }
        .padding(.vertical, 7)
        .accessibilityElement(children: .combine)
    }

    private func metaItem<Value: View>(_ label: String, maxWidth: CGFloat?, title: String = "",
                                       @ViewBuilder value: () -> Value) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).inkuFont(12).foregroundStyle(.tertiary).lineLimit(1)
            value().inkuFont(13).foregroundStyle(.secondary).lineLimit(1).truncationMode(.tail)
                .frame(maxWidth: maxWidth, alignment: .leading)
                .fixedSize(horizontal: maxWidth == nil, vertical: false)
                .inkuTooltip(display.tooltipValue(title))
        }
        .padding(.horizontal, 12)
        .overlay(alignment: .leading) { Rectangle().fill(InkuColor.border).frame(width: 1).padding(.vertical, 2) }
    }

    /// Web WorkActionMenu (header variant): every action on the displayed work in one menu.
    @ViewBuilder private var workActionMenu: some View {
        if let work = workspaceWork, hasSavedWorkspaceWork {
            Menu {
                SavedWorkRefinementActions(model: model, work: work, onAction: onWorkAction, writingLocked: automation.isOccupied)
                Divider()
                Button(display.localized("再演奏"), systemImage: "arrow.clockwise") { onReplayWork(work) }
                    .disabled(controlsDisabled)
                Button(display.localized("生成情報"), systemImage: "info.circle") { onWorkAction(work, "info") }
                Button(display.localized("系譜の奥書")) { onWorkAction(work, "colophon") }.disabled(controlsDisabled)
                Button(display.localized("系譜を開く")) { ui.workspaceTab = "lineage" }
                Divider()
                Button(display.localized("全画面で表示")) { onPresentWork() }
                    .keyboardShortcut("f", modifiers: [.command, .shift])
            } label: {
                Label(display.localized("作品の操作"), systemImage: "ellipsis.circle").inkuFont(12)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .disabled(browsingDisabled)
            // WorkActionMenu.svelte:107: a locked trigger says why (CanvasPanel passes `workActionGenerationLocked`).
            .inkuTooltip(browsingDisabled ? display.tooltip("生成中は推敲を開始できません。", serverKey: "workActionGenerationLocked")
                         : display.tooltip("作品の操作"))
        } else if workspaceWork != nil, !model.isBusy {
            Text(display.webCopy("workActionSaveFirst", "推敲するには、先に作品を保存してください。"))
                .inkuFont(11).foregroundStyle(.tertiary).lineLimit(1)
        }
    }

    /// CanvasPanel `.canvas-area`: no outer margin; navigation sits on the sides, the corner controls on the work.
    private var canvasArea: some View {
        ZStack {
            InkuColor.bg2
            if let inlinePanel {
                // refinement-workspace.css:6: `min(1120px, 100% − 136px)` wide and 28pt short of the area.
                inlinePanel
                    .frame(maxWidth: min(1120, max(320, rightPanelWidth - 136)))
                    .background(InkuColor.bg, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(InkuColor.border2))
                    .padding(.vertical, 14)
            } else if ui.workspaceTab == "lineage" && display.visible("work_tools") && workspaceWork != nil {
                LineageView(model: model, onEditWork: onEditWork, onAdjustWork: onAdjustWork, onReplayWork: onReplayWork,
                            onWorkAction: onWorkAction, onExport: onLineageExport, initialWork: workspaceWork,
                            writingLocked: controlsDisabled, onBrowseWork: { _ in batchWorkspace.showHistory() })
                    .background(InkuColor.bg)
                    .padding(.horizontal, display.visible("history") ? 68 : 0)
            } else {
                artwork
            }
        }
        .overlay(alignment: .leading) {
            if display.visible("history") && inlinePanel == nil { navigationLeft.padding(.leading, 14) }
        }
        .overlay(alignment: .trailing) {
            if display.visible("history") && inlinePanel == nil { navigationRight.padding(.trailing, 14) }
        }
        .overlay(alignment: .topTrailing) {
            if ui.generationInfoOpen, inlinePanel == nil, let work = workspaceWork { generationInfoDrawer(work) }
        }
        .clipped()
    }

    private var artwork: some View {
        ZStack {
            ArtworkCanvas(svg: workspaceWork?.svg ?? model.currentSVG, renderer: model.renderer,
                          caption: workspaceWork?.effectiveSourceText ?? "", style: .workspace,
                          showsZoomControls: display.visible("work_tools"),
                          // Below about 740pt the capsule would sit on the right corner row (seven 34pt buttons).
                          zoomControlsAtTop: rightPanelWidth < 740 * display.preferences.textScale,
                          aspectRatio: workspaceWork?.renderCanvasAspectRatio, viewport: $ui.canvasViewport)
            CreationCanvasControls(model: model, corner: .left, work: workspaceWork, saved: hasSavedWorkspaceWork,
                                   disabled: controlsDisabled, browsingDisabled: browsingDisabled,
                                   generationInfoOpen: ui.generationInfoOpen,
                                   onReplayWork: onReplayWork, onWorkAction: onWorkAction, onShowSaijiki: { ui.saijikiOpen.toggle() })
                .padding(.leading, 18).padding(.bottom, 14)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
            CreationCanvasControls(model: model, corner: .right, work: workspaceWork, saved: hasSavedWorkspaceWork,
                                   disabled: controlsDisabled, browsingDisabled: browsingDisabled,
                                   generationInfoOpen: ui.generationInfoOpen,
                                   onReplayWork: onReplayWork, onWorkAction: onWorkAction, onShowSaijiki: { ui.saijikiOpen.toggle() })
                .padding(.trailing, 18).padding(.bottom, 14)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
            if workspaceIsPreview { previewBadge.frame(maxHeight: .infinity, alignment: .top).padding(.top, 12) }
            CanvasFallbackBadges(display: display, work: workspaceWork)
                .padding([.top, .trailing], 12)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
        }
    }

    /// Web `.unsaved-refinement-badge` at the top centre, with the native save and close actions.
    private var previewBadge: some View {
        HStack(spacing: 8) {
            Label(display.localized("未保存の候補"), systemImage: "eye").inkuFont(11)
            Button(display.localized("この候補を保存")) { Task { await model.savePreview() } }
                .buttonStyle(InkuGhostButtonStyle(prominent: true))
            Button(display.localized("候補を閉じる")) { Task { await model.clearPreview() } }
                .buttonStyle(InkuGhostButtonStyle())
        }
        .padding(.vertical, 5).padding(.horizontal, 9)
        .background(Capsule().fill(InkuColor.floating))
        .overlay(Capsule().stroke(InkuColor.border2))
        .shadow(color: .black.opacity(0.12), radius: 5, y: 2)
        .disabled(controlsDisabled)
    }

    /// Web `.nav-left`: 最新 above the 38pt ‹ circle, 14pt from the edge.
    private var navigationLeft: some View {
        VStack(spacing: 6) {
            Button(display.webCopy("historyLatest", "最新")) { navigateHistory(boundary: "latest") }
                .buttonStyle(InkuFloatingPillButtonStyle())
                .disabled(!history.canMoveNewer)
                .inkuTooltip(display.tooltip("最新の履歴", serverKey: "tooltipCanvasNavLatest"), placement: .right)
            Button { navigateHistory(delta: -1) } label: { Text("‹") }
                .buttonStyle(InkuFloatingCircleButtonStyle(diameter: 38))
                .disabled(!history.canMoveNewer)
                .accessibilityLabel(display.localized("新しい作品"))
                .inkuTooltip(display.tooltip("新しい作品", serverKey: "tooltipCanvasNavNewer"), placement: .right)
        }
        .disabled(browsingDisabled)
    }

    /// Web `.nav-right`: 最古, the › circle and the `n / N` counter.
    private var navigationRight: some View {
        VStack(spacing: 6) {
            Button(display.webCopy("historyOldest", "最古")) { navigateHistory(boundary: "oldest") }
                .buttonStyle(InkuFloatingPillButtonStyle())
                .disabled(!history.canMoveOlder)
                .inkuTooltip(display.tooltip("最古の履歴", serverKey: "tooltipCanvasNavOldest"), placement: .left)
            Button { navigateHistory(delta: 1) } label: { Text("›") }
                .buttonStyle(InkuFloatingCircleButtonStyle(diameter: 38))
                .disabled(!history.canMoveOlder)
                .accessibilityLabel(display.localized("古い作品"))
                .inkuTooltip(display.tooltip("古い作品", serverKey: "tooltipCanvasNavOlder"), placement: .left)
            if history.library.total > 0 {
                Text("\((history.selectedIndex ?? 0) + 1) / \(history.library.total)")
                    .inkuFont(11).monospacedDigit().foregroundStyle(.secondary).fixedSize()
            }
        }
        .disabled(browsingDisabled)
    }

    /// CanvasGenerationInfo.svelte:378-398: `min(760px, 100% − 72px)` wide from the right edge,
    /// above the corner controls (49pt from the bottom).
    private func generationInfoDrawer(_ work: SavedWork) -> some View {
        CreationWorkInfoView(model: model, work: work, tab: $ui.generationInfoTab, onClose: { ui.generationInfoOpen = false })
            .id(work.id)
            .frame(width: min(760, max(320, rightPanelWidth - 72)))
            .frame(maxHeight: .infinity)
            .background(InkuColor.bg)
            .overlay(alignment: .leading) { Rectangle().fill(InkuColor.border2).frame(width: 1) }
            .shadow(color: .black.opacity(0.18), radius: 17, x: -14)
            .padding(.bottom, 49)
            .transition(.move(edge: .trailing))
    }

    /// SaijikiDrawer.svelte:163-170: a 460pt drawer on the right edge.
    private var saijikiDrawer: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Button { ui.saijikiOpen = false } label: { Image(systemName: "xmark").inkuFont(15).frame(width: 30, height: 30).contentShape(Rectangle()) }
                    .buttonStyle(.plain).foregroundStyle(.secondary)
                    .accessibilityLabel(display.localized("閉じる"))
                    .inkuTooltip(display.tooltip("閉じる"))
            }.padding(.horizontal, 8).padding(.top, 6)
            SaijikiView(model: model)
        }
        .frame(width: 460)
        .frame(maxHeight: .infinity)
        .background(InkuColor.bg)
        .overlay(alignment: .leading) { Rectangle().fill(InkuColor.border2).frame(width: 1) }
        .shadow(color: .black.opacity(0.18), radius: 17, x: -10)
    }

    private func navigateHistory(delta: Int = 0, boundary: String? = nil) {
        guard !browsingDisabled else { return }
        let workID = workspaceWork?.id
        batchWorkspace.invalidateReads()
        let revision = batchWorkspace.revision
        Task {
            guard let work = await history.navigate(app: model, fromWorkID: workID, delta: delta,
                                                   boundary: boundary, selectWork: false) else { return }
            guard batchWorkspace.revision == revision, !browsingDisabled else {
                await history.locate(app: model, workID: workspaceWork?.id)
                return
            }
            batchWorkspace.showHistory()
            await model.selectWork(work)
        }
    }

    private func tip(_ key: String) -> String {
        let serverKeys = ["次の作品の描画モデルを選びます。": "tooltipInputModel", "次の作品の配色を選びます。": "tooltipInputCatalog",
                          "次の作品の指示書に使う言語を選びます。": "tooltipInputLang", "次の作品の筆致を規則から外します。": "tooltipInputWild",
                          "用紙の形と意図を見て、次の作品の用紙を選びます。": "tooltipInputCanvas", "入力と次の生成条件から作品を描きます。": "tooltipSubmit",
                          "歳時記の語と説明を参照します。": "tooltipSaijikiToggle"]
        return display.tooltip(key, serverKey: serverKeys[key])
    }
}

/// Web `flex-wrap: wrap` for a row of small buttons.
struct WrappingHStack: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let height = rows.reduce(0) { $0 + $1.height } + spacing * CGFloat(max(0, rows.count - 1))
        let width = rows.map(\.width).max() ?? 0
        return CGSize(width: proposal.width ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y + (row.height - size.height) / 2), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row { var indices: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0 }
    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows: [Row] = []
        var current = Row()
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let needed = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            if needed > width, !current.indices.isEmpty {
                rows.append(current); current = Row()
            }
            current.width = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            current.height = max(current.height, size.height)
            current.indices.append(index)
        }
        if !current.indices.isEmpty { rows.append(current) }
        return rows
    }
}

struct OutputView: View {
    @Environment(\.locale) private var locale
    let ddl: String
    let score: String
    @State private var tab = "ddl"

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            InkuSegmentedButtons(options: [("ddl", "DDL"), ("score", "Score")], selection: $tab)
                .accessibilityLabel(InkuLocalization.string("出力", locale: locale))
            ScrollView {
                Text(tab == "ddl" ? ddl : score)
                    .inkuFont(12, design: .monospaced)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
            }
            .background(.background, in: RoundedRectangle(cornerRadius: 6))
        }
    }
}
