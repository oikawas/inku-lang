import InkuHost
import SwiftUI

@MainActor
struct BatchModelPickerView: View {
    @Bindable var model: AppModel
    private let initialReference: String?
    private let immediateSelection: Bool
    private let title: String
    private let purpose: String
    private let onSelection: (@MainActor (String) async throws -> Void)?
    @Environment(\.dismiss) private var dismiss
    @Environment(\.isEnabled) private var isEnabled
    @State private var settings: HostSettings?
    @State private var draftReference = ""
    @State private var hoveredReference: String?
    @State private var metadataHeight: CGFloat = 220
    @State private var selectionError: String?
    @State private var committing = false
    @State private var draftThinking = false
    @State private var selectionTab = "shared"
    @State private var draftVisionReference = ""
    @FocusState private var focusedReference: String?

    private var groups: [ProviderSettings] {
        (settings?.providers ?? []).filter { !SettingsModel.registeredModels(for: $0, purpose: selectedPurpose).isEmpty }
    }
    private var hasVisionTab: Bool {
        !immediateSelection && purpose == "llm" && onSelection == nil
            && (settings?.providers.contains { !SettingsModel.registeredModels(for: $0, purpose: "vision").isEmpty } ?? false)
    }
    private var selectedPurpose: String { hasVisionTab && selectionTab == "vision" ? "vision" : purpose }
    private var selectedReference: String { selectedPurpose == "vision" && hasVisionTab ? draftVisionReference : draftReference }
    private var inspectedReference: String? { hoveredReference ?? focusedReference }
    init(model: AppModel, initialReference: String? = nil, immediateSelection: Bool = false,
         title: String = "モデル選択", purpose: String = "llm", onSelection: (@MainActor (String) async throws -> Void)? = nil) {
        self.model = model
        self.initialReference = initialReference
        self.immediateSelection = immediateSelection
        self.title = title
        self.purpose = purpose
        self.onSelection = onSelection
    }

    private var cannotSelect: Bool { model.isBusy || !isEnabled || committing }
    private var canConfirm: Bool {
        guard !cannotSelect, let settings else { return false }
        if hasVisionTab {
            return SettingsModel.isBatchModelAvailable(draftReference, settings: settings)
                && (draftVisionReference.isEmpty || SettingsModel.isRegisteredModelAvailable(draftVisionReference, purpose: "vision", settings: settings))
        }
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
                selectionTabButton("shared", title: immediateSelection ? model.display.localized(title) : "Stage 1/2")
                if hasVisionTab { selectionTabButton("vision", title: "Vision") }
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
                    selectionSummary
                    sharedModelHint
                    Text(model.display.localized("選べるモデルがありません。設定 → モデル設定 で使用するモデルを選択してください。"))
                        .inkuFont(13).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        selectionSummary
                        sharedModelHint
                        ForEach(groups) { provider in
                            VStack(alignment: .leading, spacing: 7) {
                                Text(provider.displayName).inkuFont(12, weight: .medium).foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 7)], spacing: 7) {
                                    ForEach(sortedModels(for: provider)) { entry in
                                        modelCard(entry, provider: provider)
                                    }
                                }
                            }
                        }
                        if !immediateSelection, selectedPurpose == "llm", draftReference.contains("qwen3") {
                            Toggle(model.display.localized("思考を表示"), isOn: $draftThinking).disabled(cannotSelect)
                        }
                    }.padding(16)
                }
                .frame(height: 440)
            }
            Divider()
            HStack(spacing: 8) {
                Spacer()
                Button(model.display.localized(immediateSelection ? "閉じる" : "キャンセル")) { dismiss() }
                    .keyboardShortcut(.cancelAction).environment(\.isEnabled, true)
                    .disabled(committing)
                if !immediateSelection {
                    Button(model.display.localized("決定")) { Task { await confirmSelection() } }
                        .keyboardShortcut(.defaultAction).buttonStyle(.borderedProminent)
                        .disabled(!canConfirm)
                }
            }.padding(.horizontal, 18).padding(.vertical, 14)
        }
        #if os(macOS)
        .frame(width: groups.isEmpty ? 440 : 800)
        #else
        .frame(maxWidth: 800)
        #endif
        .overlayPreferenceValue(BatchModelCardBounds.self) { anchors in
            GeometryReader { geometry in
                if let reference = inspectedReference, let anchor = anchors[reference],
                   let selected = entry(for: reference) {
                    let card = geometry[anchor]
                    let width = min(340, geometry.size.width - 16)
                    let x = min(max(8, card.minX), geometry.size.width - width - 8)
                    let below = card.maxY + 5
                    let y = below + metadataHeight <= geometry.size.height - 8
                        ? below : max(8, card.minY - metadataHeight - 5)
                    metadata(selected.model, provider: selected.provider)
                        .frame(width: width, alignment: .leading)
                        .background {
                            GeometryReader { size in
                                Color.clear.onAppear { metadataHeight = size.size.height }
                                    .onChange(of: size.size.height) { _, height in metadataHeight = height }
                            }
                        }
                        .offset(x: x, y: y)
                        .allowsHitTesting(false)
                }
            }
        }
        .task(id: model.providerSettingsRevision) {
            let current = await model.hostSettings()
            guard !Task.isCancelled else { return }
            if settings == nil {
                draftReference = initialReference ?? model.nextBatchDrawingModelReference
                draftThinking = model.display.preferences.includeThinking ?? false
                draftVisionReference = model.display.preferences.visionModelReference ?? ""
            }
            else if !SettingsModel.isRegisteredModelAvailable(draftReference, purpose: purpose, settings: current) { draftReference = "" }
            if !SettingsModel.isRegisteredModelAvailable(draftVisionReference, purpose: "vision", settings: current) { draftVisionReference = "" }
            settings = current
            hoveredReference = nil
            focusedReference = nil
            selectionError = nil
        }
        .interactiveDismissDisabled(committing)
    }

    private func selectionTabButton(_ tab: String, title: String) -> some View {
        let selected = selectionTab == tab
        return Button {
            selectionTab = tab
            hoveredReference = nil
            focusedReference = nil
        } label: {
            Text(title).inkuFont(13, weight: .semibold).frame(maxWidth: .infinity).padding(10)
                .background(selected ? Color.accentColor.opacity(0.12) : Color.clear, in: RoundedRectangle(cornerRadius: 8))
                .overlay(alignment: .bottom) { Rectangle().fill(selected ? Color.accentColor : Color.clear).frame(height: 2) }
        }.buttonStyle(.plain).disabled(cannotSelect).accessibilityAddTraits(selected ? .isSelected : [])
    }

    private var selectionSummary: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(immediateSelection ? model.display.localized(title) : "Stage 1/2").inkuFont(11, weight: .semibold).foregroundStyle(.secondary)
            Text(entry(for: draftReference, purpose: purpose).map { $0.model.label.isEmpty ? $0.model.id : $0.model.label }
                 ?? model.display.localized("未設定"))
                .inkuFont(13).fixedSize(horizontal: false, vertical: true)
            if hasVisionTab {
                Text("Vision").inkuFont(11, weight: .semibold).foregroundStyle(.secondary)
                Text(entry(for: draftVisionReference, purpose: "vision").map { $0.model.label.isEmpty ? $0.model.id : $0.model.label }
                     ?? model.display.localized("未設定")).inkuFont(13)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(10)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
    }

    private var sharedModelHint: some View {
        Text(model.display.localized(immediateSelection ? "モデルを選ぶと変更を適用して閉じます。" : selectedPurpose == "vision"
            ? "画像を読むVision処理に使うモデルを選択します。"
            : "選んだモデルを Stage 1 と Stage 2 の両方に使います（段ごとに別のモデルは選べません）。段ごとに測ってあるモデルは、低いほうの段の順に並べます。"))
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
                if hasVisionTab { model.display.preferences.visionModelReference = draftVisionReference.isEmpty ? nil : draftVisionReference }
                if model.display.saveError != nil { throw HostError("interface_settings_save_failed") }
            }
            dismiss()
        } catch { selectionError = error.localizedDescription }
    }

    private func modelCard(_ entry: ProviderModelSettings, provider: ProviderSettings) -> some View {
        let reference = provider.id + ":" + entry.id
        let selected = reference == selectedReference
        return Button {
            guard !cannotSelect, let settings,
                  SettingsModel.isRegisteredModelAvailable(reference, purpose: selectedPurpose, settings: settings) else { return }
            if hasVisionTab && selectedPurpose == "vision" { draftVisionReference = reference }
            else { draftReference = reference }
            selectionError = nil
            if immediateSelection { Task { await confirmSelection() } }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .top, spacing: 8) {
                    Text(entry.label.isEmpty ? entry.id : entry.label)
                        .inkuFont(13, weight: .medium).strikethrough(entry.eol == true)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                    if selected { Image(systemName: "checkmark").foregroundStyle(Color.accentColor) }
                }
                if let status = statusLabel(entry) {
                    Text(status).inkuFont(12).foregroundStyle(.red)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 20, alignment: .topLeading)
            .padding(10)
            .background(selected ? Color.accentColor.opacity(0.12) : Color.primary.opacity(0.035),
                        in: RoundedRectangle(cornerRadius: 8))
            .overlay {
                RoundedRectangle(cornerRadius: 8)
                    .stroke(selected ? Color.accentColor : Color.primary.opacity(0.18), lineWidth: selected ? 2 : 1)
            }
            .contentShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
        .disabled(cannotSelect || !entry.isSelectable)
        .opacity(entry.isSelectable ? 1 : 0.55)
        .focused($focusedReference, equals: reference)
        .onHover { inside in
            if inside { hoveredReference = reference }
            else if hoveredReference == reference { hoveredReference = nil }
        }
        .accessibilityElement(children: .combine)
        .accessibilityValue(selected ? model.display.localized("選択中") : "")
        .accessibilityHint(metadataText(entry, provider: provider))
        .anchorPreference(key: BatchModelCardBounds.self, value: .bounds) { [reference: $0] }
    }

    private func sortedModels(for provider: ProviderSettings) -> [ProviderModelSettings] {
        let models = SettingsModel.registeredModels(for: provider, purpose: selectedPurpose)
        if provider.kind == .chatGPTPlan { return models }
        return models.sorted { first, second in
            if first.isSelectable != second.isSelectable { return first.isSelectable }
            let firstLevel = sharedRecommendationLevel(first), secondLevel = sharedRecommendationLevel(second)
            if firstLevel != secondLevel { return firstLevel > secondLevel }
            let firstLabel = first.label.isEmpty ? first.id : first.label
            let secondLabel = second.label.isEmpty ? second.id : second.label
            return firstLabel.localizedCompare(secondLabel) == .orderedAscending
        }
    }

    private func entry(for reference: String, purpose: String? = nil) -> (provider: ProviderSettings, model: ProviderModelSettings)? {
        for provider in settings?.providers ?? [] {
            if let model = SettingsModel.registeredModels(for: provider, purpose: purpose ?? selectedPurpose).first(where: { provider.id + ":" + $0.id == reference }) {
                return (provider, model)
            }
        }
        return nil
    }

    private func metadata(_ entry: ProviderModelSettings, provider: ProviderSettings) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let status = statusLabel(entry) { metadataRow("状態", status) }
            metadataRow("用途", purposes(entry))
            ForEach(recommendationRows(entry), id: \.0) { row in metadataRow(row.0, row.1) }
            metadataRow("速度", speed(entry, provider: provider))
            metadataRow("評価コメント", comment(entry))
        }
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
        .shadow(color: .black.opacity(0.18), radius: 12, y: 5)
        .accessibilityHidden(true)
    }

    private func metadataRow(_ key: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(model.display.localized(key)).inkuFont(11).foregroundStyle(.secondary)
            Text(value).inkuFont(12).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func sharedRecommendationLevel(_ entry: ProviderModelSettings) -> Int {
        if selectedPurpose == "vision" { return entry.recommendationVision ?? entry.recommendationLevel ?? 0 }
        let staged = [entry.recommendationStage1, entry.recommendationStage2].compactMap { $0 }.min()
        return max(0, min(5, staged ?? entry.recommendationLLM ?? entry.recommendationLevel ?? 0))
    }

    private func recommendationRows(_ entry: ProviderModelSettings) -> [(String, String)] {
        if selectedPurpose == "vision" { return [("オススメ度", ModelGuidance.recommendation(entry.recommendationVision ?? entry.recommendationLevel))] }
        let llm = entry.recommendationLLM ?? entry.recommendationLevel
        if entry.recommendationStage1 != nil || entry.recommendationStage2 != nil {
            return [("オススメ度 / Stage 1", ModelGuidance.recommendation(entry.recommendationStage1 ?? llm)),
                    ("オススメ度 / Stage 2", ModelGuidance.recommendation(entry.recommendationStage2 ?? llm))]
        }
        return [("オススメ度", ModelGuidance.recommendation(llm))]
    }

    private func purposes(_ entry: ProviderModelSettings) -> String {
        entry.purposes.map { $0 == "vision" ? "Vision" : "LLM" }.joined(separator: " / ")
    }

    private func speed(_ entry: ProviderModelSettings, provider: ProviderSettings) -> String {
        let guidance = ModelGuidanceCatalog.bundled?.guidance(for: provider.id + ":" + entry.id,
                                                           providers: settings?.providers ?? [])
        guard guidance?.speedHidden != true, let speed = entry.speedLabel, !speed.isEmpty else { return "—" }
        return speed
    }

    private func comment(_ entry: ProviderModelSettings) -> String {
        let candidates = model.display.preferences.language == "en"
            ? [entry.commentEN, entry.commentJA] : [entry.commentJA, entry.commentEN]
        return candidates.compactMap { $0 }.first { !$0.isEmpty } ?? "—"
    }

    private func statusLabel(_ entry: ProviderModelSettings) -> String? {
        if entry.eol == true {
            return model.display.localized("提供終了") + (entry.eolDate.map { " (\($0))" } ?? "")
        }
        return entry.requiresSubscription == true ? model.display.localized("有料プラン限定") : nil
    }

    private func metadataText(_ entry: ProviderModelSettings, provider: ProviderSettings) -> String {
        let rows = [("用途", purposes(entry))] + recommendationRows(entry)
            + [("速度", speed(entry, provider: provider)), ("評価コメント", comment(entry))]
        return rows.map { model.display.localized($0.0) + ": " + $0.1 }.joined(separator: ". ")
    }
}

private struct BatchModelCardBounds: PreferenceKey {
    static var defaultValue: [String: Anchor<CGRect>] { [:] }
    static func reduce(value: inout [String: Anchor<CGRect>], nextValue: () -> [String: Anchor<CGRect>]) {
        value.merge(nextValue(), uniquingKeysWith: { _, new in new })
    }
}
