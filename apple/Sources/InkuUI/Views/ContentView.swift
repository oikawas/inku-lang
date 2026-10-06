import InkuPersistence
import InkuHost
import SwiftUI
#if os(macOS)
import AppKit
#endif

extension Notification.Name {
    static let inkuOpenSection = Notification.Name("inku.open-section")
}

/// Destinations named by `inkuOpenSection`. Library and settings open over the creation screen,
/// and lineage is the workspace's second tab (Web AppRail, HistoryManager and CanvasPanel).
enum AppSection: String {
    case create, library, lineage, automation, settings
}

private struct ExportSession {
    let id = UUID()
    let works: [SavedWork]
    let preserveOrder: Bool
    var directCard = false
}

private struct WorkEditSession {
    let id = UUID()
    let work: SavedWork
    let mode: WorkEditMode
}

private struct RefinementSession {
    let id = UUID()
    let work: SavedWork
}

private struct ReplaySession {
    let id = UUID()
    let work: SavedWork
}

private struct ComparisonSession {
    let id = UUID()
    let work: SavedWork
    let kind: ComparisonKind
}

private struct NewDdlSession {
    let id = UUID()
    let imported: InkuHost.DDLPackageImport
}

private enum WorkDialog: Identifiable {
    case export(ExportSession), edit(WorkEditSession), refinement(RefinementSession), replay(ReplaySession)
    case ddl(DdlEditingSession), newDDL(NewDdlSession), comparison(ComparisonSession), advice(RefinementSession), colophon(RefinementSession), information(RefinementSession), drawingLogs
    var id: String {
        switch self {
        case .export(let session): session.id.uuidString
        case .edit(let session): session.id.uuidString
        case .refinement(let session): session.id.uuidString
        case .replay(let session): session.id.uuidString
        case .ddl(let session): session.id.uuidString
        case .newDDL(let session): session.id.uuidString
        case .comparison(let session): session.id.uuidString
        case .advice(let session): session.id.uuidString
        case .colophon(let session): session.id.uuidString
        case .information(let session): session.id.uuidString
        case .drawingLogs: "drawingLogs"
        }
    }
}

@MainActor
public struct ContentView: View {
    @Bindable private var model: AppModel
    @State private var ui = WorkspaceUIState()
    @State private var automation = AutomationModel()
    @State private var history = HistoryModel()
    @State private var libraryPreview = LibraryPreviewModel()
    @State private var workspaceWork: SavedWork?
    @State private var batchWorkspace = BatchWorkspaceSelection()
    @State private var maintenance = LocalMaintenance()
    @State private var dialog: WorkDialog?
    @State private var presentation = false
    @State private var presentationWork: SavedWork?
    @State private var presentationHistory = HistoryModel()
    @State private var presentationLoadID = UUID()
    @State private var presentationWasFullScreen = false
    @State private var windowSize = CGSize.zero
    #if os(macOS)
    @State private var importer = DDLImportController()
    @Environment(\.openWindow) private var openWindow
    #endif

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        ZStack {
            mainShell
                .opacity(presentation ? 0 : 1)
                .accessibilityHidden(presentation)
                .allowsHitTesting(!presentation)
                .environment(\.inkuTooltipsCovered, presentation || ui.libraryOpen || ui.settingsOpen)
            if ui.libraryOpen && !presentation { libraryOverlay }
            if ui.settingsOpen && !presentation { settingsOverlay }
            if presentation { presentationView }
        }
        .onGeometryChange(for: CGSize.self) { $0.size } action: { windowSize = $0 }
        .environment(\.inkuWindowSize, windowSize)
        #if os(macOS)
        .ddlImportDropTarget(model: model,
                             enabled: !model.isBusy && !automation.isOccupied && dialog == nil && !presentation && !ui.settingsOpen,
                             onImported: openImportedDDL)
        .environment(importer)
        .onDisappear { importer.cancel() }
        #endif
        .environment(model.display)
        .environment(\.locale, Locale(identifier: model.display.preferences.language))
        .preferredColorScheme(model.display.colorScheme)
        .font(.system(size: 13 * model.display.preferences.textScale))
        .environment(\.inkuTextScale, model.display.preferences.textScale)
        .task {
            await model.initialize()
            await automation.connect(app: model)
            await history.connect(app: model)
            maintenance.connect(app: model)
            restoreScreenChoices()
            await refreshDrawingKeyState()
            model.onSavedWork = { [weak model = model, weak maintenance = maintenance] work in
                guard let model, let maintenance else { return }
                await maintenance.log(work: work, enabled: model.display.preferences.saveResultLog)
            }
            model.onDrawingLog = { [weak model = model, weak maintenance = maintenance] record in
                guard let model, let maintenance else { return }
                await maintenance.log(execution: record, enabled: model.display.preferences.saveResultLog)
            }
            while !Task.isCancelled {
                await maintenance.checkBackup(app: model, automationRunning: automation.isOccupied || dialog != nil)
                do { try await Task.sleep(for: .seconds(60)) } catch { return }
            }
        }
        .onChange(of: model.selectedWorkID) { _, _ in
            batchWorkspace.showHistory()
            Task { await history.locate(app: model) }
        }
        .onChange(of: automation.running) { _, running in
            if running && automation.mode == "batch" { batchWorkspace.followLatest() }
        }
        .onChange(of: presentation) { _, _ in batchWorkspace.invalidateReads() }
        .onChange(of: dialog?.id) { _, _ in batchWorkspace.invalidateReads() }
        .onChange(of: model.works) { _, _ in Task {
            await history.library.refresh()
            await history.locate(app: model, workID: workspaceWork?.id)
        } }
        .onChange(of: model.restorationRevision) { _, revision in
            libraryPreview.close()
            automation.invalidateWorkObservationsAfterRestore()
            batchWorkspace.showHistory()
            workspaceWork = nil
            presentationLoadID = UUID()
            presentationWork = nil
            Task {
                await history.library.resetAfterRestore()
                guard model.restorationRevision == revision else { return }
                await history.refreshGenerations()
                await history.locate(app: model)
            }
        }
        .onChange(of: ui.workspaceTab) { _, tab in remember { $0.workspaceTab = tab } }
        .onChange(of: automation.workspaceInputMode) { _, mode in remember { $0.inputTab = mode } }
        .onChange(of: model.library.layout) { _, layout in
            if layout != .lineage { remember { $0.libraryLayout = layout.rawValue } }
        }
        .onChange(of: model.library.grouped) { _, grouped in remember { $0.libraryGrouped = grouped } }
        .onChange(of: ui.settingsOpen) { _, open in if !open { Task { await refreshDrawingKeyState() } } }
        .onChange(of: model.providerSettingsRevision) { _, _ in Task { await refreshDrawingKeyState() } }
        .onChange(of: model.errorText) { _, error in if error != nil { Task { await refreshDrawingKeyState() } } }
        .onReceive(NotificationCenter.default.publisher(for: .inkuOpenSection)) { message in
            guard let raw = message.object as? String, let target = AppSection(rawValue: raw), canNavigateSections else { return }
            let opensWork = message.userInfo?["workID"] is String
            if (target == .create || target == .lineage), opensWork { batchWorkspace.showHistory() }
            switch target {
            case .create: showCreation(tab: opensWork ? "artwork" : nil)
            case .lineage: showCreation(tab: "lineage")
            case .library: openLibrary()
            case .automation: openSettings(.demo)
            case .settings:
                openSettings((message.userInfo?["settingsSection"] as? String).flatMap(SettingsSection.init(rawValue:)))
            }
        }
        #if os(macOS)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if sheetDialog.wrappedValue == nil { errorNotice }
        }
        #endif
        .sheet(item: sheetDialog) { item in
            dialogView(item)
                .environment(\.locale, Locale(identifier: model.display.preferences.language))
                .environment(\.inkuWindowSize, windowSize)
                #if os(macOS)
                .safeAreaInset(edge: .bottom, spacing: 0) { errorNotice }
                #endif
        }
        #if !os(macOS)
        .alert(model.display.localized("処理できませんでした"), isPresented: Binding(get: { model.errorText != nil }, set: { if !$0 { model.errorText = nil } })) {
            Button(model.display.localized("閉じる"), role: .cancel) { model.errorText = nil }
        } message: { Text(model.errorText ?? "") }
        #endif
        .focusedSceneValue(\.inkuCommandContext, commandContext)
    }

    /// Web `.root`: the rail, then the main shell (input panel, canvas panel and history strip).
    private var mainShell: some View {
        HStack(spacing: 0) {
            AppRailView(model: model, expanded: $ui.railExpanded, settingsOpen: ui.settingsOpen,
                        drawingLogsDisabled: dialog != nil || importing,
                        onOpenSettings: { openSettings(nil) },
                        onOpenDrawingLogs: { if dialog == nil, !importing { dialog = .drawingLogs } },
                        onOpenAbout: openAbout)
                .disabled(!canNavigateSections && !ui.settingsOpen)
            CreationView(model: model, history: history, automation: automation, maintenance: maintenance, ui: ui,
                         batchWorkspace: $batchWorkspace, inlinePanel: inlineRefinement,
                         onEditWork: openWorkEdit, onAdjustWork: openRefinement, onReplayWork: openReplay,
                         onWorkAction: openWorkAction, onLineageExport: openLineageExport,
                         onPresentWork: { Task { await preparePresentation() } },
                         onWorkspaceWorkChange: { work in
                             workspaceWork = work
                             Task { await history.locate(app: model, workID: work?.id) }
                         })
                .disabled(importing)
                // HistoryManager hides the shell beneath it (`.main-shell.library-away`) and keeps its state.
                .opacity(ui.libraryOpen ? 0 : 1)
                .accessibilityHidden(ui.libraryOpen)
                .allowsHitTesting(!ui.libraryOpen)
        }
        .disabled(ui.settingsOpen || ui.libraryOpen)
    }

    /// Web HistoryManager.svelte:1311 covers the window (`position: fixed; inset: 0`).
    private var libraryOverlay: some View {
        LibraryView(model: model, preview: libraryPreview, onEditWork: openWorkEdit, onAdjustWork: openRefinement,
                    onReplayWork: openReplay, onWorkAction: openWorkAction,
                    writingLocked: model.isBusy || automation.isOccupied, onClose: closeLibrary)
            .disabled(importing)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(InkuColor.bg)
            .transition(.opacity)
    }

    /// Web SettingsModal: `min(1240px, 100vw − 48px)` × `min(840px, 100dvh − 48px)` over a dimmed backdrop.
    private var settingsOverlay: some View {
        let box = InkuDialogSize.settings.resolved(in: windowSize)
        return ZStack {
            Color.black.opacity(0.25).ignoresSafeArea()
                .contentShape(Rectangle())
                .onTapGesture { closeSettings() }
                .accessibilityHidden(true)
            SettingsView(model: model, automation: automation, maintenance: maintenance, section: $ui.settingsSection,
                         onClose: closeSettings)
                .disabled(importing)
                .frame(width: box.width, height: box.height)
                .background(InkuColor.bg, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(InkuColor.border2))
                .shadow(color: .black.opacity(0.18), radius: 24, y: 12)
        }
    }

    #if os(macOS)
    @ViewBuilder private var errorNotice: some View {
        // Starting another operation may clear and replace this error in one update.
        // Keep its presentation in SwiftUI instead of dismissing/reopening an NSAlert sheet.
        if let error = model.errorText {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label(model.display.localized("処理できませんでした"), systemImage: "exclamationmark.triangle")
                        .inkuFont(14, weight: .semibold).foregroundStyle(.red)
                    Spacer()
                    Button(model.display.localized("閉じる")) { model.errorText = nil }.buttonStyle(InkuGhostButtonStyle())
                }
                ScrollView {
                    Text(error).inkuFont(13).textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 120)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.bar)
            .overlay(alignment: .top) { Divider() }
        }
    }
    #endif

    /// Refinement opens inside the canvas area, as the Web's refine workspace does (CanvasPanel `outputTab = 'refine'`).
    private var inlineRefinement: AnyView? {
        guard case .refinement(let session) = dialog else { return nil }
        return AnyView(
            RefinementView(model: model, work: session.work, onCommitted: { closeLibrary() }, onConfigureModels: { destination in
                dialog = nil
                openSettings(SettingsSection(rawValue: destination) ?? .models)
            }, onClose: { dialog = nil })
                .id(session.id)
                .environment(model.display)
        )
    }

    /// Every dialog but the inline refinement is a sheet.
    private var sheetDialog: Binding<WorkDialog?> {
        Binding(get: {
            if case .refinement = dialog { return nil }
            return dialog
        }, set: { value in
            if value == nil, case .refinement = dialog { return }
            dialog = value
        })
    }

    private var importing: Bool {
        #if os(macOS)
        importer.isReading
        #else
        false
        #endif
    }
    private var canNavigateSections: Bool { !importing && dialog == nil && !presentation }
    private var canReadWork: Bool { !model.isBrowsingLocked && !importing && dialog == nil && !presentation }
    private var canUseWork: Bool { !model.isBusy && !automation.isOccupied && !importing && dialog == nil && !presentation }
    private var workTarget: SavedWork? {
        if ui.settingsOpen { return nil }
        return ui.libraryOpen ? libraryPreview.work : workspaceWork
    }
    private var hasSavedWork: Bool { (ui.libraryOpen || workTarget?.id != model.previewWork?.id) && workTarget?.trashed == false }
    private var canCopyImage: Bool { canUseWork && workTarget?.svg.isEmpty == false }
    private var canPresentWork: Bool { canReadWork && workTarget?.svg.isEmpty == false }
    private var canExport: Bool {
        guard canUseWork, !ui.settingsOpen else { return false }
        if ui.libraryOpen {
            return !model.library.isTrash && (!model.library.selectedIDs.isEmpty || libraryPreview.work?.trashed == false)
        }
        return hasSavedWork
    }
    private var commandContext: InkuCommandContext {
        var enabled: Set<InkuCommandAction> = []
        if canNavigateSections {
            enabled.formUnion([.settings, .creation, .library, .lineage, .drawingLogs])
            if model.display.visible("automation") { enabled.insert(.automation) }
        }
        if canUseWork {
            enabled.insert(.newWork)
            #if os(macOS)
            enabled.insert(.openDDL)
            #endif
        }
        if canExport { enabled.insert(.export) }
        if canCopyImage { enabled.insert(.copyImage) }
        if canPresentWork { enabled.insert(.presentation) }
        return InkuCommandContext(enabledActions: enabled, perform: performCommand)
    }
    private func performCommand(_ action: InkuCommandAction) {
        guard commandContext.isEnabled(action) else { return }
        switch action {
        case .newWork:
            batchWorkspace.showHistory()
            #if os(macOS)
            importer.clearMessage()
            #endif
            model.newWork(); showCreation(tab: "artwork")
        case .openDDL:
            #if os(macOS)
            showCreation(tab: nil)
            importer.read(app: model, onImported: openImportedDDL)
            #endif
        case .settings: openSettings(nil)
        case .creation: showCreation(tab: "artwork")
        case .library: openLibrary()
        case .lineage: showCreation(tab: "lineage")
        case .automation: openSettings(.demo)
        case .drawingLogs: dialog = .drawingLogs
        case .export: Task { await openExport() }
        case .copyImage: if let work = workTarget { Task { await model.copyImage(work: work) } }
        case .presentation: Task { await preparePresentation() }
        }
    }

    private func showCreation(tab: String?) {
        ui.libraryOpen = false
        ui.settingsOpen = false
        if let tab { ui.workspaceTab = tab }
    }
    private func openLibrary() {
        ui.settingsOpen = false
        ui.libraryOpen = true
    }
    private func closeLibrary() { ui.libraryOpen = false }
    /// Web `openSettings()`: with no destination, the tab the author last chose (`settings_tab`), else the first.
    private func openSettings(_ destination: SettingsSection?) {
        ui.settingsSection = destination ?? savedSettingsSection ?? .display
        ui.settingsOpen = true
    }
    private var savedSettingsSection: SettingsSection? {
        guard let section = model.display.preferences.settingsTab.flatMap(SettingsSection.init(rawValue:)) else { return nil }
        let detailedOnly: [SettingsSection] = [.plugins, .unread, .limits]
        return detailedOnly.contains(section) && model.display.preferences.settingsDetail != "detailed" ? nil : section
    }

    /// Screen choices saved in `interface.json` come back on launch; a choice the screen cannot show is skipped.
    private func restoreScreenChoices() {
        let saved = model.display.preferences
        if let tab = saved.workspaceTab, ["artwork", "lineage"].contains(tab) { ui.workspaceTab = tab }
        // Web returns to the description tab when the input switch is hidden.
        if saved.inputTab == "batch", model.display.visible("input_modes"), !automation.isOccupied {
            automation.workspaceInputMode = "batch"
        }
        if model.descriptionText.isEmpty, model.selectedWork == nil {
            // Web `DEFAULT_INPUT` (state.svelte.ts:72): the box starts with an example description.
            model.descriptionText = "山の向こうに月が昇る"
        }
    }
    private func remember(_ change: (inout DisplayPreferences) -> Void) {
        var next = model.display.preferences
        change(&next)
        if next != model.display.preferences { model.display.preferences = next }
    }

    /// R6: guidance to the connection settings while the drawing model's service has no stored API key.
    private func refreshDrawingKeyState() async {
        ui.drawingKeyMissing = await model.drawingModelKeyMissing()
    }
    private func closeSettings() { ui.settingsOpen = false }
    private func openAbout() {
        #if os(macOS)
        openWindow(id: "about")
        #else
        openSettings(.about)
        #endif
    }

    @ViewBuilder private func dialogView(_ item: WorkDialog) -> some View {
        switch item {
        case .export(let session):
            #if os(macOS)
            ExportView(model: model, works: session.works, preserveOrder: session.preserveOrder, directCard: session.directCard)
                .id(session.id)
                .environment(model.display)
            #else
            Text(model.display.localized("書き出し")).padding()
            #endif
        case .edit(let session):
            WorkEditView(model: model, work: session.work, mode: session.mode, onCommitted: { closeLibrary() })
                .id(session.id)
                .environment(model.display)
                .inkuDialogFrame(.workEdit)
        case .refinement:
            EmptyView()
        case .replay(let session):
            ReplayComparisonView(model: model, work: session.work)
                .id(session.id)
                .environment(model.display)
                .inkuDialogFrame(.replay)
        case .ddl(let session):
            DdlAuthoringEditorSheet(model: model, session: session).id(session.id).environment(model.display)
                .inkuDialogFrame(.ddlEditor)
        case .newDDL(let session):
            NewDdlAuthoringSheet(model: model, initialImport: session.imported).id(session.id).environment(model.display)
                .inkuDialogFrame(.ddlEditor)
        case .comparison(let session):
            ComparisonView(model: model, work: session.work, kind: session.kind).id(session.id).environment(model.display)
                .inkuDialogFrame(.comparison)
        case .advice(let session):
            AuxiliaryView(model: model, mode: .advice, work: session.work).id(session.id).environment(model.display)
                .inkuDialogFrame(.auxiliary)
        case .colophon(let session):
            AuxiliaryView(model: model, mode: .colophon, work: session.work).id(session.id).environment(model.display)
                .inkuDialogFrame(.auxiliary)
        case .information(let session):
            CreationWorkInfoView(model: model, work: session.work).id(session.id).environment(model.display)
                .inkuDialogFrame(.generationInfo)
        case .drawingLogs:
            DrawingLogView(model: model).environment(model.display)
                .inkuDialogFrame(.drawingLogs)
        }
    }

    #if os(macOS)
    private func openImportedDDL() {
        guard let imported = importer.importedDocument, dialog == nil else { return }
        dialog = .newDDL(NewDdlSession(imported: imported))
    }
    #endif

    private func openWorkEdit(_ work: SavedWork, _ mode: WorkEditMode) {
        guard canUseWork, !work.trashed else { return }
        dialog = .edit(WorkEditSession(work: work, mode: mode))
    }

    private func openRefinement(_ work: SavedWork) {
        guard canUseWork, !work.trashed else { return }
        // The refine workspace replaces the canvas, so the library and settings step aside.
        ui.libraryOpen = false
        ui.settingsOpen = false
        ui.generationInfoOpen = false
        dialog = .refinement(RefinementSession(work: work))
    }

    private func openReplay(_ work: SavedWork) {
        guard canUseWork, !work.trashed else { return }
        dialog = .replay(ReplaySession(work: work))
    }

    private func openWorkAction(_ work: SavedWork, _ action: String) {
        guard !work.trashed,
              canUseWork || (canReadWork && SavedWorkActionState.isBrowsingAction(action)) else { return }
        switch action {
        case "info":
            // CanvasGenerationInfo is a drawer over the canvas; elsewhere the same view opens as a sheet.
            if !ui.libraryOpen, work.id == workspaceWork?.id { ui.generationInfoOpen.toggle() }
            else { dialog = .information(RefinementSession(work: work)) }
        case "presentation": Task { await preparePresentation(work: work) }
        case "copy-hash": model.library.copyHash(work.renderHash)
        case "export-card": dialog = .export(ExportSession(works: [work], preserveOrder: false, directCard: true))
        case "draw-ddl":
            guard let source = work.ddl, DDLSource.hasBody(source) else { return }
            Task { await model.drawEditedDDL(work: work, source: source) }
        case "ddl": dialog = .ddl(DdlEditingSession(work: work))
        case "color": dialog = .comparison(ComparisonSession(work: work, kind: .catalog))
        case "model": dialog = .comparison(ComparisonSession(work: work, kind: .model))
        case "ai": dialog = .advice(RefinementSession(work: work))
        case "colophon": dialog = .colophon(RefinementSession(work: work))
        case "export": dialog = .export(ExportSession(works: [work], preserveOrder: false))
        case "parameters": openRefinement(work)
        case "description": openWorkEdit(work, .description)
        case "sketch": openWorkEdit(work, .sketch)
        case "create":
            batchWorkspace.showHistory()
            Task { await model.selectWork(work); showCreation(tab: "artwork") }
        case "lineage":
            batchWorkspace.showHistory()
            Task {
                await model.selectWork(work)
                await model.library.loadLineage(work: work)
                showCreation(tab: "lineage")
            }
        default: break
        }
    }

    private func openLineageExport(_ scope: String) {
        guard canUseWork, let graph = model.library.graph else { return }
        let focus = graph.focusNodeID
        let center = graph.nodes.first(where: { $0.id == focus })?.work
        let checked = model.library.selectedIDs.sorted()
        Task {
            do {
                let works: [SavedWork]
                if scope == "path" { works = try await model.library.lineagePathWorks(focusNodeID: focus) }
                else if scope == "checked" { works = try await model.auxiliaryDatabase().exportWorks(ids: checked) }
                else { works = center.map { [$0] } ?? [] }
                guard canUseWork, !works.isEmpty else { return }
                dialog = .export(ExportSession(works: works, preserveOrder: scope == "path"))
            } catch { model.errorText = error.localizedDescription }
        }
    }

    private func openExport() async {
        guard canExport else { return }
        let fromLibrary = ui.libraryOpen
        do {
            let works: [SavedWork]
            if fromLibrary && !model.library.selectedIDs.isEmpty {
                works = try await model.library.selectedWorks()
            } else if fromLibrary {
                works = try await libraryPreview.exportWorks(app: model)
            } else { works = workTarget.map { [$0] } ?? [] }
            guard canExport, ui.libraryOpen == fromLibrary else { return }
            if !works.isEmpty { dialog = .export(ExportSession(works: works, preserveOrder: false)) }
        } catch { model.errorText = error.localizedDescription }
    }

    private var presentationView: some View {
        VStack(spacing: 8) {
            ArtworkCanvas(svg: presentationWork?.svg ?? "", renderer: model.displayRenderer, caption: presentationWork?.effectiveSourceText ?? "",
                          style: .workspace, aspectRatio: presentationWork?.renderCanvasAspectRatio)
            // CanvasPresentationOverlay.svelte:76-133: navigation, the star and the caption switch, each with its bubble.
            HStack {
                let display = model.display
                Button(display.localized("最新")) { navigatePresentation(boundary: "latest") }
                    .disabled(!presentationHistory.canMoveNewer || model.isBrowsingLocked)
                    .inkuTooltip(display.tooltip("最新の履歴", serverKey: "tooltipCanvasNavLatest"))
                Button(display.localized("新しい作品"), systemImage: "chevron.left") { navigatePresentation(delta: -1) }
                    .disabled(!presentationHistory.canMoveNewer || model.isBrowsingLocked)
                    .inkuTooltip(display.tooltip("新しい作品", serverKey: "tooltipCanvasNavNewer"))
                Button(display.localized("古い作品"), systemImage: "chevron.right") { navigatePresentation(delta: 1) }
                    .disabled(!presentationHistory.canMoveOlder || model.isBrowsingLocked)
                    .inkuTooltip(display.tooltip("古い作品", serverKey: "tooltipCanvasNavOlder"))
                Button(display.localized("最古")) { navigatePresentation(boundary: "oldest") }
                    .disabled(!presentationHistory.canMoveOlder || model.isBrowsingLocked)
                    .inkuTooltip(display.tooltip("最古の履歴", serverKey: "tooltipCanvasNavOldest"))
                if let work = presentationWork { Text(work.renderHash.map { String($0.suffix(4)) } ?? "").inkuFont(12, design: .monospaced) }
                Spacer()
                let starred = presentationWork.map { work in model.library.works.first { $0.id == work.id }?.starred ?? work.starred } ?? false
                Button { presentationToggleStar() } label: { Text("★").foregroundStyle(starred ? Color(red: 0.84, green: 0.61, blue: 0.13) : .secondary) }
                    .disabled(presentationWork == nil || model.library.mutating || !canUseWork)
                    .accessibilityLabel(display.webCopy(starred ? "starOn" : "starOff", starred ? "スターを外す" : "スターを付ける"))
                    .inkuTooltip(display.tooltip(starred ? "スターを外す" : "スターを付ける", serverKey: starred ? "starOn" : "starOff"))
                Button { display.preferences.captionVisible.toggle() } label: { Image(systemName: "text.bubble") }
                    .buttonStyle(InkuGhostButtonStyle(active: display.preferences.captionVisible))
                    .disabled(presentationWork?.effectiveSourceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false)
                    .accessibilityLabel(display.webCopy("canvasCaptionToggle", "詞書の表示"))
                    .inkuTooltip(display.tooltip("詞書の表示", serverKey: "canvasCaptionToggle"))
                Button(display.localized("表示を終了")) { exitPresentation() }.keyboardShortcut(.escape, modifiers: [])
                    .inkuTooltip(display.tooltip("プレゼンテーションモードを閉じる", serverKey: "canvasPresentationClose"))
            }
            .buttonStyle(InkuGhostButtonStyle())
            .padding(.horizontal, 16).padding(.bottom, 10)
        }.frame(maxWidth: .infinity, maxHeight: .infinity).background(.background)
    }
    private func preparePresentation(work target: SavedWork? = nil) async {
        guard canReadWork, let work = target ?? workTarget, !work.svg.isEmpty else { return }
        let token = UUID(); presentationLoadID = token
        let fromLibrary = ui.libraryOpen
        let viewer = HistoryModel()
        await viewer.connect(app: model)
        await viewer.locate(app: model, workID: work.id)
        guard canReadWork, ui.libraryOpen == fromLibrary, presentationLoadID == token else { return }
        presentationWork = work; presentationHistory = viewer
        enterPresentation()
    }
    private func presentationToggleStar() {
        guard var work = presentationWork, !model.library.mutating else { return }
        work.starred = model.library.works.first { $0.id == work.id }?.starred ?? work.starred
        let target = work
        Task {
            await model.library.toggleStar(target)
            if let saved = try? await model.auxiliaryDatabase().work(id: target.id), presentationWork?.id == target.id {
                presentationWork?.starred = saved.starred
            }
        }
    }
    private func navigatePresentation(delta: Int = 0, boundary: String? = nil) {
        let workID = presentationWork?.id
        Task {
            if let work = await presentationHistory.navigate(app: model, fromWorkID: workID, delta: delta,
                                                             boundary: boundary, selectWork: false),
               presentation, presentationWork?.id == workID { presentationWork = work }
        }
    }
    private func enterPresentation() {
        guard presentationWork?.svg.isEmpty == false else { return }
        #if os(macOS)
        presentationWasFullScreen = NSApp.keyWindow?.styleMask.contains(.fullScreen) == true
        if !presentationWasFullScreen { NSApp.keyWindow?.toggleFullScreen(nil) }
        #endif
        presentation = true
    }
    private func exitPresentation() {
        #if os(macOS)
        if !presentationWasFullScreen, NSApp.keyWindow?.styleMask.contains(.fullScreen) == true { NSApp.keyWindow?.toggleFullScreen(nil) }
        #endif
        presentation = false
    }
}

/// RunStatus mascot (Web `RunStatus.svelte` run-mascot).
struct NativeMascot: View {
    @Environment(\.locale) private var locale
    let kind: String
    var body: some View {
        TimelineView(.animation(minimumInterval: 0.1)) { timeline in
            let wave = sin(timeline.date.timeIntervalSinceReferenceDate * 4)
            Canvas { context, size in
                var path = Path()
                if kind == "yuragi" {
                    path.addEllipse(in: CGRect(x: 7, y: 10, width: 14, height: 11))
                    for side in [CGFloat(-1), 1] {
                        for leg in 0..<3 {
                            path.move(to: CGPoint(x: 14 + side * 6, y: 13 + CGFloat(leg) * 3))
                            path.addLine(to: CGPoint(x: 14 + side * 11, y: 12 + CGFloat(leg) * 5 + wave * side))
                        }
                        path.move(to: CGPoint(x: 14 + side * 5, y: 11)); path.addLine(to: CGPoint(x: 14 + side * 9, y: 5))
                        path.addLines([CGPoint(x: 14 + side * 6, y: 2), CGPoint(x: 14 + side * 9, y: 5), CGPoint(x: 14 + side * 12, y: 2)])
                    }
                } else {
                    path.addLines([CGPoint(x: 14, y: 3), CGPoint(x: 24, y: 9), CGPoint(x: 24, y: 20), CGPoint(x: 14, y: 26), CGPoint(x: 4, y: 20), CGPoint(x: 4, y: 9), CGPoint(x: 14, y: 3)])
                    path.move(to: CGPoint(x: 4, y: 9)); path.addLines([CGPoint(x: 14, y: 15), CGPoint(x: 24, y: 9)])
                    path.move(to: CGPoint(x: 14, y: 15)); path.addLine(to: CGPoint(x: 14, y: 26))
                }
                context.stroke(path, with: .color(.accentColor), lineWidth: 1.4)
            }.rotationEffect(.degrees(wave * 5))
        }.accessibilityLabel(InkuLocalization.string(kind == "yuragi" ? "Yuragiが描画中" : "Incuが描画中", locale: locale))
    }
}
