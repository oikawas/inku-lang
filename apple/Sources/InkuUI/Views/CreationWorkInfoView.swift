import InkuPersistence
import SwiftUI

@MainActor
struct CreationWorkInfoView: View {
    @Bindable var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var sketchExpanded = false
    @State private var outputExpanded = false
    @State private var conditionsExpanded = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(model.display.localized("表示中作品の生成情報")).font(.title2)
                Spacer()
                Button(model.display.localized("閉じる")) { dismiss() }.keyboardShortcut(.cancelAction)
            }.padding(16)
            Divider()
            ScrollView {
                if let work = model.displayedWork {
                    VStack(alignment: .leading, spacing: 18) {
                        Text(work.effectiveSourceText).font(.callout).lineLimit(4).textSelection(.enabled)
                        if model.display.visible("diagnostics"), model.authoringOrigin == "stage1_generated", let ddl = work.ddl {
                            DescriptionFeedbackView(description: work.effectiveSourceText, ddl: ddl)
                        }
                        if let sketch = work.sketchText, !sketch.isEmpty {
                            DisclosureGroup(model.display.localized("写生 (Stage 0.5)"), isExpanded: $sketchExpanded) {
                                Text(sketch).font(.callout).textSelection(.enabled)
                            }
                        }
                        if let grain = work.sketchGrain {
                            Text(model.display.localizedFormat("旧写生の区切り: %@（保存記録）", grain)).font(.caption).foregroundStyle(.secondary)
                        }
                        if !model.visibleDDL.isEmpty && !model.isPreview { DdlAuthoringView(model: model) }
                        if model.display.visible("diagnostics") {
                            ProviderObservationView(model: model, metrics: model.providerMetrics, workID: work.id)
                            DisclosureGroup(model.display.localized("指示書・Score"), isExpanded: $outputExpanded) {
                                OutputView(ddl: model.visibleDDL, score: model.scoreJSON).frame(height: 230)
                            }
                        }
                        DisclosureGroup(model.display.localized("保存条件"), isExpanded: $conditionsExpanded) {
                            savedFacts(work).padding(.top, 8)
                        }
                        if !model.isPreview {
                            Button(model.display.localized("次の条件で再演奏")) { Task { await model.replayWithCurrentOptions() } }
                                .disabled(model.isBusy)
                                .help(tip("入力欄で選んだ次の条件を使い、表示中作品のScoreを再演奏します。"))
                            DisclosureGroup(model.display.localized("変奏（いまは何も動かない）")) {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(model.display.localized("動いたもの: なし")).font(.callout).foregroundStyle(.secondary)
                                    Picker(model.display.localized("変奏の幅"), selection: $model.variationAmplitude) {
                                        Text(model.display.localized("小")).tag("small")
                                        Text(model.display.localized("中")).tag("medium")
                                        Text(model.display.localized("大")).tag("large")
                                    }
                                    TextField(model.display.localized("変奏シード（空欄で新規）"), text: $model.variationSeedText).textFieldStyle(.roundedBorder)
                                    Button(model.display.localized("変奏を保存")) { Task { await model.varySelectedWork() } }
                                }.disabled(model.isBusy || work.ddl == nil)
                            }
                        }
                    }.padding(20)
                }
            }
        }
        .frame(minWidth: 620, idealWidth: 760, minHeight: 500, idealHeight: 680)
        .interactiveDismissDisabled(model.isBusy)
        .onChange(of: model.displayedWork?.id) { _, _ in
            if !model.display.preferences.keepGenerationInfo {
                sketchExpanded = false; outputExpanded = false; conditionsExpanded = false
            }
        }
    }

    private func savedFacts(_ work: SavedWork) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            LabeledContent(model.display.localized("モデル"), value: work.stage1Model ?? "DDL")
            LabeledContent(model.display.localized("配色"), value: work.renderColorCatalogName ?? work.renderColorCatalogID ?? work.catalogID ?? model.display.localized("未記録"))
            LabeledContent(model.display.localized("用紙"), value: work.renderCanvasAspectID ?? model.display.localized("未記録"))
            LabeledContent(model.display.localized("ファイル容量"), value: ByteCountFormatter.string(fromByteCount: Int64(work.svg.utf8.count), countStyle: .file))
            Text(model.display.localizedFormat("シード: %@ · 暴れる: %@", work.renderSeed ?? model.display.localized("未記録"),
                work.renderWild.map { model.display.localized($0 ? "オン" : "オフ") } ?? model.display.localized("未記録")))
                .font(.caption).foregroundStyle(.secondary)
        }.textSelection(.enabled)
    }

    private func tip(_ key: String) -> String {
        model.display.preferences.showTooltips ? model.display.localized(key) : ""
    }
}
