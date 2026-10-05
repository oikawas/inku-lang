import InkuPersistence
import InkuHost
import SwiftUI
#if os(macOS)
import AppKit
#endif

extension Notification.Name {
    static let inkuOpenSection = Notification.Name("inku.open-section")
}

enum AppSection: String, CaseIterable, Identifiable {
    case create, library, lineage, automation, settings
    var id: String { rawValue }
    var title: String {
        switch self {
        case .create: "制作"; case .library: "ライブラリ"; case .lineage: "系譜"
        case .automation: "デモ"; case .settings: "設定"
        }
    }
    var symbol: String {
        switch self {
        case .create: "paintbrush.pointed"; case .library: "square.grid.2x2"
        case .lineage: "point.3.connected.trianglepath.dotted"; case .automation: "play.rectangle.on.rectangle"
        case .settings: "gearshape"
        }
    }
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
    @State private var section: AppSection? = .create
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
    @State private var settingsSection = SettingsSection.display
    #if os(macOS)
    @State private var importer = DDLImportController()
    #endif

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        ZStack {
                NavigationSplitView {
                    List(AppSection.allCases.filter { $0 != .automation || model.display.visible("automation") }, selection: $section) { item in
                        NavigationLink(value: item) { Label(model.display.localized(item.title), systemImage: item.symbol) }
                    }
                    .listStyle(.sidebar)
                    .disabled(!canNavigateSections)
                    .navigationTitle("inku")
                    .navigationSplitViewColumnWidth(min: 160, ideal: 190, max: 240)
                } detail: {
                    VStack(spacing: 0) {
                        detail
                        Divider()
                        statusBar
                    }
                    .navigationTitle(model.display.localized((section ?? .create).title))
                    .toolbar { if !presentation { toolbar } }
                }
                .opacity(presentation ? 0 : 1)
                .accessibilityHidden(presentation)
                .allowsHitTesting(!presentation)
            if presentation { presentationView }
        }
        #if os(macOS)
        .ddlImportDropTarget(model: model,
                             enabled: !model.isBusy && !automation.isOccupied && dialog == nil && !presentation,
                             onImported: openImportedDDL)
        .environment(importer)
        .onDisappear { importer.cancel() }
        #endif
        .environment(model.display)
        .environment(\.locale, Locale(identifier: model.display.preferences.language))
        .preferredColorScheme(model.display.colorScheme)
        .font(.system(size: 13 * model.display.preferences.textScale))
        .task {
            await model.initialize()
            await automation.connect(app: model)
            await history.connect(app: model)
            maintenance.connect(app: model)
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
            await history.locate(app: model, workID: section == .create ? workspaceWork?.id : model.selectedWorkID)
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
        .onReceive(NotificationCenter.default.publisher(for: .inkuOpenSection)) { message in
            if let raw = message.object as? String, let target = AppSection(rawValue: raw), canNavigateSections {
                if target == .settings, let raw = message.userInfo?["settingsSection"] as? String,
                   let destination = SettingsSection(rawValue: raw) { settingsSection = destination }
                if (target == .create || target == .lineage), message.userInfo?["workID"] is String { batchWorkspace.showHistory() }
                section = target
            }
        }
        #if os(macOS)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if dialog == nil { errorNotice }
        }
        #endif
        .sheet(item: $dialog) { item in
            dialogView(item).environment(\.locale, Locale(identifier: model.display.preferences.language))
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

    #if os(macOS)
    @ViewBuilder private var errorNotice: some View {
        // Starting another operation may clear and replace this error in one update.
        // Keep its presentation in SwiftUI instead of dismissing/reopening an NSAlert sheet.
        if let error = model.errorText {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label(model.display.localized("処理できませんでした"), systemImage: "exclamationmark.triangle")
                        .font(.headline).foregroundStyle(.red)
                    Spacer()
                    Button(model.display.localized("閉じる")) { model.errorText = nil }
                }
                ScrollView {
                    Text(error).font(.callout).textSelection(.enabled)
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

    @ViewBuilder private var detail: some View {
        switch section ?? .create {
        case .create: CreationView(model: model, history: history, automation: automation, batchWorkspace: $batchWorkspace, onEditWork: openWorkEdit, onAdjustWork: openRefinement, onReplayWork: openReplay, onWorkAction: openWorkAction, onLineageExport: openLineageExport, onWorkspaceWorkChange: { work in
            workspaceWork = work
            Task { await history.locate(app: model, workID: work?.id) }
        }).disabled(importing)
        case .library: LibraryView(model: model, preview: libraryPreview, onEditWork: openWorkEdit, onAdjustWork: openRefinement, onReplayWork: openReplay, onWorkAction: openWorkAction, writingLocked: model.isBusy || automation.isOccupied).disabled(importing)
        case .lineage: LineageView(model: model, onEditWork: openWorkEdit, onAdjustWork: openRefinement, onReplayWork: openReplay, onWorkAction: openWorkAction, onExport: openLineageExport, writingLocked: model.isBusy || automation.isOccupied, onBrowseWork: { _ in batchWorkspace.showHistory() }).disabled(importing)
        case .automation: AutomationView(model: model, automation: automation, demoOnly: true).disabled(importing)
        case .settings: SettingsView(model: model, automation: automation, maintenance: maintenance, section: $settingsSection).disabled(importing)
        }
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
        switch section ?? .create {
        case .library: libraryPreview.work
        case .lineage: model.library.graph?.nodes.first(where: { $0.id == model.library.graph?.focusNodeID })?.work
        case .create: workspaceWork
        case .automation, .settings: nil
        }
    }
    private var hasSavedWork: Bool { (section != .create || workTarget?.id != model.previewWork?.id) && workTarget?.trashed == false }
    private var canCopyImage: Bool { canUseWork && workTarget?.svg.isEmpty == false }
    private var canPresentWork: Bool { canReadWork && workTarget?.svg.isEmpty == false }
    private var canExport: Bool {
        guard canUseWork else { return false }
        switch section ?? .create {
        case .create: return hasSavedWork
        case .library: return !model.library.isTrash && (!model.library.selectedIDs.isEmpty || libraryPreview.work?.trashed == false)
        case .lineage: return !model.library.lineageLoading && model.library.graph?.nodes.contains(where: { $0.work?.trashed == false }) == true
        case .automation, .settings: return false
        }
    }
    private var commandContext: InkuCommandContext {
        var enabled: Set<InkuCommandAction> = []
        if canNavigateSections {
            enabled.formUnion([.settings, .creation, .library, .lineage])
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
            model.newWork(); section = .create
        case .openDDL:
            #if os(macOS)
            section = .create
            importer.read(app: model, onImported: openImportedDDL)
            #endif
        case .settings: section = .settings
        case .creation: section = .create
        case .library: section = .library
        case .lineage: section = .lineage
        case .automation: section = .automation
        case .export: Task { await openExport() }
        case .copyImage: if let work = workTarget { Task { await model.copyImage(work: work) } }
        case .presentation: Task { await preparePresentation() }
        }
    }

    private var statusBar: some View {
        VStack(alignment: .leading, spacing: 6) {
            ProviderProgressView(model: model)
            HStack(spacing: 8) {
                if model.isBusy { NativeMascot(kind: model.display.preferences.mascot).frame(width: 28, height: 28) }
                VStack(alignment: .leading, spacing: 2) {
                    Text(model.display.message(automation.running ? automation.status : model.status)).lineLimit(2)
                    if !maintenance.backupStatus.isEmpty { Text(model.display.message(maintenance.backupStatus)).font(.caption2) }
                    if !maintenance.logStatus.isEmpty { Text(model.display.message(maintenance.logStatus)).font(.caption2) }
                }
                Spacer()
                if automation.running {
                    Button(model.display.localized(automation.stopping ? "停止中" : "停止")) { Task { await automation.stop(app: model) } }
                        .disabled(automation.stopping).keyboardShortcut(.escape, modifiers: [])
                }
            }
        }.font(.callout).foregroundStyle(.secondary).padding(.horizontal, 16).padding(.vertical, 8)
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            Button(model.display.localized("描画ログ"), systemImage: "list.bullet.rectangle") { dialog = .drawingLogs }
                .disabled(dialog != nil || importing)
                .help(model.display.tooltip("成功・失敗・停止した描画の記録を確認します。"))
            Button {
                model.display.preferences.showTooltips.toggle()
            } label: {
                Image(systemName: model.display.preferences.showTooltips ? "text.bubble.fill" : "text.bubble")
            }
            .accessibilityLabel(model.display.localized(model.display.preferences.showTooltips ? "ツールチップを非表示" : "ツールチップを表示"))
            .help(model.display.tooltip("ツールチップを非表示", serverKey: "tooltipsHide"))
            if model.isBusy && !automation.running {
                Button(model.display.localized("停止"), systemImage: "stop.fill") { Task { await model.cancel() } }.keyboardShortcut(.escape, modifiers: [])
            } else if section == .create, automation.workspaceInputMode != "batch" {
                Button(model.display.localized("生成"), systemImage: "play.fill") { Task { await model.generateDescription() } }
                    .disabled(!model.canGenerateDescription || !canUseWork).keyboardShortcut(.return, modifiers: .command)
                    .help(model.display.tooltip("入力と次の生成条件から作品を描きます。", serverKey: "tooltipSubmit"))
            }
            if section == .create || section == .library || section == .lineage {
                Button(model.display.localized("画像をコピー"), systemImage: "doc.on.doc") { if let work = workTarget { Task { await model.copyImage(work: work) } } }
                    .disabled(!canCopyImage)
                    .help(model.display.tooltip("画像をコピー"))
                Button(model.display.localized("書き出す"), systemImage: "square.and.arrow.up") { Task { await openExport() } }
                    .disabled(!canExport)
                    .help(model.display.tooltip("書き出す"))
                Menu(model.display.localized("作品の操作"), systemImage: "ellipsis.circle") {
                    Button(model.display.localized("再演奏"), systemImage: "arrow.clockwise") {
                        if let work = workTarget { openReplay(work) }
                    }.disabled(!canUseWork || !hasSavedWork)
                    if let work = workTarget { SavedWorkRefinementActions(model: model, work: work, onAction: openWorkAction, writingLocked: automation.isOccupied) }
                    Button(model.display.localized("生成情報"), systemImage: "info.circle") { if let work = workTarget { openWorkAction(work, "info") } }.disabled(!hasSavedWork)
                    Button(model.display.localized("系譜の奥書")) { if let work = workTarget { openWorkAction(work, "colophon") } }.disabled(!canUseWork || !hasSavedWork)
                    Button(model.display.localized("系譜を開く")) { if let work = workTarget { openWorkAction(work, "lineage") } }.disabled(!hasSavedWork)
                    Divider()
                    Button(model.display.localized("全画面で表示")) { Task { await preparePresentation() } }
                        .disabled(!canPresentWork).keyboardShortcut("f", modifiers: [.command, .shift])
                }.disabled(!canReadWork || !hasSavedWork)
                    .help(model.display.tooltip("作品の操作"))
            }
        }
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
            WorkEditView(model: model, work: session.work, mode: session.mode, onCommitted: { section = .create })
                .id(session.id)
                .environment(model.display)
        case .refinement(let session):
            RefinementView(model: model, work: session.work, onCommitted: { section = .create }, onConfigureModels: { destination in
                dialog = nil
                settingsSection = SettingsSection(rawValue: destination) ?? .models
                section = .settings
            })
                .id(session.id)
                .environment(model.display)
        case .replay(let session):
            ReplayComparisonView(model: model, work: session.work)
                .id(session.id)
                .environment(model.display)
        case .ddl(let session):
            DdlAuthoringEditorSheet(model: model, session: session).id(session.id).environment(model.display)
        case .newDDL(let session):
            NewDdlAuthoringSheet(model: model, initialImport: session.imported).id(session.id).environment(model.display)
        case .comparison(let session):
            ComparisonView(model: model, work: session.work, kind: session.kind).id(session.id).environment(model.display)
        case .advice(let session):
            AuxiliaryView(model: model, mode: .advice, work: session.work).id(session.id).environment(model.display)
        case .colophon(let session):
            AuxiliaryView(model: model, mode: .colophon, work: session.work).id(session.id).environment(model.display)
        case .information(let session):
            CreationWorkInfoView(model: model, work: session.work).id(session.id).environment(model.display)
        case .drawingLogs:
            DrawingLogView(model: model).environment(model.display)
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
        case "info": dialog = .information(RefinementSession(work: work))
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
            Task { await model.selectWork(work); section = .create }
        case "lineage": Task { await model.library.loadLineage(work: work); section = .lineage }
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
        let sourceSection = section ?? .create
        do {
            let preserveOrder = sourceSection == .lineage
            let works: [SavedWork]
            if sourceSection == .lineage {
                works = workTarget.map { [$0] } ?? []
            } else if sourceSection == .library && !model.library.selectedIDs.isEmpty {
                works = try await model.library.selectedWorks()
            } else if sourceSection == .library {
                works = try await libraryPreview.exportWorks(app: model)
            } else { works = workTarget.map { [$0] } ?? [] }
            guard canExport, section == sourceSection else { return }
            if !works.isEmpty { dialog = .export(ExportSession(works: works, preserveOrder: preserveOrder)) }
        } catch { model.errorText = error.localizedDescription }
    }

    private var presentationView: some View {
        VStack(spacing: 8) {
            ArtworkCanvas(svg: presentationWork?.svg ?? "", renderer: model.renderer, caption: presentationWork?.effectiveSourceText ?? "")
            HStack {
                Button(model.display.localized("最新")) { navigatePresentation(boundary: "latest") }
                    .disabled(!presentationHistory.canMoveNewer || model.isBrowsingLocked)
                Button(model.display.localized("新しい作品"), systemImage: "chevron.left") { navigatePresentation(delta: -1) }
                    .disabled(!presentationHistory.canMoveNewer || model.isBrowsingLocked)
                Button(model.display.localized("古い作品"), systemImage: "chevron.right") { navigatePresentation(delta: 1) }
                    .disabled(!presentationHistory.canMoveOlder || model.isBrowsingLocked)
                Button(model.display.localized("最古")) { navigatePresentation(boundary: "oldest") }
                    .disabled(!presentationHistory.canMoveOlder || model.isBrowsingLocked)
                if let work = presentationWork { Text(work.renderHash.map { String($0.suffix(4)) } ?? "").font(.caption.monospaced()) }
                Spacer()
                Button(model.display.localized("表示を終了")) { exitPresentation() }.keyboardShortcut(.escape, modifiers: [])
            }
        }.padding(16).frame(maxWidth: .infinity, maxHeight: .infinity).background(.background)
    }
    private func preparePresentation(work target: SavedWork? = nil) async {
        guard canReadWork, let work = target ?? workTarget, !work.svg.isEmpty else { return }
        let token = UUID(); presentationLoadID = token
        let sourceSection = section
        let viewer = HistoryModel()
        await viewer.connect(app: model)
        await viewer.locate(app: model, workID: work.id)
        guard canReadWork, section == sourceSection, presentationLoadID == token else { return }
        presentationWork = work; presentationHistory = viewer
        enterPresentation()
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

private struct NativeMascot: View {
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
