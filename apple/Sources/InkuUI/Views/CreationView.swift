import InkuPersistence
import InkuHost
import SwiftUI
#if os(macOS)
import AppKit
import ImageIO
import UniformTypeIdentifiers
#endif

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

private struct CanvasHeaderTab: View {
    let title: String
    let selected: Bool
    let compact: Bool
    let action: () -> Void
    @State private var hovered = false
    @Environment(\.isEnabled) private var isEnabled
    var body: some View {
        Button(action: action) {
            Text(title).inkuFont(13, weight: selected ? .medium : .regular)
                .foregroundStyle(selected ? Color.primary : Color.secondary)
                .padding(.horizontal, compact ? 12 : 16).frame(minHeight: 38, maxHeight: .infinity)
                .background(hovered && !selected && isEnabled ? InkuColor.bg2 : Color.clear)
                .overlay(alignment: .bottom) { Rectangle().fill(selected ? Color.accentColor : Color.clear).frame(height: 2) }
                .contentShape(Rectangle())
                .opacity(isEnabled ? 1 : 0.35)
        }.buttonStyle(.plain).onHover { hovered = $0 }
            .accessibilityAddTraits(selected ? .isSelected : [])
    }
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
    let onLineageExport: (LineageExportRequest) -> Void
    var onPresentWork: () -> Void = {}
    var onWorkspaceWorkChange: (SavedWork?) -> Void = { _ in }
    private var controlsDisabled: Bool { model.isBusy || automation.isOccupied || imageBatch.running }
    private var browsingDisabled: Bool { model.isBrowsingLocked }
    @State private var showColorCatalogs = false
    @State private var showModelPicker = false
    @State private var showImageModelPicker = false
    @State private var showImageNotice = false
    @State private var imageLoadError: String?
    @State private var imagePreview: CGImage?
    #if os(macOS)
    @State private var savedImageRecord: ExactJSON?
    #endif
    private var imageBatch: ImageFolderBatch { automation.imageFolderBatch }
    @State private var batchKind = "description"
    @State private var pendingImageBatchRestart: Bool?
    @State private var showConditionDetails = false
    @State private var showPaperPicker = false
    @State private var showNewDDL = false
    @State private var rightPanelWidth: CGFloat = 0
    @State private var rightPanelHeight: CGFloat = 0
    @State private var savedProviders: [InkuHost.ProviderSettings] = []
    @State private var workspaceGeneration: (nodeID: String, value: Int)?
    @State private var lineageMounted = false
    /// The 3D view's bridge; each appearance of the view mounts a new viewer through it.
    @State private var ddl3d = Ddl3DController()
    @Environment(\.inkuWindowSize) private var windowSize
    @Environment(\.inkuTooltipsCovered) private var covered
    @Environment(InkuFileDialogs.self) private var fileDialogs: InkuFileDialogs?
    private var isBatch: Bool { automation.workspaceInputMode == "batch" }
    private var isImage: Bool { automation.workspaceInputMode == "image" }
    private var workspaceCovered: Bool { ui.settingsOpen || ui.libraryOpen }
    private var batchWork: SavedWork? { batchWorkspace.pinnedWork ?? (batchWorkspace.followsLatest ? automation.observedWork : nil) }
    private var usesBatchWork: Bool { isBatch && batchWork != nil }
    private var workspaceWork: SavedWork? { usesBatchWork ? batchWork : model.displayedWork }
    private var workspaceIsPreview: Bool { !usesBatchWork && model.isPreview }
    private var hasSavedWorkspaceWork: Bool { workspaceWork?.trashed == false && !workspaceIsPreview }
    private var canInsertIntoBox: Bool {
        !isBatch && hasSavedWorkspaceWork && !controlsDisabled && !model.isBusy && workspaceWork?.ddl != nil && display.visible("ddl_tools")
    }
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
                // The 3D full screen keeps only the canvas area (Web requests full screen for `.canvas-area`).
                if !ui.leftPanelCollapsed && !ui.canvasFullScreen {
                    leftPanel.frame(width: leftPanelWidth).disabled(inlinePanel != nil)
                }
                if !ui.canvasFullScreen { leftPanelToggle }
                rightPanel
            }
            if display.visible("history") {
                VStack(spacing: 0) {
                    Rectangle().fill(InkuColor.border).frame(height: 1)
                    HistoryStripView(model: model, history: history, displayedWorkID: workspaceWork?.id,
                                     onSelectWork: { _ in batchWorkspace.showHistory() })
                        .disabled(inlinePanel != nil)
                }
                // Folded rather than removed in the 3D full screen, so the strip's reads are not restarted.
                .frame(height: ui.canvasFullScreen ? 0 : nil, alignment: .top)
                .clipped()
                .opacity(ui.canvasFullScreen ? 0 : 1)
                .allowsHitTesting(!ui.canvasFullScreen)
                .accessibilityHidden(ui.canvasFullScreen)
            }
        }
        .overlay(alignment: .trailing) {
            if ui.saijikiOpen { saijikiDrawer.transition(.move(edge: .trailing)) }
        }
        .animation(.easeOut(duration: 0.2), value: ui.saijikiOpen)
        .sheet(isPresented: $showColorCatalogs) {
            ColorCatalogView(model: model)
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.colorCatalog)
        }
        .sheet(isPresented: $showModelPicker) {
            BatchModelPickerView(model: model)
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.modelSelection)
        }
        .sheet(isPresented: $showImageModelPicker) {
            BatchModelPickerView(model: model, initialReference: model.imageVisionModel, immediateSelection: true,
                title: "Visionモデル", purpose: "vision", onSelection: { reference in
                    model.selectImageVisionModel(reference)
                }).environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.modelSelection)
        }
        .alert(display.webCopy("imageTab", "画像"), isPresented: $showImageNotice) {
            Button(display.webCopy("imageUploadNoticeContinue", "了解して描画する")) {
                model.imageWarningAcknowledged = true
                #if os(macOS)
                if let restart = pendingImageBatchRestart {
                    pendingImageBatchRestart = nil
                    Task { await imageBatch.run(app: model, restart: restart, provenance: imageProvenance) }
                } else { Task { await model.generate() } }
                #else
                Task { await model.generate() }
                #endif
            }
            Button(display.localized("キャンセル"), role: .cancel) { pendingImageBatchRestart = nil }
        } message: {
            Text(display.webCopy("imageUploadNoticeMessage", "画像から描画を行う場合、画像データがAIにアップロードされます。アップロードされたデータの扱いは、ユーザーが指定したモデルと、それをホストするプロバイダの規約に準じます。\nセンシティブなデータをアップロードしないでください。"))
        }
        .sheet(isPresented: $showNewDDL) {
            NewDdlAuthoringSheet(model: model, onPendingReview: {
                batchWorkspace.showHistory()
                automation.selectInputTab("description", app: model)
                ui.exitCanvasFullScreen()
                ui.leftPanelCollapsed = false
                ui.libraryOpen = false; ui.settingsOpen = false; ui.workspaceTab = "artwork"
            })
                .environment(\.inkuWindowSize, windowSize).inkuDialogFrame(.ddlEditor)
        }
        .onChange(of: automation.workspaceInputMode) { _, mode in
            if mode == "batch" { batchWorkspace.invalidateReads() }
            model.activeDrawTab = mode == "image" ? "image" : mode == "batch" ? (batchKind == "image" ? "batch_image" : "batch_text") : "describe"
        }
        .onChange(of: batchKind) { _, kind in
            if isBatch { model.activeDrawTab = kind == "image" ? "batch_image" : "batch_text" }
        }
        .onChange(of: model.savedImageDDL) { _, value in
            if value != nil && !model.isBusy { automation.workspaceInputMode = "image" }
        }
        .onChange(of: model.inputMode) { _, value in
            if value == "description", isImage, model.selectedWork != nil { automation.workspaceInputMode = "description" }
        }
        .onChange(of: ui.workspaceTab, initial: true) { _, tab in
            batchWorkspace.invalidateReads()
            if tab == "lineage" { lineageMounted = true }
            if tab == "lineage", isBatch, batchWorkspace.followsLatest,
               let work = batchWork, let rowID = automation.observedRow?.id {
                batchWorkspace.pin(work, rowID: rowID)
            }
        }
        .onDisappear { batchWorkspace.invalidateReads() }
        .onChange(of: model.imageInput?.jpeg, initial: true) { _, data in imagePreview = data.flatMap(PlatformImage.load(data:)) }
        #if os(macOS)
        .onChange(of: model.savedImageDDL, initial: true) { _, data in savedImageRecord = data.flatMap { try? ExactJSON(data: $0) } }
        #endif
        .task(id: model.providerSettingsRevision) { savedProviders = await model.hostSettings().providers }
        .task(id: workspaceWork?.lineageNodeID) {
            workspaceGeneration = nil
            guard let nodeID = workspaceWork?.lineageNodeID else { return }
            let generations = try? await model.auxiliaryDatabase().lineageGenerations(nodeIDs: [nodeID])
            guard !Task.isCancelled, workspaceWork?.lineageNodeID == nodeID,
                  let generation = generations?[nodeID] else { return }
            workspaceGeneration = (nodeID, generation)
        }
        .task(id: workspaceWork?.id) {
            guard let work = workspaceWork else { return }
            _ = try? await model.savedConfiguration(workID: work.id)
        }
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
                if !isBatch { PipelineCompletionView(model: model) }
                if !isBatch { PipelineDiagnosticsView(raw: model.diagnosticsJSON, display: display, pluginWords: model.pluginWords) }
                if !isBatch, let work = workspaceWork {
                    CreationDisplayedProcess(model: model, work: work, saved: hasSavedWorkspaceWork,
                                             disabled: controlsDisabled, onWorkAction: onWorkAction)
                }
                if !isBatch, display.visible("detail_status"), let work = workspaceWork {
                    CreationResultLog(model: model, work: work)
                }
                statusFooter
            }
            .frame(width: max(0, leftPanelWidth - (compactWindow ? 24 : 32)), alignment: .leading)
            .padding(.vertical, 14).padding(.horizontal, compactWindow ? 12 : 16)
        }
        .background(InkuColor.bg)
    }

    /// InputPanel.svelte:180-198: two equal underline tabs; a running tab carries a dot and `(n/N ↻r)`.
    private var inputTabs: some View {
        HStack(spacing: 0) {
            InkuPanelTab(title: display.webCopy("modeSingle", "記述"), selected: !isBatch && !isImage,
                         running: automation.inputTabRunning("description", app: model)) {
                automation.selectInputTab("description", app: model)
            }
            .inkuTooltip(display.tooltip("自由な自然言語で記述を入力して1枚ずつ描画します", serverKey: "tooltipInputTabSingle"))
            #if os(macOS)
            InkuPanelTab(title: display.webCopy("imageTab", "画像"), selected: isImage,
                         running: automation.inputTabRunning("image", app: model)) {
                automation.selectInputTab("image", app: model)
            }
            #endif
            InkuPanelTab(title: display.webCopy("modeBatch", "バッチ"), selected: isBatch,
                         running: automation.inputTabRunning("batch", app: model), progress: batchProgress) {
                automation.selectInputTab("batch", app: model)
            }
            .inkuTooltip(display.tooltip("改行区切りで複数の記述を入力し、順次連続して描画します", serverKey: "tooltipInputTabBatch"))
        }
        .overlay(alignment: .bottom) { Rectangle().fill(InkuColor.border).frame(height: 1).allowsHitTesting(false) }
    }

    private var batchProgress: String {
        guard automation.running, automation.mode == "batch", !automation.rows.isEmpty else { return "" }
        let current = DrawPresentation.batchRow(activeID: automation.activeRow?.id, rows: automation.rows,
                                                completed: automation.completedCount, failed: automation.failedCount)
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
                #if os(macOS)
                Picker(display.localized("入力"), selection: $batchKind) {
                    Text(display.webCopy("modeSingle", "記述")).tag("description")
                    Text(display.webCopy("imageTab", "画像")).tag("image")
                }.pickerStyle(.segmented).disabled(controlsDisabled)
                if batchKind == "image" { imageFolderPanel }
                else {
                    BatchPanelView(model: model, automation: automation,
                                   onObserveWork: { work, rowID in batchWorkspace.pin(work, rowID: rowID) },
                                   followsLatestWork: batchWorkspace.followsLatest,
                                   selectedRowID: batchWorkspace.rowID, observationRevision: $batchWorkspace.revision,
                                   onNewBatch: { batchWorkspace.showHistory() }, ui: ui)
                }
                #else
                BatchPanelView(model: model, automation: automation,
                    onObserveWork: { work, rowID in batchWorkspace.pin(work, rowID: rowID) },
                    followsLatestWork: batchWorkspace.followsLatest,
                    selectedRowID: batchWorkspace.rowID, observationRevision: $batchWorkspace.revision,
                    onNewBatch: { batchWorkspace.showHistory() }, ui: ui)
                #endif
            } else {
                #if os(macOS)
                if isImage { imageInputPanel } else {
                    input
                    if display.visible("drawing_settings") { nextConditions }
                    generationAction.padding(.top, 8)
                }
                #else
                input
                if display.visible("drawing_settings") { nextConditions }
                generationAction.padding(.top, 8)
                #endif
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    #if os(macOS)
    private var imageFolderPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button(display.webCopy("clearInputBtn", "新規作成")) {
                imageBatch.newWork(app: model); batchWorkspace.showHistory()
            }.disabled(controlsDisabled || imageBatch.selecting)
            Button(display.localized("画像フォルダを選ぶ")) {
                Task {
                    guard let url = await fileDialogs?.choose(.folder()) else { return }
                    do { try await imageBatch.select(url, app: model) } catch { imageLoadError = error.localizedDescription }
                }
            }.disabled(controlsDisabled || imageBatch.selecting)
            if !imageBatch.folder.isEmpty { Text(imageBatch.folder).textSelection(.enabled).inkuFont(12) }
            conditionRow("Vision", value: model.imageVisionModel.isEmpty ? display.localized("選択してください") : model.imageVisionModel,
                         help: "Vision") { showImageModelPicker = true }.disabled(controlsDisabled)
            conditionRow(display.webCopy("colorCatalogButton", "色カタログ"), value: catalogSummary, help: "") {
                showColorCatalogs = true
            }.disabled(controlsDisabled || model.catalogs.isEmpty)
            imagePaperCondition
            if imageBatch.hasJournal {
                Text("\(imageBatch.completed) / \(imageBatch.total) · \(display.localized("失敗")) \(imageBatch.failed)")
                ForEach(imageBatch.failures, id: \.self) { failure in
                    Text(failure).foregroundStyle(.red).inkuFont(12).textSelection(.enabled)
                }
                if imageBatch.uncertain > 0 {
                    Text(display.localized("前回の処理結果を確認できない画像があります。履歴を確認してください。"))
                        .foregroundStyle(.orange)
                }
                if imageBatch.running {
                    RunStatusView(display: display, label: imageBatch.status, onStop: { Task { await imageBatch.stop(app: model) } }, journalModel: model,
                                  journalActive: imageBatch.drawing) { EmptyView() }
                } else {
                    HStack {
                        Button(display.localized("続きから描く")) { startImageBatch(restart: false) }
                        Button(display.localized("最初から描く")) { startImageBatch(restart: true) }
                    }.disabled(model.isBusy || automation.isOccupied || imageBatch.total == 0 || model.imageVisionModel.isEmpty)
                }
            }
            if !imageBatch.status.isEmpty { Text(imageBatch.status).inkuFont(12) }
            if let error = imageBatch.error ?? imageLoadError { Text(error).foregroundStyle(.red).inkuFont(12) }
        }
    }

    private func startImageBatch(restart: Bool) {
        if model.imageWarningAcknowledged { Task { await imageBatch.run(app: model, restart: restart, provenance: imageProvenance) } }
        else { pendingImageBatchRestart = restart; showImageNotice = true }
    }

    private var imageInputPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button(display.webCopy("clearInputBtn", "新規作成")) { model.newWork(); batchWorkspace.showHistory() }
                .buttonStyle(InkuGhostButtonStyle()).disabled(controlsDisabled)
            Text(display.webCopy("imageProvenanceLabel", "来歴")).inkuFont(14, weight: .semibold)
            editor(text: Binding(get: { model.imageProvenance }, set: { model.setImageProvenanceFromUser($0) }),
                   readOnly: model.savedImageDDL != nil && model.imageInput == nil)
            HStack {
                Text(display.webCopy("imageTab", "画像")).inkuFont(14, weight: .semibold)
                Spacer()
                Button(display.webCopy("imageChooseFile", "画像を選ぶ")) { chooseImage() }
                    .buttonStyle(InkuGhostButtonStyle()).disabled(controlsDisabled)
            }
            if model.imageInput != nil, let preview = imagePreview {
                Image(decorative: preview, scale: 1).resizable().scaledToFit().frame(maxWidth: .infinity, maxHeight: 220)
                Text(model.imageFileName).inkuFont(12).foregroundStyle(.secondary)
            }
            if let record = savedImageRecord {
                if let ddl = model.selectedWork?.ddl {
                    Text(display.localized("指示書")).inkuFont(14, weight: .semibold)
                    Text(ddl).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }
                if let before = record["before_review"].string, !before.isEmpty {
                    DisclosureGroup(display.localized("見比べる前の指示書")) {
                        Text(before).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                        if let work = model.selectedWork {
                            Button(display.localized("この指示書で子を描く")) {
                                Task { _ = await model.drawEditedDDL(work: work, source: before, forceEdit: true) }
                            }.disabled(controlsDisabled)
                        }
                    }
                }
                Text(display.localized("描き直すには画像を選び直してください。")).foregroundStyle(.secondary).inkuFont(12)
            }
            if let imageLoadError { Text(imageLoadError).foregroundStyle(.red).inkuFont(12) }
            conditionRow("Vision", value: model.imageVisionModel.isEmpty ? display.localized("選択してください") : model.imageVisionModel,
                         help: "Vision") { showImageModelPicker = true }.disabled(controlsDisabled)
            conditionRow(display.webCopy("colorCatalogButton", "色カタログ"), value: catalogSummary, help: "") {
                showColorCatalogs = true
            }.disabled(controlsDisabled || model.catalogs.isEmpty)
            imagePaperCondition
            if model.singleRunStatusVisible(in: "image") {
                let label = model.status == display.localized("見比べる画を描いています…") ? model.status :
                    model.providerProgress.flatMap { $0.outcome == .running ? display.localized($0.stageTitleKey) : nil }
                    ?? display.webCopy("imageWritingDdl", "画像から指示書を書いています…")
                runStatus(label: label, onStop: { Task { await model.cancel() } }, stopping: false)
            } else {
                Button(display.webCopy("generateButton", "描画する")) {
                    if model.imageWarningAcknowledged { Task { await model.generate() } }
                    else { showImageNotice = true }
                }.buttonStyle(.borderedProminent).disabled(!model.canGenerate || controlsDisabled)
            }
        }
        .dropDestination(for: URL.self) { urls, _ in
            guard !controlsDisabled, let url = urls.first, url.isFileURL else { return false }
            loadImage(url)
            return true
        }
    }

    private var imagePaperCondition: some View {
        let value = model.imageCanvasID == "image" ? display.localized("画像の縦横比を使う") :
            (model.canvases.first { $0.id == model.imageCanvasID }?.label ?? model.imageCanvasID)
        return conditionRow(display.localized("画面比"), value: value, help: "") { showPaperPicker = true }
            .disabled(controlsDisabled)
            .popover(isPresented: $showPaperPicker) {
                CreationPaperPicker(model: model, imageSelection: true) { showPaperPicker = false }.environment(display)
            }
    }

    private func chooseImage() {
        Task {
            guard let url = await fileDialogs?.choose(InkuFileRequest(types: [.jpeg, .png, .gif, .tiff])) else { return }
            loadImage(url)
        }
    }

    private func loadImage(_ url: URL) {
        do {
            let image = try ImageInput.prepare(Data(contentsOf: url))
            model.setImageInput(image, fileName: url.lastPathComponent, automaticProvenance: imageProvenance(url: url))
            imageLoadError = nil
        } catch { imageLoadError = model.failureMessage(error) }
    }

    private func imageProvenance(url: URL) -> String {
        ImageProvenance.text(url: url, includeFileName: display.preferences.imageIncludeFileName ?? true,
                             includeExif: display.preferences.imageIncludeExif ?? true, language: display.preferences.language)
    }
    #endif

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
                    Text(display.webCopy("inputSectionHint", "短い文で、表現したいものを入力。")).inkuFont(12).foregroundStyle(.secondary)
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
            HStack {
                Text(display.webCopy("nextWorkConditions", "次の生成条件")).inkuFont(12, weight: .medium).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Button { showConditionDetails = true } label: { Image(systemName: "ellipsis") }
                    .buttonStyle(InkuGhostButtonStyle()).disabled(controlsDisabled)
                    .accessibilityLabel(display.localized("生成条件の詳細"))
                    .popover(isPresented: $showConditionDetails) { conditionDetails }
            }.padding(.top, 8).padding(.bottom, 2)
            conditionRow(display.webCopy("modelButton", "モデル"),
                         value: DrawPresentation.modelReference(model.nextBatchDrawingModelReference, empty: display.localized("選択してください")),
                         help: display.tooltip("次の作品の描画モデルを選びます。", serverKey: "tooltipInputModel"),
                         showsPlan: model.nextBatchDrawingModelReference.hasPrefix("chatgpt:")) { showModelPicker = true }
                .disabled(controlsDisabled)
            Rectangle().fill(InkuColor.border).frame(height: 1)
            conditionRow(display.webCopy("colorCatalogButton", "色カタログ"), value: catalogSummary,
                         help: tip("次の作品の配色を選びます。")) { showColorCatalogs = true }
                .disabled(controlsDisabled || model.catalogs.isEmpty)
                .accessibilityLabel(display.localized("色カタログを開く"))
                .accessibilityValue(catalogSummary)
            Rectangle().fill(InkuColor.border).frame(height: 1)
            if model.inputMode == "description" {
                DrawConditionsView(model: model, sketch: model.sketchMode, onSketch: { model.sketchMode = $0 })
                    .disabled(controlsDisabled)
                    .padding(.bottom, 8)
                Rectangle().fill(InkuColor.border).frame(height: 1)
            }
            DrawingCompactConditions(model: model, wild: model.wild, canvasID: model.canvasID, showPaperPicker: $showPaperPicker)
                .disabled(controlsDisabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var catalogSummary: String {
        DrawPresentation.catalogSummary(mode: model.catalogMode, id: model.catalogID, catalogs: model.catalogs,
            auto: display.webCopy("colorCatalogAuto", "記述から自動選択"),
            random: display.localized("ランダム"), missing: display.localized("未記録"))
    }

    private func conditionRow(_ label: String, value: String, help: String, showsPlan: Bool = false, action: @escaping () -> Void) -> some View {
        DrawingConditionRow(display: display, label: label, value: value, help: help, showsPlan: showsPlan, action: action)
    }

    private var conditionDetails: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(display.localized("生成条件の詳細")).inkuFont(14, weight: .semibold)
            Picker(display.localized("配色の選び方"), selection: $model.catalogMode) {
                Text(display.localized("指定")).tag("fixed")
                Text(display.localized("記述から選択")).tag("auto")
            }.inkuTooltip(tip("次の作品の配色を選びます。"))
            TextField(display.localized("シード（空欄で新規）"), text: $model.seedText).textFieldStyle(.roundedBorder)
                .inkuTooltip(tip("空欄なら次の描画で新しいシードを使います。"), focus: .text)
        }.padding(16).frame(width: 360).disabled(controlsDisabled)
    }

    /// InputPanel.svelte:308-337: the paint button, or the run status while drawing.
    private var generationAction: some View {
        VStack(alignment: .leading, spacing: 10) {
            if model.inputMode == "description" && !model.hasAvailableNextDrawingModel {
                Button {
                    ui.settingsSection = .drawingGuidance(hasConnection: model.hasDrawingConnection); ui.settingsOpen = true
                } label: {
                    Label(display.localized(model.hasDrawingConnection
                        ? "描くときのデフォルトで、使える描画モデルを選んでください。"
                        : "モデル設定で接続先を追加してください。"), systemImage: "gearshape")
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
            } else if model.singleRunStatusVisible(in: "description") {
                runStatus(label: model.status, onStop: { Task { await model.cancel() } }, stopping: false)
            } else if descriptionLocked {
                // InputPanel.svelte:326-334: a held work is drawn from its description only as a new work, named as such.
                Button { batchWorkspace.showHistory(); Task { await model.forkDescription() } } label: {
                    HStack(spacing: 8) {
                        Text("▶").inkuFont(12).accessibilityHidden(true)
                        Text(display.webCopy("pipelineForkDescription", "この記述から新しい作品を作る"))
                    }
                }
                .buttonStyle(InkuPaintButtonStyle())
                .keyboardShortcut(.return, modifiers: .command)
                .disabled(!model.canForkDescription || automation.isOccupied || workspaceCovered)
                .inkuTooltip(display.tooltip("この記述をそのまま使って、新しい作品として描き直します。", serverKey: "tooltipForkDescription"))
            } else {
                Button { batchWorkspace.showHistory(); Task { await model.generateDescription() } } label: {
                    Text(display.webCopy("submitBtn", "生成"))
                }
                .buttonStyle(InkuPaintButtonStyle())
                .keyboardShortcut(.return, modifiers: .command)
                .disabled(!model.canGenerateDescription || automation.isOccupied || workspaceCovered)
                .inkuTooltip(tip("入力と次の生成条件から作品を描きます。"))
            }
        }
    }

    /// Web RunStatus.svelte: mascot, the stage and its provider facts, and the stop button, in one bordered box.
    private func runStatus(label: String, onStop: @escaping () -> Void, stopping: Bool) -> some View {
        RunStatusView(display: display, label: label, stopping: stopping, stopTooltip: tip("実行中の描画を停止します。"),
                      stopsWithEscape: !workspaceCovered, onStop: onStop, journalModel: model) { ProviderProgressView(model: model, embedded: true) }
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
            if inlinePanel == nil && !ui.canvasFullScreen { tabsRow }
            canvasArea
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onGeometryChange(for: CGSize.self) { $0.size } action: { size in
            rightPanelWidth = size.width; rightPanelHeight = size.height
        }
        .task(id: workspaceWork?.id) {
            guard let work = workspaceWork, hasSavedWorkspaceWork, !Task.isCancelled else { return }
            await history.locate(app: model, workID: work.id)
            guard !Task.isCancelled, workspaceWork?.id == work.id else { return }
            await model.loadWorkActionState(work)
        }
    }

    /// The conditions share the tabs' row above 45em, and wrap below it on narrow panels.
    private var tabsRow: some View {
        let scale = display.preferences.textScale
        let wide = rightPanelWidth > 45 * 13 * scale
        let compact = !wide
        let showsMeta = workspaceWork != nil
        return VStack(spacing: 0) {
            HStack(spacing: 0) {
                CanvasHeaderTab(title: display.webCopy("tabCanvas", "作品"), selected: ui.workspaceTab != "lineage", compact: compact) {
                    ui.workspaceTab = "artwork"
                }
                .inkuTooltip(display.tooltip("描画された作品のキャンバスを表示します", serverKey: "tooltipCanvasTabCanvas"), placement: .bottom)
                CanvasHeaderTab(title: display.localized("系譜"), selected: ui.workspaceTab == "lineage", compact: compact) {
                    ui.workspaceTab = "lineage"
                }
                .disabled(workspaceWork == nil || browsingDisabled)
                .inkuTooltip(display.tooltip("作品の派生関係を表示"), placement: .bottom)
                if wide && showsMeta, let work = workspaceWork {
                    Rectangle().fill(InkuColor.border).frame(width: 1).padding(.vertical, 5).padding(.leading, 16)
                    metaStrip(work).frame(maxWidth: .infinity, alignment: .leading)
                } else { Spacer(minLength: 0) }
            }.fixedSize(horizontal: false, vertical: true)
            if !wide && showsMeta, let work = workspaceWork {
                metaStrip(work).frame(maxWidth: .infinity, alignment: .leading)
                    .overlay(alignment: .top) { Rectangle().fill(InkuColor.border).frame(height: 1) }
            }
        }
        .padding(.horizontal, wide ? 16 : 10)
        .background(InkuColor.bg)
        .overlay(alignment: .bottom) { Rectangle().fill(InkuColor.border).frame(height: 1) }
    }

    private func metaStrip(_ work: SavedWork) -> some View {
        let recordedState = model.workActionState(for: work)
        let isImage = recordedState == .image || (!usesBatchWork && model.selectedWorkID == work.id && model.savedImageDDL != nil)
        let options = model.cachedRecordedOptions(workID: work.id, isImage: isImage) ?? [:]
        let naming = ModelNaming(providers: savedProviders, stageProvider: model.stageDefaultProviderID)
        let unavailable = display.webCopy("drawOptionsUnavailable", "N/A")
        let size = ByteCountFormatter.string(fromByteCount: Int64(work.svg.utf8.count), countStyle: .file)
        let created = Date(timeIntervalSince1970: Double(work.at) / 1000).formatted(.dateTime.year().month(.twoDigits).day(.twoDigits).hour().minute())
        let generation = workspaceGeneration?.nodeID == work.lineageNodeID ? workspaceGeneration?.value : nil
        func label(_ key: String) -> String {
            switch key {
            case "models": return isImage ? display.webCopy("drawDefaultsVision", "画像を読むモデル") : display.webCopy("drawDefaultsModel", "描画モデル")
            case "catalog": return display.webCopy("colorCatalogButton", "色カタログ")
            case "route": return display.webCopy("drawDefaultsRoute", "描き方")
            case "sketch": return display.webCopy("sketchLabel", "写生")
            case "composition": return display.webCopy("drawDefaultsComposition", "構図・法則・配色")
            case "wild": return display.webCopy("wildButton", "筆致制限を外す")
            default: return display.webCopy("drawDefaultsCanvas", "キャンバス")
            }
        }
        func value(_ key: String) -> String {
            guard let raw = options[key], !(raw is NSNull) else { return unavailable }
            if let text = raw as? String {
                switch text {
                case "on": return display.webCopy("drawDefaultsOn", "オン")
                case "off": return display.webCopy("drawDefaultsOff", "オフ")
                case "read_and_draw": return display.webCopy("drawDefaultsRead", "言葉で描く")
                case "stages": return display.webCopy("drawDefaultsStages", "型で描く")
                default: return key == "canvas_aspect" ? model.canvases.first(where: { $0.id == text })?.label ?? text : text
                }
            }
            guard let object = raw as? [String: Any] else { return unavailable }
            if key == "catalog" {
                let id = object["id"] as? String
                let name = id.flatMap { chosen in model.catalogs.first(where: { $0.id == chosen })?.name ?? chosen } ?? unavailable
                let mode = object["mode"] as? String
                let modeName = mode == "auto" ? display.webCopy("colorCatalogAuto", "記述から自動選択")
                    : mode == "fixed" ? display.webCopy("drawDefaultsFixed", "固定") : unavailable
                return name + " (" + modeName + ")"
            }
            if key == "models" {
                func name(_ key: String) -> String { (object[key] as? String).map(naming.displayName) ?? unavailable }
                if object["vision"] as? String != nil { return name("vision") }
                let first = name("stage1"), second = name("stage2")
                return first == second ? first : first + " / " + second
            }
            return unavailable
        }
        let compact = rightPanelWidth <= 32 * 13 * display.preferences.textScale
        let outer = compact ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2)) : AnyLayout(HStackLayout(alignment: .center, spacing: 14))
        let contextLayout = compact ? AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 10)) : AnyLayout(VStackLayout(alignment: .leading, spacing: 1))
        return outer {
            contextLayout {
                Text(display.webCopy("displayedWorkConditions", "表示中作品の条件"))
                    .inkuFont(11).foregroundStyle(.tertiary)
                HStack(spacing: 5) {
                    if generation != nil || work.lineageNodeID != nil {
                        Text(display.label("系譜", "Lineage")).inkuFont(11).foregroundStyle(.tertiary)
                    }
                    Text(generation.map { display.label("第\($0)世代", "Gen. \($0)") }
                         ?? (work.lineageNodeID == nil ? display.label("独立作品", "Standalone") : "…"))
                        .inkuFont(12).foregroundStyle(.secondary)
                }
            }.fixedSize()
            WrappingHStack(spacing: 14) {
                ForEach(DrawOptionPresentation.keys(isImage: isImage).filter {
                    recordedState != nil || !["route", "sketch", "composition", "models"].contains($0)
                }, id: \.self) { key in
                    if key == "models", let models = options[key] as? [String: Any],
                       let first = models["stage1"] as? String, let second = models["stage2"] as? String, first != second {
                        modelMetaField(label(key), first: naming.displayName(first), second: naming.displayName(second))
                    } else if key == "sketch", let onOff = options[key] as? String {
                        let short = DrawPresentation.sketchShort(work.sketchState, japanese: display.preferences.language != "en")
                        let note = DrawPresentation.sketchNote(work.sketchState, japanese: display.preferences.language != "en")
                        metaField(label(key), short + " (" + value(key) + ")", tooltip: (note.isEmpty ? short : note) + " — " + (onOff == "on" ? display.webCopy("drawDefaultsOn", "オン") : display.webCopy("drawDefaultsOff", "オフ")))
                    } else { metaField(label(key), value(key)) }
                }
                metaField(display.label("サイズ", "Size"), size)
                metaField(display.label("作成", "Created"), created)
            }
        }
        .padding(.leading, rightPanelWidth > 45 * 13 * display.preferences.textScale ? 16 : 0)
        .padding(.vertical, 5)
        .accessibilityElement(children: .combine)
        .task(id: AppModel.RecordedOptionsKey(workID: work.id, isImage: isImage)) {
            _ = try? model.prepareRecordedOptions(work, isImage: isImage)
        }
    }

    private func metaField(_ label: String, _ value: String, tooltip: String? = nil) -> some View {
        HStack(spacing: 4) {
            Text(label).inkuFont(11).foregroundStyle(.tertiary)
            Text(value).inkuFont(12).foregroundStyle(.secondary).lineLimit(1).truncationMode(.tail)
                .inkuTooltip(display.tooltipValue(tooltip ?? value))
        }.frame(maxWidth: 280 * display.preferences.textScale, alignment: .leading)
    }

    private func modelMetaField(_ label: String, first: String, second: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            Text(label).inkuFont(11).foregroundStyle(.tertiary)
            VStack(alignment: .leading, spacing: 1) {
                metaField(display.webCopy("drawOptionsStage1Short", "解釈"), first)
                metaField(display.webCopy("drawOptionsStage2Short", "描画"), second)
            }
        }.frame(maxWidth: 280 * display.preferences.textScale, alignment: .leading)
    }

    /// Web WorkActionMenu (header variant): editing only; viewing tools stay in the canvas toolbar.
    @ViewBuilder private var workActionMenu: some View {
        if let work = workspaceWork, hasSavedWorkspaceWork {
            Button {
                ui.refinementMenuWorkID = work.id
            } label: {
                Text(display.webCopy("workActionRefine", "推敲する")).inkuFont(12)
            }
            .buttonStyle(InkuGhostButtonStyle())
            .shadow(color: .black.opacity(0.12), radius: 5, y: 2)
            .popover(isPresented: Binding(get: { ui.refinementMenuWorkID == work.id }, set: { if !$0 { ui.refinementMenuWorkID = nil } })) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(workActionTitle(work)).inkuFont(12, weight: .semibold)
                        SavedWorkRefinementActions(model: model, work: work, onAction: { target, action in
                            ui.refinementMenuWorkID = nil
                            onWorkAction(target, action)
                        }, writingLocked: automation.isOccupied)
                    }.padding(16).frame(width: 300)
                }.frame(maxHeight: max(120, rightPanelHeight - 80))
            }
            .fixedSize()
            .disabled(browsingDisabled)
            // WorkActionMenu.svelte:107: a locked trigger says why (CanvasPanel passes `workActionGenerationLocked`).
            .inkuTooltip(browsingDisabled ? display.tooltip("生成中は推敲を開始できません。", serverKey: "workActionGenerationLocked")
                         : display.tooltip("作品の操作"))
        } else if workspaceWork != nil, !model.isBusy {
            Text(display.webCopy("workActionSaveFirst", "推敲するには、先に作品を保存してください。"))
                .inkuFont(11).foregroundStyle(.tertiary).lineLimit(1)
                .padding(.horizontal, 9).padding(.vertical, 5)
                .background(InkuColor.panel.opacity(0.94), in: Capsule())
                .overlay(Capsule().stroke(InkuColor.border2))
                .shadow(color: .black.opacity(0.12), radius: 5, y: 2)
        }
    }

    private func workActionTitle(_ work: SavedWork) -> String {
        let title = display.webCopy("workActionMenuTitle", "作品編集")
        switch model.workActionState(for: work) {
        case .userDDL: return title + " " + display.webCopy("workActionDdlOrigin", "（DDL直接生成作品）")
        case .lockedDescription: return title + " " + display.webCopy("descriptionLockedMark", "ロック")
        default: return title
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
            } else {
                let showsLineage = ui.workspaceTab == "lineage" && workspaceWork != nil
                artwork
                    .environment(\.inkuTooltipsCovered, covered || showsLineage)
                    .opacity(showsLineage ? 0 : 1)
                    .allowsHitTesting(!showsLineage)
                    .accessibilityHidden(showsLineage)
                if (lineageMounted || showsLineage) && workspaceWork != nil {
                    LineageView(model: model, onWorkAction: onWorkAction, onExport: onLineageExport, initialWork: workspaceWork,
                                writingLocked: controlsDisabled, onBrowseWork: { _ in batchWorkspace.showHistory() },
                                onOpenInCanvas: { work in
                                    batchWorkspace.showHistory()
                                    Task { await model.selectWork(work); ui.workspaceTab = "artwork" }
                                }, onDetach: {
                                    batchWorkspace.showHistory(); model.detachLineage(); ui.workspaceTab = "artwork"
                                })
                        .background(InkuColor.bg)
                        .padding(.horizontal, display.visible("history") ? 68 : 0)
                        // Native scroll views can still receive pointer events while their SwiftUI
                        // parent is transparent and hit testing is disabled. Keep the lineage
                        // mounted, but move it outside the clipped canvas when artwork is shown.
                        .offset(x: showsLineage ? 0 : max(rightPanelWidth, windowSize?.width ?? 1320) + 128)
                        .opacity(showsLineage ? 1 : 0)
                        .allowsHitTesting(showsLineage)
                        .accessibilityHidden(!showsLineage)
                        .environment(\.inkuTooltipsCovered, covered || ui.generationInfoOpen || ui.saijikiOpen)
                }
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
            ArtworkCanvas(svg: workspaceWork?.svg ?? model.currentSVG, renderer: model.displayRenderer,
                          caption: workspaceWork?.effectiveSourceText ?? "", style: .workspace,
                          showsZoomControls: display.visible("work_tools"),
                          // Below about 740pt the capsule would sit on the right corner row (seven 34pt buttons).
                          zoomControlsAtTop: rightPanelWidth < 740 * display.preferences.textScale,
                          aspectRatio: workspaceWork?.renderCanvasAspectRatio, viewport: $ui.canvasViewport,
                          rangePreview: usesBatchWork ? nil : model.rangePreview,
                          replacement: threeDimensionalReplacement)
            CreationCanvasControls(model: model, corner: .left, work: workspaceWork, saved: hasSavedWorkspaceWork,
                                   disabled: controlsDisabled, browsingDisabled: browsingDisabled,
                                   generationInfoOpen: ui.generationInfoOpen,
                                   onReplayWork: onReplayWork, onWorkAction: onWorkAction, onShowSaijiki: { ui.saijikiOpen.toggle() })
                .padding(.leading, 18).padding(.bottom, 14)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
            CreationCanvasControls(model: model, corner: .right, work: workspaceWork, saved: hasSavedWorkspaceWork,
                                   disabled: controlsDisabled, browsingDisabled: browsingDisabled,
                                   canInsertSaijikiWord: canInsertIntoBox,
                                   generationInfoOpen: ui.generationInfoOpen,
                                   threeDimensional: workspaceWork != nil && Ddl3DInstallation.available ? $ui.canvasThreeDimensional : nil,
                                   onReplayWork: onReplayWork, onWorkAction: onWorkAction, onShowSaijiki: { ui.saijikiOpen.toggle() })
                .padding(.trailing, 18).padding(.bottom, 14)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
            if workspaceIsPreview { previewBadge.frame(maxHeight: .infinity, alignment: .top).padding(.top, 12) }
            VStack(alignment: .trailing, spacing: 6) {
                workActionMenu
                CanvasFallbackBadges(display: display, work: workspaceWork)
            }
                .padding([.top, .trailing], 12)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
        }
    }

    /// CanvasPanel `threeDimensionalContent`: the viewer in the picture's place while 3D is chosen and a work is shown.
    /// Its first front view matches the picture where it stands (Web `initialView`).
    private var threeDimensionalReplacement: ArtworkReplacement? {
        #if os(macOS)
        guard !covered, ui.workspaceTab != "lineage", ui.canvasThreeDimensional, let work = workspaceWork, let registration = Ddl3DInstallation.registered else { return nil }
        let controller = ddl3d, ui = ui
        return ArtworkReplacement(zoom: controller.displayZoom, available: controller.ready && controller.failure == nil,
                                  setZoom: { controller.zoom(to: $0) }, fit: { controller.reset() }) { _, box, scale, offset in
            AnyView(Ddl3DCanvas(controller: controller, registration: registration, work: work,
                                initialView: Ddl3DInitialView(pixelWidth: box.width * scale, pixelHeight: box.height * scale,
                                                              panX: offset.width, panY: offset.height, zoom: scale),
                                onReturn: { ui.canvasThreeDimensional = false },
                                onEscape: {
                                    // In the full screen, Esc leaves it first, as a browser's full screen does.
                                    guard ui.canvasFullScreen else { return false }
                                    ui.exitCanvasFullScreen(); return true
                                }))
        }
        #else
        return nil
        #endif
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
            // SaijikiDrawer: a chosen word goes into the instruction box when it can be edited; otherwise only the sample.
            SaijikiView(model: model, onInsertWord: canInsertIntoBox
                        ? { model.ddlBoxInsertion = InkuEditorInsertion(text: $0, atEndUnlessUsed: true) } : nil,
                        onClose: { ui.saijikiOpen = false })
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
