import InkuHost
import InkuPersistence
import SwiftUI

/// The menu dialogs share the Web's target column and independent options area.
@MainActor
struct RefinementDialog<Controls: View, Options: View>: View {
    @Bindable var model: AppModel
    let title: String
    let work: SavedWork
    let closeDisabled: Bool
    let onClose: () -> Void
    var targetTitle = "推敲対象"
    var targetModelName: String? = nil
    var topControls: AnyView? = nil
    @ViewBuilder let controls: () -> Controls
    @ViewBuilder let options: () -> Options
    @State private var topControlsHeight: CGFloat = 0

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(model.display.localized(title)).inkuFont(16, weight: .semibold)
                Spacer()
                Button(action: onClose) { Image(systemName: "xmark").frame(width: 26, height: 26) }
                    .buttonStyle(.bordered).accessibilityLabel(model.display.localized("閉じる"))
                    .disabled(closeDisabled).keyboardShortcut(.cancelAction)
            }.padding(.horizontal, 16).frame(height: 48)
            Divider()
            GeometryReader { geometry in
                ScrollView {
                    VStack(spacing: 12) {
                        if let topControls {
                            topControls.background {
                                GeometryReader { size in
                                    Color.clear.onAppear { topControlsHeight = size.size.height }
                                        .onChange(of: size.size.height) { _, height in topControlsHeight = height }
                                }
                            }
                        }
                        HStack(alignment: .top, spacing: 14) {
                            ScrollView {
                                VStack(alignment: .leading, spacing: 12) {
                                    RefinementTargetCard(model: model, work: work, title: targetTitle, modelName: targetModelName)
                                    controls()
                                }.frame(maxWidth: .infinity, alignment: .leading)
                            }.frame(width: 280)
                            options().frame(maxWidth: .infinity, maxHeight: .infinity)
                        }.frame(height: max(360, geometry.size.height - 32 - (topControls == nil ? 0 : topControlsHeight + 12)))
                    }.padding(16)
                }
            }
        }.background(InkuColor.panel)
        #if os(macOS)
        .frame(minWidth: 700, idealWidth: 1200, minHeight: 520, idealHeight: 780)
        #endif
    }
}

@MainActor
private struct RefinementTargetCard: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let title: String
    let modelName: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.display.localized(title)).inkuFont(11).foregroundStyle(.secondary)
            ArtworkThumbnail(work: work, thumbnails: model.thumbnails)
                .aspectRatio(work.renderCanvasAspectRatio ?? 1, contentMode: .fit)
                .accessibilityLabel(model.display.localized(title))
            if let modelName, !modelName.isEmpty {
                Text(modelName).inkuFont(11).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
            }
            Text(refinementSeedSummary(work, display: model.display)).inkuFont(11).foregroundStyle(.secondary)
                .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
        }.padding(8).overlay(Rectangle().stroke(InkuColor.border))
    }
}

@MainActor func refinementSeedSummary(_ work: SavedWork, display: DisplaySettings) -> String {
    var summary = "r \(work.renderSeed ?? "-") / v \(work.compositionSeed ?? display.webCopy("seedBaseLabel", "base"))"
    if let seed = work.interpretationSeed, !seed.isEmpty { summary += " / i \(seed.prefix(8))" }
    return summary
}

struct RefinementOption: Identifiable {
    let id: String
    let work: SavedWork
    let label: String
    var details: [String] = []
    var selected = false
    var saved = false
    var observation: PreparedCandidate?
}

/// Preview and adoption are separate buttons. Enlarging never changes the chosen set.
@MainActor
struct RefinementOptionsGrid: View {
    @Bindable var model: AppModel
    let options: [RefinementOption]
    let previewID: String?
    let maxColumns: Int
    let busy: Bool
    let placeholder: String
    var errors: [String] = []
    var status: String = ""
    let onPreview: (String?) -> Void
    let onSelect: (String, Bool) -> Void
    let onDiscard: () -> Void
    let onSave: () -> Void
    @State private var observationID: String?

    private var shown: [RefinementOption] { options.filter { previewID == nil || $0.id == previewID } }

    var body: some View {
        GeometryReader { geometry in
            VStack(alignment: .leading, spacing: 12) {
                if !status.isEmpty { Text(model.display.message(status)).inkuFont(12).foregroundStyle(.secondary) }
                if !options.isEmpty {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 8) { actions }.frame(maxWidth: .infinity, alignment: .trailing)
                        VStack(alignment: .trailing, spacing: 8) { actions }.frame(maxWidth: .infinity, alignment: .trailing)
                    }
                }
                GeometryReader { viewport in
                  ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        if shown.isEmpty {
                            Text(model.display.localized(placeholder)).inkuFont(12).foregroundStyle(.secondary)
                                .multilineTextAlignment(.center).frame(maxWidth: .infinity, minHeight: max(180, viewport.size.height - 4))
                                .background(InkuColor.bg2)
                                .overlay(Rectangle().stroke(InkuColor.border, style: StrokeStyle(dash: [4])))
                        } else {
                            let count = previewID == nil ? max(1, min(maxColumns, shown.count)) : 1
                            let rows = (shown.count + count - 1) / count
                            let height = max(150, (viewport.size.height - 4 - CGFloat(rows - 1) * 10) / CGFloat(rows))
                            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: count), spacing: 10) {
                                ForEach(shown) { option in
                                    VStack(alignment: .leading, spacing: 4) {
                                        optionCard(option, height: height)
                                            .contextMenu {
                                                if option.observation != nil {
                                                    Button(model.display.localized("モデルの実測記録")) { observationID = option.id }
                                                }
                                            }
                                            .popover(isPresented: Binding(get: { observationID == option.id }, set: { if !$0 { observationID = nil } })) {
                                                if let observation = option.observation {
                                                    ProviderObservationView(model: model, metrics: observation.providerMetrics,
                                                        workID: option.saved ? option.work.id : nil, executionID: observation.executionID)
                                                        .padding(16).frame(width: 360)
                                                }
                                            }
                                    }
                                }
                            }
                        }
                        ForEach(Array(errors.enumerated()), id: \.offset) { _, error in
                            Text(model.display.message(error)).inkuFont(12).foregroundStyle(.red).textSelection(.enabled)
                        }
                    }.padding(2)
                  }.id(previewID.map { "preview:" + $0 } ?? "grid:" + (options.first?.id ?? "empty"))
                }
            }
        }
    }

    @ViewBuilder private var actions: some View {
        if previewID != nil {
            Button(model.display.localized("一覧へ戻る")) { onPreview(nil) }.disabled(busy)
        }
        Button(model.display.localized("すべて破棄して閉じる"), action: onDiscard).disabled(busy)
            .inkuTooltip(model.display.tooltip("未保存の候補をすべて捨てて閉じます。保存済みの候補は履歴に残ります。", serverKey: "tooltipRefineDiscardAndClose"))
        Button(model.display.localized("選んだ候補を保存して閉じる"), action: onSave)
            .disabled(busy || !options.contains { $0.selected && !$0.saved })
            .buttonStyle(.borderedProminent)
            .inkuTooltip(model.display.tooltip("チェックした候補を履歴に保存して閉じます。選ばなかった候補は破棄します。保存した候補には、スターと選んだ理由を残せます。", serverKey: "tooltipVariationGridSaveSelected"))
    }

    private func optionCard(_ option: RefinementOption, height: CGFloat) -> some View {
        Button { onPreview(previewID == option.id ? nil : option.id) } label: {
            VStack(alignment: .leading, spacing: 0) {
                if previewID == option.id {
                    ArtworkCanvas(svg: option.work.svg, renderer: model.displayRenderer, style: .workspace, showsZoomControls: false,
                        aspectRatio: option.work.renderCanvasAspectRatio)
                        .frame(minHeight: 0, maxHeight: .infinity).allowsHitTesting(false).accessibilityHidden(true)
                } else {
                    ArtworkThumbnail(work: option.work, thumbnails: model.thumbnails)
                        .frame(minHeight: 0, maxHeight: .infinity)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(option.label).inkuFont(10).lineLimit(1)
                    ForEach(Array(option.details.enumerated()), id: \.offset) { _, line in
                        Text(line).inkuFont(10).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                    Text(refinementSeedSummary(option.work, display: model.display)).inkuFont(10).foregroundStyle(.secondary).lineLimit(1)
                }.padding(.horizontal, 8).padding(.vertical, 6)
            }.frame(maxWidth: .infinity, alignment: .leading).frame(height: height).contentShape(Rectangle())
        }.buttonStyle(.plain).disabled(busy)
            .accessibilityLabel(model.display.localized(previewID == option.id ? "拡大を戻す" : "候補を拡大") + ": " + option.label)
            .background(InkuColor.bg2)
            .overlay(Rectangle().stroke(option.selected ? Color.accentColor : InkuColor.border2, lineWidth: option.selected ? 2 : 1))
            .opacity(option.saved ? 0.62 : 1)
            .overlay(alignment: .topTrailing) { selectButton(option) }
    }

    private func selectButton(_ option: RefinementOption) -> some View {
        let symbol = option.saved ? "✔" : (option.selected ? "✓" : "+")
        let label = option.saved ? "保存済み" : (option.selected ? "選択を外す" : "この候補を保存")
        return Button { onSelect(option.id, !option.selected) } label: {
            Text(symbol).inkuFont(15, weight: .semibold).frame(width: 30, height: 30)
        }.buttonStyle(.bordered).buttonBorderShape(.circle)
            .tint(option.selected ? Color.accentColor : Color.secondary).padding(6)
            .disabled(busy || option.saved)
            .accessibilityLabel(model.display.localized(label) + ": " + option.label)
            .accessibilityValue(model.display.localized(option.selected ? "選択済み" : "未選択"))
            .inkuTooltip(option.saved ? model.display.tooltip("保存済み") : "")
    }
}
