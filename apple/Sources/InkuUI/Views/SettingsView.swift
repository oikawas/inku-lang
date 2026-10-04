import InkuHost
import SwiftUI

enum SettingsSection: String, CaseIterable, Identifiable {
    case display, making, models, personalPlan, database, export, clipboard, plugins, unread, limits, about
    var id: String { rawValue }
    var title: String {
        switch self {
        case .display: "表示と操作"; case .making: "制作"; case .models: "モデル設定"
        case .personalPlan: "Personal ChatGPT"
        case .database: "DB設定"; case .clipboard: "クリップボード"; case .plugins: "プラグイン・歳時記"
        case .export: "エクスポート"
        case .unread: "未読語台帳"
        case .limits: "制限値"; case .about: "inkuについて"
        }
    }
    var symbol: String {
        switch self {
        case .display: "slider.horizontal.3"; case .making: "paintbrush.pointed"
        case .models: "cpu"; case .personalPlan: "person.crop.circle"
        case .database: "externaldrive"; case .export: "square.and.arrow.up"
        case .clipboard: "doc.on.clipboard"; case .plugins: "puzzlepiece.extension"
        case .unread: "text.magnifyingglass"; case .limits: "gauge.with.dots.needle.33percent"
        case .about: "info.circle"
        }
    }
}

@MainActor struct SettingsView: View {
    @Bindable var model: AppModel
    @State private var settings = SettingsModel()
    @Binding var section: SettingsSection
    @State private var confirmRestore = false
    @State private var confirmClearKey = false
    @State private var rateHelp: String?

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            List(SettingsSection.allCases, selection: $section) { item in
                Label(model.display.localized(item.title), systemImage: item.symbol).tag(item)
            }.listStyle(.sidebar).frame(width: 190)
            Divider()
            Form {
                switch section {
                case .display: appearance
                case .making: making
                case .models: providers
                case .personalPlan: ChatGPTPlanSettingsView(model: model)
                case .database: database
                case .export: ExportSettingsView(model: model)
                case .clipboard: clipboard
                case .plugins:
                    PluginSettingsView(model: model)
                    Section(model.display.localized("歳時記")) { SaijikiView(model: model).frame(minHeight: 480) }
                case .unread: Section { UnreadWordsView(model: model) }
                case .limits: OperationalLimitsView(model: model)
                case .about: about
                }
            }.formStyle(.grouped).frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .task(id: section) { await settings.load(model: model) }
        .onDisappear { settings.cancelDiscovery() }
        .alert(model.display.localized("設定を変更できませんでした"), isPresented: Binding(get: { settings.error != nil }, set: { if !$0 { settings.error = nil } })) {
            Button(model.display.localized("閉じる"), role: .cancel) { settings.error = nil }
        } message: {
            Text(model.display.localized(settings.error ?? ""))
        }
        .confirmationDialog(model.display.localized("現在の保存データを置き換えます"), isPresented: $confirmRestore, titleVisibility: .visible) {
            #if os(macOS)
            Button(model.display.localized("復元するバックアップを選択…"), role: .destructive) {
                if let url = NativeFilePanels.restore(language: model.display.preferences.language) { Task { await model.restore(from: url) } }
            }
            #endif
            Button(model.display.localized("キャンセル"), role: .cancel) {}
        } message: { Text(model.display.localized("現在のデータを残す場合は、先にバックアップを保存してください。")) }
        .confirmationDialog(model.display.localized("この接続のAPIキーを削除します"), isPresented: $confirmClearKey, titleVisibility: .visible) {
            Button(model.display.localized("APIキーを削除"), role: .destructive) { Task { await settings.clearCredential() } }
            Button(model.display.localized("キャンセル"), role: .cancel) {}
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
                Picker(model.display.localized("文字サイズ"), selection: $display.preferences.textSizeStep) {
                    ForEach(0..<5) { step in Text("\(Int([0.9, 1, 1.1, 1.2, 1.3][step] * 100))%").tag(step) }
                }
                Picker(model.display.localized("UIモード"), selection: $display.preferences.uiMode) {
                    Text(model.display.localized("シンプル")).tag("simple"); Text(model.display.localized("カスタム")).tag("custom"); Text(model.display.localized("フル")).tag("full")
                }
                if display.preferences.uiMode == "custom" {
                    ForEach([("history", "履歴"), ("diagnostics", "指示書と生成情報"), ("automation", "バッチ・デモ"), ("saijiki", "歳時記")], id: \.0) { feature in
                        Toggle(display.localized(feature.1), isOn: membership(feature.0, in: $display.preferences.customFeatures))
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
            if let error = display.saveError { Text(display.message(error)).foregroundStyle(.red) }
        }
    }
    private var making: some View {
        @Bindable var display = model.display
        return Group {
            Section(model.display.localized("バッチの再試行")) {
                Stepper(display.localizedFormat("失敗行の再試行: %ld回", display.preferences.batchRetries), value: $display.preferences.batchRetries, in: 0...5)
                Text(model.display.localized("一巡したあと失敗した行だけを再試行します。0なら再試行せず、中断したときも再試行しません。"))
                    .font(.callout).foregroundStyle(.secondary)
            }
            Section(model.display.localized("結果ログ")) {
                Toggle(model.display.localized("生成結果のログを保存"), isOn: $display.preferences.saveResultLog)
                Text(model.display.localized("指示書・Score・生成情報を端末内へ記録します。APIキーは記録しません。"))
                    .font(.callout).foregroundStyle(.secondary)
            }
            if model.developerModeEnabled {
                Section(model.display.localized("開発用の応答記録")) {
                    Toggle(model.display.localized("生成時の送受信を記録"), isOn: Binding(
                        get: { display.preferences.captureProviderIO == true },
                        set: { display.preferences.captureProviderIO = $0 }))
                        .disabled(model.isBusy)
                    Text(model.display.localized("モデルへ送った本文と受け取った応答を端末内に保存します。接続先・ヘッダー・認証情報は記録しません。"))
                        .font(.callout).foregroundStyle(.secondary)
                }
            }
        }
    }
    private var providers: some View {
        @Bindable var state = settings
        let availableModels = state.selectedProvider.map { state.availableModels(for: $0) } ?? []
        return Group {
            Section(model.display.localized("AIサービス接続")) {
                Picker(model.display.localized("サービス"), selection: $state.selectedProviderID) {
                    Text(model.display.localized("選択してください")).tag(String?.none)
                    ForEach(state.host.providers.filter { $0.kind != .chatGPTPlan }) { provider in Text(provider.displayName).tag(Optional(provider.id)) }
                }.onChange(of: state.selectedProviderID) { _, _ in Task { await state.inspectCredential() } }
                HStack {
                    Button(model.display.localized("サービス追加")) { state.addProvider() }
                    Button(model.display.localized("削除"), role: .destructive) { state.removeProvider() }.disabled(state.selectedProvider == nil)
                }
                if let index = state.providerIndex {
                    Text(model.display.localizedFormat("サービスID: %@", state.host.providers[index].id)).font(.caption).foregroundStyle(.secondary)
                    Picker(model.display.localized("接続方式"), selection: $state.host.providers[index].kind) {
                        Text(model.display.localized("OpenAI互換 / Ollama / MLX")).tag(ProviderKind.openAICompatible)
                        Text("Claude API").tag(ProviderKind.anthropic); Text("Gemini API").tag(ProviderKind.gemini)
                    }
                    TextField(model.display.localized("接続先URL"), text: Binding(get: { state.host.providers[index].baseURL.absoluteString }, set: { if let url = URL(string: $0) { state.host.providers[index].baseURL = url } }))
                        .autocorrectionDisabled()
                    if state.host.providers[index].kind == .openAICompatible {
                        Toggle("MLX JSON schema profile", isOn: Binding(get: { state.host.providers[index].apiProfile == "mlx" }, set: { state.host.providers[index].apiProfile = $0 ? "mlx" : nil }))
                    }
                    Toggle(model.display.localized("APIキーを使用"), isOn: $state.host.providers[index].requiresAPIKey)
                    SecureField(model.display.localized(state.credentialConfigured ? "APIキーを更新（設定済み）" : "APIキー"), text: $state.credentialDraft)
                    if state.credentialConfigured { Button(model.display.localized("APIキーを削除…"), role: .destructive) { confirmClearKey = true } }
                    DisclosureGroup(model.display.localized("レート制限")) {
                        limitField("毎分の要求数（RPM）", help: "このアプリが同じ接続先へ送る要求数です。写生文・解釈・辞書選択・構図・補完・再試行を含みます。0は上限なしです。", index: index, key: \.requestsPerMinute)
                        limitField("毎分の入力トークン数（TPM）", help: "指示・記述・応答の型を含む入力の上限です。Geminiは送る前に計測し、ほかの接続先は安全側に見積もります。0は上限なしです。", index: index, key: \.tokensPerMinute)
                        limitField("日次の要求数（RPD）", help: "再試行を含む1日当たりの要求数です。Geminiは太平洋時間、ほかの接続先はUTCの0時にリセットします。0は上限なしです。", index: index, key: \.requestsPerDay)
                        Text(model.display.localized("0は上限なし。毎分の枠を待ち、日次上限では生成を開始しません。"))
                            .font(.caption).foregroundStyle(.secondary)
                        Text(model.display.localized("未設定の標準Gemini接続は30／16,000／14,400、ほかの接続先は0が初期値です。契約の利用枠に合わせて設定してください。"))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Section(model.display.localized("描画モデル")) {
                TextField(model.display.localized("サービスID:モデルID"), text: $state.host.models.stage1Model).autocorrectionDisabled()
                Button(model.display.localized(state.isLoadingModels ? "取得中…" : "接続先からモデル一覧を取得")) { Task { await state.discoverModels() } }
                    .disabled(state.selectedProvider == nil || state.isLoadingModels)
                if !availableModels.isEmpty {
                    Picker(model.display.localized("モデル"), selection: $state.host.models.stage1Model) {
                        Text(model.display.localized("選択してください")).tag("")
                        if !state.host.models.stage1Model.isEmpty, !availableModels.contains(where: { $0.id == state.host.models.stage1Model }) {
                            Text(state.host.models.stage1Model).tag(state.host.models.stage1Model)
                        }
                        ForEach(availableModels) { item in Text(item.name).tag(item.id) }
                    }
                }
                if !state.host.models.stage1Model.isEmpty {
                    ModelGuidanceView(reference: state.host.models.stage1Model, providers: state.host.providers,
                                      discovered: state.modelCatalog.first { $0.id == state.host.models.stage1Model }, display: model.display)
                }
                Stepper(model.display.localizedFormat("解釈の出力上限: %ld", state.host.models.stage1MaxTokens), value: $state.host.models.stage1MaxTokens, in: 256...65536, step: 256)
                Stepper(model.display.localizedFormat("補完の出力上限: %ld", state.host.models.holeMaxTokens), value: $state.host.models.holeMaxTokens, in: 256...65536, step: 256)
                Text(model.display.localized("解釈と構造化に同じモデルを使います。接続設定の保存では生成を開始しません。"))
                    .font(.callout).foregroundStyle(.secondary)
                Button(model.display.localized("接続設定を保存")) {
                    state.host.models.stage2Model = state.host.models.stage1Model
                    Task { await state.save(model: model) }
                }.disabled(model.isBusy)
                if !state.status.isEmpty { Text(model.display.message(state.status)).foregroundStyle(.secondary) }
            }
        }
    }
    private var database: some View {
        @Bindable var display = model.display
        return Group {
            #if os(macOS)
            Section(model.display.localized("保存データ")) {
                if let directory = model.localDataDirectory() { Text(directory.path).font(.caption).textSelection(.enabled) }
                Button(model.display.localized("バックアップを保存…")) { if let url = NativeFilePanels.backup(language: model.display.preferences.language) { Task { await model.backup(to: url) } } }
                Button(model.display.localized("バックアップから復元…")) { confirmRestore = true }
                Text(model.display.localized("作品・系譜・作業状態をSQLiteへ保存します。接続設定とKeychainのAPIキーは別です。"))
                    .font(.callout).foregroundStyle(.secondary)
            }.disabled(model.isBusy)
            Section(model.display.localized("自動バックアップ")) {
                Toggle(model.display.localized("自動バックアップ"), isOn: $display.preferences.automaticBackup)
                Stepper(display.localizedFormat("間隔: %ld時間", display.preferences.backupIntervalHours), value: $display.preferences.backupIntervalHours, in: 1...168)
                Stepper(display.localizedFormat("保持: %ld世代", display.preferences.backupGenerations), value: $display.preferences.backupGenerations, in: 1...30)
                Text(model.display.localized("アプリの起動中に実行し、生成中・復元中は待ちます。"))
                    .font(.callout).foregroundStyle(.secondary)
            }
            #endif
        }
    }
    private var clipboard: some View {
        @Bindable var display = model.display
        return Section(model.display.localized("画像コピー")) {
            Picker(model.display.localized("Y軸の高さ"), selection: $display.preferences.clipboardHeight) {
                Text("1080 px").tag(1080); Text("2160 px").tag(2160); Text("4320 px").tag(4320)
            }
            Text(model.display.localized("表示中作品の保存SVGから画像を作り、OSのクリップボードへコピーします。"))
                .font(.callout).foregroundStyle(.secondary)
        }
    }
    private var about: some View {
        AboutInkuView(model: model)
    }
    private func membership(_ item: String, in selection: Binding<Set<String>>, maximum: Int = .max) -> Binding<Bool> {
        Binding(get: { selection.wrappedValue.contains(item) }, set: { enabled in
            var next = selection.wrappedValue
            if enabled && next.count < maximum { next.insert(item) } else if !enabled { next.remove(item) }
            selection.wrappedValue = next
        })
    }
    private func limitField(_ title: String, help: String, index: Int,
                            key: WritableKeyPath<ProviderRateLimits, Int?>) -> some View {
        let providerID = settings.host.providers[index].id
        return HStack {
            HStack(spacing: 6) {
                Text(model.display.localized(title))
                Button { rateHelp = title } label: { Image(systemName: "info.circle") }
                    .buttonStyle(.plain).foregroundStyle(.secondary)
                    .accessibilityLabel(model.display.localizedFormat("%@の説明", model.display.localized(title)))
                    .help(model.display.preferences.showTooltips ? model.display.localized(help) : "")
                    .popover(isPresented: Binding(get: { rateHelp == title }, set: { if !$0 { rateHelp = nil } })) {
                        Text(model.display.localized(help)).font(.callout).padding()
                            .frame(maxWidth: 320).fixedSize(horizontal: false, vertical: true)
                    }
            }
            Spacer(minLength: 16)
            TextField(model.display.localized(title), value: Binding(get: {
                guard settings.host.providers.indices.contains(index),
                      settings.host.providers[index].id == providerID else { return 0 }
                let provider = settings.host.providers[index]
                return (provider.rateLimits ?? ProviderRateLimits.defaults(providerID: provider.id))[keyPath: key] ?? 0
            }, set: { value in
                guard settings.host.providers.indices.contains(index),
                      settings.host.providers[index].id == providerID else { return }
                let provider = settings.host.providers[index]
                var limits = provider.rateLimits ?? ProviderRateLimits.defaults(providerID: provider.id)
                limits[keyPath: key] = value
                settings.host.providers[index].rateLimits = limits
            }), format: .number)
            .labelsHidden().multilineTextAlignment(.trailing).frame(maxWidth: 180)
            .accessibilityLabel(model.display.localized(title))
            .accessibilityHint(model.display.localized(help))
        }
    }
}
