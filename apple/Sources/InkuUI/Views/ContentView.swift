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

private enum WorkDialog: Identifiable {
    case export(ExportSession), comparison, advice, colophon
    var id: String {
        switch self {
        case .export(let session): session.id.uuidString
        case .comparison: "comparison"
        case .advice: "advice"
        case .colophon: "colophon"
        }
    }
}

@MainActor
public struct ContentView: View {
    @Bindable private var model: AppModel
    @State private var section: AppSection? = .create
    @State private var automation = AutomationModel()
    @State private var history = HistoryModel()
    @State private var maintenance = LocalMaintenance()
    @State private var dialog: WorkDialog?
    @State private var presentation = false
    @State private var presentationWasFullScreen = false

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        Group {
            if presentation { presentationView }
            else {
                NavigationSplitView {
                    List(AppSection.allCases.filter { $0 != .automation || model.display.visible("automation") }, selection: $section) { item in
                        NavigationLink(value: item) { Label(model.display.localized(item.title), systemImage: item.symbol) }
                    }
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
            while !Task.isCancelled {
                await maintenance.checkBackup(app: model, automationRunning: automation.running || dialog != nil)
                do { try await Task.sleep(for: .seconds(60)) } catch { return }
            }
        }
        .onChange(of: model.selectedWorkID) { _, _ in Task { await history.locate(app: model) } }
        .onChange(of: model.works) { _, _ in Task { await history.library.refresh() } }
        .onReceive(NotificationCenter.default.publisher(for: .inkuOpenSection)) { message in
            if let raw = message.object as? String, let target = AppSection(rawValue: raw), !automation.running { section = target }
        }
        .sheet(item: $dialog) { item in
            dialogView(item).environment(\.locale, Locale(identifier: model.display.preferences.language))
        }
        .alert(model.display.localized("処理できませんでした"), isPresented: Binding(get: { model.errorText != nil }, set: { if !$0 { model.errorText = nil } })) {
            Button(model.display.localized("閉じる"), role: .cancel) { model.errorText = nil }
        } message: { Text(model.errorText ?? "") }
    }

    @ViewBuilder private var detail: some View {
        switch section ?? .create {
        case .create: CreationView(model: model, history: history).disabled(automation.running)
        case .library: LibraryView(model: model).disabled(automation.running)
        case .lineage: LineageView(model: model).disabled(automation.running)
        case .automation: AutomationView(model: model, automation: automation)
        case .settings: SettingsView(model: model).disabled(automation.running)
        }
    }

    private var statusBar: some View {
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
                    .disabled(automation.stopping)
            }
        }.font(.callout).foregroundStyle(.secondary).padding(.horizontal, 16).padding(.vertical, 8)
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            if model.isBusy && !automation.running {
                Button(model.display.localized("停止"), systemImage: "stop.fill") { Task { await model.cancel() } }.keyboardShortcut(.escape, modifiers: [])
            } else if section == .create {
                Button(model.display.localized("生成"), systemImage: "play.fill") { Task { await model.generate() } }
                    .disabled(!model.canGenerate || automation.running).keyboardShortcut(.return, modifiers: .command)
            }
            if section == .create || section == .library || section == .lineage {
                Button(model.display.localized("画像をコピー"), systemImage: "doc.on.doc") { Task { await model.copyImage() } }
                    .disabled(model.currentSVG.isEmpty || model.isBusy || automation.running)
                Button(model.display.localized("書き出す"), systemImage: "square.and.arrow.up") { Task { await openExport() } }
                    .disabled((model.selectedWork == nil && model.library.selectedIDs.isEmpty) || model.isBusy || automation.running)
                Menu(model.display.localized("作品の操作"), systemImage: "ellipsis.circle") {
                    Button(model.display.localized("配色・モデルを比較")) { dialog = .comparison }
                    Button(model.display.localized("AIの助言・自律推敲")) { dialog = .advice }
                    Button(model.display.localized("系譜の奥書")) { dialog = .colophon }
                    Button(model.display.localized("系譜を開く")) { section = .lineage }
                    Button(model.display.localized("全画面で表示")) { enterPresentation() }.keyboardShortcut("f", modifiers: [.command, .shift])
                }.disabled(model.selectedWork == nil || model.isBusy || automation.running)
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
        case .comparison:
            ComparisonView(model: model).environment(model.display)
        case .advice:
            AuxiliaryView(model: model, mode: .advice).environment(model.display)
        case .colophon:
            AuxiliaryView(model: model, mode: .colophon).environment(model.display)
        }
    }

    private func openExport() async {
        do {
            let preserveOrder = section == .lineage
            let works: [SavedWork]
            if section == .lineage && model.library.selectedIDs.isEmpty {
                works = try await model.library.lineagePathWorks()
            } else if !model.library.selectedIDs.isEmpty {
                works = try await model.library.selectedWorks()
            } else { works = model.selectedWork.map { [$0] } ?? [] }
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
