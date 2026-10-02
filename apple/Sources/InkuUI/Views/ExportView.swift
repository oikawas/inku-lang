import InkuExport
import InkuPersistence
import SwiftUI
#if os(macOS)
import AppKit
import UniformTypeIdentifiers

@MainActor
struct ExportView: View {
    @Bindable var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var candidates: [SavedWork]
    @State private var selectedIDs: Set<String>
    @State private var options = ExportOptions()
    @State private var resolution = 1080
    @State private var customHeight = 720
    @State private var isBusy = false
    @State private var status = ""
    @State private var error: String?
    @State private var operation: Task<Void, Never>?
    @State private var exportedURLs: [URL] = []
    private let preserveOrder: Bool

    init(model: AppModel, works: [SavedWork]? = nil, preserveOrder: Bool = false) {
        self.model = model
        let candidates = works ?? model.works.filter { !$0.trashed }
        _candidates = State(initialValue: candidates)
        _selectedIDs = State(initialValue: works == nil ? Set(model.selectedWorkID.map { [$0] } ?? []) : Set(candidates.map(\.id)))
        let defaults = model.display.preferences.exportDefaults
        _options = State(initialValue: defaults.options)
        _resolution = State(initialValue: defaults.resolution)
        _customHeight = State(initialValue: defaults.customHeight)
        self.preserveOrder = preserveOrder
    }

    private var selection: [SavedWork] {
        let works = candidates.filter { selectedIDs.contains($0.id) }
        return preserveOrder ? works : works.sorted { $0.at == $1.at ? $0.id < $1.id : $0.at < $1.at }
    }
    private var animation: Bool { options.format == .apng || options.format == .gif }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(model.display.localized("保存作品を書き出す")).font(.title2.bold())
                Spacer()
                Text(model.display.localizedFormat("%ld作品", selectedIDs.count)).foregroundStyle(.secondary)
            }
            HStack(alignment: .top, spacing: 20) {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Button(model.display.localized("すべて選択")) { selectedIDs = Set(candidates.map(\.id)) }
                        Button(model.display.localized("選択解除")) { selectedIDs = [] }
                    }.disabled(isBusy)
                    List(candidates, id: \.id) { work in
                        Toggle(isOn: Binding(get: { selectedIDs.contains(work.id) }, set: { included in
                            if included { selectedIDs.insert(work.id) } else { selectedIDs.remove(work.id) }
                        })) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(work.effectiveSourceText.isEmpty ? model.display.localized("無題") : work.effectiveSourceText).lineLimit(2)
                                Text(Date(timeIntervalSince1970: Double(work.at) / 1000), format: .dateTime).font(.caption).foregroundStyle(.secondary)
                            }
                        }.disabled(isBusy || work.trashed)
                    }.frame(minWidth: 240, maxWidth: 310, minHeight: 260)
                    Text(model.display.localized(preserveOrder ? "系譜の順序で書き出します。" : "選択作品を作成日時の順で書き出します。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
                Form {
                    Picker(model.display.localized("形式"), selection: $options.format) {
                        ForEach(SavedExportFormat.allCases, id: \.self) { format in Text(model.display.localized(format.title)).tag(format) }
                    }
                    if options.format == .svg {
                        Picker(model.display.localized("プロファイル"), selection: $options.svgProfile) {
                            Text(model.display.localized("保存済みの表示SVG")).tag("display")
                            Text(model.display.localized("編集用")).tag("editable")
                            Text(model.display.localized("互換用")).tag("compat")
                            Text(model.display.localized("ライブ用")).tag("live")
                        }
                        Text(model.display.localized("表示用は保存済みSVGをそのまま保存します。各プロファイルは作品の保存条件で描画します。"))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if options.format == .png || options.format == .shareCard || animation {
                        Picker(model.display.localized("Y軸"), selection: $resolution) {
                            if animation {
                                Text("150px").tag(150); Text("300px").tag(300); Text("500px").tag(500)
                            }
                            Text("1080px").tag(1080); Text("2160px").tag(2160); Text("4320px").tag(4320); Text(model.display.localized("カスタム")).tag(0)
                            if resolution != 0, ![150, 300, 500, 1080, 2160, 4320].contains(resolution) { Text("\(resolution)px").tag(resolution) }
                        }
                        if resolution == 0 { TextField("64〜12000px", value: $customHeight, format: .number) }
                        Text(model.display.localized("用紙比率を保ちます。1画像は1億4400万画素まで。"))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if options.format == .png {
                        Menu(model.display.localized("PNGテンプレート")) {
                            ForEach(ExportTemplate.normalized(model.display.preferences.exportTemplates)) { template in
                                Button("\(template.name)（\(template.pixelHeight)px）") { resolution = template.pixelHeight }
                            }
                        }
                        Toggle(model.display.localized("透明部分を白にする"), isOn: $options.pngAlphaWhite)
                    }
                    if options.format == .shareCard {
                        Picker(model.display.localized("用紙"), selection: $options.cardLayout) {
                            Text(model.display.localized("正方形（1:1）")).tag("square"); Text(model.display.localized("縦長（4:5）")).tag("portrait")
                        }
                        Toggle(model.display.localized("inkuの署名"), isOn: $options.cardSeal)
                    }
                    if options.format == .reviewSheet || options.format == .aiSheet {
                        TextField(model.display.localized("タイトル"), text: $options.title)
                        TextField(model.display.localized("サブタイトル"), text: $options.subtitle)
                        Text(model.display.localized(options.format == .aiSheet ? "12作品ずつ番号付き画像と全文の説明ファイルを書き出します。" : "28作品ずつ説明付きの閲覧用シートを書き出します。"))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if animation {
                        if selection.count == 1 {
                            Stepper(model.display.localizedFormat("フレーム数: %ld", options.layerFrameCount), value: $options.layerFrameCount, in: 2...120)
                            TextField(model.display.localized("描画間隔（0.1〜30秒）"), value: $options.layerIntervalSeconds, format: .number)
                            Picker(model.display.localized("再生"), selection: $options.layerReplay) {
                                Text(model.display.localized("最初から繰り返し")).tag("restart"); Text(model.display.localized("往復")).tag("reverse"); Text(model.display.localized("1回のみ")).tag("once")
                            }
                        } else {
                            Picker(model.display.localized("切り替え"), selection: $options.transition) {
                                Text(model.display.localized("カット")).tag("cut"); Text(model.display.localized("クロスフェード")).tag("crossfade")
                                Text(model.display.localized("白へフェード")).tag("fade_white"); Text(model.display.localized("スライド")).tag("slide")
                            }
                            TextField(model.display.localized("作品の表示時間（0.1〜30秒）"), value: $options.holdSeconds, format: .number)
                        }
                        Text(model.display.localized("1作品では描画要素を順に表示します。合計6億画素を超える設定は書き出す前に確認します。"))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }.formStyle(.grouped).frame(minWidth: 370).disabled(isBusy)
            }
            if let error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
            if !status.isEmpty { Text(model.display.message(status)).font(.callout).foregroundStyle(.secondary) }
            HStack {
                if isBusy { ProgressView().controlSize(.small); Button(model.display.localized("中止")) { operation?.cancel(); status = "中止しています…" } }
                if !exportedURLs.isEmpty {
                    Button(model.display.localized("Finderで表示")) { NSWorkspace.shared.activateFileViewerSelecting(exportedURLs) }
                    Button(model.display.localized("共有")) { share() }
                }
                Spacer()
                Button(model.display.localized("閉じる")) { dismiss() }.disabled(isBusy).keyboardShortcut(.cancelAction)
                Button(model.display.localized("書き出す")) { begin() }.disabled(isBusy || model.isBusy || selection.isEmpty).keyboardShortcut(.defaultAction)
            }
        }
        .padding(24).frame(minWidth: 760, minHeight: 520)
        .interactiveDismissDisabled(isBusy)
        .onChange(of: options.format) { _, _ in
            if !animation, [150, 300, 500].contains(resolution) { resolution = 1080 }
        }
        .onChange(of: options) { _, _ in persistDefaults() }
        .onChange(of: resolution) { _, _ in persistDefaults() }
        .onChange(of: customHeight) { _, _ in persistDefaults() }
        .onDisappear { operation?.cancel() }
    }

    private func persistDefaults() {
        var defaults = model.display.preferences.exportDefaults
        defaults.options = options; defaults.resolution = resolution; defaults.customHeight = customHeight
        model.display.preferences.exportConfiguration = defaults.normalized()
        model.display.preferences.exportHeight = resolution == 0 ? min(12000, max(64, customHeight)) : resolution
        model.display.preferences.exportProfile = options.svgProfile
    }

    private func begin() {
        let capturedWorks = selection
        var capturedOptions = options
        capturedOptions.pixelHeight = resolution == 0 ? customHeight : resolution
        let capturedDestination = model.display.preferences.exportDefaults
        isBusy = true; error = nil; status = "保存作品の書き出し条件を確認しています…"
        operation = Task { @MainActor in
            defer { isBusy = false; operation = nil }
            do {
                let profile = capturedOptions.format == .svg ? capturedOptions.svgProfile : "display"
                let sources = try await model.prepareExportSources(works: capturedWorks, profile: profile, requiresPluginDefinitions: capturedOptions.format == .ddl)
                try Task.checkCancellation()
                status = "\(capturedWorks.count)作品を描画・エンコードしています…"
                let artifacts = try await ExportService.prepare(sources: sources, options: capturedOptions)
                try Task.checkCancellation()
                guard let destination = try destination(artifacts: artifacts, format: capturedOptions.format, configuration: capturedDestination) else { status = "保存を取り消しました。"; return }
                let urls = try await save(artifacts: artifacts, destination: destination)
                exportedURLs = urls; status = "\(urls.count)ファイルを書き出しました。"
            } catch is CancellationError { status = "書き出しを中止しました。" }
            catch { self.error = error.localizedDescription; status = "" }
        }
    }

    private func destination(artifacts: [ExportArtifact], format: SavedExportFormat, configuration: ExportConfiguration) throws -> URL? {
        if let bookmark = configuration.destinationBookmark {
            var stale = false
            let folder = try URL(resolvingBookmarkData: bookmark, options: .withSecurityScope, relativeTo: nil, bookmarkDataIsStale: &stale)
            guard !stale else { throw ExportFailure("保存先のアクセス権を更新するため、設定でフォルダーを選び直してください。") }
            // A fresh child folder avoids silently replacing earlier exports.
            return folder
        }
        if artifacts.count == 1 {
            let panel = NSSavePanel(); panel.title = model.display.localized("作品を書き出す")
            panel.allowedContentTypes = [UTType(filenameExtension: format.fileExtension) ?? .data]
            panel.nameFieldStringValue = artifacts[0].name
            return panel.runModal() == .OK ? panel.url : nil
        }
        let panel = NSOpenPanel(); panel.title = model.display.localized("書き出しフォルダーを選択")
        panel.message = model.display.localized("選択した場所に新しい書き出しフォルダーを作ります。")
        panel.canChooseFiles = false; panel.canChooseDirectories = true; panel.canCreateDirectories = true
        return panel.runModal() == .OK ? panel.url : nil
    }

    private func save(artifacts: [ExportArtifact], destination: URL) async throws -> [URL] {
        let worker = Task.detached(priority: .userInitiated) {
            let scoped = destination.startAccessingSecurityScopedResource()
            defer { if scoped { destination.stopAccessingSecurityScopedResource() } }
            try Task.checkCancellation()
            var isDirectory: ObjCBool = false
            let destinationIsDirectory = FileManager.default.fileExists(atPath: destination.path, isDirectory: &isDirectory) && isDirectory.boolValue
            if artifacts.count == 1, !destinationIsDirectory {
                try artifacts[0].data.write(to: destination, options: .atomic)
                return [destination]
            }
            let bundle = destination.appendingPathComponent("inku-export-" + UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(at: bundle, withIntermediateDirectories: false)
            do {
                var urls: [URL] = []
                for artifact in artifacts {
                    try Task.checkCancellation()
                    let url = bundle.appendingPathComponent(artifact.name)
                    try artifact.data.write(to: url, options: .withoutOverwriting); urls.append(url)
                }
                return urls
            } catch {
                try? FileManager.default.removeItem(at: bundle)
                throw error
            }
        }
        return try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
    }

    private func share() {
        guard let view = NSApp.keyWindow?.contentView else { return }
        NSSharingServicePicker(items: exportedURLs).show(relativeTo: view.bounds, of: view, preferredEdge: .minY)
    }
}
#endif
