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

    public var animationDefaults: ExportConfiguration {
        if let animationExportConfiguration { return animationExportConfiguration.normalized() }
        var value = exportDefaults
        if value.options.format != .apng && value.options.format != .gif { value.options.format = .apng }
        if exportConfiguration == nil { value.resolution = 1080 }
        return value.normalized()
    }
}

@MainActor
struct ExportSettingsView: View {
    @Bindable var model: AppModel
    @State private var configuration: ExportConfiguration
    @State private var animationConfiguration: ExportConfiguration
    @State private var templates: [ExportTemplate]
    @State private var savedTemplates: [ExportTemplate]
    @State private var page = "destination"
    @State private var animationMode = "layer"
    @State private var templateError: String?
    @State private var pendingSavedTemplateID: String?

    init(model: AppModel) {
        self.model = model
        _configuration = State(initialValue: model.display.preferences.exportDefaults)
        _animationConfiguration = State(initialValue: model.display.preferences.animationDefaults)
        _templates = State(initialValue: ExportTemplate.normalized(model.display.preferences.exportTemplates))
        _savedTemplates = State(initialValue: ExportTemplate.normalized(model.display.preferences.exportTemplates))
    }

    var body: some View {
        @Bindable var display = model.display
        return Group {
            Section {
                InkuSegmentedButtons(options: [("destination", model.display.webCopy("settingsExportNavDestination", "保存先")), ("png", model.display.webCopy("settingsExportNavPng", "PNG")),
                                               ("animation", model.display.webCopy("settingsExportNavAnimation", "アニメーション")), ("card", model.display.webCopy("settingsExportNavCard", "共有カード"))],
                                     selection: $page)
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
            Section(model.display.webCopy("settingsExportTemplatesTitle", "PNG保存テンプレート")) {
                Text(model.display.webCopy("settingsExportTemplatesDescription", "ステータスバーのPNGメニューに表示する保存形式を管理します。Y軸の高さをピクセル数で指定します。"))
                    .inkuFont(13).foregroundStyle(.secondary)
                ForEach($templates) { $template in
                    VStack(alignment: .leading, spacing: 8) {
                        TextField(model.display.webCopy("settingsExportTemplateName", "テンプレート名"), text: $template.name)
                        TextField(model.display.webCopy("settingsExportTemplateDescription", "説明"), text: $template.description)
                        TextField(model.display.webCopy("settingsExportTemplateHeight", "Y軸の高さ"), value: $template.pixelHeight, format: .number)
                        HStack {
                            if templateIsDirty(template) {
                                Button(model.display.localized("保存")) { saveTemplate(template) }.disabled(templateValidation(template) != nil)
                                Button(model.display.webCopy("settingsExportTemplateReset", "変更を戻す")) { resetTemplate(template.id) }
                            } else {
                                Button(model.display.localized("削除"), role: .destructive) { removeTemplate(template.id) }
                            }
                        }
                        if templateIsDirty(template) {
                            Text(templateValidation(template) ?? model.display.webCopy("settingsExportTemplateUnsaved", "未保存の変更"))
                                .inkuFont(12).foregroundStyle(templateValidation(template) == nil ? Color.secondary : Color.red)
                        }
                    }
                }
                Button(model.display.localized("テンプレートを追加")) { addTemplate() }.disabled(templates.count >= 20)
            }
            Section(model.display.webCopy("settingsExportLabel", "書き出し")) {
                Text(model.display.label("この端末で次に書き出す作品の既定値です。", "Defaults for works exported next on this device."))
                    .inkuFont(13).foregroundStyle(.secondary)
                Toggle(model.display.webCopy("settingsPngAlpha", "白背景時アルファチャンネルを有効にする"),
                       isOn: $display.preferences.singleWorkPNGTransparent)
            }
            Section {
                DisclosureGroup(model.display.label("macOSの補助設定", "Additional macOS settings")) {
                    Picker(model.display.localized("形式"), selection: $configuration.options.format) {
                        ForEach(SavedExportFormat.allCases, id: \.self) { Text(model.display.localized($0.title)).tag($0) }
                    }
                    Picker(model.display.localized("SVGプロファイル"), selection: $configuration.options.svgProfile) {
                        Text(model.display.localized("表示用")).tag("display"); Text(model.display.localized("編集用")).tag("editable"); Text(model.display.localized("互換用")).tag("compat"); Text(model.display.localized("ライブ用")).tag("live")
                    }
                    resolutionFields($configuration)
                    Toggle(model.display.label("複数作品PNGの透明部分を白にする", "Paint transparent areas white in multiple-work PNGs"), isOn: $configuration.options.pngAlphaWhite)
                }
            }
            }
            if page == "animation" {
            Section(model.display.webCopy("settingsAnimationExportTitle", "アニメーションの書き出し")) {
                Text(model.display.webCopy("settingsAnimationExportDescription", "1作品はレイヤーの進行として、複数作品は作品間の切り替えとして書き出します。"))
                    .inkuFont(13).foregroundStyle(.secondary)
                InkuSegmentedButtons(options: [("layer", model.display.webCopy("settingsExportAnimationLayer", "1作品（レイヤー）")),
                                               ("transition", model.display.webCopy("settingsExportAnimationTransition", "複数作品（切り替え）"))], selection: $animationMode)
                Picker(model.display.webCopy("settingsAnimationFormat", "フォーマット"), selection: $animationConfiguration.options.format) {
                    Text(model.display.webCopy("animationFormatApng", "PNGアニメーション（APNG・可逆圧縮）")).tag(SavedExportFormat.apng)
                    Text(model.display.webCopy("animationFormatGif", "GIFアニメーション（256色）")).tag(SavedExportFormat.gif)
                }
                if animationMode == "transition" {
                Picker(model.display.webCopy("settingsAnimationPattern", "切り替えパターン"), selection: $animationConfiguration.options.transition) {
                    Text(model.display.webCopy("animationPatternCut", "カット")).tag("cut")
                    Text(model.display.webCopy("animationPatternCrossfade", "クロスフェード")).tag("crossfade")
                    Text(model.display.webCopy("animationPatternFadeWhite", "白を介したフェード")).tag("fade_white")
                    Text(model.display.webCopy("animationPatternSlide", "横スライド")).tag("slide")
                }
                TextField(model.display.webCopy("settingsAnimationHold", "表示ウェイト"), value: $animationConfiguration.options.holdSeconds, format: .number)
                Text(model.display.webCopy("settingsAnimationHoldHint", "各作品を表示する秒数")).inkuFont(12).foregroundStyle(.secondary)
                } else {
                Stepper(model.display.webCopy("settingsAnimationLayerFrames", "レイヤーの分割枚数") + ": \(animationConfiguration.options.layerFrameCount)", value: $animationConfiguration.options.layerFrameCount, in: 2...120)
                Text(model.display.webCopy("settingsAnimationLayerFramesHint", "背景から完成までの順方向フレーム数")).inkuFont(12).foregroundStyle(.secondary)
                TextField(model.display.webCopy("settingsAnimationLayerInterval", "レイヤーの間隔"), value: $animationConfiguration.options.layerIntervalSeconds, format: .number)
                Text(model.display.webCopy("settingsAnimationLayerIntervalHint", "各フレームを表示する秒数")).inkuFont(12).foregroundStyle(.secondary)
                Picker(model.display.webCopy("settingsAnimationLayerReplay", "繰り返し方"), selection: $animationConfiguration.options.layerReplay) {
                    Text(model.display.webCopy("animationLayerReplayRestart", "最初に戻る")).tag("restart")
                    Text(model.display.webCopy("animationLayerReplayReverse", "逆に再生する")).tag("reverse")
                    Text(model.display.webCopy("animationLayerReplayOnce", "最初だけ再生する")).tag("once")
                }
                }
                resolutionFields($animationConfiguration, animation: true)
            }
            }
            if page == "card" {
            Section(model.display.webCopy("settingsCardExportTitle", "カード書き出し")) {
                Picker(model.display.webCopy("settingsCardLayout", "版面"), selection: $configuration.options.cardLayout) { Text(model.display.localized("正方形（1:1）")).tag("square"); Text(model.display.localized("縦長（4:5）")).tag("portrait") }
                Toggle(model.display.webCopy("settingsCardSeal", "「inku」の刻印を入れる"), isOn: $configuration.options.cardSeal)
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
        .onChange(of: animationConfiguration) { _, _ in
            model.display.preferences.animationExportConfiguration = animationConfiguration.normalized()
        }
    }

    private func resolutionFields(_ configuration: Binding<ExportConfiguration>, animation: Bool = false) -> some View {
        Group {
            Picker(animation ? model.display.webCopy("settingsAnimationResolution", "解像度（Y軸）") : model.display.localized("Y軸"), selection: configuration.resolution) {
                ForEach([150, 300, 500, 1080, 2160, 4320], id: \.self) { height in
                    Text(animation ? model.display.webCopy("animationResolution" + ([1080: "1k", 2160: "4k", 4320: "8k"][height] ?? String(height)), "\(height) px") : "\(height)px").tag(height)
                }
                if configuration.wrappedValue.resolution != 0, ![150, 300, 500, 1080, 2160, 4320].contains(configuration.wrappedValue.resolution) {
                    Text("\(configuration.wrappedValue.resolution)px").tag(configuration.wrappedValue.resolution)
                }
                Text(animation ? model.display.webCopy("animationResolutionCustom", "任意指定") : model.display.localized("カスタム")).tag(0)
            }
            if configuration.wrappedValue.resolution == 0 {
                TextField(animation ? model.display.webCopy("animationCustomHeight", "Y軸ピクセル数") : model.display.localized("カスタムY軸（64〜12000px）"), value: configuration.customHeight, format: .number)
            }
        }
    }

    private func templateIsDirty(_ template: ExportTemplate) -> Bool {
        savedTemplates.first(where: { $0.id == template.id }) != template
    }
    private func templateValidation(_ template: ExportTemplate) -> String? {
        if template.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return model.display.webCopy("settingsExportTemplateNameRequired", "テンプレート名を入力してください。") }
        return (64...12000).contains(template.pixelHeight) ? nil : model.display.webCopy("settingsExportTemplateHeightRange", "高さは64〜12000pxで指定してください。")
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
