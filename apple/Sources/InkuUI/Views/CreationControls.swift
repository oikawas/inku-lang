import InkuHost
import SwiftUI

extension View {
    func creationPanel() -> some View {
        padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.quaternary))
    }
}

@MainActor
struct CreationModelPicker: View {
    @Bindable var model: AppModel
    @State private var settings = SettingsModel()
    @State private var providerID: String?
    @State private var personalModels: [ProviderModelInfo] = []
    @State private var loadingPersonalModels = false
    @State private var catalogError: String?
    @State private var discovery: Task<Void, Never>?

    private var provider: ProviderSettings? { settings.host.providers.first { $0.id == providerID } }
    private var loading: Bool { settings.isLoadingModels || loadingPersonalModels }
    private var models: [ProviderModelInfo] {
        guard let provider else { return [] }
        var seen: Set<String> = []
        let configured = [model.nextDrawingModelReference, settings.host.models.stage1Model, settings.host.models.stage2Model]
            .filter { $0.hasPrefix(provider.id + ":") && $0.count > provider.id.count + 1 }
            .map { ProviderModelInfo(id: $0, name: String($0.dropFirst(provider.id.count + 1)), contextLimit: nil, capabilities: []) }
        let discovered = provider.kind == .chatGPTPlan ? personalModels : settings.modelCatalog
        return (discovered + configured).filter { $0.id.hasPrefix(provider.id + ":") && seen.insert($0.id).inserted }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(model.display.localized("描画モデル")).font(.subheadline.weight(.semibold))
                Spacer()
                Button { openSettings() } label: { Image(systemName: "gearshape") }
                    .buttonStyle(.plain)
                    .accessibilityLabel(model.display.localized("モデル設定"))
                    .help(model.display.preferences.showTooltips ? model.display.localized("モデル設定") : "")
                    .disabled(model.isBusy)
            }
            if !settings.host.providers.isEmpty {
                Picker(model.display.localized("サービス"), selection: $providerID) {
                    ForEach(settings.host.providers) { item in Text(item.id).tag(Optional(item.id)) }
                }
                .disabled(model.isBusy || loading)
                .help(tip("次の作品のモデルを提供するサービスを選びます。"))
                Picker(model.display.localized("モデル"), selection: Binding(
                    get: { models.contains(where: { $0.id == model.nextDrawingModelReference }) ? model.nextDrawingModelReference : "" },
                    set: { model.selectNextDrawingModel($0) }
                )) {
                    Text(model.display.localized("選択してください")).tag("")
                    ForEach(models) { item in Text(item.name).tag(item.id) }
                }
                .disabled(model.isBusy || loading || models.isEmpty)
                .help(tip("解釈と構造化に使うモデルを選びます。"))
                Button {
                    discovery = Task { await discoverModels() }
                } label: {
                    Label(model.display.localized(loading ? "取得中…" : "接続先からモデル一覧を取得"), systemImage: "arrow.clockwise")
                        .font(.caption)
                }
                .disabled(model.isBusy || loading || provider == nil)
                .help(tip("接続先が提供するモデル一覧を取得します。"))
                if !model.nextDrawingModelReference.isEmpty {
                    Text(model.display.localizedFormat("次のモデル: %@", model.nextDrawingModelReference))
                        .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    ModelGuidanceView(reference: model.nextDrawingModelReference, providers: settings.host.providers,
                                      discovered: models.first { $0.id == model.nextDrawingModelReference }, display: model.display)
                }
            } else {
                Button(model.display.localized("モデル設定"), systemImage: "plus.circle") { openSettings() }
                    .disabled(model.isBusy)
            }
            if let catalogError {
                Text(model.display.message(catalogError)).font(.caption).foregroundStyle(.red)
            }
            Text(model.display.localized("解釈と構造化に同じモデルを使います。"))
                .font(.caption).foregroundStyle(.secondary)
        }
        .task(id: model.providerSettingsRevision) {
            discovery?.cancel()
            settings.cancelDiscovery()
            let refreshed = SettingsModel()
            await refreshed.load(model: model)
            guard !Task.isCancelled else { return }
            settings = refreshed
            personalModels = []
            catalogError = nil
            providerID = refreshed.host.providers.first(where: { model.nextDrawingModelReference.hasPrefix($0.id + ":") })?.id
                ?? refreshed.host.providers.first?.id
        }
        .onChange(of: providerID) { _, _ in catalogError = nil }
        .onDisappear { discovery?.cancel(); settings.cancelDiscovery() }
    }

    private func openSettings() {
        NotificationCenter.default.post(name: .inkuOpenSection, object: "settings",
            userInfo: ["settingsSection": provider?.kind == .chatGPTPlan ? "personalPlan" : "models"])
    }

    private func tip(_ key: String) -> String {
        model.display.preferences.showTooltips ? model.display.localized(key) : ""
    }

    private func discoverModels() async {
        guard !model.isBusy, !loading, let provider else { return }
        let revision = model.providerSettingsRevision
        catalogError = nil
        if provider.kind == .chatGPTPlan {
            loadingPersonalModels = true
            defer { loadingPersonalModels = false }
            do {
                let offered = try await model.personalPlanRuntime().models(force: true)
                guard !Task.isCancelled, providerID == provider.id, revision == model.providerSettingsRevision else { return }
                personalModels = offered.map { ProviderModelInfo(id: provider.id + ":" + $0.id, name: $0.label, contextLimit: nil, capabilities: []) }
            } catch {
                guard !Task.isCancelled, revision == model.providerSettingsRevision else { return }
                catalogError = error.localizedDescription
            }
        } else {
            settings.selectedProviderID = provider.id
            await settings.discoverModels()
            guard !Task.isCancelled, providerID == provider.id, revision == model.providerSettingsRevision else { return }
            catalogError = settings.error
        }
    }
}
