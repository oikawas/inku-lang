import InkuPersistence
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
        case .automation: "バッチ・デモ"; case .settings: "設定"
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

private enum WorkDialog: Identifiable {
    case export(ExportSession), edit(WorkEditSession), refinement(RefinementSession), replay(ReplaySession), comparison, advice, colophon, drawingLogs
    var id: String {
        switch self {
        case .export(let session): session.id.uuidString
        case .edit(let session): session.id.uuidString
        case .refinement(let session): session.id.uuidString
        case .replay(let session): session.id.uuidString
        case .comparison: "comparison"
        case .advice: "advice"
        case .colophon: "colophon"
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
    @State private var maintenance = LocalMaintenance()
    @State private var dialog: WorkDialog?
    @State private var presentation = false
    @State private var presentationWasFullScreen = false
    @State private var settingsSection = SettingsSection.display
    #if os(macOS)
    @State private var importer = DDLImportController()
    #endif

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        Group {
            if presentation { presentationView }
            else {
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
                    .toolbar { toolbar }
                }
            }
        }
        #if os(macOS)
        .ddlImportDropTarget(model: model,
                             enabled: !model.isBusy && !automation.isOccupied && dialog == nil && !presentation,
                             onImported: { section = .create })
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
        .onChange(of: model.selectedWorkID) { _, _ in Task { await history.locate(app: model) } }
        .onChange(of: model.works) { _, _ in Task { await history.library.refresh() } }
        .onReceive(NotificationCenter.default.publisher(for: .inkuOpenSection)) { message in
            if let raw = message.object as? String, let target = AppSection(rawValue: raw), canNavigateSections {
                if target == .settings, let raw = message.userInfo?["settingsSection"] as? String,
                   let destination = SettingsSection(rawValue: raw) { settingsSection = destination }
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
        case .create: CreationView(model: model, history: history, onEditWork: openWorkEdit, onAdjustWork: openRefinement, onReplayWork: openReplay).disabled(automation.isOccupied || importing)
        case .library: LibraryView(model: model, preview: libraryPreview, onEditWork: openWorkEdit, onAdjustWork: openRefinement, onReplayWork: openReplay).disabled(automation.isOccupied || importing)
        case .lineage: LineageView(model: model, onEditWork: openWorkEdit, onAdjustWork: openRefinement, onReplayWork: openReplay).disabled(automation.isOccupied || importing)
        case .automation: AutomationView(model: model, automation: automation).disabled(importing)
        case .settings: SettingsView(model: model, section: $settingsSection).disabled(automation.isOccupied || importing)
        }
    }

    private var importing: Bool {
        #if os(macOS)
        importer.isReading
        #else
        false
        #endif
    }
    private var canNavigateSections: Bool { !automation.isOccupied && !importing && dialog == nil && !presentation }
    private var canUseWork: Bool { !model.isBusy && !automation.isOccupied && !importing && dialog == nil && !presentation }
    private var hasSavedWork: Bool { !model.isPreview && model.selectedWork?.trashed == false }
    private var canCopyImage: Bool { canUseWork && !model.currentSVG.isEmpty && [.create, .lineage].contains(section ?? .create) }
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
        if canCopyImage { enabled.formUnion([.copyImage, .presentation]) }
        return InkuCommandContext(enabledActions: enabled, perform: performCommand)
    }
    private func performCommand(_ action: InkuCommandAction) {
        guard commandContext.isEnabled(action) else { return }
        switch action {
        case .newWork:
            #if os(macOS)
            importer.clearMessage()
            #endif
            model.newWork(); section = .create
        case .openDDL:
            #if os(macOS)
            section = .create
            importer.read(app: model)
            #endif
        case .settings: section = .settings
        case .creation: section = .create
        case .library: section = .library
        case .lineage: section = .lineage
        case .automation: section = .automation
        case .export: Task { await openExport() }
        case .copyImage: Task { await model.copyImage() }
        case .presentation: enterPresentation()
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
                .help(model.display.preferences.showTooltips ? model.display.localized("成功・失敗・停止した描画の記録を確認します。") : "")
            Button {
                model.display.preferences.showTooltips.toggle()
            } label: {
                Image(systemName: model.display.preferences.showTooltips ? "text.bubble.fill" : "text.bubble")
            }
            .accessibilityLabel(model.display.localized(model.display.preferences.showTooltips ? "ツールチップを非表示" : "ツールチップを表示"))
            .help(model.display.preferences.showTooltips ? model.display.localized("ツールチップを非表示") : "")
            if model.isBusy && !automation.running {
                Button(model.display.localized("停止"), systemImage: "stop.fill") { Task { await model.cancel() } }.keyboardShortcut(.escape, modifiers: [])
            } else if section == .create {
                Button(model.display.localized("生成"), systemImage: "play.fill") { Task { await model.generate() } }
                    .disabled(!model.canGenerate || !canUseWork).keyboardShortcut(.return, modifiers: .command)
                    .help(model.display.preferences.showTooltips ? model.display.localized("生成") : "")
            }
            if section == .create || section == .library || section == .lineage {
                Button(model.display.localized("画像をコピー"), systemImage: "doc.on.doc") { Task { await model.copyImage() } }
                    .disabled(!canCopyImage)
                    .help(model.display.preferences.showTooltips ? model.display.localized("画像をコピー") : "")
                Button(model.display.localized("書き出す"), systemImage: "square.and.arrow.up") { Task { await openExport() } }
                    .disabled(!canExport)
                    .help(model.display.preferences.showTooltips ? model.display.localized("書き出す") : "")
                Menu(model.display.localized("作品の操作"), systemImage: "ellipsis.circle") {
                    Button(model.display.localized("再演奏"), systemImage: "arrow.clockwise") {
                        if let work = model.selectedWork { openReplay(work) }
                    }.disabled(!hasSavedWork)
                    Button(model.display.localized("描画パラメータの編集"), systemImage: "slider.horizontal.3") {
                        if let work = model.selectedWork { openRefinement(work) }
                    }.disabled(!hasSavedWork)
                    Button(model.display.localized("記述を変える"), systemImage: "text.cursor") {
                        if let work = model.selectedWork { openWorkEdit(work, .description) }
                    }.disabled(!hasSavedWork || model.sourceLocked)
                    Button(model.display.localized("写生なし／ありで描き直す"), systemImage: "pencil.and.outline") {
                        if let work = model.selectedWork { openWorkEdit(work, .sketch) }
                    }.disabled(!hasSavedWork || model.sourceLocked)
                    Divider()
                    Button(model.display.localized("配色・モデルを比較")) { dialog = .comparison }.disabled(!hasSavedWork)
                    Button(model.display.localized("AIの助言・自律推敲")) { dialog = .advice }.disabled(!hasSavedWork)
                    Button(model.display.localized("系譜の奥書")) { dialog = .colophon }.disabled(!hasSavedWork)
                    Button(model.display.localized("系譜を開く")) { section = .lineage }.disabled(!hasSavedWork)
                    Divider()
                    Button(model.display.localized("全画面で表示")) { enterPresentation() }
                        .disabled(model.currentSVG.isEmpty).keyboardShortcut("f", modifiers: [.command, .shift])
                }.disabled(section == .library || !canUseWork || (model.currentSVG.isEmpty && !hasSavedWork))
                    .help(model.display.preferences.showTooltips ? model.display.localized("作品の操作") : "")
            }
        }
    }

    @ViewBuilder private func dialogView(_ item: WorkDialog) -> some View {
        switch item {
        case .export(let session):
            #if os(macOS)
            ExportView(model: model, works: session.works, preserveOrder: session.preserveOrder)
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
        case .comparison:
            ComparisonView(model: model).environment(model.display)
        case .advice:
            AuxiliaryView(model: model, mode: .advice).environment(model.display)
        case .colophon:
            AuxiliaryView(model: model, mode: .colophon).environment(model.display)
        case .drawingLogs:
            DrawingLogView(model: model).environment(model.display)
        }
    }

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

    private func openExport() async {
        guard canExport else { return }
        let sourceSection = section ?? .create
        do {
            let preserveOrder = sourceSection == .lineage
            let works: [SavedWork]
            if sourceSection == .lineage {
                works = try await model.library.lineagePathWorks()
            } else if sourceSection == .library && !model.library.selectedIDs.isEmpty {
                works = try await model.library.selectedWorks()
            } else if sourceSection == .library {
                works = try await libraryPreview.exportWorks(app: model)
            } else { works = model.selectedWork.map { [$0] } ?? [] }
            guard canExport, section == sourceSection else { return }
            if !works.isEmpty { dialog = .export(ExportSession(works: works, preserveOrder: preserveOrder)) }
        } catch { model.errorText = error.localizedDescription }
    }

    private var presentationView: some View {
        VStack(spacing: 8) {
            ArtworkCanvas(svg: model.currentSVG, renderer: model.renderer, caption: model.displayedWork?.effectiveSourceText ?? "")
            HStack {
                Button(model.display.localized("最新")) { Task { await history.navigate(app: model, boundary: "latest") } }
                Button(model.display.localized("新しい作品"), systemImage: "chevron.left") { Task { await history.navigate(app: model, delta: -1) } }
                Button(model.display.localized("古い作品"), systemImage: "chevron.right") { Task { await history.navigate(app: model, delta: 1) } }
                Button(model.display.localized("最古")) { Task { await history.navigate(app: model, boundary: "oldest") } }
                if let work = model.displayedWork { Text(work.renderHash.map { String($0.suffix(4)) } ?? "").font(.caption.monospaced()) }
                Spacer()
                Button(model.display.localized("表示を終了")) { exitPresentation() }.keyboardShortcut(.escape, modifiers: [])
            }
        }.padding(16).frame(maxWidth: .infinity, maxHeight: .infinity).background(.background)
    }
    private func enterPresentation() {
        guard !model.currentSVG.isEmpty else { return }
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
