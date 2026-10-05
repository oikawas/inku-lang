import InkuHost
import InkuPersistence
import SwiftUI

@MainActor
public struct ComparisonView: View {
    @Bindable var model: AppModel
    @State private var comparison: ComparisonModel
    @Environment(\.dismiss) private var dismiss

    public init(model: AppModel, work: SavedWork? = nil, kind: ComparisonKind = .catalog) {
        self.model = model
        _comparison = State(initialValue: ComparisonModel(work: work, kind: kind))
    }

    public var body: some View {
        @Bindable var comparison = comparison
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text(model.display.localized(comparison.kind == .catalog ? "色カタログを変える" : "モデルを変える")).inkuFont(16, weight: .semibold)
                    Spacer()
                    Button(model.display.localized(comparison.hasUnsaved ? "破棄して閉じる" : "閉じる")) {
                        Task { await comparison.stop(app: model); comparison.discardCandidates(); dismiss() }
                    }.keyboardShortcut(.cancelAction)
                        .disabled(comparison.stopping || model.isBusy && !comparison.running)
                }
                if let work = comparison.original {
                    HStack(alignment: .top, spacing: 14) {
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(width: 150, height: 130)
                        VStack(alignment: .leading, spacing: 8) {
                            Text(model.display.localized("元の作品")).inkuFont(14, weight: .semibold)
                            Text(work.effectiveSourceText).textSelection(.enabled)
                            Text(model.display.localizedFormat("配色 %@ · シード %@", work.renderColorCatalogID ?? work.catalogID ?? model.display.localized("不明"), work.renderSeed ?? model.display.localized("不明")))
                                .inkuFont(12).foregroundStyle(.secondary)
                            Text(model.display.localized("候補はまだ履歴に保存されていません。選択して保存した候補が履歴と系譜に追加されます。"))
                                .inkuFont(12).foregroundStyle(.secondary)
                        }
                    }
                    if comparison.kind == .catalog { catalogChoices }
                    else { modelChoices }
                    HStack {
                        if comparison.running {
                            ProgressView().controlSize(.small)
                            Button(model.display.localized(comparison.stopping ? "停止中" : "停止"), role: .destructive) { Task { await comparison.stop(app: model) } }
                                .disabled(comparison.stopping)
                        } else {
                            Button(model.display.localizedFormat("%ld件の候補を生成", comparison.requestedCount), systemImage: "square.grid.2x2") {
                                Task { await comparison.generate(app: model) }
                            }.buttonStyle(.borderedProminent).disabled(!comparison.canGenerate || model.isBusy)
                                // RefinementModelCompareView.svelte:58.
                                .inkuTooltip(comparison.kind == .model
                                             ? model.display.tooltip("選んだモデルで記述から描き直し、候補を並べます。記述、色カタログ、キャンバスは保ちます。", serverKey: "tooltipModelCompare")
                                             : "", placement: .bottom)
                        }
                        Spacer()
                        Button(model.display.localizedFormat("選択した%ld案を採用して閉じる", comparison.selectedCount), systemImage: "checkmark.circle") {
                            Task { if await comparison.saveSelected(app: model) { dismiss() } }
                        }.disabled(comparison.selectedCount == 0 || comparison.running || model.isBusy)
                            .buttonStyle(.borderedProminent)
                    }
                    if comparison.hasUnsaved {
                        Button(model.display.localized("候補を破棄"), role: .destructive) { comparison.discardCandidates() }
                            .disabled(comparison.running || model.isBusy)
                    }
                    if !comparison.candidates.isEmpty { candidateGrid }
                } else {
                    ContentUnavailableView(model.display.localized("保存作品を選択"), systemImage: "photo", description: Text(model.display.localized("ライブラリか制作画面で元の作品を選択してください。")))
                }
                Text(model.display.message(comparison.status)).inkuFont(13).foregroundStyle(.secondary)
                if let error = comparison.errorText { Text(error).foregroundStyle(.red).textSelection(.enabled) }
                ForEach(Array(comparison.failures.enumerated()), id: \.offset) { _, failure in
                    Text(failure).inkuFont(13).foregroundStyle(.red).textSelection(.enabled)
                }
            }.padding(20)
        }
        #if os(macOS)
        .frame(minWidth: 540, idealWidth: 850, minHeight: 550)
        #endif
        .task {
            await comparison.initialize(app: model)
            // Web `model_inspection_selected_models`: the last choice, less models no longer offered (at most 4). Those
            // leave the saved choice at once, as the Web's effect writes the filtered list back.
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

    private var catalogChoices: some View {
        GroupBox(model.display.localized("同じScoreを別の配色で描く")) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 145))], alignment: .leading, spacing: 10) {
                ForEach(model.catalogs.filter { $0.id != (comparison.original?.renderColorCatalogID ?? comparison.original?.catalogID) }, id: \.id) { catalog in
                    Text(catalog.name).inkuFont(13)
                }
            }.padding(6)
        }
    }

    private var modelChoices: some View {
        return GroupBox(model.display.localized("記述を各モデルで読み直す")) {
            VStack(alignment: .leading, spacing: 8) {
                Text(model.display.localized("使用中のLLMモデルを4件まで選択してください。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                ForEach(comparison.modelProviders) { provider in
                    Text(provider.displayName).inkuFont(12, weight: .semibold)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 190))], alignment: .leading) {
                        ForEach(SettingsModel.batchModels(for: provider)) { entry in
                            comparisonModelCard(entry, provider: provider)
                        }
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
            }.padding(6)
        }
    }

    private func comparisonModelCard(_ entry: ProviderModelSettings, provider: ProviderSettings) -> some View {
        let reference = provider.id + ":" + entry.id
        let selected = comparison.selectedModelReferences.contains(reference)
        let target = reference == comparison.targetModelReference
        let full = !selected && comparison.modelReferences.count >= 4
        return VStack(alignment: .leading, spacing: 6) {
            Toggle(entry.label.isEmpty ? entry.id : entry.label, isOn: Binding(
                get: { selected }, set: {
                    comparison.selectModel(reference, selected: $0)
                    model.display.preferences.comparisonModels = Array(comparison.modelReferences.prefix(4))
                }))
                .disabled(comparison.running || model.isBusy || comparison.hasUnsaved || comparison.sourceIsLocked || target || full || !entry.isSelectable)
                .strikethrough(entry.eol == true)
            if target { Text(model.display.localized("元の作品のモデル")).inkuFont(12).foregroundStyle(.secondary) }
            if entry.eol == true {
                Text(model.display.localized("提供終了") + (entry.eolDate.map { " (\($0))" } ?? "")).inkuFont(12).foregroundStyle(.secondary)
            } else if entry.requiresSubscription == true {
                Text(model.display.localized("有料プラン限定")).inkuFont(12).foregroundStyle(.secondary)
            }
            if comparison.failedModelReferences.contains(reference) { Text(model.display.localized("このモデルの候補を用意できませんでした。")).inkuFont(12).foregroundStyle(.red) }
            DisclosureGroup(model.display.localized("モデルの適性・用途")) {
                RegisteredModelMetadataView(entry: entry, provider: provider, display: model.display)
            }.inkuFont(12)
        }.padding(10).background(.quaternary.opacity(0.2), in: RoundedRectangle(cornerRadius: 8))
    }

    private var candidateGrid: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 210))], alignment: .leading, spacing: 16) {
            ForEach(comparison.candidates) { candidate in
                VStack(alignment: .leading, spacing: 10) {
                    ArtworkThumbnail(work: candidate.work, renderer: model.renderer).frame(height: 185)
                    Text(candidate.label).inkuFont(14, weight: .semibold).textSelection(.enabled)
                    ProviderObservationView(model: model, metrics: candidate.prepared.providerMetrics,
                        workID: candidate.savedWork?.id, executionID: candidate.prepared.executionID)
                    if let saved = candidate.savedWork {
                        HStack {
                            Label(model.display.localized("保存済み"), systemImage: "checkmark.circle").foregroundStyle(.secondary)
                            Spacer()
                            Button(model.display.localized("作品を開く")) { Task { await model.selectWork(saved) } }
                                .disabled(comparison.running || model.isBusy)
                        }.inkuFont(12)
                    } else {
                        Toggle(model.display.localized("この候補を保存"), isOn: Binding(get: { candidate.selected },
                            set: { comparison.selectCandidate(candidate.id, selected: $0) }))
                            .disabled(comparison.running || model.isBusy)
                        Text(model.display.localized("未保存")).inkuFont(12).foregroundStyle(.secondary)
                    }
                }.padding(12).background(.quaternary.opacity(0.3), in: RoundedRectangle(cornerRadius: 10))
            }
        }
    }
}
