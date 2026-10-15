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
    var topControls: AnyView? = nil
    @ViewBuilder let controls: () -> Controls
    @ViewBuilder let options: () -> Options

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
                VStack(spacing: 14) {
                    if let topControls { topControls.frame(maxHeight: min(350, geometry.size.height * 0.46)) }
                    HStack(alignment: .top, spacing: 14) {
                        ScrollView {
                            VStack(alignment: .leading, spacing: 14) {
                                RefinementTargetCard(model: model, work: work)
                                controls()
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }.frame(width: min(280, max(220, geometry.size.width * 0.26)))
                        options().frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }.padding(16)
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
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.display.localized("推敲対象")).inkuFont(12).foregroundStyle(.secondary)
            ArtworkThumbnail(work: work, thumbnails: model.thumbnails)
                .aspectRatio(work.renderCanvasAspectRatio ?? 1, contentMode: .fit)
                .accessibilityLabel(model.display.localized("推敲対象"))
            Text(refinementSeedSummary(work, display: model.display)).inkuFont(11).foregroundStyle(.secondary)
                .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
        }.padding(8).overlay(Rectangle().stroke(InkuColor.border))
    }
}

@MainActor func refinementSeedSummary(_ work: SavedWork, display: DisplaySettings) -> String {
    "r \(work.renderSeed ?? "-") / v \(work.compositionSeed ?? display.webCopy("seedBaseLabel", "base"))"
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
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if shown.isEmpty {
                            Text(model.display.localized(placeholder)).inkuFont(12).foregroundStyle(.secondary)
                                .multilineTextAlignment(.center).frame(maxWidth: .infinity, minHeight: 270)
                                .overlay(Rectangle().stroke(InkuColor.border, style: StrokeStyle(dash: [4])))
                        } else {
                            let count = previewID == nil ? max(1, min(maxColumns, shown.count, Int((geometry.size.width + 12) / 190))) : 1
                            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: count), spacing: 12) {
                                ForEach(shown) { option in
                                    VStack(alignment: .leading, spacing: 4) {
                                        optionCard(option, height: previewID == nil ? max(150, (geometry.size.width - CGFloat(count - 1) * 12) / CGFloat(count) / (option.work.renderCanvasAspectRatio ?? 1)) : max(350, geometry.size.height - 110))
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
            VStack(alignment: .leading, spacing: 7) {
                if previewID == option.id {
                    ArtworkCanvas(svg: option.work.svg, renderer: model.displayRenderer, style: .workspace, showsZoomControls: false,
                        aspectRatio: option.work.renderCanvasAspectRatio)
                        .frame(height: height).allowsHitTesting(false).accessibilityHidden(true)
                } else { ArtworkThumbnail(work: option.work, thumbnails: model.thumbnails).frame(height: height) }
                VStack(alignment: .leading, spacing: 3) {
                    Text(option.label).inkuFont(12, weight: .semibold)
                    ForEach(Array(option.details.enumerated()), id: \.offset) { _, line in Text(line).inkuFont(11).foregroundStyle(.secondary) }
                    Text(refinementSeedSummary(option.work, display: model.display)).inkuFont(11).foregroundStyle(.secondary)
                }.padding(8)
            }.frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
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
