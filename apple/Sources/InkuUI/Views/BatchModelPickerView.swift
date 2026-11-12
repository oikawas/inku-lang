import InkuHost
import SwiftUI

@MainActor
struct BatchModelPickerView: View {
    @Bindable var model: AppModel
    private let initialReference: String?
    private let singlePurposeSelection: Bool
    private let title: String
    private let purpose: String
    private let onSelection: (@MainActor (String) async throws -> Void)?
    @Environment(\.dismiss) private var dismiss
    @Environment(\.isEnabled) private var isEnabled
    @State private var settings: HostSettings?
    @State private var draftReference = ""
    @State private var selectionError: String?
    @State private var committing = false
    @State private var draftThinking = false

    private var groups: [ProviderSettings] {
        (settings?.providers ?? []).filter { !SettingsModel.registeredModels(for: $0, purpose: selectedPurpose).isEmpty }
    }
    private var selectedPurpose: String { purpose }
    private var selectedReference: String { draftReference }
    init(model: AppModel, initialReference: String? = nil, immediateSelection: Bool = false,
         title: String = "モデル選択", purpose: String = "llm",
         onSelection: (@MainActor (String) async throws -> Void)? = nil) {
        self.model = model
        self.initialReference = initialReference
        // Preserve existing caller syntax while every entry now confirms its local draft.
        self.singlePurposeSelection = immediateSelection
        self.title = title
        self.purpose = purpose
        self.onSelection = onSelection
    }

    private var cannotSelect: Bool { model.isBusy || !isEnabled || committing }
    private var canConfirm: Bool {
        guard !cannotSelect, let settings else { return false }
        return SettingsModel.isRegisteredModelAvailable(draftReference, purpose: selectedPurpose, settings: settings)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(model.display.localized(title)).inkuFont(14, weight: .semibold)
                Spacer()
                Button { dismiss() } label: {
                    Image(systemName: "xmark").inkuFont(16)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(model.display.localized("閉じる"))
                .environment(\.isEnabled, true)
                .disabled(committing)
            }.padding(16)
            Divider()
            HStack {
                selectionTabButton("shared", title: singlePurposeSelection ? model.display.localized(title) : model.display.label("描画モデル", "Drawing model"))
            }.padding(.horizontal, 24).padding(.vertical, 12)
            Divider()
            if let selectionError {
                Text(model.display.localized("モデルの変更に失敗しました。もう一度選択してください。") + "\n" + model.display.message(selectionError))
                    .inkuFont(13).foregroundStyle(.red)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading).padding([.horizontal, .top], 16)
            }
            if settings == nil {
                ProgressView().frame(maxWidth: .infinity).padding(24)
            } else if groups.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    sharedModelHint
                    Text(model.display.localized("選べるモデルがありません。設定 → モデル設定 で使用するモデルを選択してください。"))
                        .inkuFont(13).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        sharedModelHint
                        ForEach(groups) { provider in
                            VStack(alignment: .leading, spacing: 7) {
                                Text(model.display.providerName(provider)).inkuFont(12, weight: .medium).foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 7)], alignment: .leading, spacing: 7) {
                                    ForEach(sortedModels(for: provider)) { entry in
                                        modelCard(entry, provider: provider)
                                    }
                                }
                            }
                        }
                        if !singlePurposeSelection, selectedPurpose == "llm", draftReference.contains("qwen3") {
                            Toggle(model.display.localized("思考を表示"), isOn: $draftThinking).disabled(cannotSelect)
                        }
                    }.padding(16)
                }
                .frame(height: 440)
            }
            Divider()
            HStack(spacing: 8) {
                // ModelSelectionSettings.svelte `model-selection-current`: the chosen model, beside Cancel and Confirm.
                // A long name wraps instead of being cut, and has no tooltip (author 2026-11-12, as on the Web).
                Text(selectedSummaryText).inkuFont(12).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Button(model.display.localized("キャンセル")) { dismiss() }
                    .keyboardShortcut(.cancelAction).environment(\.isEnabled, true)
                    .disabled(committing)
                Button(model.display.localized("決定")) { Task { await confirmSelection() } }
                    .keyboardShortcut(.defaultAction).buttonStyle(.borderedProminent)
                    .disabled(!canConfirm)
            }.padding(.horizontal, 18).padding(.vertical, 14)
        }
        // No floating card over a hovered, focused or pressed model (author 2026-11-12: every float in model choice
        // is gone, as on the Web). The card's name, labels, use and recommendation stay inside the button.
        .inkuDialogFrame(width: groups.isEmpty ? 440 : 800, iOSMaxWidth: 800)
        .task(id: model.providerSettingsRevision) {
            let current = await model.hostSettings()
            guard !Task.isCancelled else { return }
            if settings == nil {
                draftReference = initialReference ?? model.nextBatchDrawingModelReference
                draftThinking = model.display.preferences.includeThinking ?? false
            }
            else if !SettingsModel.isRegisteredModelAvailable(draftReference, purpose: purpose, settings: current) { draftReference = "" }
            settings = current
            selectionError = nil
        }
        .interactiveDismissDisabled(committing)
    }

    private func selectionTabButton(_ tab: String, title: String) -> some View {
        Text(title).inkuFont(13, weight: .semibold).frame(maxWidth: .infinity).padding(10)
            .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            .overlay(alignment: .bottom) { Rectangle().fill(Color.accentColor).frame(height: 2) }
            .accessibilityAddTraits(.isSelected)
    }

    /// ModelSelectionSettings.svelte `selectedName`: the chosen model's label, else its id as stored.
    private var selectedSummaryText: String {
        let name = entry(for: draftReference, purpose: purpose).map { $0.model.label.isEmpty ? $0.model.id : $0.model.label }
            ?? (draftReference.isEmpty ? model.display.localized("未設定") : draftReference)
        return model.display.webCopyFormat("modelSelectionSelected", "選択中 %@", name)
    }

    private var sharedModelHint: some View {
        Text(selectedPurpose == "vision"
             ? model.display.webCopy("modelSelectionVisionHint", "画像を読むVision処理に使うモデルを選択します。")
             : singlePurposeSelection ? model.display.label("選んだモデルをこの操作に使います。", "The chosen model is used for this operation.")
             : model.display.webCopy("modelSelectionSharedHint", model.display.label("ここで選んだモデルを指示書を書く工程と補完に設定します。補完のモデルは別に変更できます。", "The model chosen here is set for writing the instructions and completion. The completion model can be changed separately.")))
            .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
    }

    private func confirmSelection() async {
        guard canConfirm else { return }
        committing = true
        defer { committing = false }
        do {
            if let onSelection { try await onSelection(draftReference) }
            else {
                try await model.selectSharedDrawingModel(draftReference)
                guard model.nextBatchDrawingModelReference == draftReference else { throw HostError("drawing_model_not_available") }
                model.display.preferences.includeThinking = draftThinking
                if model.display.saveError != nil { throw HostError("interface_settings_save_failed") }
            }
            dismiss()
        } catch { selectionError = error.localizedDescription }
    }

    private func modelCard(_ entry: ProviderModelSettings, provider: ProviderSettings) -> some View {
        let reference = provider.id + ":" + entry.id
        let selected = reference == selectedReference
        let unrecommended = entry.isNotRecommended(for: selectedPurpose)
        return Button {
            guard !cannotSelect, let settings,
                  SettingsModel.isRegisteredModelAvailable(reference, purpose: selectedPurpose, settings: settings) else { return }
            draftReference = reference
            selectionError = nil
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .top, spacing: 8) {
                    Text(entry.label.isEmpty ? entry.id : entry.label)
                        .inkuFont(13, weight: .medium).strikethrough(entry.modelFold == "eol")
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                    if selected { Image(systemName: "checkmark").foregroundStyle(Color.accentColor) }
                }
                if unrecommended {
                    Text(model.display.webCopy("modelNotRecommended", Self.notRecommended(language: model.display.preferences.language)))
                        .inkuFont(11, weight: .semibold).foregroundStyle(Color.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ModelLabelsView(labels: entry.resolvedLabels, display: model.display, endOfLifeDate: entry.eolDate)
                HStack {
                    ModelPurposeBadgesView(entry: entry, language: model.display.preferences.language)
                    Spacer(minLength: 0)
                    Text(ModelGuidance.recommendation(sharedRecommendationLevel(entry)))
                        .inkuFont(11).foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 20, alignment: .topLeading)
            .padding(10)
            .background(selected ? Color.accentColor.opacity(0.12) : Color.primary.opacity(0.035),
                        in: RoundedRectangle(cornerRadius: 8))
            .overlay {
                // Published for a purpose it did not answer when measured: choosable, framed in red (2026-10-26).
                RoundedRectangle(cornerRadius: 8)
                    .stroke(unrecommended ? Color.red : selected ? Color.accentColor : Color.primary.opacity(0.18),
                            lineWidth: selected || unrecommended ? 2 : 1)
            }
            .contentShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
        .disabled(cannotSelect || !entry.isSelectable)
        // The red frame's tooltip is gone with the floats (author 2026-11-12); the card says "not recommended".
        .opacity(entry.isSelectable ? 1 : 0.55)
        .accessibilityElement(children: .combine)
        .accessibilityValue(selected ? model.display.localized("選択中") : "")
        .accessibilityHint(metadataText(entry, provider: provider))
    }

    private func sortedModels(for provider: ProviderSettings) -> [ProviderModelSettings] {
        let models = SettingsModel.registeredModels(for: provider, purpose: selectedPurpose)
        return ProviderModelOrdering.picker(models, purpose: selectedPurpose, chatGPT: provider.kind == .chatGPTPlan)
    }

    private func entry(for reference: String, purpose: String? = nil) -> (provider: ProviderSettings, model: ProviderModelSettings)? {
        for provider in settings?.providers ?? [] {
            if let model = SettingsModel.registeredModels(for: provider, purpose: purpose ?? selectedPurpose).first(where: { provider.id + ":" + $0.id == reference }) {
                return (provider, model)
            }
        }
        return nil
    }

    private func sharedRecommendationLevel(_ entry: ProviderModelSettings) -> Int {
        entry.catalogLevel(purpose: selectedPurpose, stage: selectedPurpose == "vision" ? "none" : "both") ?? 0
    }

    private func recommendationRows(_ entry: ProviderModelSettings) -> [(String, String)] {
        if selectedPurpose == "vision" { return [("オススメ度", ModelGuidance.recommendation(entry.catalogLevel(purpose: "vision")))] }
        if entry.recommendationStage1 != nil || entry.recommendationStage2 != nil {
            return [(model.display.label("指示書を書く工程のオススメ度", "Recommendation for writing the instructions"), ModelGuidance.recommendation(entry.catalogLevel(purpose: "llm", stage: "stage1"))),
                    (model.display.label("補完のオススメ度", "Recommendation for completion"), ModelGuidance.recommendation(entry.catalogLevel(purpose: "llm", stage: "stage2")))]
        }
        return [("オススメ度", ModelGuidance.recommendation(entry.catalogLevel(purpose: "llm")))]
    }

    private func purposes(_ entry: ProviderModelSettings) -> String {
        ["llm", "vision"].map { purpose in
            let label = purpose == "llm" ? "LLM" : "Vision"
            return label + (ModelMetadataPresentation.supports(entry, purpose: purpose) ? "" : model.display.preferences.language == "en" ? " (not selectable)" : "（選べません）")
        }.joined(separator: " / ")
    }

    private func speed(_ entry: ProviderModelSettings, provider: ProviderSettings) -> String {
        let guidance = ModelGuidanceCatalog.bundled?.guidance(for: provider.id + ":" + entry.id,
                                                           providers: settings?.providers ?? [])
        return ModelMetadataPresentation.speed(entry, hidden: guidance?.speedHidden == true, language: model.display.preferences.language)
    }

    private func comment(_ entry: ProviderModelSettings) -> String {
        let candidates = model.display.preferences.language == "en"
            ? [entry.commentEN, entry.commentJA] : [entry.commentJA, entry.commentEN]
        return candidates.compactMap { $0 }.first { !$0.isEmpty } ?? "—"
    }

    /// web/src/lib/i18n modelNotRecommended (2026-10-26).
    static func notRecommended(language: String) -> String {
        language == "en" ? "Not recommended (no response when measured)" : "推奨しません（計測で応答なし）"
    }

    private func metadataText(_ entry: ProviderModelSettings, provider: ProviderSettings) -> String {
        let rows = [("用途", purposes(entry))] + recommendationRows(entry)
            + [("概算コスト", ModelMetadataPresentation.cost(entry, language: model.display.preferences.language)),
               ("速度", speed(entry, provider: provider)), ("評価コメント", comment(entry))]
        let warning = entry.isNotRecommended(for: selectedPurpose) ? [Self.notRecommended(language: model.display.preferences.language)] : []
        return (warning + entry.resolvedLabels.map { $0.name(language: model.display.preferences.language) }
                + rows.map { model.display.localized($0.0) + ": " + $0.1 }).joined(separator: ". ")
    }
}
