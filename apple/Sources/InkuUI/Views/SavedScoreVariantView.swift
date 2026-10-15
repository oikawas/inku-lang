import InkuHost
import InkuPersistence
import SwiftUI

@MainActor
struct SavedScoreVariantView: View {
    @Bindable var model: AppModel
    @State private var change: SavedScoreVariantModel
    @Environment(\.dismiss) private var dismiss
    private let onCommitted: (SavedWork) -> Void
    init(model: AppModel, work: SavedWork, kind: SavedScoreVariantKind, onCommitted: @escaping (SavedWork) -> Void = { _ in }) {
        self.model = model
        self.onCommitted = onCommitted
        _change = State(initialValue: SavedScoreVariantModel(work: work, kind: kind))
    }
    private var title: String { change.kind == .ground ? "支持体を変える" : "配色を変える" }
    var body: some View {
        RefinementDialog(model: model, title: title, work: change.work,
            closeDisabled: change.running || change.hasUnsaved || model.isBusy, onClose: { dismiss() }) {
            VStack(alignment: .leading, spacing: 10) {
                if change.kind == .ground {
                    Text(model.display.localized("いまの支持体") + ": " + currentGround).inkuFont(12, weight: .semibold)
                    Text(model.display.localized("支持体（じ）だけを、この作品が使っていない支持体に差し替えます。配置・色・タッチは保ちます。"))
                } else {
                    Text(model.display.localized("いまの色カタログ") + ": " + catalogName).inkuFont(12, weight: .semibold)
                    Text(model.display.localized("色カタログを保ち、色の割当だけを入れ替えます。配置とタッチは保ちます。"))
                }
                if !change.running && (change.kind == .colorArrangement || change.candidates.isEmpty) {
                    Button(model.display.localized(change.kind == .ground ? "候補を作る" : change.candidates.isEmpty ? "8案を作る" : "次の8案"), systemImage: "play.fill") {
                        Task { await change.generate(app: model) }
                    }.buttonStyle(.borderedProminent).disabled(model.isBusy || change.exhausted)
                }
                if change.exhausted { Text(model.display.localized("ほかに試せる配色はありません。")) }
                Text(model.display.localized("超高速（LLM不要）")).foregroundStyle(.secondary)
                if change.running {
                    RunStatusView(display: model.display, label: change.saving ? "選択した候補を保存中" : title,
                        stopping: change.stopping, onStop: { Task { await change.stop(app: model) } }) { EmptyView() }
                    VariationLanesView(display: model.display, states: change.lanes.map {
                        switch $0 { case .waiting: .waiting; case .running: .running; case .done: .done }
                    }, labels: [], named: false)
                }
            }.inkuFont(12).fixedSize(horizontal: false, vertical: true)
        } options: {
            RefinementOptionsGrid(model: model, options: change.candidates.map { candidate in
                RefinementOption(id: candidate.id, work: candidate.work,
                    label: candidate.plan.ground?.name(language: model.display.preferences.language) ??
                        model.display.localizedFormat("配色 %@", String((candidate.plan.index ?? 0) + 1)),
                    selected: candidate.selected, saved: candidate.savedWork != nil)
            }, previewID: change.previewID, maxColumns: 4, busy: change.running || model.isBusy,
                placeholder: change.kind == .ground ? "この作品が使っていない支持体に差し替えた候補を並べます（支持体を指定した作品は6案、指定のない作品は7案）。" : "同じ色カタログの中で、重複しない配色の候補を8案ずつ並べます。",
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
        .task { await change.initialize(app: model) }
        .interactiveDismissDisabled(change.running || change.hasUnsaved || model.isBusy)
        .onDisappear { Task { await change.stop(app: model); change.discardCandidates() } }
    }
    private var catalogName: String {
        let id = change.work.renderColorCatalogID ?? change.work.catalogID ?? ""
        return model.catalogs.first { $0.id == id }?.name ?? id
    }
    private var currentGround: String {
        let score = try? ExactJSON(data: Data(change.work.score.utf8))
        let current = score?["canvas"]["ground"]["material"].string ?? "plain"
        return (try? RefinementResources.grounds())?.first { $0.value == current }?.name(language: model.display.preferences.language)
            ?? model.display.localized("無地（指定なし）")
    }
}
