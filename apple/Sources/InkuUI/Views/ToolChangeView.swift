import InkuHost
import InkuPersistence
import SwiftUI

@MainActor
public struct ToolChangeView: View {
    @Bindable var model: AppModel
    @State private var change: ToolChangeModel
    @Environment(\.dismiss) private var dismiss
    private let onCommitted: (SavedWork) -> Void

    public init(model: AppModel, work: SavedWork, onCommitted: @escaping (SavedWork) -> Void = { _ in }) {
        self.model = model
        self.onCommitted = onCommitted
        _change = State(initialValue: ToolChangeModel(work: work))
    }

    public var body: some View {
        @Bindable var change = change
        RefinementDialog(model: model, title: "てざわりを変える", work: change.work,
            closeDisabled: change.running || change.hasUnsaved || model.isBusy, onClose: { dismiss() }) {
            VStack(alignment: .leading, spacing: 12) {
                Text(model.display.webCopy("toolChangeHint", "てざわり（筆記具）だけを替えます。配置・色・支持体は保ちます。てざわりを書いていない文には、新しい語を書き足します。"))
                    .inkuFont(11).foregroundStyle(.secondary)
                Picker(model.display.localized("てざわりを変える"), selection: $change.mode) {
                    Text(model.display.localized("すべての文を同じ筆記具にする")).tag(ToolChangeMode.uniform)
                    Text(model.display.localized("文ごとに違う筆記具にする")).tag(ToolChangeMode.perSentence)
                }
                #if os(macOS)
                .pickerStyle(.radioGroup)
                #else
                .pickerStyle(.segmented)
                #endif
                .disabled(change.running || model.isBusy)
                Button(model.display.localized("4案を作る"), systemImage: "play.fill") { Task {
                    let before = change.committedWorks.count
                    await change.generate(app: model)
                    if change.committedWorks.count > before, let latest = change.committedWorks.last { onCommitted(latest) }
                } }
                    .buttonStyle(.borderedProminent).disabled(change.running || model.isBusy)
                Label(model.display.localized("超高速（LLM不要）"), systemImage: "clock").inkuFont(11).foregroundStyle(.secondary)
                if change.running {
                    RunStatusView(display: model.display, label: change.saving ? "選択した候補を保存中" : "てざわりの候補を用意中",
                        stopping: change.stopping, onStop: { Task { await change.stop(app: model) } }) { EmptyView() }
                    VariationLanesView(display: model.display, states: change.lanes.map {
                        switch $0 { case .waiting: .waiting; case .running: .running; case .done: .done }
                    }, labels: [], named: false)
                }
                if change.noChangeableSentences {
                    Text(model.display.localized("この作品には、てざわりを替えられる文がありません。")).foregroundStyle(.secondary)
                }
            }
        } options: {
            RefinementOptionsGrid(model: model, options: change.candidates.map { candidate in
                RefinementOption(id: candidate.id, work: candidate.work,
                    label: candidate.plan.mode == .uniform
                        ? candidate.plan.toolName(candidate.plan.tools.values.first ?? "", language: model.display.preferences.language)
                        : model.display.localizedFormat("文ごと %ld", candidate.number),
                    details: candidate.plan.mode == .perSentence ? candidate.plan.changes.map { item in
                        "\(item.index + 1): \(candidate.plan.toolName(item.from, language: model.display.preferences.language)) → \(candidate.plan.toolName(item.to, language: model.display.preferences.language))"
                    } : [], selected: candidate.selected, saved: candidate.savedWork != nil)
            }, previewID: change.previewID, maxColumns: 4, busy: change.running || model.isBusy,
                placeholder: model.display.webCopy("toolChangePlaceholder", "替え方を選んで「4案を作る」を押すと、筆記具を替えた4案を並べます。もう一度押すと、チェックした候補を先に保存してから新しい4案に替えます。"),
                errors: change.failures + [change.errorText].compactMap { $0 },
                onPreview: { change.preview($0) }, onSelect: { change.selectCandidate($0, selected: $1) },
                onDiscard: { change.discardCandidates(); dismiss() },
                onSave: { Task {
                    if await change.saveSelected(app: model) {
                        if let latest = change.candidates.compactMap(\.savedWork).last { onCommitted(latest) }
                        dismiss()
                    }
                } })
        }
        .interactiveDismissDisabled(change.running || change.hasUnsaved || model.isBusy)
        .onDisappear { Task { await change.stop(app: model); change.discardCandidates() } }
    }

}
