import InkuHost
import SwiftUI

extension DisplaySettings {
    /// The reserved `chatgpt` provider is named by core's sign-in descriptor ("ChatGPT でサインイン" /
    /// "Sign in with ChatGPT") wherever other providers show their label.
    func providerName(_ provider: ProviderSettings) -> String {
        provider.kind == .chatGPTPlan ? signInLabel(provider.id) : provider.displayName
    }

    /// Core `sign_in_services`: the connection's name in the display language.
    func signInLabel(_ id: String = ProviderSettings.personalPlan.id) -> String {
        ProviderCoreSettings.signInService(id, language: preferences.language)?["label"] as? String ?? id
    }

    /// Core `sign_in_services`: the service's usage page.
    func signInUsageURL(_ id: String = ProviderSettings.personalPlan.id) -> URL? {
        (ProviderCoreSettings.signInService(id, language: preferences.language)?["usage_url"] as? String).flatMap(URL.init(string:))
    }

    /// A Web function text such as `chatgptModelsLoaded(count)`, exported as a `%@` template.
    func webCopyFormat(_ key: String, _ fallback: String, _ arguments: CVarArg...) -> String {
        let templateKey = key == "ddlImportMigrated" && preferences.language == "en" && arguments.count == 1 && String(describing: arguments[0]) == "1"
            ? "ddlImportMigrated.one" : key
        let template = ServerTips.template(templateKey, language: preferences.language, argumentCount: arguments.count) ?? localized(fallback)
        return String(format: template, locale: Locale(identifier: preferences.language),
                      arguments: arguments.map { String(describing: $0) })
    }
}

/// ModelAdministrationSettings.svelte's model picker for the `chatgpt` provider: the active profile's saved catalog,
/// published per profile. Opening reads the saved catalog only; "Refresh models" fetches it (Server
/// `POST /api/me/chatgpt/models/refresh`) and Save publishes the checked models (`PUT .../models/settings`).
@MainActor
struct ChatGPTModelsSheet: View {
    @Bindable var model: AppModel
    let onChange: @MainActor (ChatGPTPlanPublication) async -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var publication: ChatGPTPlanPublication
    /// Core `sign_in_publication_draft`: the selection, purposes, dirty state and save body (Web model-administration).
    @State private var draft: SignInPublicationDraft?
    @State private var search = ""
    @State private var filter: ProviderModelFilter = .all
    @State private var working = false
    @State private var statusMessage: String?
    @State private var errorMessage: String?

    init(model: AppModel, publication: ChatGPTPlanPublication,
         onChange: @escaping @MainActor (ChatGPTPlanPublication) async -> Void) {
        self.model = model
        self.onChange = onChange
        _publication = State(initialValue: publication)
        _draft = State(initialValue: SignInPublicationDraft(publication: publication))
    }

    private var display: DisplaySettings { model.display }
    private var dirty: Bool { draft?.dirty ?? false }
    private func isSelected(_ id: String) -> Bool { draft?.row(id)?.selected ?? false }
    private func purposes(of id: String) -> [String] { draft?.row(id)?.purposes ?? [] }
    /// The same filter as the other services' picker; the catalog keeps ChatGPT's order. Assessments come from the
    /// publication's own rows (core `chatgpt_publication`) only, not from the bundled catalog.
    private var catalogModels: [ProviderModelSettings] {
        publication.models.map { item in
            var model = publication.assessedModels[item.id] ?? ProviderModelSettings(id: item.id, label: item.label)
            model.purposes = purposes(of: item.id)
            return model
        }
    }
    private var visibleModels: [ProviderModelSettings] {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        return catalogModels.filter { item in
            guard query.isEmpty || item.label.localizedCaseInsensitiveContains(query) || item.id.localizedCaseInsensitiveContains(query) else { return false }
            switch filter {
            case .all: return true
            case .enabled: return isSelected(item.id)
            case .disabled: return !isSelected(item.id)
            case .llm: return purposes(of: item.id).contains("llm")
            case .vision: return purposes(of: item.id).contains("vision")
            }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            toolbar
            Divider()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    if visibleModels.isEmpty {
                        Text(display.localized("該当するモデルがありません。"))
                            .foregroundStyle(.secondary).frame(maxWidth: .infinity).padding(32)
                    }
                    ModelCatalogGroupsView(models: visibleModels, display: display) { item in row(item) }
                }.padding(16)
            }
            .disabled(working)
            Divider()
            footer
        }
        .inkuWideFrame(minWidth: 560, idealWidth: 680, minHeight: 420, idealHeight: 560)
        .interactiveDismissDisabled(working)
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(display.webCopyFormat("settingsModelSelectModelsTitle", "%@ の公開モデル選択", display.signInLabel()))
                    .inkuFont(16, weight: .semibold)
                Text(display.localizedFormat("サービスID: %@", "chatgpt")).inkuFont(12).foregroundStyle(.secondary)
            }
            Spacer()
            Button { dismiss() } label: { Image(systemName: "xmark") }
                .buttonStyle(.plain).accessibilityLabel(display.localized("閉じる"))
                .disabled(working)
        }.padding(20)
    }

    private var toolbar: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField(display.localized("モデルを検索"), text: $search).autocorrectionDisabled()
                        .textFieldStyle(.plain)
                }.padding(8)
                    .background(.background, in: RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(.secondary.opacity(0.25)))
                Picker(display.localized("絞り込み"), selection: $filter) {
                    Text(display.localized("すべて")).tag(ProviderModelFilter.all)
                    Text(display.webCopy("settingsModelFilterPublished", "公開中")).tag(ProviderModelFilter.enabled)
                    Text(display.webCopy("settingsModelFilterUnpublished", "非公開")).tag(ProviderModelFilter.disabled)
                    Text(display.localized("LLM 用")).tag(ProviderModelFilter.llm)
                    Text(display.localized("Vision 用")).tag(ProviderModelFilter.vision)
                }.frame(width: 200)
            }
            HStack(spacing: 10) {
                Button(display.webCopy("chatgptRefreshModels", "モデル一覧を更新")) { Task { await refresh() } }
                    .disabled(working || !(draft?.canRefresh ?? true) || model.isSettingsInteractionLocked)
                    .inkuTooltip(dirty ? display.tooltip("未保存の変更を保存または取り消してからモデルリストを取得してください。", serverKey: "settingsModelFetchDisabledWhileDirty") : "")
                Button(display.webCopy("settingsModelSelectVisible", "表示中を全て選択")) { draft?.select(visibleModels.map(\.id), selected: true) }
                    .disabled(working || visibleModels.isEmpty)
                Button(display.webCopy("settingsModelClearVisible", "表示中を全て解除")) { draft?.select(visibleModels.map(\.id), selected: false) }
                    .disabled(working || visibleModels.isEmpty)
                Spacer()
                Text(display.localizedFormat("%ld / %ld モデルを表示", visibleModels.count, publication.models.count))
                    .inkuFont(12).foregroundStyle(.secondary)
            }.inkuPhoneSlidesSideways()
        }.padding(16)
    }

    private func row(_ item: ProviderModelSettings) -> some View {
      VStack(alignment: .leading, spacing: 10) {
        HStack(alignment: .top, spacing: 12) {
            Toggle(isOn: Binding(get: { isSelected(item.id) }, set: { draft?.toggleModel(item.id, selected: $0) })) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(item.label).inkuFont(14, weight: .semibold)
                    Text(item.id).inkuFont(12, design: .monospaced).foregroundStyle(.secondary).textSelection(.enabled)
                    ModelLabelsView(labels: item.resolvedLabels, display: display, endOfLifeDate: item.eolDate)
                }
            }
            .inkuCheckboxStyle()
            // core: a model it cannot publish, or one with no purpose, is not toggled (a purpose publishes it again).
            .disabled(!(draft?.row(item.id)?.canToggle ?? false) && !isSelected(item.id))
            .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 6) {
                purposeButton("LLM", purpose: "llm", item: item)
                purposeButton("Vision", purpose: "vision", item: item)
            }
        }
        DisclosureGroup(display.localized("モデル詳細")) {
            RegisteredModelMetadataView(entry: item, provider: metadataProvider, display: display)
        }.inkuFont(13)
      }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(.secondary.opacity(0.18)))
    }

    /// The other services' purpose capsule (ProviderModelsSheet).
    private var metadataProvider: ProviderSettings {
        var provider = ProviderSettings.personalPlan
        provider.models = catalogModels
        return provider
    }

    private func purposeButton(_ label: String, purpose: String, item: ProviderModelSettings) -> some View {
        let on = purposes(of: item.id).contains(purpose)
        let locked = draft?.row(item.id)?.lockedPurposes.contains(purpose) ?? true
        // A ChatGPT purpose measured without a response is disabled; its tooltip is gone with the model choice's floats
        // (author 2026-11-12, Web `noResponseTitle` removed). VoiceOver still reads the reason.
        let note = display.preferences.language == "en" ? "Not selectable: no response when measured" : "計測で応答が無かったため選べません"
        return Button(label) { draft?.togglePurpose(item.id, purpose: purpose) }
            .buttonStyle(.plain)
            .disabled(locked)
            .inkuFont(12, weight: .medium)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .foregroundStyle(on ? Color.accentColor : Color.secondary)
            .background(on ? Color.accentColor.opacity(0.14) : Color.secondary.opacity(0.08), in: Capsule())
            .overlay(Capsule().stroke(on ? Color.accentColor.opacity(0.4) : Color.secondary.opacity(0.2)))
            .accessibilityLabel(item.label + " " + label)
            .accessibilityValue(display.localized(on ? "選択中" : "未選択"))
            .accessibilityHint(locked ? note : "")
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let errorMessage {
                Text(errorMessage).inkuFont(12).foregroundStyle(.red).lineLimit(3).textSelection(.enabled)
            } else if let statusMessage {
                Text(statusMessage).inkuFont(12).foregroundStyle(.secondary).lineLimit(3)
            }
            HStack(spacing: 12) {
                Text(display.webCopyFormat("settingsModelPublishedCount", "%@ モデルを公開中", publication.models.filter { isSelected($0.id) }.count))
                    .inkuFont(13).foregroundStyle(.secondary)
                if dirty { Text(display.localized("未保存の変更")).inkuFont(12, weight: .semibold) }
                Spacer()
                if working { ProgressView().controlSize(.small) }
                Button(display.localized("キャンセル")) { dismiss() }
                    .keyboardShortcut(.cancelAction).disabled(working)
                Button(display.localized("保存")) { Task { await save() } }
                    .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(working || draft == nil || !(draft?.canSave ?? false) || model.isSettingsInteractionLocked)
            }
        }.padding(16)
    }

    private func refresh() async {
        working = true; errorMessage = nil
        statusMessage = ChatGPTStatusCopy.text("chatgpt_models_loading", language: display.preferences.language)
        do {
            let next = try await model.personalPlanRuntime().refreshPublication()
            publication = next; draft = SignInPublicationDraft(publication: next)
            statusMessage = next.models.isEmpty
                ? display.webCopy("chatgptModelsEmpty", "この登録で選択できるモデルはありません。接続とプラン利用の許可を確認してください。")
                : display.webCopyFormat("chatgptModelsLoaded", "%@件のモデルを取得しました。公開するモデルを選んで保存してください。", next.models.count)
            await onChange(next)
        } catch { report(error) }
        working = false
    }

    private func save() async {
        working = true; errorMessage = nil; statusMessage = nil
        do {
            // core's save body: the catalog order, and every model's purposes (Web model-administration).
            guard let draft else { throw HostError("chatgpt_publication_invalid") }
            let next = try await model.personalPlanRuntime().savePublication(
                profileID: publication.profileID, generation: publication.generation, models: draft.savedModels, purposes: draft.savedPurposes)
            publication = next; self.draft = SignInPublicationDraft(publication: next)
            await onChange(next)
            working = false
            dismiss()
        } catch { report(error); working = false }
    }

    private func report(_ error: Error) {
        statusMessage = nil
        errorMessage = ChatGPTStatusCopy.text(ChatGPTPlanRuntime.diagnostic(error).code, language: display.preferences.language)
    }
}
