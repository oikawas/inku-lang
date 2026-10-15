import InkuHost
import InkuPersistence
import SwiftUI

@MainActor
public struct ComparisonView: View {
    @Bindable var model: AppModel
    @State private var comparison: ComparisonModel
    @State private var modelDetailsReference: String?
    @Environment(\.inkuWindowSize) private var windowSize
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
                        Text(model.display.localized(comparison.kind == .catalog ? "超高速（LLM不要）" : "低速（LLM・API使用）")).inkuFont(12).foregroundStyle(.secondary)
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
                Button(model.display.localized("暴れる") + " " + model.display.localized(effectiveWild ? "入" : "切")) {
                    comparison.wildOverride = !effectiveWild; comparison.inheritWild = false
                }.disabled(comparison.running || model.isBusy)
                Spacer()
                Button(model.display.webCopy("modelCompareButton", "選んだモデルで描く"), systemImage: "play.fill") {
                    Task { await comparison.generate(app: model) }
                }.buttonStyle(.borderedProminent).disabled(!comparison.canGenerate || model.isBusy)
                    .inkuTooltip(model.display.tooltip("選んだモデルで記述から描き直し、候補を並べます。記述、色カタログ、キャンバスは保ちます。", serverKey: "tooltipModelCompare"))
            }
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 8)], alignment: .leading, spacing: 8) {
                    ForEach(comparison.modelProviders) { provider in
                        ForEach(SettingsModel.batchModels(for: provider)) { entry in comparisonModelCard(entry, provider: provider) }
                    }
                }
            }.frame(height: modelGridHeight)
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
    private var modelGridHeight: CGFloat {
        let choices = comparison.modelProviders.reduce(0) { $0 + SettingsModel.batchModels(for: $1).count }
        let columns = max(1, Int(((windowSize?.width ?? 1280) - 80) / 188))
        return min(250, CGFloat(max(1, (choices + columns - 1) / columns)) * 76)
    }

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
                Button { modelDetailsReference = reference } label: { Image(systemName: "info.circle") }
                    .buttonStyle(.plain).accessibilityLabel(model.display.localized("モデルの適性・用途") + ": " + entry.id)
                    .popover(isPresented: Binding(get: { modelDetailsReference == reference }, set: { if !$0 { modelDetailsReference = nil } })) {
                        RegisteredModelMetadataView(entry: entry, provider: provider, display: model.display).padding(16).frame(width: 320)
                    }
            }
            Text(model.display.providerName(provider)).inkuFont(10).foregroundStyle(.secondary)
            if target { Text(model.display.localized("元の作品のモデル")).inkuFont(10).foregroundStyle(.secondary) }
            if comparison.failedModelReferences.contains(reference) { Text(model.display.localized("このモデルの候補を用意できませんでした。")).inkuFont(10).foregroundStyle(.red) }
        }.padding(8).frame(maxWidth: .infinity, minHeight: 50, alignment: .topLeading)
            .background(selected ? Color.accentColor.opacity(0.12) : InkuColor.bg2)
            .overlay(Rectangle().stroke(selected || target ? Color.accentColor : InkuColor.border))
    }
}
