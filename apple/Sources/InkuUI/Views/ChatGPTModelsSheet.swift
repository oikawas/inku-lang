import InkuHost
import SwiftUI

extension DisplaySettings {
    /// ModelSelectionSettings.svelte / ModelAdministrationSettings.svelte name the reserved `chatgpt` provider
    /// "ChatGPT plan" (`chatgptPlanLabel`) wherever other providers show their label.
    func providerName(_ provider: ProviderSettings) -> String {
        provider.kind == .chatGPTPlan ? webCopy("chatgptPlanLabel", "ChatGPTプラン") : provider.displayName
    }

    /// A Web function text such as `chatgptModelsLoaded(count)`, exported as a `%@` template.
    func webCopyFormat(_ key: String, _ fallback: String, _ arguments: CVarArg...) -> String {
        let template = ServerTips.template(key, language: preferences.language, argumentCount: arguments.count) ?? localized(fallback)
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
    @State private var selected: Set<String>
    @State private var purposes: [String: [String]]
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
        _selected = State(initialValue: publication.published)
        _purposes = State(initialValue: publication.purposes)
    }

    private var display: DisplaySettings { model.display }
    private var dirty: Bool { selected != publication.published || purposes != publication.purposes }
    private func purposes(of id: String) -> [String] { purposes[id] ?? ChatGPTPlanPublication.defaultPurposes }
    /// A published model needs a purpose, as on the other services.
    private var missingPurpose: Bool { selected.contains { purposes(of: $0).isEmpty } }
    /// The same filter as the other services' picker; the catalog keeps ChatGPT's order.
    private var catalogModels: [ProviderModelSettings] {
        publication.models.map { item in
            let saved = ProviderModelSettings(id: item.id, label: item.label, purposes: purposes(of: item.id))
            return ModelGuidanceCatalog.bundled?.applyingCatalog(to: saved, providerID: "chatgpt", kind: .chatGPTPlan) ?? saved
        }
    }
    private var visibleModels: [ProviderModelSettings] {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        return catalogModels.filter { item in
            guard query.isEmpty || item.label.localizedCaseInsensitiveContains(query) || item.id.localizedCaseInsensitiveContains(query) else { return false }
            switch filter {
            case .all: return true
            case .enabled: return selected.contains(item.id)
            case .disabled: return !selected.contains(item.id)
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
        .frame(minWidth: 560, idealWidth: 680, minHeight: 420, idealHeight: 560)
        .interactiveDismissDisabled(working)
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(display.localizedFormat("%@ の使用モデル選択", display.webCopy("chatgptPlanLabel", "ChatGPTプラン")))
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
                    Text(display.localized("使用中")).tag(ProviderModelFilter.enabled)
                    Text(display.localized("不使用")).tag(ProviderModelFilter.disabled)
                    Text(display.localized("LLM 用")).tag(ProviderModelFilter.llm)
                    Text(display.localized("Vision 用")).tag(ProviderModelFilter.vision)
                }.frame(width: 200)
            }
            HStack(spacing: 10) {
                Button(display.webCopy("chatgptRefreshModels", "モデル一覧を更新")) { Task { await refresh() } }
                    .disabled(working || dirty || model.isBrowsingLocked)
                    .inkuTooltip(dirty ? display.tooltip("未保存の変更を保存または取り消してからモデルリストを取得してください。", serverKey: "settingsModelFetchDisabledWhileDirty") : "")
                Button(display.webCopy("settingsModelSelectVisible", "表示中を全て選択")) { selected.formUnion(visibleModels.filter(\.isSelectable).map(\.id)) }
                    .disabled(working || visibleModels.isEmpty)
                Button(display.webCopy("settingsModelClearVisible", "表示中を全て解除")) { selected.subtract(visibleModels.map(\.id)) }
                    .disabled(working || visibleModels.isEmpty)
                Spacer()
                Text(display.localizedFormat("%ld / %ld モデルを表示", visibleModels.count, publication.models.count))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
        }.padding(16)
    }

    private func row(_ item: ProviderModelSettings) -> some View {
      VStack(alignment: .leading, spacing: 10) {
        HStack(alignment: .top, spacing: 12) {
            Toggle(isOn: Binding(get: { selected.contains(item.id) },
                                 set: { if $0 && item.isSelectable { selected.insert(item.id) } else { selected.remove(item.id) } })) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(item.label).inkuFont(14, weight: .semibold)
                    Text(item.id).inkuFont(12, design: .monospaced).foregroundStyle(.secondary).textSelection(.enabled)
                    ModelLabelsView(labels: item.resolvedLabels, display: display)
                    if selected.contains(item.id), purposes(of: item.id).isEmpty {
                        Text(display.localized("LLM か Vision の用途を選んでください。")).inkuFont(12).foregroundStyle(.orange)
                    }
                }
            }
            .toggleStyle(.checkbox)
            .disabled(!item.isSelectable && !selected.contains(item.id))
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
        return Button(label) {
            var next = purposes(of: item.id)
            if on { next.removeAll { $0 == purpose } } else { next.append(purpose) }
            purposes[item.id] = ["llm", "vision"].filter(next.contains)
        }
            .buttonStyle(.plain)
            .disabled(!ProviderModelsDraft.canEditPurposes(item) || (item.unsupportedPurposes ?? []).contains(purpose))
            .inkuFont(12, weight: .medium)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .foregroundStyle(on ? Color.accentColor : Color.secondary)
            .background(on ? Color.accentColor.opacity(0.14) : Color.secondary.opacity(0.08), in: Capsule())
            .overlay(Capsule().stroke(on ? Color.accentColor.opacity(0.4) : Color.secondary.opacity(0.2)))
            .accessibilityLabel(item.label + " " + label)
            .accessibilityValue(display.localized(on ? "選択中" : "未選択"))
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let errorMessage {
                Text(errorMessage).inkuFont(12).foregroundStyle(.red).lineLimit(3).textSelection(.enabled)
            } else if let statusMessage {
                Text(statusMessage).inkuFont(12).foregroundStyle(.secondary).lineLimit(3)
            }
            HStack(spacing: 12) {
                Text(display.localizedFormat("%ld モデルを使用中", publication.models.filter { selected.contains($0.id) }.count))
                    .inkuFont(13).foregroundStyle(.secondary)
                if dirty { Text(display.localized("未保存の変更")).inkuFont(12, weight: .semibold) }
                Spacer()
                if working { ProgressView().controlSize(.small) }
                Button(display.localized("取消")) { dismiss() }
                    .keyboardShortcut(.cancelAction).disabled(working)
                Button(display.localized("保存")) { Task { await save() } }
                    .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(working || !dirty || missingPurpose || catalogModels.contains { selected.contains($0.id) && !$0.isSelectable } || model.isBrowsingLocked)
            }
        }.padding(16)
    }

    private func refresh() async {
        working = true; errorMessage = nil
        statusMessage = ChatGPTStatusCopy.text("chatgpt_models_loading", language: display.preferences.language)
        do {
            let next = try await model.personalPlanRuntime().refreshPublication()
            publication = next; selected = next.published; purposes = next.purposes
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
            // Web sends the catalog order, not the order the boxes were checked.
            let ids = publication.models.map(\.id).filter(selected.contains)
            let changed = purposes.filter { publication.purposes[$0.key] != $0.value }
            let next = try await model.personalPlanRuntime().savePublication(
                profileID: publication.profileID, generation: publication.generation, models: ids, purposes: changed)
            publication = next; selected = next.published; purposes = next.purposes
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
