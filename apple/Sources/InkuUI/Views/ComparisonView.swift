import SwiftUI

@MainActor
public struct ComparisonView: View {
    @Bindable var model: AppModel
    @State private var comparison = ComparisonModel()
    @Environment(\.dismiss) private var dismiss

    public init(model: AppModel) { self.model = model }

    public var body: some View {
        @Bindable var comparison = comparison
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text(model.display.localized("候補を比較")).font(.title2.weight(.semibold))
                    Spacer()
                    Button(model.display.localized("閉じる")) { Task { await comparison.stop(app: model); dismiss() } }
                        .disabled(comparison.stopping || model.isBusy && !comparison.running)
                }
                if let work = comparison.original {
                    HStack(alignment: .top, spacing: 14) {
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(width: 150, height: 130)
                        VStack(alignment: .leading, spacing: 8) {
                            Text(model.display.localized("元の作品")).font(.headline)
                            Text(work.effectiveSourceText).textSelection(.enabled)
                            Text(model.display.localizedFormat("配色 %@ · シード %@", work.renderColorCatalogID ?? work.catalogID ?? model.display.localized("不明"), work.renderSeed ?? model.display.localized("不明")))
                                .font(.caption).foregroundStyle(.secondary)
                            Text(model.display.localized("候補はまだ履歴に保存されていません。選択して保存した候補が履歴と系譜に追加されます。"))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Picker(model.display.localized("比較する条件"), selection: $comparison.kind) {
                        Text(model.display.localized("配色")).tag(ComparisonKind.catalog)
                        Text(model.display.localized("モデル")).tag(ComparisonKind.model)
                    }.pickerStyle(.segmented).frame(maxWidth: 300).disabled(comparison.running || model.isBusy)
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
                        }
                        Spacer()
                        Button(model.display.localizedFormat("選択した%ld件を保存", comparison.selectedCount), systemImage: "square.and.arrow.down") {
                            Task { await comparison.saveSelected(app: model) }
                        }.disabled(comparison.selectedCount == 0 || comparison.running || model.isBusy)
                    }
                    if !comparison.candidates.isEmpty { candidateGrid }
                } else {
                    ContentUnavailableView(model.display.localized("保存作品を選択"), systemImage: "photo", description: Text(model.display.localized("ライブラリか制作画面で元の作品を選択してください。")))
                }
                Text(model.display.message(comparison.status)).font(.callout).foregroundStyle(.secondary)
                if let error = comparison.errorText { Text(error).foregroundStyle(.red).textSelection(.enabled) }
                ForEach(Array(comparison.failures.enumerated()), id: \.offset) { _, failure in
                    Text(failure).font(.callout).foregroundStyle(.red).textSelection(.enabled)
                }
            }.padding(20)
        }
        .frame(minWidth: 540, idealWidth: 850, minHeight: 550)
        .task { await comparison.initialize(app: model) }
        .interactiveDismissDisabled(comparison.running || model.isBusy)
        .onDisappear { Task { await comparison.stop(app: model) } }
    }

    private var catalogChoices: some View {
        GroupBox(model.display.localized("同じScoreを別の配色で描く")) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 145))], alignment: .leading, spacing: 10) {
                ForEach(model.catalogs.filter { $0.id != comparison.original?.renderColorCatalogID && $0.id != comparison.original?.catalogID }, id: \.id) { catalog in
                    Toggle(catalog.name, isOn: Binding(get: { comparison.selectedCatalogIDs.contains(catalog.id) },
                        set: { comparison.selectCatalog(catalog.id, selected: $0) }))
                        .disabled(comparison.running || model.isBusy)
                }
            }.padding(6)
        }
    }

    private var modelChoices: some View {
        @Bindable var comparison = comparison
        return GroupBox(model.display.localized("記述を各モデルで読み直す")) {
            VStack(alignment: .leading, spacing: 8) {
                Text(model.display.localized("サービスID:モデルIDを1行に1件入力します。各候補では同じモデルを描画の両段階に使います。"))
                    .font(.caption).foregroundStyle(.secondary)
                TextEditor(text: $comparison.modelReferencesText).font(.system(.body, design: .monospaced)).frame(minHeight: 95)
                    .disabled(comparison.running || model.isBusy || comparison.sourceIsLocked)
                    .accessibilityLabel(model.display.localized("比較するモデル"))
                if comparison.sourceIsLocked {
                    Text(model.display.localized("DDLを編集した作品は記述を読み直せません。配色の比較を選択してください。"))
                        .font(.callout).foregroundStyle(.secondary)
                }
            }.padding(6)
        }
    }

    private var candidateGrid: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 210))], alignment: .leading, spacing: 16) {
            ForEach(comparison.candidates) { candidate in
                VStack(alignment: .leading, spacing: 10) {
                    ArtworkThumbnail(work: candidate.work, renderer: model.renderer).frame(height: 185)
                    Text(candidate.label).font(.headline).textSelection(.enabled)
                    if let saved = candidate.savedWork {
                        HStack {
                            Label(model.display.localized("保存済み"), systemImage: "checkmark.circle").foregroundStyle(.secondary)
                            Spacer()
                            Button(model.display.localized("作品を開く")) { Task { await model.selectWork(saved) } }
                                .disabled(comparison.running || model.isBusy)
                        }.font(.caption)
                    } else {
                        Toggle(model.display.localized("この候補を保存"), isOn: Binding(get: { candidate.selected },
                            set: { comparison.selectCandidate(candidate.id, selected: $0) }))
                            .disabled(comparison.running || model.isBusy)
                        Text(model.display.localized("未保存")).font(.caption).foregroundStyle(.secondary)
                    }
                }.padding(12).background(.quaternary.opacity(0.3), in: RoundedRectangle(cornerRadius: 10))
            }
        }
    }
}
