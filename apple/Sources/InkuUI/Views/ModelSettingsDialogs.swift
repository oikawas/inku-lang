import InkuHost
import SwiftUI

enum ProviderServiceEditorMode: Identifiable {
    case add
    case rename(String)
    case memo(String)

    var id: String {
        switch self {
        case .add: "add"
        case .rename(let id): "rename:" + id
        case .memo(let id): "memo:" + id
        }
    }

    fileprivate var providerID: String? {
        switch self {
        case .add: nil
        case .rename(let id), .memo(let id): id
        }
    }
}

private enum NewProviderConnection: String, CaseIterable, Identifiable {
    case openAICompatible, mlx, anthropic, gemini
    var id: String { rawValue }
    var kind: ProviderKind {
        switch self {
        case .openAICompatible, .mlx: .openAICompatible
        case .anthropic: .anthropic
        case .gemini: .gemini
        }
    }
    var apiProfile: String? { self == .mlx ? "mlx" : nil }
}

@MainActor
struct ProviderServiceEditorSheet: View {
    let mode: ProviderServiceEditorMode
    @Bindable var model: AppModel
    @Bindable var settings: SettingsModel
    @Environment(\.dismiss) private var dismiss
    @State private var serviceID: String
    @State private var serviceName: String
    @State private var memo: String
    @State private var connection: NewProviderConnection = .openAICompatible
    @State private var baseURL = ""
    @State private var apiKey = ""
    @State private var isSaving = false
    @State private var errorMessage: String?

    init(mode: ProviderServiceEditorMode, model: AppModel, settings: SettingsModel) {
        self.mode = mode
        self.model = model
        self.settings = settings
        let provider = settings.host.providers.first { $0.id == mode.providerID }
        _serviceID = State(initialValue: mode.providerID ?? "")
        _serviceName = State(initialValue: provider?.displayName ?? "")
        _memo = State(initialValue: provider?.memo ?? "")
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(title).font(.title2.weight(.semibold))
                Spacer()
                Button { cancel() } label: { Image(systemName: "xmark") }
                    .buttonStyle(.plain)
                    .accessibilityLabel(model.display.localized("閉じる"))
                    .disabled(isSaving)
            }.padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    switch mode {
                    case .add: addFields
                    case .rename: renameFields
                    case .memo: memoFields
                    }
                }.padding(20)
            }
            .disabled(isSaving)
            Divider()
            HStack(spacing: 12) {
                if let errorMessage {
                    Text(model.display.localized(errorMessage)).font(.caption).foregroundStyle(.red).lineLimit(3)
                }
                Spacer()
                if isSaving { ProgressView().controlSize(.small) }
                Button(model.display.localized("取消")) { cancel() }
                    .keyboardShortcut(.cancelAction)
                    .disabled(isSaving)
                Button(model.display.localized(isAdding ? "追加" : "保存")) { Task { await save() } }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .disabled(!canSave)
            }.padding(16)
        }
        .frame(minWidth: 500, idealWidth: 600, minHeight: 360, idealHeight: isAdding ? 490 : 380)
        .interactiveDismissDisabled(isSaving)
        .onDisappear { apiKey = "" }
    }

    private var isAdding: Bool { if case .add = mode { true } else { false } }
    private var title: String {
        switch mode {
        case .add: model.display.localized("AIサービスを追加")
        case .rename: model.display.localized("AIサービス名を編集")
        case .memo: model.display.localizedFormat("%@ のメモ", serviceName)
        }
    }

    private var addFields: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 16) {
                field("サービスID") {
                    TextField("my-openai", text: $serviceID).autocorrectionDisabled()
                    if !serviceID.isEmpty, let issue = serviceIDIssue {
                        Text(model.display.localized(issue)).font(.caption).foregroundStyle(.red)
                    }
                }
                field("サービス名") {
                    TextField(model.display.localized("表示名（空欄ならサービスID）"), text: $serviceName)
                }
            }
            Text(model.display.localized("サービスIDは変更できません。英数字・ハイフン・アンダースコアで短い名前を付けてください。"))
                .font(.caption).foregroundStyle(.secondary)
            field("接続形式") {
                Picker(model.display.localized("接続形式"), selection: $connection) {
                    Text(model.display.localized("OpenAI互換")).tag(NewProviderConnection.openAICompatible)
                    Text("MLX (mlx-vlm)").tag(NewProviderConnection.mlx)
                    Text("Claude API").tag(NewProviderConnection.anthropic)
                    Text("Gemini API").tag(NewProviderConnection.gemini)
                }.labelsHidden()
            }
            field("接続先URL") {
                TextField("http://127.0.0.1:11434/v1", text: $baseURL).autocorrectionDisabled()
                if !baseURL.isEmpty, !validURL {
                    Text(model.display.localized("接続先URLには http または https のURLを入力してください。"))
                        .font(.caption).foregroundStyle(.red)
                }
            }
            field("APIキー（任意）") {
                SecureField(model.display.localized("新しいAPIキー"), text: $apiKey).autocorrectionDisabled()
                Text(model.display.localized("ローカルLLMはAPIキー無しで利用できる場合があります。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var renameFields: some View {
        VStack(alignment: .leading, spacing: 16) {
            field("サービスID") {
                Text(serviceID).font(.system(.body, design: .monospaced)).textSelection(.enabled)
            }
            field("サービス名") { TextField(model.display.localized("サービス名"), text: $serviceName) }
        }
    }

    private var memoFields: some View {
        field("メモ") {
            TextEditor(text: $memo).frame(minHeight: 200)
                .scrollContentBackground(.hidden).padding(6)
                .background(.background, in: RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(.secondary.opacity(0.25)))
                .accessibilityLabel(model.display.localized("メモ"))
            Text(model.display.localized("契約状況、支払い元、利用上限、連絡先、運用注意などを記録"))
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func field<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(model.display.localized(label)).font(.caption.weight(.medium)).foregroundStyle(.secondary)
            content()
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private var normalizedID: String { serviceID.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
    private var serviceIDIssue: String? {
        guard !normalizedID.isEmpty,
              normalizedID.range(of: "^[a-z0-9_-]+$", options: .regularExpression) != nil
        else { return "サービスIDには英数字・ハイフン・アンダースコアを使ってください。" }
        guard normalizedID != "chatgpt" else { return "このサービスIDは予約されています。" }
        return settings.host.providers.contains { $0.id == normalizedID } ? "同じサービスIDが登録されています。" : nil
    }
    private var validURL: Bool {
        guard let url = URL(string: baseURL.trimmingCharacters(in: .whitespacesAndNewlines)) else { return false }
        let provider = ProviderSettings(id: "service", kind: connection.kind, baseURL: url,
                                        apiProfile: connection.apiProfile, requiresAPIKey: false)
        return (try? provider.validate()) != nil
    }
    private var canSave: Bool {
        guard !isSaving, !model.isBusy, !settings.isLoadingModels else { return false }
        switch mode {
        case .add: return serviceIDIssue == nil && validURL
        case .rename: return !serviceName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && settings.host.providers.contains { $0.id == serviceID }
        case .memo: return settings.host.providers.contains { $0.id == serviceID }
        }
    }

    private func cancel() {
        guard !isSaving else { return }
        apiKey = ""
        dismiss()
    }

    private func save() async {
        guard canSave else { return }
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }
        do {
            switch mode {
            case .add:
                try await settings.addProvider(id: normalizedID, label: serviceName, kind: connection.kind,
                    baseURL: baseURL.trimmingCharacters(in: .whitespacesAndNewlines),
                    apiProfile: connection.apiProfile, apiKey: apiKey, model: model)
            case .rename(let providerID):
                try await settings.saveProviderLabel(providerID: providerID, label: serviceName, model: model)
            case .memo(let providerID):
                try await settings.saveProviderMemo(providerID: providerID, memo: memo, model: model)
            }
            apiKey = ""
            dismiss()
        } catch {
            // Credential failures must not echo input or arbitrary error payloads.
            switch (error as? HostError)?.code {
            case "duplicate_provider": errorMessage = "同じサービスIDが登録されています。"
            case "provider_id_invalid":
                errorMessage = "サービスIDには英数字・ハイフン・アンダースコアを使ってください。"
            case "personal_plan_provider_settings_required": errorMessage = "このサービスIDは予約されています。"
            case "provider_base_url_invalid": errorMessage = "接続先URLには http または https のURLを入力してください。"
            case "credentials_write_failed": errorMessage = "APIキーを保存できませんでした。"
            default:
                switch mode {
                case .add: errorMessage = "サービスを追加できませんでした。"
                case .rename: errorMessage = "サービス名を保存できませんでした。"
                case .memo: errorMessage = "メモを保存できませんでした。"
                }
            }
        }
    }
}

@MainActor
struct ProviderModelsSheet: View {
    let providerID: String
    @Bindable var model: AppModel
    @Bindable var settings: SettingsModel
    @Environment(\.dismiss) private var dismiss
    @State private var draft: ProviderModelsDraft
    @State private var search = ""
    @State private var filter: ProviderModelFilter = .all
    @State private var isSaving = false
    @State private var isFetching = false
    @State private var errorMessage: String?
    @State private var statusMessage: String?

    init(providerID: String, model: AppModel, settings: SettingsModel) {
        self.providerID = providerID
        self.model = model
        self.settings = settings
        let provider = settings.host.providers.first { $0.id == providerID }
        _draft = State(initialValue: ProviderModelsDraft(
            models: provider.map { settings.catalogModels(for: $0) } ?? [],
            enabled: provider?.enabledModels ?? [:]))
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            toolbar
            Divider()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if visibleModels.isEmpty {
                        Text(model.display.localized("該当するモデルがありません。"))
                            .foregroundStyle(.secondary).frame(maxWidth: .infinity).padding(32)
                    }
                    ForEach(visibleModels) { item in modelRow(item) }
                }.padding(16)
            }
            .disabled(isWorking)
            Divider()
            footer
        }
        .frame(minWidth: 690, idealWidth: 840, minHeight: 500, idealHeight: 680)
        .interactiveDismissDisabled(isWorking)
    }

    private var provider: ProviderSettings? { settings.host.providers.first { $0.id == providerID } }
    private var visibleModels: [ProviderModelSettings] { draft.filteredModels(search: search, filter: filter) }
    private var isWorking: Bool { isSaving || isFetching }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(model.display.localizedFormat("%@ の使用モデル選択", provider?.displayName ?? providerID))
                    .font(.title2.weight(.semibold))
                Text(model.display.localizedFormat("サービスID: %@", providerID)).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Button { cancel() } label: { Image(systemName: "xmark") }
                .buttonStyle(.plain).accessibilityLabel(model.display.localized("閉じる"))
                .disabled(isWorking)
        }.padding(20)
    }

    private var toolbar: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField(model.display.localized("モデルを検索"), text: $search).autocorrectionDisabled()
                        .textFieldStyle(.plain)
                }.padding(8)
                    .background(.background, in: RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(.secondary.opacity(0.25)))
                Picker(model.display.localized("絞り込み"), selection: $filter) {
                    Text(model.display.localized("すべて")).tag(ProviderModelFilter.all)
                    Text(model.display.localized("使用中")).tag(ProviderModelFilter.enabled)
                    Text(model.display.localized("不使用")).tag(ProviderModelFilter.disabled)
                    Text(model.display.localized("LLM 用")).tag(ProviderModelFilter.llm)
                    Text(model.display.localized("Vision 用")).tag(ProviderModelFilter.vision)
                }.frame(width: 200)
            }
            HStack(spacing: 10) {
                Button(model.display.localized(isFetching ? "取得中…" : "モデルリスト取得")) { Task { await fetch() } }
                    .disabled(isWorking || model.isBusy || settings.isLoadingModels || draft.isDirty || provider == nil)
                    .help(draft.isDirty ? model.display.localized("未保存の変更を保存または取り消してからモデルリストを取得してください。") : "")
                Button(model.display.localized("表示中を全て使用")) { draft.setVisible(models: visibleModels, enabled: true) }
                    .disabled(isWorking || visibleModels.isEmpty)
                Button(model.display.localized("表示中を全て解除")) { draft.setVisible(models: visibleModels, enabled: false) }
                    .disabled(isWorking || visibleModels.isEmpty)
                Spacer()
                Text(model.display.localizedFormat("%ld / %ld モデルを表示", visibleModels.count, draft.models.count))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.padding(16)
    }

    private func modelRow(_ item: ProviderModelSettings) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                enabledToggle(item)
                VStack(alignment: .leading, spacing: 3) {
                    Text(item.label).font(.body.weight(.semibold))
                    Text(item.id).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
                        .textSelection(.enabled)
                    if let status = statusLabel(item) { Text(status).font(.caption).foregroundStyle(.orange) }
                }.frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 6) {
                    purposeButton("LLM", purpose: "llm", item: item)
                    purposeButton("Vision", purpose: "vision", item: item)
                }
            }
            DisclosureGroup(model.display.localized("モデル詳細")) { metadataFields(item) }
                .font(.callout)
        }.padding(14)
            .background(.background, in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(.secondary.opacity(0.18)))
    }

    @ViewBuilder
    private func enabledToggle(_ item: ProviderModelSettings) -> some View {
        let toggle = Toggle(model.display.localizedFormat("使用: %@", item.label), isOn: Binding(
            get: { draft.isEnabled(modelID: item.id) },
            set: { draft.setEnabled(modelID: item.id, enabled: $0) }))
            .labelsHidden().disabled(!item.isSelectable)
        #if os(macOS)
        toggle.toggleStyle(.checkbox)
        #else
        toggle.toggleStyle(.switch).fixedSize()
        #endif
    }

    private func purposeButton(_ label: String, purpose: String, item: ProviderModelSettings) -> some View {
        let selected = item.purposes.contains(purpose)
        return Button(label) { draft.togglePurpose(modelID: item.id, purpose: purpose) }
            .buttonStyle(.plain)
            .font(.caption.weight(.medium))
            .padding(.horizontal, 10).padding(.vertical, 5)
            .foregroundStyle(selected ? Color.accentColor : Color.secondary)
            .background(selected ? Color.accentColor.opacity(0.14) : Color.secondary.opacity(0.08), in: Capsule())
            .overlay(Capsule().stroke(selected ? Color.accentColor.opacity(0.4) : Color.secondary.opacity(0.2)))
            .accessibilityLabel(item.label + " " + label)
            .accessibilityValue(model.display.localized(selected ? "選択中" : "未選択"))
            .disabled(!item.isSelectable)
    }

    private func metadataFields(_ item: ProviderModelSettings) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 16) {
                metadataField("オススメ度") {
                    Picker(model.display.localized("オススメ度"), selection: recommendationBinding(item.id)) {
                        Text("—").tag(0)
                        ForEach(1...5, id: \.self) { level in Text("\(level) / 5").tag(level) }
                    }.labelsHidden()
                }
                metadataField("速度区分") {
                    Picker(model.display.localized("速度区分"), selection: metadataBinding(item.id, key: \.speedClass)) {
                        Text("—").tag("")
                        ForEach(Self.speedClasses, id: \.self) { value in Text(value).tag(value) }
                        if let existing = item.speedClass, !existing.isEmpty, !Self.speedClasses.contains(existing) {
                            Text(existing).tag(existing)
                        }
                    }.labelsHidden()
                }
            }
            metadataField("実測値に基づく速度ラベル") {
                TextField(model.display.localized("実測値に基づく速度ラベル"), text: metadataBinding(item.id, key: \.speedLabel))
            }
            metadataField("評価コメント（日本語）") { commentEditor(item.id, key: \.commentJA, label: "評価コメント（日本語）") }
            metadataField("評価コメント（英語）") { commentEditor(item.id, key: \.commentEN, label: "評価コメント（英語）") }
        }.padding(.top, 10)
    }

    private func metadataField<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(model.display.localized(label)).font(.caption).foregroundStyle(.secondary)
            content()
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func commentEditor(_ modelID: String, key: WritableKeyPath<ProviderModelSettings, String?>, label: String) -> some View {
        TextEditor(text: metadataBinding(modelID, key: key)).frame(height: 60)
            .scrollContentBackground(.hidden).padding(5)
            .background(.background, in: RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(.secondary.opacity(0.25)))
            .accessibilityLabel(model.display.localized(label))
    }

    private func recommendationBinding(_ modelID: String) -> Binding<Int> {
        Binding(get: { draft.model(modelID: modelID)?.recommendationLevel ?? 0 }, set: { level in
            guard var item = draft.model(modelID: modelID) else { return }
            item.recommendationLevel = level == 0 ? nil : level
            draft.updateModel(item)
        })
    }

    private func metadataBinding(_ modelID: String, key: WritableKeyPath<ProviderModelSettings, String?>) -> Binding<String> {
        Binding(get: { draft.model(modelID: modelID)?[keyPath: key] ?? "" }, set: { value in
            guard var item = draft.model(modelID: modelID) else { return }
            item[keyPath: key] = value.isEmpty ? nil : value
            draft.updateModel(item)
        })
    }

    private func statusLabel(_ item: ProviderModelSettings) -> String? {
        if item.eol == true {
            return model.display.localized("提供終了") + (item.eolDate.map { " (\($0))" } ?? "")
        }
        return item.requiresSubscription == true ? model.display.localized("有料プラン限定") : nil
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let errorMessage {
                Text(model.display.localized(errorMessage)).font(.caption).foregroundStyle(.red).lineLimit(3)
            } else if let statusMessage {
                Text(model.display.message(statusMessage)).font(.caption).foregroundStyle(.secondary).lineLimit(3)
            }
            HStack(spacing: 12) {
                Text(model.display.localizedFormat("%ld モデルを使用中", draft.enabledCount))
                    .font(.callout).foregroundStyle(.secondary)
                if draft.isDirty { Text(model.display.localized("未保存の変更")).font(.caption.weight(.semibold)) }
                Spacer()
                if isWorking { ProgressView().controlSize(.small) }
                Button(model.display.localized("取消")) { cancel() }
                    .keyboardShortcut(.cancelAction).disabled(isWorking)
                Button(model.display.localized("保存")) { Task { await save() } }
                    .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(isWorking || model.isBusy || settings.isLoadingModels || provider == nil)
            }
        }.padding(16)
    }

    private func cancel() {
        guard !isWorking else { return }
        dismiss()
    }

    private func save() async {
        guard !isWorking, !model.isBusy, !settings.isLoadingModels, provider != nil else { return }
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }
        do {
            try await settings.saveProviderModels(providerID: providerID, models: draft.models, enabled: draft.enabled, model: model)
            dismiss()
        } catch {
            errorMessage = "モデル設定を保存できませんでした。"
        }
    }

    private func fetch() async {
        guard !isWorking, !model.isBusy, !settings.isLoadingModels, !draft.isDirty, provider != nil else { return }
        isFetching = true
        errorMessage = nil
        statusMessage = nil
        defer { isFetching = false }
        do {
            try await settings.fetchProviderModels(providerID: providerID, model: model)
            guard let latest = provider else { throw HostError("provider_not_found") }
            draft = ProviderModelsDraft(models: settings.catalogModels(for: latest), enabled: latest.enabledModels ?? [:])
            statusMessage = "\(draft.models.count)個のモデルを取得しました。"
        } catch {
            errorMessage = "モデル一覧を取得できませんでした。"
        }
    }

    private static let speedClasses = ["ultra-fast", "fast", "medium", "slow", "low-speed-outlier"]
}
