import InkuPersistence
import SwiftUI

@MainActor
public struct ReplayComparisonView: View {
    @Bindable private var model: AppModel
    @State private var comparison: ReplayComparisonModel
    @State private var closing = false
    @Environment(\.dismiss) private var dismiss

    public init(model: AppModel, work: SavedWork) {
        self.model = model
        _comparison = State(initialValue: ReplayComparisonModel(work: work))
    }

    public var body: some View {
        VStack(spacing: 0) {
            Text(model.display.localized("再現を比較"))
                .inkuFont(16, weight: .semibold)
                .frame(maxWidth: .infinity, alignment: .leading).padding(20)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    sourceSummary
                    warnings
                    if let snapshot = comparison.snapshot {
                        ProviderObservationView(model: model, metrics: snapshot.providerMetrics, workID: snapshot.workID)
                    }
                    if let error = comparison.errorText {
                        Label {
                            Text(model.display.message(error)).textSelection(.enabled)
                        } icon: { Image(systemName: "exclamationmark.triangle") }
                            .inkuFont(13).foregroundStyle(.red)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 18)], alignment: .leading, spacing: 18) {
                        artworkCard(title: "保存時の作品", version: recordedVersion, svg: originalSVG)
                        artworkCard(title: "現行エンジンによる描き直し", version: comparison.snapshot?.currentVersion,
                                    svg: comparison.snapshot?.replayedSVG, replay: true)
                    }
                }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider()
            footer.padding(20).background(.bar)
        }
        #if os(macOS)
        .frame(minWidth: 520, idealWidth: 1000, minHeight: 600, idealHeight: 760)
        #endif
        .task { await comparison.compare(app: model) }
        .interactiveDismissDisabled(comparison.running || closing)
        .onDisappear { Task { await comparison.close(app: model) } }
    }

    private var recordedVersion: String? {
        if let snapshot = comparison.snapshot { return snapshot.recordedVersion }
        return comparison.work.renderEngineVersion
    }

    private var originalSVG: String? {
        let svg = comparison.snapshot?.originalSVG ?? comparison.work.svg
        return svg.isEmpty ? nil : svg
    }

    private var sourceSummary: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.display.localized("記述")).inkuFont(14, weight: .semibold)
            Text(comparison.work.effectiveSourceText.isEmpty
                ? model.display.localized("この作品には記述が保存されていません。")
                : comparison.work.effectiveSourceText)
                .inkuFont(13).lineLimit(4).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                .inkuTooltip(model.display.preferences.showTooltips ? comparison.work.effectiveSourceText : "")
            Text(model.display.localized("保存時のSVGと、同じ保存条件を現行エンジンで描いた結果を比較します。作品・履歴・系譜は変わりません。"))
                .inkuFont(12).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.replayComparisonPanel()
    }

    @ViewBuilder private var warnings: some View {
        if let snapshot = comparison.snapshot {
            if let seed = snapshot.provisionalSeed {
                warning(model.display.localizedFormat("描画シードとタッチの言葉が保存されていないため、シード %@ を補った暫定表示です。", seed))
            }
            if let recorded = snapshot.recordedVersion {
                if recorded != snapshot.currentVersion {
                    warning(model.display.localizedFormat("保存時の描画エンジンは %@、現行は %@ です。版の違いにより見た目が変わることがあります。", recorded, snapshot.currentVersion))
                }
            } else {
                warning(model.display.localizedFormat("保存時の描画エンジンの版は記録されていません。現行の %@ で描き直しています。", snapshot.currentVersion))
            }
        }
    }

    private func warning(_ message: String) -> some View {
        Label(message, systemImage: "exclamationmark.triangle")
            .inkuFont(13).fixedSize(horizontal: false, vertical: true)
            .replayComparisonPanel()
    }

    private func artworkCard(title: String, version: String?, svg: String?, replay: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(model.display.localized(title)).inkuFont(14, weight: .semibold)
                    .fixedSize(horizontal: false, vertical: true)
                Text(model.display.localizedFormat("描画エンジンの版: %@", version ?? model.display.localized(replay ? "未取得" : "記録なし")))
                    .inkuFont(12).foregroundStyle(.secondary).textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }.frame(maxWidth: .infinity, minHeight: 64, alignment: .topLeading)
            Group {
                if let svg {
                    ArtworkCanvas(svg: svg, renderer: model.renderer)
                } else if comparison.running {
                    ProgressView(model.display.localized(replay ? "現行エンジンで描き直し中" : "保存時のSVGを読み込み中"))
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ContentUnavailableView(model.display.localized("比較結果はまだありません。"), systemImage: "photo.on.rectangle")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }.frame(height: 360)
        }.replayComparisonPanel()
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(model.display.message(comparison.status)).inkuFont(13).foregroundStyle(.secondary)
                .lineLimit(2).fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 12) {
                if comparison.running {
                    ProgressView().controlSize(.small)
                    Button(model.display.localized(comparison.stopping ? "停止中" : "停止")) {
                        Task { await comparison.stop(app: model) }
                    }.disabled(comparison.stopping || closing)
                } else if comparison.snapshot == nil {
                    Button(model.display.localized("もう一度比較する"), systemImage: "arrow.clockwise") {
                        Task { await comparison.compare(app: model) }
                    }.disabled(model.isBusy || closing || comparison.closed)
                }
                Spacer()
                Button(model.display.localized("閉じる")) { Task { await close() } }
                    .buttonStyle(.borderedProminent).keyboardShortcut(.cancelAction)
                    .disabled(closing || comparison.stopping)
            }
        }
    }

    private func close() async {
        guard !closing else { return }
        closing = true
        await comparison.close(app: model)
        dismiss()
    }
}

private extension View {
    func replayComparisonPanel() -> some View {
        padding(16).frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary))
    }
}
