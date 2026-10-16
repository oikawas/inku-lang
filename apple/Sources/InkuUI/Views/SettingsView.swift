import InkuHost
import SwiftUI

enum SettingsSection: String, CaseIterable, Identifiable {
    case display, making, demo, models, personalPlan, database, export, clipboard, plugins, unread, limits, other, native
    #if !os(macOS)
    case about
    #endif
    var id: String { rawValue }
    var title: String {
        switch self {
        case .display: "表示と操作"; case .making: "バッチの再試行"; case .models: "モデル設定"
        case .demo: "デモ"
        case .personalPlan: "ChatGPTプラン"
        case .database: "DB設定"; case .clipboard: "クリップボード"; case .plugins: "プラグイン"
        case .export: "エクスポート"
        case .unread: "未読語台帳"
        case .limits: "制限値"
        case .other: "その他"
        case .native: "macOS補助"
        #if !os(macOS)
        case .about: "inkuについて"
        #endif
        }
    }
    var symbol: String {
        switch self {
        case .display: "slider.horizontal.3"; case .making: "paintbrush.pointed"
        case .demo: "play.rectangle"
        case .models: "cpu"; case .personalPlan: "person.crop.circle"
        case .database: "externaldrive"; case .export: "square.and.arrow.up"
        case .clipboard: "doc.on.clipboard"; case .plugins: "puzzlepiece.extension"
        case .unread: "text.magnifyingglass"; case .limits: "gauge.with.dots.needle.33percent"
        case .other: "ellipsis.circle"; case .native: "desktopcomputer"
        #if !os(macOS)
        case .about: "info.circle"
        #endif
        }
    }
}

@MainActor struct SettingsView: View {
    @Bindable var model: AppModel
    @Bindable var automation: AutomationModel
    @Bindable var maintenance: LocalMaintenance
    @State private var settings = SettingsModel()
    @Binding var section: SettingsSection
    @State private var confirmRestore = false
    @State private var backupDraft = BackupSchedule()
    @State private var backupConfigurationError: String?
    @State private var fanoutDraft = "4"
    @State private var fanoutError: String?
    private var detailed: Bool { model.display.preferences.settingsDetail == "detailed" }
    private var sections: [SettingsSection] {
        SettingsSection.allCases.filter { detailed || ![.plugins, .unread, .limits].contains($0) }
    }

    var onClose: () -> Void = {}

    var body: some View {
        VStack(spacing: 0) {
            header
            HStack(spacing: 0) {
                navigation
                Rectangle().fill(InkuColor.border).frame(width: 1)
                VStack(spacing: 0) {
                    pageHeading
                    pageBody.frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                .inkuFont(14)
            }
        }
        .task(id: section) { await settings.load(model: model) }
        .onAppear {
            if [.plugins, .unread, .limits].contains(section) { model.display.preferences.settingsDetail = "detailed" }
        }
        .onChange(of: section) { _, value in
            if [.plugins, .unread, .limits].contains(value) { model.display.preferences.settingsDetail = "detailed" }
        }
        .onDisappear { settings.cancelDiscovery() }
        .alert(model.display.localized("設定を変更できませんでした"), isPresented: Binding(get: { settings.error != nil }, set: { if !$0 { settings.error = nil } })) {
            Button(model.display.localized("閉じる"), role: .cancel) { settings.error = nil }
        } message: {
            Text(model.display.localized(settings.error ?? ""))
        }
        .confirmationDialog(model.display.localized("現在の保存データを置き換えます"), isPresented: $confirmRestore, titleVisibility: .visible) {
            #if os(macOS)
            Button(model.display.localized("復元するバックアップを選択…"), role: .destructive) {
                guard !model.isBusy, !automation.isOccupied else { return }
                if let url = NativeFilePanels.restore(language: model.display.preferences.language) { Task { await model.restore(from: url) } }
            }.disabled(model.isBusy || automation.isOccupied)
            #endif
            Button(model.display.localized("キャンセル"), role: .cancel) {}
        } message: { Text(model.display.localized("現在のデータを残す場合は、先にバックアップを保存してください。")) }
    }

    /// settings-modal.css `.modal-head`: 16px title, the detail switch and the close button, padding 14×22.
    private var header: some View {
        HStack(spacing: 12) {
            Text(model.display.webCopy("settingsTitle", "設定")).inkuFont(16, weight: .semibold)
            Spacer()
            Toggle(isOn: Binding(get: { detailed }, set: { enabled in
                model.display.preferences.settingsDetail = enabled ? "detailed" : "standard"
                if !enabled && [.plugins, .unread, .limits].contains(section) { section = .display }
            })) {
                Text(model.display.webCopy(detailed ? "settingsDetailDetailed" : "settingsDetailStandard", detailed ? "詳細" : "標準"))
                    .inkuFont(12).foregroundStyle(detailed ? Color.accentColor : Color.secondary)
            }
            .toggleStyle(.switch).controlSize(.mini)
            .accessibilityLabel(model.display.webCopy("settingsDetailLabel", "表示モード"))
            Button(action: onClose) { Image(systemName: "xmark").inkuFont(15).frame(width: 32, height: 32).contentShape(Rectangle()) }
                .buttonStyle(.plain).foregroundStyle(.secondary)
                .keyboardShortcut(.cancelAction)
                .accessibilityLabel(model.display.localized("閉じる"))
        }
        .padding(.horizontal, 22).padding(.vertical, 10)
        .overlay(alignment: .bottom) { Rectangle().fill(InkuColor.border).frame(height: 1) }
    }

    /// SettingsModal.svelte:270-318: categories with a 12px label and 14px items, 208pt wide.
    private var groups: [(label: String, items: [SettingsSection])] {
        var result: [(label: String, items: [SettingsSection])] = [
            (model.display.webCopy("settingsCategoryDisplayOperation", "表示と操作"), [.display]),
            (model.display.webCopy("settingsCategoryMaking", "制作"), [.making, .demo]),
            (title(.personalPlan), [.personalPlan]),
            (model.display.webCopy("settingsTabExport", "エクスポート"), [.export, .clipboard]),
            (model.display.webCopy("settingsCategoryAdministration", "接続と管理"), [.models, .database] + (detailed ? [.limits] : [])),
        ]
        if detailed { result.append((model.display.webCopy("settingsCategoryExtensions", "拡張と詳細"), [.plugins, .unread])) }
        result.append((model.display.label("この端末", "This device"), [.other, .native]))
        #if !os(macOS)
        result.append((model.display.localized("inkuについて"), [.about]))
        #endif
        return result
    }

    private var navigation: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                ForEach(groups, id: \.label) { group in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(group.label).inkuFont(12, weight: .medium).foregroundStyle(.secondary)
                            .padding(.horizontal, 10).padding(.bottom, 3)
                        ForEach(group.items) { item in navigationItem(item) }
                    }
                }
            }
            .padding(.vertical, 18).padding(.horizontal, 12)
        }
        .frame(width: 208)
        .background(InkuColor.bg)
    }

    private func navigationItem(_ item: SettingsSection) -> some View {
        let active = section == item
        return Button {
            section = item
            // Web `selectTab` saves the author's choice (`settings_tab`); opening at a named page does not.
            model.display.preferences.settingsTab = item.rawValue
        } label: {
            Text(title(item))
                .inkuFont(14, weight: active ? .semibold : .regular)
                .foregroundStyle(active ? Color.primary : Color.secondary)
                .lineLimit(2)
                .frame(maxWidth: .infinity, minHeight: 38, alignment: .leading)
                .padding(.horizontal, 10)
                .background(RoundedRectangle(cornerRadius: 4).fill(active ? InkuColor.panel : Color.clear))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(active ? InkuColor.border2 : Color.clear))
                .overlay(alignment: .leading) {
                    if active { Rectangle().fill(Color.accentColor).frame(width: 3).padding(.vertical, 1) }
                }
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(active ? .isSelected : [])
    }

    private func title(_ item: SettingsSection) -> String {
        switch item {
        case .display: model.display.webCopy("settingsCategoryDisplayOperation", item.title)
        case .making: model.display.webCopy("settingsBatchRetryLabel", item.title)
        case .personalPlan: model.display.webCopy("chatgptPlanLabel", item.title)
        case .plugins: model.display.webCopy("settingsTabPlugins", item.title)
        case .other: model.display.label("その他", "Other")
        case .native: model.display.label("macOS補助", "Additional macOS settings")
        default: model.display.localized(item.title)
        }
    }

    private var pageHint: String {
        switch section {
        case .display: model.display.webCopy("settingsDisplayHint", "")
        case .making: model.display.webCopy("settingsMakingHint", "")
        case .demo: model.display.webCopy("tooltipInputTabDemo", "")
        case .models: model.display.webCopy("settingsModelsHint", "")
        case .personalPlan: model.display.webCopy("chatgptPlanNotice", "")
        case .database: model.display.webCopy("settingsDatabaseHint", "")
        case .export: model.display.webCopy("settingsExportHint", "")
        case .clipboard: model.display.webCopy("settingsClipboardHint", "")
        case .plugins: model.display.webCopy("settingsPluginsHint", "")
        case .unread: model.display.webCopy("settingsUnreadHint", "")
        case .limits: model.display.webCopy("settingsLimitsHint", "")
        case .other: model.display.label("この端末で行う判定と推敲候補の同時処理数を設定します。", "Set local text analysis and the number of refinement candidates processed at once.")
        case .native: model.display.label("端末の表示とローカル記録を設定します。", "Set the device appearance and local records.")
        #if !os(macOS)
        case .about: ""
        #endif
        }
    }

    /// settings-modal.css `.settings-page-heading`: 20px title over a 13px hint, padding 22/24/18.
    private var pageHeading: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title(section)).inkuFont(20, weight: .semibold)
            if !pageHint.isEmpty {
                Text(pageHint).inkuFont(13).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: 620, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 22).padding(.horizontal, 24).padding(.bottom, 18)
        .overlay(alignment: .bottom) { Rectangle().fill(InkuColor.border).frame(height: 1) }
    }

    @ViewBuilder private var pageBody: some View {
        if section == .models {
            ModelSettingsView(model: model, settings: settings, automation: automation)
        } else if section == .demo {
            AutomationView(model: model, automation: automation, demoOnly: true)
        } else {
            Form {
                switch section {
                case .display: appearance
                case .making: making
                case .other: localOther
                case .native: nativeSettings
                case .demo: EmptyView()
                case .models: EmptyView()
                case .personalPlan:
                    ChatGPTPlanSettingsView(model: model) { section = .models }.disabled(model.isBusy || automation.isOccupied)
                case .database: database
                case .export: ExportSettingsView(model: model)
                case .clipboard: clipboard
                case .plugins:
                    PluginSettingsView(model: model).disabled(model.isBusy || automation.isOccupied)
                    Section(model.display.localized("歳時記")) { SaijikiView(model: model).frame(minHeight: 480) }
                case .unread: Section { UnreadWordsView(model: model) }
                case .limits: OperationalLimitsView(model: model)
                #if !os(macOS)
                case .about: AboutInkuView(model: model)
                #endif
                }
            }.formStyle(.grouped)
        }
    }

    private var appearance: some View {
        return Group {
            textSizeSettings
            captionPositionSettings
            uiModeSettings
            historySettings
            generationInfoSettings
            mascotSettings
            preferenceSaveError
        }
    }

    private var textSizeSettings: some View {
        Section(model.display.webCopy("settingsTextSizeLabel", "文字サイズ")) {
            Text(model.display.label("この端末に保存し、すぐに反映します。", "Saved on this device and applied immediately."))
                .inkuFont(13).foregroundStyle(.secondary)
            HStack {
                Text(model.display.webCopy("settingsTextSizeSmallEnd", "小"))
                Slider(value: Binding(get: { Double(model.display.preferences.textSizeStep) }, set: { model.display.previewTextSize(Int($0)) }),
                       in: 0...4, step: 1, onEditingChanged: { editing in if !editing { model.display.saveTextSize() } })
                    .accessibilityLabel(model.display.webCopy("settingsTextSizeLabel", "文字サイズ"))
                Text(model.display.webCopy("settingsTextSizeLargeEnd", "大"))
            }
            Text(textSizeValue).monospacedDigit()
            Button(model.display.webCopy("settingsTextSizeReset", "標準に戻す")) { model.display.resetTextSize() }
        }
    }

    private var textSizeValue: String {
        let labels = [("settingsTextSizeVerySmall", "かなり小さい"), ("settingsTextSizeStandard", "標準"),
                      ("settingsTextSizeLarge", "大きい"), ("settingsTextSizeVeryLarge", "かなり大きい"), ("settingsTextSizeLargest", "最大")]
        let level = labels[min(4, max(0, model.display.preferences.textSizeStep))]
        let name = model.display.webCopy(level.0, level.1)
        let percent = Int(model.display.preferences.textScale * 100)
        return model.display.label("\(percent)%（\(name)）", "\(percent)% (\(name))")
    }

    private var captionPositionSettings: some View {
        @Bindable var display = model.display
        return Section(model.display.webCopy("settingsCaptionPosition", "詞書きの表示位置")) {
            Text(model.display.webCopy("settingsCaptionPositionDescription", "通常表示と全画面表示で、縦書きの配置と横書きの文字揃えを選びます。"))
                .inkuFont(13).foregroundStyle(.secondary)
            Picker(model.display.webCopy("settingsCaptionPosition", "詞書きの表示位置"), selection: $display.preferences.captionPosition) {
                Text(model.display.webCopy("settingsCaptionPositionLeft", "左（既定）")).tag("left")
                Text(model.display.webCopy("settingsCaptionPositionRight", "右")).tag("right")
            }.labelsHidden()
            #if os(macOS)
            .pickerStyle(.radioGroup)
            #endif
        }
    }

    private var uiModeSettings: some View {
        @Bindable var display = model.display
        return Section(model.display.webCopy("uiModeLabel", "UIモード")) {
            Text(model.display.webCopy("uiModeDescription", "シンプルUIは主要な作業に不可欠な項目だけを表示します。"))
                .inkuFont(13).foregroundStyle(.secondary)
            Picker(model.display.webCopy("uiModeLabel", "UIモード"), selection: $display.preferences.uiMode) {
                ForEach([("simple", "Simple", "シンプルUI"), ("custom", "Custom", "カスタムUI"), ("full", "Full", "フルUI")], id: \.0) { mode in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(model.display.webCopy("uiMode" + mode.1, mode.2)).fontWeight(.medium)
                        Text(model.display.webCopy("uiMode" + mode.1 + "Description", ""))
                            .inkuFont(12).foregroundStyle(.secondary)
                    }.tag(mode.0)
                }
            }.labelsHidden()
            #if os(macOS)
            .pickerStyle(.radioGroup)
            #endif
            if model.display.preferences.uiMode == "custom" {
                customVisibilitySettings
                Button(model.display.webCopy("uiModeResetSimple", "シンプルに戻す")) { model.display.preferences.uiMode = "simple" }
            }
            Text(model.display.label("設定、単発の記述と描画、キャンバスは常に表示されます。", "Settings, a single description and Paint action, and the canvas are always shown."))
                .inkuFont(13).foregroundStyle(.secondary)
        }
    }

    private var customVisibilitySettings: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.display.webCopy("uiModeCustomItems", "追加で表示する項目")).inkuFont(13, weight: .medium)
            ForEach([("input_modes", "uiModeInputModes", "まとめ描き・デモ"), ("drawing_settings", "uiModeDrawingSettings", "モデル・色・写生・キャンバス設定"),
                     ("ddl_tools", "uiModeDdlTools", "指示書の表示・編集"), ("detail_status", "uiModeDetailStatus", "処理時間・トークン・生成情報"),
                     ("work_tools", "uiModeWorkTools", "推敲・比較・書き出し・作品操作"), ("history", "uiModeHistory", "履歴と作品の移動"),
                     ("auxiliary", "uiModeAuxiliary", "テーマ・言語・作品情報")], id: \.0) { feature in
                Toggle(model.display.webCopy(feature.1, feature.2), isOn: Binding(get: { model.display.visible(feature.0) }, set: { enabled in
                    var next = model.display.preferences.customFeatures
                    let legacy = ["detail_status": "diagnostics", "input_modes": "automation", "auxiliary": "saijiki"]
                    if let alias = legacy[feature.0] { next.remove(alias) }
                    if enabled { next.insert(feature.0) } else { next.remove(feature.0) }
                    model.display.preferences.customFeatures = next
                }))
                #if os(macOS)
                .toggleStyle(.checkbox)
                #endif
            }
        }
    }

    private var historySettings: some View {
        @Bindable var display = model.display
        return Section(model.display.webCopy("historyStripFieldsLabel", "履歴帯に添える情報")) {
            Text(model.display.webCopy("historyStripFieldsDescription", "履歴帯のサムネイルの下に出す情報です。最大3つまで選べます。選ばなければ絵だけが並びます。"))
                .inkuFont(13).foregroundStyle(.secondary)
            ForEach([("generation", "historyStripFieldGeneration", "世代"), ("model", "historyStripFieldModel", "モデル"),
                     ("engine", "historyStripFieldEngineVersion", "engineバージョン"), ("size", "historyStripFieldBytes", "ファイル容量")], id: \.0) { field in
                Toggle(model.display.webCopy(field.1, field.2), isOn: membership(field.0, in: $display.preferences.historyFields, maximum: 3))
                    .disabled(!model.display.preferences.historyFields.contains(field.0) && model.display.preferences.historyFields.count >= 3)
                    #if os(macOS)
                    .toggleStyle(.checkbox)
                    #endif
            }
        }
    }

    private var generationInfoSettings: some View {
        @Bindable var display = model.display
        return Section(model.display.webCopy("generationInfoFollowLabel", "生成情報")) {
            Text(model.display.webCopy("generationInfoFollowDescription", "生成情報を開いたまま履歴帯で別の作品を選ぶと、その作品の生成情報に切り替わります。オフにすると、これまでどおり閉じます。"))
                .inkuFont(13).foregroundStyle(.secondary)
            Toggle(model.display.webCopy("generationInfoFollowToggle", "履歴帯で作品を選んでも生成情報を開いたままにする"), isOn: $display.preferences.keepGenerationInfo)
                #if os(macOS)
                .toggleStyle(.checkbox)
                #endif
        }
    }

    private var mascotSettings: some View {
        @Bindable var display = model.display
        return Section(model.display.webCopy("settingsMascotLabel", "描画中のマスコット")) {
            Picker(model.display.webCopy("settingsMascotLabel", "描画中のマスコット"), selection: $display.preferences.mascot) {
                Text(model.display.webCopy("settingsMascotIncu", "Incu（立方体）")).tag("incu")
                Text(model.display.webCopy("settingsMascotYuragi", "Yuragi（蟹）")).tag("yuragi")
            }.labelsHidden()
            #if os(macOS)
            .pickerStyle(.radioGroup)
            #endif
        }
    }

    @ViewBuilder private var preferenceSaveError: some View {
        if let error = model.display.saveError {
            Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled)
            Button(model.display.localized("もう一度保存")) { model.display.retrySave() }
        }
    }

    private var making: some View {
        @Bindable var display = model.display
        return Section(model.display.webCopy("settingsBatchRetryLabel", "バッチの再試行")) {
            Text(model.display.webCopy("settingsBatchRetryDescription", "バッチが一巡したあと、失敗した行だけをもう一度描きます。0なら再試行しません。中断したときは再試行しません。"))
                .inkuFont(13).foregroundStyle(.secondary)
            HStack {
                Text(model.display.webCopy("settingsBatchRetryCount", "再試行の回数"))
                Spacer()
                Stepper(value: $display.preferences.batchRetries, in: 0...5) {
                    Text("\(model.display.preferences.batchRetries)").monospacedDigit()
                }.fixedSize()
            }
            preferenceSaveError
        }
    }

    private var localOther: some View {
        Group {
            Section(model.display.label("詩型・形式の判定", "Verse and form analysis")) {
                DescriptionMeterSettingsView(meter: model.descriptionMeter)
            }
            Section(model.display.label("推敲候補の同時処理数", "Refinement candidates processed at once")) {
                Text(model.display.label("この端末で同時に処理する候補数です。1〜16の整数。既定は4です。開始済みの処理には適用しません。",
                                         "The number of candidates processed at once on this device. Enter an integer from 1 to 16; the default is 4. Runs already started keep their captured value."))
                    .inkuFont(13).foregroundStyle(.secondary)
                HStack(spacing: 6) {
                    Button { stepFanout(by: -1) } label: { Image(systemName: "minus") }
                        .accessibilityLabel(model.display.label("同時処理数を減らす", "Decrease parallel candidates"))
                    TextField(model.display.label("同時処理数", "Parallel candidates"), text: $fanoutDraft)
                        .labelsHidden().textFieldStyle(.roundedBorder).multilineTextAlignment(.trailing).frame(width: 80)
                        .onChange(of: fanoutDraft) { _, _ in fanoutError = nil }
                    Button { stepFanout(by: 1) } label: { Image(systemName: "plus") }
                        .accessibilityLabel(model.display.label("同時処理数を増やす", "Increase parallel candidates"))
                    Spacer()
                    Button(model.display.localized("保存")) { saveFanout() }
                        .disabled(fanoutDraft == String(model.display.preferences.refinementFanoutLimit))
                }.buttonStyle(.borderless)
                if let fanoutError { Text(fanoutError).foregroundStyle(.red).inkuFont(13) }
                preferenceSaveError
            }
        }.onAppear { fanoutDraft = String(model.display.preferences.refinementFanoutLimit); fanoutError = nil }
    }

    private func stepFanout(by amount: Int) {
        guard let value = Int(fanoutDraft), (1...16).contains(value), (1...16).contains(value + amount) else { return }
        fanoutDraft = String(value + amount)
        fanoutError = nil
    }

    private func saveFanout() {
        guard let parsed = Int(fanoutDraft), let value = try? RefinementFanout.validatedLimit(parsed) else {
            fanoutError = model.display.label("同時処理数には1〜16の整数を入力してください。", "Enter an integer from 1 to 16 for parallel candidates.")
            return
        }
        model.display.preferences.refinementFanoutLimit = value
        fanoutDraft = String(value)
        fanoutError = nil
    }

    private func stepClipboardHeight(by amount: Int) {
        let current = min(4096, max(256, model.display.preferences.clipboardHeight))
        model.display.preferences.clipboardHeight = min(4096, max(256, current + amount))
    }

    private var nativeSettings: some View {
        @Bindable var display = model.display
        return Group {
            Section(model.display.label("表示の補助設定", "Additional appearance settings")) {
                Picker(model.display.localized("テーマ"), selection: $display.preferences.theme) {
                    Text(model.display.localized("システム")).tag("system"); Text(model.display.localized("ライト")).tag("light"); Text(model.display.localized("ダーク")).tag("dark")
                }
                Picker(model.display.localized("表示言語"), selection: $display.preferences.language) { Text(model.display.localized("日本語")).tag("ja"); Text("English").tag("en") }
                Toggle(model.display.localized("ツールチップ"), isOn: $display.preferences.showTooltips)
                Toggle(model.display.localized("作品に詞書きを表示"), isOn: $display.preferences.captionVisible)
                Toggle(model.display.localized("縦書き"), isOn: $display.preferences.captionVertical)
            }
            Section(model.display.localized("結果ログ")) {
                Toggle(model.display.localized("生成結果のログを保存"), isOn: $display.preferences.saveResultLog)
                    .disabled(model.isBusy || automation.isOccupied)
                Text(model.display.localized("成功・失敗・停止の経過を描画ログへ保存します。ファイル保存を切っても端末の実行記録は確認できます。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                Text(model.display.localized("指示書・Score・生成情報を端末内へ記録します。APIキーは記録しません。"))
                    .inkuFont(13).foregroundStyle(.secondary)
            }
            if model.developerModeEnabled {
                Section(model.display.localized("開発用の応答記録")) {
                    Toggle(model.display.localized("生成時の送受信を記録"), isOn: Binding(
                        get: { display.preferences.captureProviderIO == true },
                        set: { display.preferences.captureProviderIO = $0 }))
                        .disabled(model.isBrowsingLocked)
                    Text(model.display.localized("モデルへ送った本文と受け取った応答を端末内に保存します。接続先・ヘッダー・認証情報は記録しません。"))
                        .inkuFont(13).foregroundStyle(.secondary)
                }
            }
            preferenceSaveError
        }
    }
    private var database: some View {
        @Bindable var display = model.display
        return Group {
            #if os(macOS)
            Section(model.display.localized("保存データ")) {
                if let directory = model.localDataDirectory() { Text(directory.path).inkuFont(12).textSelection(.enabled) }
                Button(model.display.localized("バックアップを保存…")) { if let url = NativeFilePanels.backup(language: model.display.preferences.language) { Task { await model.backup(to: url) } } }
                Button(model.display.localized("バックアップから復元…")) { confirmRestore = true }
                Text(model.display.localized("作品・系譜・作業状態をSQLiteへ保存します。接続設定とKeychainのAPIキーは別です。"))
                    .inkuFont(13).foregroundStyle(.secondary)
            }.disabled(model.isBusy || automation.isOccupied)
            Section(model.display.localized("自動バックアップ")) {
                Toggle(model.display.localized("自動バックアップ"), isOn: $display.preferences.automaticBackup)
                if display.preferences.usesLegacyBackupInterval {
                    Text(display.label("旧設定を保持しています: \(display.preferences.backupIntervalHours)時間ごと・\(display.preferences.backupGenerations)世代。日数と時刻を保存すると新方式へ切り替わります。",
                                       "Keeping the previous schedule: every \(display.preferences.backupIntervalHours) hours, \(display.preferences.backupGenerations) copies. Save the days and local time to switch schedules."))
                        .inkuFont(13).foregroundStyle(.secondary)
                }
                Stepper(display.label("間隔: \(backupDraft.intervalDays)日", "Interval: \(backupDraft.intervalDays) days"), value: $backupDraft.intervalDays, in: 1...365)
                Stepper(display.localizedFormat("保持: %ld世代", backupDraft.maxGenerations), value: $backupDraft.maxGenerations, in: 1...100)
                HStack {
                    Text(display.label("実行時刻（ローカル）", "Backup time (local)"))
                    Picker(display.label("時", "Hour"), selection: $backupDraft.hour) {
                        ForEach(0..<24, id: \.self) { Text(String(format: "%02d", $0)).tag($0) }
                    }.labelsHidden().accessibilityLabel(display.label("時", "Hour"))
                    Text(":")
                    Picker(display.label("分", "Minute"), selection: $backupDraft.minute) {
                        ForEach(0..<60, id: \.self) { Text(String(format: "%02d", $0)).tag($0) }
                    }.labelsHidden().accessibilityLabel(display.label("分", "Minute"))
                }
                Button(display.localized("保存")) {
                    do {
                        var preferences = display.preferences
                        try preferences.applyBackupSchedule(backupDraft)
                        display.preferences = preferences
                        backupConfigurationError = nil
                    } catch { backupConfigurationError = error.localizedDescription }
                }.disabled(!display.preferences.usesLegacyBackupInterval && backupDraft == display.preferences.backupSchedule)
                Text(display.label("最終自動バックアップのローカル日付に日数を足し、指定時刻に実行します。初回はすぐに対象となり、手動保存では次回予定は変わりません。",
                                   "The next backup uses the last automatic backup's local date plus the interval, at the chosen time. The first backup is due immediately. Manual backups keep that date unchanged."))
                    .inkuFont(13).foregroundStyle(.secondary)
                Text(display.label("アプリの起動中だけ実行します。スリープ復帰・タイムゾーン変更後は現在のローカル時刻で再判定し、生成中・復元中は待ちます。",
                                   "Backups run while the app is open. After waking or a time zone change, the current local time is checked again. Drawing and restore operations postpone the backup."))
                    .inkuFont(13).foregroundStyle(.secondary)
                if let backupConfigurationError { Text(display.message(backupConfigurationError)).foregroundStyle(.red) }
                if let error = display.saveError {
                    Text(display.message(error)).foregroundStyle(.red)
                    Button(display.localized("もう一度保存")) { display.retrySave() }
                }
                backupInformation
            }
            #endif
        }.onAppear { backupDraft = display.preferences.backupSchedule; backupConfigurationError = nil }
    }
    private var backupInformation: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let directory = maintenance.backupDirectory {
                Text(model.display.localized("保存先") + ": " + directory.path).inkuFont(12).textSelection(.enabled)
            }
            if maintenance.backupInfoLoaded {
                Text(model.display.localized("最新の成功") + ": " + (maintenance.backupLastSuccess?.formatted(date: .numeric, time: .shortened) ?? model.display.localized("未実行")))
                Text(model.display.localized("次回予定") + ": " + (maintenance.nextBackupDate(preferences: model.display.preferences)?.formatted(date: .numeric, time: .shortened)
                    ?? model.display.localized(model.display.preferences.automaticBackup ? "状態の読込待ち" : "無効")))
                if let bytes = maintenance.databaseBytes {
                    // DatabaseAdministrationSettings.svelte:146: the estimate names what it counts on hover.
                    Text(model.display.webCopy("settingsDbBackupEstimatedDisk", "必要な空き容量（概算）") + ": "
                         + ByteCountFormatter.string(fromByteCount: bytes * Int64(max(1, model.display.preferences.automaticBackupRetention)), countStyle: .file))
                        .inkuTooltip(model.display.tooltip("いまの DB ファイルの大きさ × 最大保存世代数。手動バックアップは間引かれないので、この見積もりには入りません。",
                                                           serverKey: "settingsDbBackupEstimatedDiskHint"))
                }
                Text(model.display.localizedFormat("保持済み: %ld世代", maintenance.backupGenerations.count)
                     + " · " + ByteCountFormatter.string(fromByteCount: maintenance.backupTotalBytes, countStyle: .file))
                if !maintenance.backupGenerations.isEmpty {
                    DisclosureGroup(model.display.localized("保持中の世代")) {
                        ForEach(maintenance.backupGenerations) { generation in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(generation.name).inkuFont(12, design: .monospaced).textSelection(.enabled)
                                Text(ByteCountFormatter.string(fromByteCount: generation.byteCount, countStyle: .file)
                                     + (generation.modifiedAt.map { " · " + $0.formatted(date: .numeric, time: .shortened) } ?? ""))
                                    .inkuFont(12).foregroundStyle(.secondary)
                            }.padding(.vertical, 3)
                        }
                    }
                }
            } else { Text(model.display.localized("状態の読込待ち")).inkuFont(12).foregroundStyle(.secondary) }
            if !maintenance.backupStatus.isEmpty { Text(model.display.message(maintenance.backupStatus)).inkuFont(12).textSelection(.enabled) }
            if let error = maintenance.backupInfoError { Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled) }
            if let error = maintenance.backupError { Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled) }
            Button(model.display.localized("状態を再読込")) { Task { await maintenance.refreshBackupInfo(app: model) } }
                .inkuTooltip(model.display.tooltip("自動バックアップの状態と保存済みファイルの情報を読み直します。バックアップは作成しません。"))
        }.inkuFont(13).task { await maintenance.refreshBackupInfo(app: model) }
    }
    private var clipboard: some View {
        @Bindable var display = model.display
        return Group {
            Section(display.webCopy("clipboardFormatLabel", "形式")) {
            Picker(display.webCopy("clipboardFormatLabel", "形式"), selection: Binding(get: { display.preferences.clipboardFormat ?? "image" },
                  set: { display.preferences.clipboardFormat = $0 })) {
                Text(display.webCopy("clipboardFormatImage", "画像だけ")).tag("image")
                Text(display.webCopy("clipboardFormatCard", "カード形式")).tag("card")
            }.labelsHidden()
            #if os(macOS)
            .pickerStyle(.radioGroup)
            #endif
            if display.preferences.clipboardFormat == "card" {
                Text(display.webCopy("clipboardFormatCardNote", "カードの形と印は、「エクスポート」の共有カードの設定を使います。カード形式は保存した作品だけコピーできます。"))
                    .inkuFont(13).foregroundStyle(.secondary)
            }
            }
            Section(display.webCopy("clipboardHeightLabel", "画像の高さ（px）")) {
            Text(display.webCopy("clipboardHeightDescription", "256〜4096。幅は作品やカードの形に合わせて決まります。"))
                .inkuFont(13).foregroundStyle(.secondary)
            HStack(spacing: 6) {
                Button { stepClipboardHeight(by: -64) } label: { Image(systemName: "minus") }
                    .accessibilityLabel(display.label("高さを減らす", "Decrease height"))
                TextField(display.webCopy("clipboardHeightLabel", "画像の高さ（px）"), value: Binding(
                    get: { display.preferences.clipboardHeight },
                    set: { display.preferences.clipboardHeight = min(4096, max(256, $0)) }), format: .number)
                    .labelsHidden().textFieldStyle(.roundedBorder).multilineTextAlignment(.trailing).frame(width: 90)
                Button { stepClipboardHeight(by: 64) } label: { Image(systemName: "plus") }
                    .accessibilityLabel(display.label("高さを増やす", "Increase height"))
                Spacer()
            }.buttonStyle(.borderless)
            }
            preferenceSaveError
        }
    }
    private func membership(_ item: String, in selection: Binding<Set<String>>, maximum: Int = .max) -> Binding<Bool> {
        Binding(get: { selection.wrappedValue.contains(item) }, set: { enabled in
            var next = selection.wrappedValue
            if enabled && next.count < maximum { next.insert(item) } else if !enabled { next.remove(item) }
            selection.wrappedValue = next
        })
    }
}
