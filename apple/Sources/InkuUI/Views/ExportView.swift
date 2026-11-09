import InkuExport
import InkuPersistence
import SwiftUI
import UniformTypeIdentifiers

@MainActor
struct ExportView: View {
    @Bindable var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.inkuPhoneLayout) private var phone
    @Environment(InkuFileDialogs.self) private var fileDialogs: InkuFileDialogs?
    @State private var candidates: [SavedWork]
    @State private var selectedIDs: Set<String>
    @State private var options = ExportOptions()
    @State private var singleWorkPNGTransparent = false
    @State private var resolution = 1080
    @State private var customHeight = 720
    @State private var isBusy = false
    @State private var status = ""
    @State private var error: String?
    @State private var operation: Task<Void, Never>?
    @State private var exportedURLs: [URL] = []
    @State private var animationDestination: URL?
    @State private var svgHelpOpen = false
    @State private var directExportStarted = false
    private let preserveOrder: Bool
    private let directCard: Bool
    private let directFormat: Bool
    private let lineAnimation: Bool
    @State private var restorationRevision: UInt64

    init(model: AppModel, works: [SavedWork], preserveOrder: Bool = false, directCard: Bool = false, initialFormat: SavedExportFormat? = nil,
         initialSVGProfile: String? = nil, initialPixelHeight: Int? = nil, lineAnimation: Bool = false) {
        self.model = model
        _restorationRevision = State(initialValue: model.restorationRevision)
        let candidates = works
        _candidates = State(initialValue: candidates)
        _selectedIDs = State(initialValue: Set(candidates.map(\.id)))
        let requestedFormat = lineAnimation ? model.display.preferences.animationDefaults.options.format : directCard ? SavedExportFormat.shareCard : initialFormat ?? model.display.preferences.exportDefaults.options.format
        let defaults = requestedFormat == .apng || requestedFormat == .gif
            ? model.display.preferences.animationDefaults : model.display.preferences.exportDefaults
        var initialOptions = defaults.options
        initialOptions.format = requestedFormat
        if directCard { initialOptions.format = .shareCard }
        if let initialFormat { initialOptions.format = initialFormat }
        if let initialSVGProfile { initialOptions.svgProfile = initialSVGProfile }
        _options = State(initialValue: initialOptions)
        _singleWorkPNGTransparent = State(initialValue: model.display.preferences.singleWorkPNGTransparent)
        _resolution = State(initialValue: initialPixelHeight ?? defaults.resolution)
        _customHeight = State(initialValue: defaults.customHeight)
        self.preserveOrder = preserveOrder
        self.directCard = directCard
        self.lineAnimation = lineAnimation
        self.directFormat = !directCard && initialFormat != nil
    }

    private var selection: [SavedWork] {
        let works = candidates.filter { selectedIDs.contains($0.id) }
        return preserveOrder ? works : works.sorted { $0.at == $1.at ? $0.id < $1.id : $0.at < $1.at }
    }
    private var animation: Bool { options.format == .apng || options.format == .gif }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(lineAnimation ? copy("animationExportLayerTitle", "行ごとのアニメーションを書き出す") : model.display.localized(directCard ? "共有カードを書き出す" : "保存作品を書き出す")).inkuFont(16, weight: .semibold)
                Spacer()
                Text(model.display.localizedFormat("%ld作品", selectedIDs.count)).foregroundStyle(.secondary)
            }
            if !directCard && !directFormat {
              // iPhone (ios-app step 7c): the works above the format, each on the whole width.
              (phone ? AnyLayout(VStackLayout(alignment: .leading, spacing: 12)) : AnyLayout(HStackLayout(alignment: .top, spacing: 20))) {
                if !lineAnimation { VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Button(model.display.localized("すべて選択")) { selectedIDs = Set(candidates.map(\.id)) }
                        Button(model.display.localized("選択解除")) { selectedIDs = [] }
                    }.disabled(isBusy)
                    List(candidates, id: \.id) { work in
                        Toggle(isOn: Binding(get: { selectedIDs.contains(work.id) }, set: { included in
                            if included { selectedIDs.insert(work.id) } else { selectedIDs.remove(work.id) }
                        })) {
                            // SavedWorkExportMenu.svelte:189-190: the id prefix and the text, each whole on hover.
                            VStack(alignment: .leading, spacing: 3) {
                                LibraryWorkTitle(work: work, untitled: model.display.localized("無題"))
                                    .inkuTooltip(model.display.tooltipValue(work.effectiveSourceText))
                                HStack(spacing: 6) {
                                    Text(Date(timeIntervalSince1970: Double(work.at) / 1000), format: .dateTime)
                                    Text(String(work.id.prefix(8))).monospaced().inkuTooltip(model.display.tooltipValue(work.id))
                                }.inkuFont(12).foregroundStyle(.secondary)
                            }
                        }.disabled(isBusy || work.trashed)
                    }.frame(minWidth: phone ? nil : 240, maxWidth: phone ? .infinity : 310, minHeight: phone ? 180 : 260, maxHeight: phone ? 240 : nil)
                    Text(model.display.localized(preserveOrder ? "系譜の順序で書き出します。" : "選択作品を作成日時の順で書き出します。"))
                        .inkuFont(12).foregroundStyle(.secondary)
                } }
                Form {
                    Picker(lineAnimation ? copy("settingsAnimationFormat", "フォーマット") : model.display.localized("形式"), selection: $options.format) {
                        ForEach(lineAnimation ? [.apng, .gif] : SavedExportFormat.allCases, id: \.self) { format in
                            Text(lineAnimation ? copy(format == .apng ? "animationFormatApng" : "animationFormatGif", format.title) : model.display.localized(format.title)).tag(format)
                        }
                    }
                    if options.format == .svg {
                        HStack {
                            Picker(model.display.localized("プロファイル"), selection: $options.svgProfile) {
                                Text(copy("svgExportDisplayName", "表示用")).tag("display")
                                Text(copy("svgExportEditableName", "編集用")).tag("editable")
                                Text(copy("svgExportCompatName", "互換用")).tag("compat")
                                Text(copy("svgExportLiveName", "ライブ用")).tag("live")
                            }
                            Button { svgHelpOpen.toggle() } label: { Image(systemName: "questionmark.circle") }
                                .buttonStyle(.borderless).accessibilityLabel(copy("svgExportHelpAria", "SVGの用途と特徴"))
                                .inkuTooltip(model.display.tooltip("SVGの用途と特徴", serverKey: "svgExportHelpAria"))
                                .popover(isPresented: $svgHelpOpen) { svgHelp.inkuPopoverContent() }
                        }
                        Text(model.display.localized("表示用は保存時の記述をSVGへ添えます。ほかのプロファイルは作品の保存条件で描画します。"))
                            .inkuFont(12).foregroundStyle(.secondary)
                    }
                    if !animation && (options.format == .png || options.format == .shareCard) {
                        Picker(model.display.localized("Y軸"), selection: $resolution) {
                            Text("1080px").tag(1080)
                            Text("2160px").tag(2160)
                            Text("4320px").tag(4320)
                            Text(model.display.localized("カスタム")).tag(0)
                            if resolution != 0, ![150, 300, 500, 1080, 2160, 4320].contains(resolution) { Text("\(resolution)px").tag(resolution) }
                        }
                        if resolution == 0 { TextField("64〜12000px", value: $customHeight, format: .number) }
                        Text(model.display.localized("用紙比率を保ちます。1画像は1億4400万画素まで。"))
                            .inkuFont(12).foregroundStyle(.secondary)
                    }
                    if options.format == .png {
                        Menu(model.display.localized("PNGテンプレート")) {
                            ForEach(model.display.preferences.savedPNGTemplates) { template in
                                Button("\(template.name)（\(template.pixelHeight)px）") { resolution = template.pixelHeight }
                            }
                        }
                        if selection.count == 1 {
                            Toggle(model.display.label("白背景時アルファチャンネルを有効にする", "Enable alpha channel on white background"), isOn: $singleWorkPNGTransparent)
                        } else {
                            Toggle(model.display.label("複数作品PNGの透明部分を白にする", "Paint transparent areas white in multiple-work PNGs"), isOn: $options.pngAlphaWhite)
                        }
                    }
                    if options.format == .shareCard {
                        if selection.count != 1 { Text(model.display.localized("共有カードは1作品を選択してください。")).foregroundStyle(.red) }
                        Picker(model.display.localized("用紙"), selection: $options.cardLayout) {
                            Text(model.display.localized("正方形（1:1）")).tag("square"); Text(model.display.localized("縦長（4:5）")).tag("portrait")
                        }
                        Toggle(model.display.localized("inkuの署名"), isOn: $options.cardSeal)
                    }
                    if options.format == .reviewSheet || options.format == .aiSheet {
                        TextField(model.display.localized("タイトル"), text: $options.title)
                        TextField(model.display.localized("サブタイトル"), text: $options.subtitle)
                        Text(model.display.localized(options.format == .aiSheet ? "12作品ずつ番号付き画像と全文の説明ファイルを書き出します。" : "28作品ずつ説明付きの閲覧用シートを書き出します。"))
                            .inkuFont(12).foregroundStyle(.secondary)
                    }
                    if animation {
                        if selection.count == 1 {
                            Toggle(copy("settingsAnimationShowDdl", "DDL を並べる"), isOn: $options.showDDL)
                            TextField(copy("settingsAnimationLayerInterval", "行の間隔"), value: $options.layerIntervalSeconds, format: .number)
                            Text(copy("settingsAnimationLayerIntervalHint", "各フレームを表示する秒数")).inkuFont(12).foregroundStyle(.secondary)
                            Picker(copy("settingsAnimationLayerReplay", "繰り返し方"), selection: $options.layerReplay) {
                                Text(copy("animationLayerReplayRestart", "最初に戻る")).tag("restart"); Text(copy("animationLayerReplayReverse", "逆に再生する")).tag("reverse"); Text(copy("animationLayerReplayOnce", "最初だけ再生する")).tag("once")
                            }
                        } else {
                            Picker(model.display.localized("切り替え"), selection: $options.transition) {
                                Text(model.display.localized("カット")).tag("cut"); Text(model.display.localized("クロスフェード")).tag("crossfade")
                                Text(model.display.localized("白へフェード")).tag("fade_white"); Text(model.display.localized("スライド")).tag("slide")
                            }
                            TextField(model.display.localized("作品の表示時間（0.1〜30秒）"), value: $options.holdSeconds, format: .number)
                        }
                        Text(copy("settingsAnimationExportDescription", "1作品は行ごとに描画します。"))
                            .inkuFont(12).foregroundStyle(.secondary)
                        Picker(copy("settingsAnimationResolution", "解像度（Y軸）"), selection: $resolution) {
                            Text("150px").tag(150); Text("300px").tag(300); Text("500px").tag(500)
                            Text("1K（1080px）").tag(1080); Text("4K（2160px）").tag(2160); Text("8K（4320px）").tag(4320)
                            Text(copy("animationResolutionCustom", "任意指定")).tag(0)
                            if resolution != 0, ![150, 300, 500, 1080, 2160, 4320].contains(resolution) { Text("\(resolution)px").tag(resolution) }
                        }
                        if resolution == 0 { TextField(copy("animationCustomHeight", "Y軸ピクセル数"), value: $customHeight, format: .number) }
                    }
                }.formStyle(.grouped).inkuWideFrame(minWidth: 370).disabled(isBusy)
              }
            }
            if lineAnimation {
                HStack {
                    Text(copy("settingsDownloadFolderLabel", "保存先"))
                    Text(animationDestination?.lastPathComponent ?? model.display.preferences.exportDefaults.destinationName ?? copy("settingsDownloadFolderNone", "書き出すときに選択"))
                        .foregroundStyle(.secondary)
                    Button(copy("animationExportChoosePath", "保存先を選択")) {
                        Task { if let url = await fileDialogs?.choose(.folder()) { animationDestination = url } }
                    }.disabled(isBusy)
                }
            }
            if let error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
            if !status.isEmpty { Text(model.display.message(status)).inkuFont(13).foregroundStyle(.secondary) }
            HStack {
                if isBusy { ProgressView().controlSize(.small); Button(model.display.localized("中止")) { operation?.cancel(); status = "中止しています…" } }
                if !exportedURLs.isEmpty {
                    if InkuFileViewer.available {
                        Button(model.display.localized("Finderで表示")) { InkuFileViewer.reveal(exportedURLs) }
                    }
                    ShareLink(items: exportedURLs) { Text(model.display.localized("共有")) }
                }
                Spacer()
                Button(model.display.localized("閉じる")) { dismiss() }.disabled(isBusy).keyboardShortcut(.cancelAction)
                if !directFormat {
                    Button(model.display.localized("書き出す")) { begin() }.disabled(isBusy || model.isBusy || selection.isEmpty || (options.format == .shareCard && selection.count != 1)).keyboardShortcut(.defaultAction)
                }
            }
        }
        .padding(24).frame(minWidth: directCard || directFormat ? 440 : 760, minHeight: directCard || directFormat ? 220 : 520)
        .interactiveDismissDisabled(isBusy)
        .onChange(of: options.format) { previous, next in
            let wasAnimation = previous == .apng || previous == .gif
            if animation != wasAnimation {
                let defaults = animation ? model.display.preferences.animationDefaults : model.display.preferences.exportDefaults
                options = defaults.options
                options.format = next
                resolution = defaults.resolution
                customHeight = defaults.customHeight
            }
            if !animation, [150, 300, 500].contains(resolution) { resolution = 1080 }
        }
        .onDisappear { operation?.cancel() }
        .task { if directCard || directFormat { begin() } }
    }

    private func copy(_ key: String, _ fallback: String) -> String {
        model.productReference?.localized(language: model.display.preferences.language)?.texts[key] ?? model.display.localized(fallback)
    }

    private var svgHelp: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(copy("svgExportHelpTitle", "SVGの用途と特徴")).inkuFont(14, weight: .semibold)
            Grid(alignment: .topLeading, horizontalSpacing: 14, verticalSpacing: 12) {
                GridRow {
                    Text(copy("svgExportTableFormat", "形式")).bold()
                    Text(copy("svgExportTableUse", "用途")).bold()
                    Text(copy("svgExportTableFeature", "特徴")).bold()
                }
                ForEach(["Display", "Editable", "Compat", "Live"], id: \.self) { profile in
                    GridRow {
                        Text(copy("svgExport" + profile + "Name", profile)).fontWeight(.medium)
                        Text(copy("svgExport" + profile + "Use", "")).frame(width: 140, alignment: .leading)
                        Text(copy("svgExport" + profile + "Feature", "")).frame(width: 220, alignment: .leading)
                    }
                }
            }.inkuFont(13).fixedSize(horizontal: false, vertical: true)
        }.padding(20).inkuFixedWidth(530)
    }

    private func begin() {
        guard !isBusy, !selection.isEmpty, options.format != .shareCard || selection.count == 1 else { return }
        guard model.restorationRevision == restorationRevision else {
            error = model.display.localized("作品が復元されたため、書き出し画面を開き直してください。")
            return
        }
        if directFormat {
            guard !directExportStarted else { return }
            directExportStarted = true
        }
        let capturedWorks = selection
        var capturedOptions = options
        capturedOptions.pixelHeight = resolution == 0 ? customHeight : resolution
        if capturedOptions.format == .png, capturedWorks.count == 1 {
            capturedOptions.setSingleWorkPNGTransparent(singleWorkPNGTransparent)
        }
        let capturedDestination = model.display.preferences.exportDefaults
        isBusy = true; error = nil; status = "保存作品の書き出し条件を確認しています…"
        operation = Task { @MainActor in
            defer { isBusy = false; operation = nil }
            do {
                let profile = capturedOptions.format == .svg ? capturedOptions.svgProfile : "display"
                let sources = try await model.prepareExportSources(works: capturedWorks, profile: profile, requiresPluginDefinitions: capturedOptions.format == .ddl,
                                                                   lineAnimation: capturedWorks.count == 1 && (capturedOptions.format == .apng || capturedOptions.format == .gif))
                try Task.checkCancellation()
                try ExportService.validate(sources: sources, options: capturedOptions)
                let names = ExportService.artifactNames(sources: sources, options: capturedOptions)
                try Task.checkCancellation()
                guard let destination = try await destination(names: names, format: capturedOptions.format, configuration: capturedDestination) else {
                    status = "保存を取り消しました。"
                    if directFormat { model.reportExportStatus(status); dismiss() }
                    return
                }
                status = "\(capturedWorks.count)作品を描画・エンコードしています…"
                let saved = try await save(sources: sources, options: capturedOptions, names: names, destination: destination)
                guard let urls = await NativeFilePanels.handOff(saved.urls, dialogs: fileDialogs, share: true) else {
                    status = "保存を取り消しました。"
                    if directFormat { model.reportExportStatus(status); dismiss() }
                    return
                }
                exportedURLs = urls; status = "\(urls.count)ファイルを書き出しました。"
                if capturedWorks.count == 1, let matches = saved.matches {
                    var warnings: [String] = []
                    if !matches { warnings.append(copy("animationSavedMismatch", "現在の描画結果は保存された絵と異なります。")) }
                    if saved.outcome != "complete" { warnings.append(copy("animationCompileIncomplete", "指示書の一部を描けませんでした。")) }
                    if warnings.isEmpty { dismiss() } else { status = warnings.joined(separator: " ") }
                }
                if directFormat { model.reportExportStatus(status); dismiss() }
            } catch is CancellationError {
                status = "書き出しを中止しました。"
                if directFormat { model.reportExportStatus(status); dismiss() }
            }
            catch { self.error = error.localizedDescription; status = "" }
        }
    }

    private func destination(names: [String], format: SavedExportFormat, configuration: ExportConfiguration) async throws -> URL? {
        if lineAnimation, let animationDestination { return animationDestination }
        if !directFormat, let bookmark = configuration.destinationBookmark {
            let (folder, stale) = try InkuFolderBookmark.resolve(bookmark)
            guard !stale else { throw ExportFailure("保存先のアクセス権を更新するため、設定でフォルダーを選び直してください。") }
            // A fresh child folder avoids silently replacing earlier exports.
            return folder
        }
        if names.count == 1 {
            return NativeFilePanels.exportFile(title: model.display.localized("作品を書き出す"),
                                               type: UTType(filenameExtension: format.fileExtension) ?? .data, name: names[0])
        }
        return await fileDialogs?.choose(.folder(message: model.display.localized("選択した場所に新しい書き出しフォルダーを作ります。")))
    }

    private func save(sources: [ExportSource], options: ExportOptions, names: [String], destination: URL) async throws -> (urls: [URL], matches: Bool?, outcome: String?) {
        let worker = Task.detached(priority: .userInitiated) {
            let scoped = destination.startAccessingSecurityScopedResource()
            defer { if scoped { destination.stopAccessingSecurityScopedResource() } }
            try Task.checkCancellation()
            var isDirectory: ObjCBool = false
            let destinationIsDirectory = FileManager.default.fileExists(atPath: destination.path, isDirectory: &isDirectory) && isDirectory.boolValue
            let singleFile = names.count == 1 && !destinationIsDirectory
            let bundle = singleFile ? destination : destination.appendingPathComponent("inku-export-" + UUID().uuidString, isDirectory: true)
            if !singleFile { try FileManager.default.createDirectory(at: bundle, withIntermediateDirectories: false) }
            do {
                var urls: [URL] = []
                var matches: Bool?; var outcome: String?
                try ExportService.emit(sources: sources, options: options) { artifact in
                    try Task.checkCancellation()
                    let url = singleFile ? destination : bundle.appendingPathComponent(artifact.name)
                    try artifact.data.write(to: url, options: singleFile ? .atomic : .withoutOverwriting)
                    urls.append(url); matches = artifact.matchesSavedSVG; outcome = artifact.compileOutcome
                }
                return (urls, matches, outcome)
            } catch {
                if !singleFile { try? FileManager.default.removeItem(at: bundle) }
                throw error
            }
        }
        return try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
    }
}
