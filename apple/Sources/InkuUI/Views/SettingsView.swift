import InkuHost
import SwiftUI

enum SettingsSection: String, CaseIterable, Identifiable {
    case display, making, demo, models, personalPlan, database, export, clipboard, plugins, unread, limits
    #if !os(macOS)
    case about
    #endif
    var id: String { rawValue }
    var title: String {
        switch self {
        case .display: "表示と操作"; case .making: "制作"; case .models: "モデル設定"
        case .demo: "デモ"
        case .personalPlan: "Personal ChatGPT"
        case .database: "DB設定"; case .clipboard: "クリップボード"; case .plugins: "プラグイン・歳時記"
        case .export: "エクスポート"
        case .unread: "未読語台帳"
        case .limits: "制限値"
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
            (model.display.localized(SettingsSection.personalPlan.title), [.personalPlan]),
            (model.display.webCopy("settingsTabExport", "エクスポート"), [.export, .clipboard]),
            (model.display.webCopy("settingsCategoryAdministration", "接続と管理"), [.models, .database] + (detailed ? [.limits] : [])),
        ]
        if detailed { result.append((model.display.webCopy("settingsCategoryExtensions", "拡張と詳細"), [.plugins, .unread])) }
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
            Text(model.display.localized(item.title))
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
        #if !os(macOS)
        case .about: ""
        #endif
        }
    }

    /// settings-modal.css `.settings-page-heading`: 20px title over a 13px hint, padding 22/24/18.
    private var pageHeading: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(model.display.localized(section.title)).inkuFont(20, weight: .semibold)
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
                case .demo: EmptyView()
                case .models: EmptyView()
                case .personalPlan:
                    ChatGPTPlanSettingsView(model: model).disabled(model.isBusy || automation.isOccupied)
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
        @Bindable var display = model.display
        return Group {
            Section(model.display.localized("表示")) {
                Picker(model.display.localized("テーマ"), selection: $display.preferences.theme) {
                    Text(model.display.localized("システム")).tag("system"); Text(model.display.localized("ライト")).tag("light"); Text(model.display.localized("ダーク")).tag("dark")
                }
                Picker(model.display.localized("表示言語"), selection: $display.preferences.language) { Text(model.display.localized("日本語")).tag("ja"); Text("English").tag("en") }
                HStack {
                    Text(model.display.localized("文字サイズ"))
                    Slider(value: Binding(get: { Double(display.preferences.textSizeStep) }, set: { display.previewTextSize(Int($0)) }),
                           in: 0...4, step: 1, onEditingChanged: { editing in if !editing { display.saveTextSize() } })
                    Text("\(Int(display.preferences.textScale * 100))%").monospacedDigit().frame(width: 48)
                    Button(model.display.localized("リセット")) { display.resetTextSize() }
                }
                Picker(model.display.localized("UIモード"), selection: $display.preferences.uiMode) {
                    Text(model.display.localized("シンプル")).tag("simple"); Text(model.display.localized("カスタム")).tag("custom"); Text(model.display.localized("フル")).tag("full")
                }
                if display.preferences.uiMode == "custom" {
                    ForEach([("input_modes", "入力の切り替え"), ("drawing_settings", "描画条件"), ("ddl_tools", "指示書の操作"),
                             ("detail_status", "指示書と生成情報"), ("work_tools", "作品の操作"), ("history", "履歴"), ("auxiliary", "付帯文")], id: \.0) { feature in
                        Toggle(display.localized(feature.1), isOn: Binding(get: { display.visible(feature.0) }, set: { enabled in
                            var next = display.preferences.customFeatures
                            let legacy = ["detail_status": "diagnostics", "input_modes": "automation", "auxiliary": "saijiki"]
                            if let alias = legacy[feature.0] { next.remove(alias) }
                            if enabled { next.insert(feature.0) } else { next.remove(feature.0) }
                            display.preferences.customFeatures = next
                        }))
                    }
                }
                Toggle(model.display.localized("ツールチップ"), isOn: $display.preferences.showTooltips)
            }
            DescriptionMeterSettingsView(meter: model.descriptionMeter)
            Section(model.display.localized("詞書き")) {
                Toggle(model.display.localized("作品に詞書きを表示"), isOn: $display.preferences.captionVisible)
                Toggle(model.display.localized("縦書き"), isOn: $display.preferences.captionVertical)
                Picker(model.display.localized("表示位置"), selection: $display.preferences.captionPosition) { Text(model.display.localized("左")).tag("left"); Text(model.display.localized("右")).tag("right") }
            }
            Section(model.display.localized("履歴と生成情報")) {
                ForEach([("generation", "世代"), ("model", "モデル"), ("engine", "描画版"), ("size", "ファイル容量")], id: \.0) { field in
                    Toggle(display.localized(field.1), isOn: membership(field.0, in: $display.preferences.historyFields, maximum: 3))
                        .disabled(!display.preferences.historyFields.contains(field.0) && display.preferences.historyFields.count >= 3)
                }
                Toggle(model.display.localized("作品を切り替えても生成情報を開いたままにする"), isOn: $display.preferences.keepGenerationInfo)
                Picker(model.display.localized("描画中のマスコット"), selection: $display.preferences.mascot) { Text(model.display.localized("Incu（立方体）")).tag("incu"); Text(model.display.localized("Yuragi（蟹）")).tag("yuragi") }
            }
            if let error = display.saveError {
                Text(display.message(error)).foregroundStyle(.red).textSelection(.enabled)
                Button(model.display.localized("もう一度保存")) { display.retrySave() }
            }
        }
    }
    private var making: some View {
        @Bindable var display = model.display
        return Group {
            Section(model.display.localized("バッチの再試行")) {
                Stepper(display.localizedFormat("失敗行の再試行: %ld回", display.preferences.batchRetries), value: $display.preferences.batchRetries, in: 0...5)
                Text(model.display.localized("一巡したあと失敗した行だけを再試行します。0なら再試行せず、中断したときも再試行しません。"))
                    .inkuFont(13).foregroundStyle(.secondary)
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
                Stepper(display.localizedFormat("間隔: %ld時間", display.preferences.backupIntervalHours), value: $display.preferences.backupIntervalHours, in: 1...168)
                Stepper(display.localizedFormat("保持: %ld世代", display.preferences.backupGenerations), value: $display.preferences.backupGenerations, in: 1...30)
                Text(model.display.localized("アプリの起動中に実行し、生成中・復元中は待ちます。"))
                    .inkuFont(13).foregroundStyle(.secondary)
                backupInformation
            }
            #endif
        }
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
                .help(model.display.tooltip("自動バックアップの状態と保存済みファイルの情報を読み直します。バックアップは作成しません。"))
        }.inkuFont(13).task { await maintenance.refreshBackupInfo(app: model) }
    }
    private var clipboard: some View {
        @Bindable var display = model.display
        return Section(model.display.localized("画像コピー")) {
            Picker(model.display.localized("形式"), selection: Binding(get: { display.preferences.clipboardFormat ?? "image" },
                  set: { display.preferences.clipboardFormat = $0 })) {
                Text(model.display.localized("画像")).tag("image")
                Text(model.display.localized("カード")).tag("card")
            }
            Stepper(display.localizedFormat("Y軸の高さ: %ld px", display.preferences.clipboardHeight),
                    value: $display.preferences.clipboardHeight, in: 256...4096, step: 64)
            Text(model.display.localized("表示中作品の保存SVGから画像を作り、OSのクリップボードへコピーします。"))
                .inkuFont(13).foregroundStyle(.secondary)
            Text(model.display.localized("カードは保存済みの作品に使えます。カードのレイアウトと印はエクスポート設定に従います。"))
                .inkuFont(12).foregroundStyle(.secondary)
            if let error = display.saveError {
                Text(display.message(error)).foregroundStyle(.red).textSelection(.enabled)
                Button(model.display.localized("もう一度保存")) { display.retrySave() }
            }
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
