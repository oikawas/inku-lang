import InkuHost
import InkuPersistence
import SwiftUI

/// Web `RefinementCompositionFormView.svelte`: the target picture, the switch notice, the seven forms (name and
/// description, the work's own marked "current"), "one option" and "four options", the run's progress and lanes, and
/// the candidate grid with save and discard. The grid and saving are the model comparison's (`RefinementOptionsGrid`,
/// `saveComparisonCandidate`); no comparison logic is copied (SPEC.ja.md 663).
@MainActor
public struct CompositionFormView: View {
    @Bindable var model: AppModel
    @State private var form: CompositionFormModel
    @Environment(\.dismiss) private var dismiss
    private let onCommitted: (SavedWork) -> Void

    public init(model: AppModel, work: SavedWork? = nil, onCommitted: @escaping (SavedWork) -> Void = { _ in }) {
        self.model = model
        self.onCommitted = onCommitted
        _form = State(initialValue: CompositionFormModel(work: work))
    }

    public var body: some View {
        Group {
            if let work = form.original {
                RefinementDialog(model: model, title: model.display.webCopy("workActionCompositionForm", "構図の形を変える"), work: work,
                    closeDisabled: form.running || form.hasUnsaved || model.isBusy, onClose: { dismiss() },
                    targetTitle: model.display.webCopy("refineTargetTitle", "推敲対象")) {
                    controls
                } options: {
                    RefinementOptionsGrid(model: model, options: form.candidates.map {
                        RefinementOption(id: $0.id, work: $0.work, label: $0.label, selected: $0.selected, saved: $0.savedWork != nil,
                            observation: $0.prepared)
                    }, previewID: form.previewID, maxColumns: 4, busy: form.running || model.isBusy,
                        placeholder: "形を選んで描くと、候補をここに並べます。",
                        errors: form.failures + [form.errorText].compactMap { $0 }, status: form.status,
                        onPreview: { form.preview($0) }, onSelect: { form.selectCandidate($0, selected: $1) },
                        onDiscard: { form.discardCandidates(); dismiss() },
                        onSave: { Task {
                            if await form.saveSelected(app: model) {
                                if let latest = form.candidates.compactMap(\.savedWork).last { onCommitted(latest) }
                                dismiss()
                            }
                        } })
                }
            } else {
                VStack {
                    if let error = form.errorText { Text(model.display.message(error)).foregroundStyle(.red) }
                    else { ProgressView() }
                    Button(model.display.localized("閉じる")) { dismiss() }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task { await form.initialize(app: model) }
        .interactiveDismissDisabled(form.running || form.hasUnsaved || model.isBusy)
        .onDisappear { Task { await form.stop(app: model); form.discardCandidates() } }
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 12) {
            if form.switchesComposition {
                Text(model.display.webCopy("compositionFormSwitchNotice", "言葉で描く＋構図ありに切り替えて描きます")).inkuFont(12)
            }
            if form.sourceIsLocked {
                Text(model.display.tooltip("編集した指示書で確定した作品です。記述を読み直す操作は使えません。", serverKey: "descriptionLockedReason"))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 7) {
                ForEach(Array(CompositionForm.all.enumerated()), id: \.element) { index, id in formOption(id, index: index) }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(model.display.webCopy("workActionCompositionForm", "構図の形を変える"))
            VStack(alignment: .leading, spacing: 8) {
                Button(model.display.webCopy("refineSingleButton", "1案を作る"), systemImage: "play.fill") {
                    Task { await form.generate(app: model, count: 1) }
                }.buttonStyle(.borderedProminent).disabled(!form.canGenerate || model.isBusy)
                Button(model.display.webCopy("variationGridDefault", "4案を作る"), systemImage: "square.grid.2x2") {
                    Task { await form.generate(app: model, count: 4) }
                }.buttonStyle(.bordered).disabled(!form.canGenerate || model.isBusy)
            }
            Label(model.display.localized("低速（LLM・API使用）"), systemImage: "clock").inkuFont(11).foregroundStyle(.secondary)
            if form.running {
                RunStatusView(display: model.display, label: form.status, stopping: form.stopping,
                    onStop: { Task { await form.stop(app: model) } }, journalModel: model, journalActive: !form.saving) {
                    if !form.saving { ProviderProgressView(model: model, embedded: true) }
                }
                if !form.saving {
                    VariationLanesView(display: model.display, states: form.laneStates.map {
                        switch $0 { case .waiting: .waiting; case .running: .running; case .done: .done }
                    }, labels: form.laneLabels, named: false)
                }
            }
        }
    }

    /// One radio row: the form's name (with "current" on the work's own form) over its description.
    private func formOption(_ id: String, index: Int) -> some View {
        let selected = form.selectedForm == id
        let name = model.display.webCopy("compositionFormNames.\(index)", id)
        let current = id == form.currentForm ? " (" + model.display.webCopy("compositionFormCurrent", "今の形") + ")" : ""
        return Button { form.selectedForm = id } label: {
            HStack(alignment: .top, spacing: 6) {
                Image(systemName: selected ? "largecircle.fill.circle" : "circle").foregroundStyle(selected ? Color.accentColor : .secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name + current).inkuFont(12, weight: .semibold)
                    Text(model.display.webCopy("compositionFormDescriptions.\(index)", "")).inkuFont(12).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }.contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(form.running || model.isBusy)
        .accessibilityAddTraits(selected ? [.isSelected] : [])
    }
}
