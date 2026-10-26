import InkuHost
import InkuPersistence
import SwiftUI

@MainActor
public struct ComparisonView: View {
    @Bindable var model: AppModel
    @State private var comparison: ComparisonModel
    @State private var namingProviders: [ProviderSettings] = []
    @Environment(\.dismiss) private var dismiss
    private let onCommitted: (SavedWork) -> Void

    public init(model: AppModel, work: SavedWork? = nil, kind: ComparisonKind = .catalog, onCommitted: @escaping (SavedWork) -> Void = { _ in }) {
        self.model = model
        self.onCommitted = onCommitted
        _comparison = State(initialValue: ComparisonModel(work: work, kind: kind))
    }

    public var body: some View {
        Group {
            if let work = comparison.original {
                RefinementDialog(model: model, title: comparison.kind == .catalog ? "色カタログを変える" : "モデルを変える", work: work,
                    closeDisabled: comparison.running || comparison.hasUnsaved || model.isBusy, onClose: { dismiss() },
                    targetTitle: comparison.kind == .model ? model.display.webCopy("modelCompareTargetTitle", "対象作品") : "推敲対象",
                    targetModelName: comparison.kind == .model ? ModelNaming(providers: namingProviders).displayName(work.stage1Model ?? work.stage2Model) : nil,
                    topControls: comparison.kind == .model ? AnyView(modelChoices) : nil) {
                    VStack(alignment: .leading, spacing: 12) {
                        if comparison.kind == .catalog { catalogControls }
                        if !comparison.running && comparison.kind == .catalog && comparison.candidates.isEmpty {
                            Button(model.display.webCopy("colorCatalogChangeDraw", "ほかの色カタログで描く"), systemImage: "play.fill") {
                                Task { await comparison.generate(app: model) }
                            }.buttonStyle(.borderedProminent).disabled(!comparison.canGenerate || model.isBusy)
                                .inkuTooltip(comparison.kind == .model
                                    ? model.display.tooltip("選んだモデルで記述から描き直し、候補を並べます。記述、色カタログ、キャンバスは保ちます。", serverKey: "tooltipModelCompare") : "", placement: .bottom)
                        }
                        Label(model.display.localized(comparison.kind == .catalog ? "超高速（LLM不要）" : "低速（LLM・API使用）"), systemImage: "clock")
                            .inkuFont(11).foregroundStyle(.secondary)
                        if comparison.running {
                            RunStatusView(display: model.display, label: comparison.status, stopping: comparison.stopping,
                                onStop: { Task { await comparison.stop(app: model) } }) { ProviderProgressView(model: model) }
                            if !comparison.saving {
                                VariationLanesView(display: model.display, states: comparison.laneStates.map {
                                    switch $0 { case .waiting: .waiting; case .running: .running; case .done: .done }
                                }, labels: comparison.laneLabels, named: comparison.kind == .model)
                            }
                        }
                    }
                } options: {
                    RefinementOptionsGrid(model: model, options: comparison.candidates.map {
                        RefinementOption(id: $0.id, work: $0.work, label: $0.label, selected: $0.selected, saved: $0.savedWork != nil,
                            observation: $0.prepared)
                    }, previewID: comparison.previewID, maxColumns: comparison.kind == .catalog ? 4 : 2,
                        busy: comparison.running || model.isBusy,
                        placeholder: comparison.kind == .catalog ? "色カタログを替えた候補を並べます。" : "モデルを選んで描くと、候補をここに並べます。",
                        errors: comparison.failures + [comparison.errorText].compactMap { $0 }, status: comparison.status,
                        onPreview: { comparison.preview($0) }, onSelect: { comparison.selectCandidate($0, selected: $1) },
                        onDiscard: { comparison.discardCandidates(); dismiss() },
                        onSave: { Task {
                            if await comparison.saveSelected(app: model) {
                                if let latest = comparison.candidates.compactMap(\.savedWork).last { onCommitted(latest) }
                                dismiss()
                            }
                        } })
                }
            } else {
                VStack {
                    if let error = comparison.errorText { Text(model.display.message(error)).foregroundStyle(.red) }
                    else { ProgressView() }
                    Button(model.display.localized("閉じる")) { dismiss() }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task {
            await comparison.initialize(app: model)
            if comparison.kind == .model, comparison.contextAvailable, let saved = model.display.preferences.comparisonModels {
                let kept = Array(saved.filter(comparison.isModelChoice).prefix(4))
                if kept != saved { model.display.preferences.comparisonModels = kept }
                for reference in kept { comparison.selectModel(reference, selected: true) }
            }
            if comparison.kind == .catalog, comparison.canGenerate { await comparison.generate(app: model) }
        }
        .task(id: model.providerSettingsRevision) { namingProviders = (await model.hostSettings()).providers }
        .interactiveDismissDisabled(comparison.running || comparison.hasUnsaved || model.isBusy)
        .onDisappear { Task { await comparison.stop(app: model); comparison.discardCandidates() } }
    }

    private var catalogControls: some View {
        let id = comparison.original?.renderColorCatalogID ?? comparison.original?.catalogID ?? ""
        return VStack(alignment: .leading, spacing: 6) {
            Text(model.display.localized("いまの色カタログ") + ": " + (model.catalogs.first { $0.id == id }?.name ?? id)).inkuFont(12, weight: .semibold)
            Text(model.display.tooltip("保存済みの指示書を別の色カタログで描きます。配置とタッチは保ちます。", serverKey: "tooltipCanvasVaryColor"))
                .inkuFont(12).foregroundStyle(.secondary)
        }
    }

    private var modelChoices: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(model.display.localized(comparison.inheritWild ? "筆致制限（継承）" : "筆致制限")).inkuFont(12).foregroundStyle(.secondary)
                Button(model.display.localized("暴れる")) {
                    comparison.wildOverride = !effectiveWild; comparison.inheritWild = false
                }.disabled(comparison.running || model.isBusy)
                    .buttonStyle(.bordered).tint(effectiveWild ? Color.accentColor : Color.secondary)
                    .accessibilityValue(model.display.localized(effectiveWild ? "入" : "切"))
                Spacer()
                Button(model.display.webCopy("modelCompareButton", "選んだモデルで描く"), systemImage: "play.fill") {
                    Task { await comparison.generate(app: model) }
                }.buttonStyle(.borderedProminent).disabled(!comparison.canGenerate || model.isBusy)
                    .inkuTooltip(model.display.tooltip("選んだモデルで記述から描き直し、候補を並べます。記述、色カタログ、キャンバスは保ちます。", serverKey: "tooltipModelCompare"))
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 8)], alignment: .leading, spacing: 8) {
                ForEach(comparison.modelProviders) { provider in
                    ForEach(SettingsModel.batchModels(for: provider)) { entry in comparisonModelCard(entry, provider: provider) }
                }
            }
            Text(model.display.localizedFormat("選択中: %ld / 4", comparison.modelReferences.count)).inkuFont(12).monospacedDigit()
            if comparison.modelProviders.isEmpty {
                Text(model.display.localized("選べるモデルがありません。設定 → モデル設定 で使用するモデルを選択してください。"))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
            if comparison.sourceIsLocked {
                Text(model.display.localized("DDLを編集した作品は記述を読み直せません。配色の比較を選択してください。"))
                    .inkuFont(13).foregroundStyle(.secondary)
            }
        }
    }

    private var effectiveWild: Bool { comparison.inheritWild ? comparison.original?.renderWild ?? false : comparison.wildOverride }
    private func comparisonModelCard(_ entry: ProviderModelSettings, provider: ProviderSettings) -> some View {
        let reference = provider.id + ":" + entry.id
        let selected = comparison.selectedModelReferences.contains(reference)
        let target = reference == comparison.targetModelReference || reference == comparison.original?.stage2Model
        let full = !selected && comparison.modelReferences.count >= 4
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 4) {
                Toggle(entry.label.isEmpty ? entry.id : entry.label, isOn: Binding(
                    get: { selected }, set: {
                        comparison.selectModel(reference, selected: $0)
                        model.display.preferences.comparisonModels = Array(comparison.modelReferences.prefix(4))
                    })).inkuFont(12, weight: .semibold)
                    .disabled(comparison.running || model.isBusy || comparison.sourceIsLocked || target || full || !entry.isSelectable)
                    .strikethrough(entry.modelFold == "eol")
                Spacer(minLength: 0)
            }
            Text(model.display.providerName(provider)).inkuFont(10).foregroundStyle(.secondary)
            if entry.isNotRecommended(for: "llm") {
                Text(BatchModelPickerView.notRecommended(language: model.display.preferences.language))
                    .inkuFont(10, weight: .semibold).foregroundStyle(.red)
            }
            if target { Text(model.display.localized("元の作品のモデル")).inkuFont(10).foregroundStyle(.secondary) }
            if comparison.failedModelReferences.contains(reference) { Text(model.display.localized("このモデルの候補を用意できませんでした。")).inkuFont(10).foregroundStyle(.red) }
        }.padding(8).frame(maxWidth: .infinity, minHeight: 50, alignment: .topLeading)
            .background(selected ? Color.accentColor.opacity(0.12) : InkuColor.bg2)
            // Published for drawing though it did not answer when measured: framed in red (2026-10-26).
            .overlay(Rectangle().stroke(entry.isNotRecommended(for: "llm") ? Color.red : selected || target ? Color.accentColor : InkuColor.border,
                                        lineWidth: entry.isNotRecommended(for: "llm") ? 2 : 1))
            .inkuTooltip(model.display.preferences.showTooltips ? modelMetadata(entry, provider: provider) : "")
            .accessibilityHint(modelMetadata(entry, provider: provider))
    }

    private func modelMetadata(_ entry: ProviderModelSettings, provider: ProviderSettings) -> String {
        let language = model.display.preferences.language
        let guidance = ModelGuidanceCatalog.bundled?.guidance(for: provider.id + ":" + entry.id, providers: comparison.modelProviders)
        let purpose = ["llm", "vision"].map { purpose in
            let label = purpose == "llm" ? "LLM" : "Vision"
            return label + (ModelMetadataPresentation.supports(entry, purpose: purpose) ? ""
                : language == "en" ? " (not selectable)" : "（選べません）")
        }.joined(separator: " / ")
        let comments = language == "en" ? [entry.commentEN, entry.commentJA] : [entry.commentJA, entry.commentEN]
        let recommendation = entry.recommendationLLM ?? entry.recommendationLevel
        let recommendations = entry.recommendationStage1 != nil || entry.recommendationStage2 != nil
            ? [("オススメ度 / Stage 1", ModelGuidance.recommendation(entry.recommendationStage1 ?? recommendation)),
               ("オススメ度 / Stage 2", ModelGuidance.recommendation(entry.recommendationStage2 ?? recommendation))]
            : [("オススメ度", ModelGuidance.recommendation(recommendation))]
        let rows = [("用途", purpose)] + recommendations
            + [("概算コスト", ModelMetadataPresentation.cost(entry, language: language)),
               ("速度", ModelMetadataPresentation.speed(entry, hidden: guidance?.speedHidden == true, language: language)),
               ("評価コメント", comments.compactMap { $0 }.first { !$0.isEmpty } ?? "—")]
        return (entry.resolvedLabels.map { $0.name(language: language) }
            + rows.map { model.display.localized($0.0) + ": " + $0.1 }).joined(separator: "\n")
    }
}
