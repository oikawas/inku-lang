import InkuExport
import SwiftUI
#if os(macOS)
import AppKit
#endif

extension DisplayPreferences {
    var exportDefaults: ExportConfiguration {
        if let exportConfiguration { return exportConfiguration.normalized() }
        var options = ExportOptions()
        options.pixelHeight = exportHeight; options.svgProfile = exportProfile
        return ExportConfiguration(options: options, resolution: exportHeight).normalized()
    }
}

@MainActor
struct ExportSettingsView: View {
    @Bindable var model: AppModel
    @State private var configuration: ExportConfiguration
    @State private var templates: [ExportTemplate]
    @State private var templateError: String?

    init(model: AppModel) {
        self.model = model
        _configuration = State(initialValue: model.display.preferences.exportDefaults)
        _templates = State(initialValue: ExportTemplate.normalized(model.display.preferences.exportTemplates))
    }

    var body: some View {
        Group {
            #if os(macOS)
            Section(model.display.localized("保存先")) {
                Text(configuration.destinationName.map { model.display.localizedFormat("保存先: %@", $0) } ?? model.display.localized("書き出すときに保存先を選択します。"))
                    .foregroundStyle(.secondary)
                HStack {
                    Button(model.display.localized("保存先フォルダーを選択…")) { chooseDestination() }
                    if configuration.destinationBookmark != nil {
                        Button(model.display.localized("解除")) { configuration.destinationBookmark = nil; configuration.destinationName = nil }
                    }
                }
            }
            #endif
            Section(model.display.localized("書き出しの初期設定")) {
                Text(model.display.localized("この端末で使う書き出し条件です。作品の保存内容は変わりません。"))
                    .font(.callout).foregroundStyle(.secondary)
                Picker(model.display.localized("形式"), selection: $configuration.options.format) {
                    ForEach(SavedExportFormat.allCases, id: \.self) { Text(model.display.localized($0.title)).tag($0) }
                }
                Picker(model.display.localized("SVGプロファイル"), selection: $configuration.options.svgProfile) {
                    Text(model.display.localized("表示用")).tag("display"); Text(model.display.localized("編集用")).tag("editable"); Text(model.display.localized("互換用")).tag("compat"); Text(model.display.localized("ライブ用")).tag("live")
                }
                Picker(model.display.localized("Y軸"), selection: $configuration.resolution) {
                    ForEach([150, 300, 500, 1080, 2160, 4320], id: \.self) { Text("\($0)px").tag($0) }
                    if configuration.resolution != 0, ![150, 300, 500, 1080, 2160, 4320].contains(configuration.resolution) { Text("\(configuration.resolution)px").tag(configuration.resolution) }
                    Text(model.display.localized("カスタム")).tag(0)
                }
                if configuration.resolution == 0 { TextField(model.display.localized("カスタムY軸（64〜12000px）"), value: $configuration.customHeight, format: .number) }
                Toggle(model.display.localized("PNGの透明部分を白にする"), isOn: $configuration.options.pngAlphaWhite)
            }
            Section(model.display.localized("PNGテンプレート")) {
                ForEach($templates) { $template in
                    VStack(alignment: .leading, spacing: 8) {
                        TextField(model.display.localized("名前"), text: $template.name)
                        TextField(model.display.localized("説明"), text: $template.description)
                        TextField(model.display.localized("Y軸（64〜12000px）"), value: $template.pixelHeight, format: .number)
                        Button(model.display.localized("削除"), role: .destructive) { templates.removeAll { $0.id == template.id } }
                    }
                }
                Button(model.display.localized("テンプレートを追加")) { templates.append(.init()) }.disabled(templates.count >= 20)
                Button(model.display.localized("テンプレートを保存")) { saveTemplates() }
                if let templateError { Text(model.display.message(templateError)).foregroundStyle(.red) }
            }
            Section(model.display.localized("アニメーション")) {
                Picker(model.display.localized("作品の切り替え"), selection: $configuration.options.transition) {
                    Text(model.display.localized("カット")).tag("cut"); Text(model.display.localized("クロスフェード")).tag("crossfade"); Text(model.display.localized("白へフェード")).tag("fade_white"); Text(model.display.localized("スライド")).tag("slide")
                }
                TextField(model.display.localized("作品の表示時間（0.1〜30秒）"), value: $configuration.options.holdSeconds, format: .number)
                Stepper(model.display.localizedFormat("1作品のフレーム数: %ld", configuration.options.layerFrameCount), value: $configuration.options.layerFrameCount, in: 2...120)
                TextField(model.display.localized("描画間隔（0.1〜30秒）"), value: $configuration.options.layerIntervalSeconds, format: .number)
                Picker(model.display.localized("1作品の再生"), selection: $configuration.options.layerReplay) {
                    Text(model.display.localized("最初から繰り返し")).tag("restart"); Text(model.display.localized("往復")).tag("reverse"); Text(model.display.localized("1回のみ")).tag("once")
                }
            }
            Section(model.display.localized("共有カード")) {
                Picker(model.display.localized("用紙"), selection: $configuration.options.cardLayout) { Text(model.display.localized("正方形（1:1）")).tag("square"); Text(model.display.localized("縦長（4:5）")).tag("portrait") }
                Toggle(model.display.localized("inkuの署名"), isOn: $configuration.options.cardSeal)
            }
            if let error = model.display.saveError { Text(model.display.message(error)).foregroundStyle(.red) }
        }
        .onChange(of: configuration) { _, _ in
            let defaults = configuration.normalized()
            model.display.preferences.exportConfiguration = defaults
            model.display.preferences.exportHeight = defaults.options.pixelHeight
            model.display.preferences.exportProfile = defaults.options.svgProfile
        }
    }

    private func saveTemplates() {
        guard templates.count <= 20, templates.allSatisfy({ !$0.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && (64...12000).contains($0.pixelHeight) }) else {
            templateError = "名前と64〜12000pxのY軸を指定してください。テンプレートは20件までです。"; return
        }
        templates = ExportTemplate.normalized(templates)
        model.display.preferences.exportTemplates = templates
        templateError = nil
    }

    #if os(macOS)
    private func chooseDestination() {
        let panel = NSOpenPanel()
        panel.title = model.display.localized("書き出し先フォルダーを選択")
        panel.canChooseFiles = false; panel.canChooseDirectories = true; panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            configuration.destinationBookmark = try url.bookmarkData(options: .withSecurityScope, includingResourceValuesForKeys: nil, relativeTo: nil)
            configuration.destinationName = url.lastPathComponent
            templateError = nil
        } catch { templateError = "保存先を記録できませんでした: \(error.localizedDescription)" }
    }
    #endif
}
