import InkuHost
import InkuPersistence
import SwiftUI

@MainActor
public struct RefinementView: View {
    @Bindable private var model: AppModel
    @State private var refinement: RefinementModel
    @State private var closing = false
    @Environment(\.dismiss) private var dismiss
    private let onCommitted: @MainActor (SavedWork) -> Void
    private let onConfigureModels: @MainActor (String) -> Void
    private let onClose: (@MainActor () -> Void)?

    public init(model: AppModel, work: SavedWork, onCommitted: @escaping @MainActor (SavedWork) -> Void = { _ in },
                onConfigureModels: @escaping @MainActor (String) -> Void = { _ in },
                onClose: (@MainActor () -> Void)? = nil) {
        self.model = model; self.onCommitted = onCommitted
        self.onConfigureModels = onConfigureModels; self.onClose = onClose
        _refinement = State(initialValue: RefinementModel(work: work))
    }

    private func finish() { if let onClose { onClose() } else { dismiss() } }
    private var controlsDisabled: Bool { refinement.running || model.isBusy || closing || refinement.closed }
    private var effectiveWild: Bool { refinement.inheritWild ? refinement.work.renderWild ?? false : refinement.wildOverride }

    public var body: some View {
        @Bindable var refinement = refinement
        RefinementDialog(model: model, title: "配置を変える", work: refinement.work,
            closeDisabled: controlsDisabled || refinement.hasUnsaved, onClose: { Task { await close() } }) {
            VStack(alignment: .leading, spacing: 12) {
                Text(model.display.localized("元の指示書を使い、配置を変えます。記述は読み直しません。"))
                    .inkuFont(12).foregroundStyle(.secondary)
                    .inkuTooltip(model.display.tooltip("保存した指示書の数で書いた範囲を、原理に沿うか偶然に委ねるかで選び直します。明示したかたむきと「隅」も候補のseedで選び直します。動かせないときは理由を示し、元の指示書を配置の seed だけ変えて描き直します", serverKey: "tooltipCanvasVaryComposition"))
                Picker(model.display.localized("配置を変える"), selection: $refinement.recomposeMode) {
                    Text(model.display.localized("原理に沿う")).tag(Recomposition.Mode.principled)
                    Text(model.display.localized("偶然に委ねる")).tag(Recomposition.Mode.chance)
                }.pickerStyle(.radioGroup).labelsHidden().disabled(controlsDisabled)
                generateButton(count: 1)
                generateButton(count: 4)
                Text(model.display.localized("高速（補完の穴があるときだけLLM）")).inkuFont(12).foregroundStyle(.secondary)
                RefinementDrawingModelPicker(model: model, reference: $refinement.modelReference, disabled: controlsDisabled,
                    configurationDisabled: controlsDisabled || self.refinement.hasUnsaved,
                    onConfigureModels: { section in Task { await configureModels(section) } })
                HStack {
                    Text(model.display.localized(self.refinement.inheritWild ? "筆致制限（継承）" : "筆致制限")).inkuFont(12).foregroundStyle(.secondary)
                    Button(model.display.localized("暴れる") + " " + model.display.localized(effectiveWild ? "入" : "切")) {
                        refinement.wildOverride = !effectiveWild; refinement.inheritWild = false
                    }.buttonStyle(.bordered).tint(effectiveWild ? Color.accentColor : Color.secondary)
                }.disabled(controlsDisabled)
                if refinement.running {
                    RunStatusView(display: model.display, label: refinement.saving ? "選択した候補を保存中" : "候補の準備中",
                        stopping: refinement.stopping || closing, onStop: { Task { await refinement.stop(app: model) } }) { ProviderProgressView(model: model) }
                    if !refinement.saving {
                        VariationLanesView(display: model.display, states: refinement.slots.map {
                            switch $0.state { case .waiting: .waiting; case .running: .running; case .ready, .failed: .done }
                        }, labels: refinement.slots.map { _ in model.display.localized(refinement.kind.titleKey) })
                    }
                }
            }
        } options: {
            RefinementOptionsGrid(model: model, options: refinement.candidates.map {
                RefinementOption(id: $0.id, work: $0.work, label: model.display.localizedFormat("候補 %ld", $0.number),
                    details: $0.recomposition?.lines(display: model.display) ?? [], selected: $0.selected, saved: $0.savedWork != nil)
            }, previewID: refinement.previewID, maxColumns: 2, busy: controlsDisabled,
                placeholder: "条件を選んで描くと、候補をここに並べます。",
                errors: [refinement.errorText].compactMap { $0 } + refinement.slots.compactMap(\.error), status: refinement.status,
                onPreview: { refinement.preview($0) }, onSelect: { refinement.selectCandidate($0, selected: $1) },
                onDiscard: { Task { await close() } }, onSave: { Task { await save() } })
        }
        .task { await refinement.initialize(app: model) }
        .interactiveDismissDisabled(refinement.running || refinement.hasUnsaved || model.isBusy || closing)
        .onDisappear { Task { _ = await refinement.close(app: model) } }
    }

    private func generateButton(count: Int) -> some View {
        Button(model.display.webCopy(count == 1 ? "refineSingleButton" : "variationGridDefault", count == 1 ? "1案を作る" : "4案を作る"), systemImage: "play.fill") {
            Task { await refinement.generate(app: model, count: count) }
        }.buttonStyle(.borderedProminent).disabled(!refinement.canGenerate(count: count) || controlsDisabled || model.isPreview)
            .inkuTooltip(count == 1 ? model.display.tooltip("選択した1種類の要素だけを変更した1案を作ります。選んだ候補は履歴に保存できます", serverKey: "tooltipRefineSingle")
                : model.display.tooltip("選択した1種類の要素だけを変えて4案を作ります。", serverKey: "tooltipVariationGridDefault"))
    }

    private func save() async {
        let before = refinement.committedWorks.count
        let succeeded = await refinement.saveSelected(app: model)
        if refinement.committedWorks.count > before, let latest = refinement.committedWorks.last { onCommitted(latest) }
        if succeeded && !refinement.running && !refinement.hasUnsaved && !model.isBusy && !closing { finish() }
    }
    private func configureModels(_ section: String) async {
        guard !closing, !refinement.running, !refinement.hasUnsaved, !model.isBusy else { return }
        closing = true
        if await refinement.close(app: model) { onConfigureModels(section); finish() } else { closing = false }
    }
    private func close() async {
        guard !closing else { return }
        closing = true
        if await refinement.close(app: model) { finish() } else { closing = false }
    }
}

/// Selecting a drawing model saves the Stage 2 default immediately.
@MainActor
private struct RefinementDrawingModelPicker: View {
    @Bindable var model: AppModel
    @Binding var reference: String
    let disabled: Bool
    let configurationDisabled: Bool
    let onConfigureModels: @MainActor (String) -> Void
    @State private var showModels = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button { showModels = true } label: {
                VStack(alignment: .leading, spacing: 3) {
                    Text(model.display.localized("描画モデル")).inkuFont(12, weight: .semibold)
                    Text(reference.isEmpty ? model.display.localized("選択してください") : reference).inkuFont(13)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.buttonStyle(.bordered).disabled(disabled)
            Text(model.display.localized("選択したモデルを構造化の既定モデルとして保存します。読み取りの既定モデルは変わりません。"))
                .inkuFont(12).foregroundStyle(.secondary)
            Button(model.display.localized("モデル設定"), systemImage: "gearshape") { onConfigureModels("models") }.disabled(configurationDisabled)
        }
        .sheet(isPresented: $showModels) {
            BatchModelPickerView(model: model, initialReference: reference, immediateSelection: true, title: "描画モデル") { value in
                try await model.selectDdlDrawingModel(value); reference = value
            }.disabled(disabled)
        }
    }
}
