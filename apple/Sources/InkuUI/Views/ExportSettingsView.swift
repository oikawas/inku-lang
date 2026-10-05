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
    @State private var savedTemplates: [ExportTemplate]
    @State private var page = "destination"
    @State private var templateError: String?
    @State private var pendingSavedTemplateID: String?

    init(model: AppModel) {
        self.model = model
        _configuration = State(initialValue: model.display.preferences.exportDefaults)
        _templates = State(initialValue: ExportTemplate.normalized(model.display.preferences.exportTemplates))
        _savedTemplates = State(initialValue: ExportTemplate.normalized(model.display.preferences.exportTemplates))
    }

    var body: some View {
        Group {
            Section {
                InkuSegmentedButtons(options: [("destination", model.display.localized("保存先")), ("png", model.display.localized("PNGテンプレート")),
                                               ("animation", model.display.localized("アニメーション")), ("card", model.display.localized("共有カード"))],
                                     selection: $page)
                    .accessibilityLabel(model.display.localized("エクスポート"))
            }
            if page == "destination" {
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
            #else
            Section(model.display.localized("保存先")) {
                Text(model.display.localized("書き出すときに保存先を選択します。"))
            }
            #endif
            }
            if page == "png" {
            Section(model.display.localized("書き出しの初期設定")) {
                Text(model.display.localized("この端末で使う書き出し条件です。作品の保存内容は変わりません。"))
                    .inkuFont(13).foregroundStyle(.secondary)
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
                        HStack {
                            if templateIsDirty(template) {
                                Button(model.display.localized("保存")) { saveTemplate(template) }.disabled(templateValidation(template) != nil)
                                Button(model.display.localized("リセット")) { resetTemplate(template.id) }
                            } else {
                                Button(model.display.localized("削除"), role: .destructive) { removeTemplate(template.id) }
                            }
                        }
                        if templateIsDirty(template) {
                            Text(model.display.localized(templateValidation(template) ?? "未保存"))
                                .inkuFont(12).foregroundStyle(templateValidation(template) == nil ? Color.secondary : Color.red)
                        }
                    }
                }
                Button(model.display.localized("テンプレートを追加")) { addTemplate() }.disabled(templates.count >= 20)
            }
            }
            if page == "animation" {
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
            }
            if page == "card" {
            Section(model.display.localized("共有カード")) {
                Picker(model.display.localized("用紙"), selection: $configuration.options.cardLayout) { Text(model.display.localized("正方形（1:1）")).tag("square"); Text(model.display.localized("縦長（4:5）")).tag("portrait") }
                Toggle(model.display.localized("inkuの署名"), isOn: $configuration.options.cardSeal)
            }
            }
            if let templateError { Text(model.display.message(templateError)).foregroundStyle(.red).textSelection(.enabled) }
            if let error = model.display.saveError {
                Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled)
                Button(model.display.localized("もう一度保存")) {
                    model.display.retrySave()
                    if model.display.saveError == nil { synchronizeTemplates() }
                }
            }
        }
        .onChange(of: configuration) { _, _ in
            let defaults = configuration.normalized()
            model.display.preferences.exportConfiguration = defaults
            model.display.preferences.exportHeight = defaults.options.pixelHeight
            model.display.preferences.exportProfile = defaults.options.svgProfile
        }
    }

    private func templateIsDirty(_ template: ExportTemplate) -> Bool {
        savedTemplates.first(where: { $0.id == template.id }) != template
    }
    private func templateValidation(_ template: ExportTemplate) -> String? {
        if template.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "名前を入力してください。" }
        return (64...12000).contains(template.pixelHeight) ? nil : "Y軸は64〜12000pxで指定してください。"
    }
    private func saveTemplate(_ template: ExportTemplate) {
        if let validation = templateValidation(template) { templateError = validation; return }
        var next = ExportTemplate.normalized(model.display.preferences.exportTemplates)
        guard let index = next.firstIndex(where: { $0.id == template.id }) else { return }
        next[index] = template
        writeTemplates(next, savedID: template.id)
    }
    private func resetTemplate(_ id: String) {
        guard let saved = savedTemplates.first(where: { $0.id == id }), let index = templates.firstIndex(where: { $0.id == id }) else { return }
        templates[index] = saved
        templateError = nil
    }
    private func addTemplate() {
        var next = ExportTemplate.normalized(model.display.preferences.exportTemplates)
        guard next.count < 20 else { return }
        next.append(.init())
        writeTemplates(next)
    }
    private func removeTemplate(_ id: String) {
        writeTemplates(ExportTemplate.normalized(model.display.preferences.exportTemplates).filter { $0.id != id })
    }
    private func writeTemplates(_ next: [ExportTemplate], savedID: String? = nil) {
        pendingSavedTemplateID = savedID
        model.display.preferences.exportTemplates = ExportTemplate.normalized(next)
        guard model.display.saveError == nil else { templateError = model.display.saveError; return }
        synchronizeTemplates()
        templateError = nil
    }
    private func synchronizeTemplates() {
        let next = ExportTemplate.normalized(model.display.preferences.exportTemplates)
        let dirty = templates.filter { $0.id != pendingSavedTemplateID && templateIsDirty($0) }
        savedTemplates = next
        templates = next.map { saved in dirty.first(where: { $0.id == saved.id }) ?? saved }
        pendingSavedTemplateID = nil
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
