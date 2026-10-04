import InkuHost
import SwiftUI

@MainActor
struct BatchModelPickerView: View {
    @Bindable var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.isEnabled) private var isEnabled
    @State private var settings: HostSettings?
    @State private var draftReference = ""
    @State private var hoveredReference: String?
    @State private var metadataHeight: CGFloat = 220
    @State private var selectionError = false
    @FocusState private var focusedReference: String?

    private var groups: [ProviderSettings] {
        (settings?.providers ?? []).filter { !SettingsModel.batchModels(for: $0).isEmpty }
    }
    private var inspectedReference: String? { hoveredReference ?? focusedReference }
    private var cannotSelect: Bool { model.isBusy || !isEnabled }
    private var canConfirm: Bool {
        guard !cannotSelect, let settings else { return false }
        return SettingsModel.isBatchModelAvailable(draftReference, settings: settings)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(model.display.localized("モデル選択")).font(.headline)
                Spacer()
                Button { dismiss() } label: {
                    Image(systemName: "xmark").font(.title3)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(model.display.localized("閉じる"))
                .environment(\.isEnabled, true)
            }.padding(16)
            Divider()
            Button {} label: {
                Text("Stage 1/2").font(.callout.weight(.semibold))
                    .frame(maxWidth: .infinity).padding(10)
                    .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
                    .overlay(alignment: .bottom) { Rectangle().fill(Color.accentColor).frame(height: 2) }
            }
            .buttonStyle(.plain).accessibilityAddTraits(.isSelected).padding(.horizontal, 24).padding(.vertical, 12)
            Divider()
            if selectionError {
                Text(model.display.localized("モデルの変更に失敗しました。もう一度選択してください。"))
                    .font(.callout).foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .leading).padding([.horizontal, .top], 16)
            }
            if settings == nil {
                ProgressView().frame(maxWidth: .infinity).padding(24)
            } else if groups.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    selectionSummary
                    sharedModelHint
                    Text(model.display.localized("選べるモデルがありません。設定 → モデル設定 で使用するモデルを選択してください。"))
                        .font(.callout).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        selectionSummary
                        sharedModelHint
                        ForEach(groups) { provider in
                            VStack(alignment: .leading, spacing: 7) {
                                Text(provider.displayName).font(.caption.weight(.medium)).foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 7)], spacing: 7) {
                                    ForEach(sortedModels(for: provider)) { entry in
                                        modelCard(entry, provider: provider)
                                    }
                                }
                            }
                        }
                    }.padding(16)
                }
                .frame(height: 440)
            }
            Divider()
            HStack(spacing: 8) {
                Spacer()
                Button(model.display.localized("キャンセル")) { dismiss() }
                    .keyboardShortcut(.cancelAction).environment(\.isEnabled, true)
                Button(model.display.localized("決定")) { confirmSelection() }
                    .keyboardShortcut(.defaultAction).buttonStyle(.borderedProminent)
                    .disabled(!canConfirm)
            }.padding(.horizontal, 18).padding(.vertical, 14)
        }
        .frame(width: groups.isEmpty ? 440 : 800)
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
            if settings == nil { draftReference = model.nextBatchDrawingModelReference }
            else if !SettingsModel.isBatchModelAvailable(draftReference, settings: current) { draftReference = "" }
            settings = current
            hoveredReference = nil
            focusedReference = nil
            selectionError = false
        }
    }

    private var selectionSummary: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Stage 1/2").font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
            Text(entry(for: draftReference).map { $0.model.label.isEmpty ? $0.model.id : $0.model.label }
                 ?? model.display.localized("未設定"))
                .font(.callout).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(10)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
    }

    private var sharedModelHint: some View {
        Text(model.display.localized("選んだモデルを Stage 1 と Stage 2 の両方に使います（段ごとに別のモデルは選べません）。段ごとに測ってあるモデルは、低いほうの段の順に並べます。"))
            .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
    }

    private func confirmSelection() {
        guard !cannotSelect, let settings,
              SettingsModel.isBatchModelAvailable(draftReference, settings: settings) else { return }
        model.selectNextDrawingModel(draftReference)
        if model.nextBatchDrawingModelReference == draftReference { dismiss() }
        else { selectionError = true }
    }

    private func modelCard(_ entry: ProviderModelSettings, provider: ProviderSettings) -> some View {
        let reference = provider.id + ":" + entry.id
        let selected = reference == draftReference
        return Button {
            guard !cannotSelect, let settings,
                  SettingsModel.isBatchModelAvailable(reference, settings: settings) else { return }
            draftReference = reference
            selectionError = false
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .top, spacing: 8) {
                    Text(entry.label.isEmpty ? entry.id : entry.label)
                        .font(.callout.weight(.medium)).strikethrough(entry.eol == true)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                    if selected { Image(systemName: "checkmark").foregroundStyle(Color.accentColor) }
                }
                if let status = statusLabel(entry) {
                    Text(status).font(.caption).foregroundStyle(.red)
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
        let models = SettingsModel.batchModels(for: provider)
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

    private func entry(for reference: String) -> (provider: ProviderSettings, model: ProviderModelSettings)? {
        for provider in groups {
            if let model = SettingsModel.batchModels(for: provider).first(where: { provider.id + ":" + $0.id == reference }) {
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
            Text(model.display.localized(key)).font(.caption2).foregroundStyle(.secondary)
            Text(value).font(.caption).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func sharedRecommendationLevel(_ entry: ProviderModelSettings) -> Int {
        let staged = [entry.recommendationStage1, entry.recommendationStage2].compactMap { $0 }.min()
        return max(0, min(5, staged ?? entry.recommendationLLM ?? entry.recommendationLevel ?? 0))
    }

    private func recommendationRows(_ entry: ProviderModelSettings) -> [(String, String)] {
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
