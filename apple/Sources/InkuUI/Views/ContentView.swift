import InkuPersistence
import SwiftUI

enum AppSection: String, CaseIterable, Identifiable {
    case create, library, lineage, settings

    var id: String { rawValue }
    var title: String {
        switch self {
        case .create: "作成"
        case .library: "ライブラリ"
        case .lineage: "系譜"
        case .settings: "設定"
        }
    }
    var symbol: String {
        switch self {
        case .create: "paintbrush.pointed"
        case .library: "square.grid.2x2"
        case .lineage: "point.3.connected.trianglepath.dotted"
        case .settings: "gearshape"
        }
    }
}

@MainActor
public struct ContentView: View {
    @Bindable private var model: AppModel
    @State private var section: AppSection? = .create

    public init(model: AppModel) {
        self.model = model
    }

    public var body: some View {
        NavigationSplitView {
            List(AppSection.allCases, selection: $section) { item in
                NavigationLink(value: item) {
                    Label(item.title, systemImage: item.symbol)
                }
            }
            .navigationTitle("inku")
            .navigationSplitViewColumnWidth(min: 160, ideal: 190, max: 240)
        } detail: {
            VStack(spacing: 0) {
                detail
                Divider()
                HStack(spacing: 8) {
                    if model.isBusy { ProgressView().controlSize(.small) }
                    Text(model.status).lineLimit(2)
                    Spacer()
                }
                .font(.callout)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
            .navigationTitle((section ?? .create).title)
            .toolbar { toolbar }
        }
        .task { await model.initialize() }
        .alert("処理できませんでした", isPresented: Binding(
            get: { model.errorText != nil },
            set: { if !$0 { model.errorText = nil } }
        )) {
            Button("閉じる", role: .cancel) { model.errorText = nil }
        } message: {
            Text(model.errorText ?? "")
        }
    }

    @ViewBuilder
    private var detail: some View {
        switch section ?? .create {
        case .create:
            CreationView(model: model)
        case .library:
            LibraryView(model: model)
        case .lineage:
            VStack(spacing: 16) {
                ContentUnavailableView(
                    "系譜", systemImage: AppSection.lineage.symbol,
                    description: Text("作品のつながりを表示する画面は準備中です。保存作品はライブラリから開けます。")
                )
                Button("ライブラリを開く") { section = .library }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .settings:
            SettingsView(model: model)
        }
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            if model.isBusy {
                Button("停止", systemImage: "stop.fill") { Task { await model.cancel() } }
                    .keyboardShortcut(.escape, modifiers: [])
            } else if section == .create {
                Button("生成", systemImage: "play.fill") { Task { await model.generate() } }
                    .disabled(!model.canGenerate)
                    .keyboardShortcut(.return, modifiers: .command)
            }
            #if os(macOS)
            if section == .create || section == .library {
                Button("画像をコピー", systemImage: "doc.on.doc") { Task { await model.copyImage() } }
                    .disabled(model.currentSVG.isEmpty || model.isBusy)
                Menu("書き出す", systemImage: "square.and.arrow.up") {
                    Button("SVG") { chooseExport(kind: .svg) }
                    Button("PNG（高さ1024px）") { chooseExport(kind: .png) }
                }
                .disabled(model.currentSVG.isEmpty || model.isBusy)
            }
            #endif
        }
    }

    #if os(macOS)
    private func chooseExport(kind: ExportKind) {
        guard let url = NativeFilePanels.export(kind: kind) else { return }
        Task {
            switch kind {
            case .svg: await model.exportSVG(to: url)
            case .png: await model.exportPNG(to: url, height: 1024)
            }
        }
    }
    #endif
}
