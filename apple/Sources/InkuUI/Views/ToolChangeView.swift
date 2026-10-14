import InkuHost
import InkuPersistence
import SwiftUI

@MainActor
public struct ToolChangeView: View {
    @Bindable var model: AppModel
    @State private var change: ToolChangeModel
    @Environment(\.dismiss) private var dismiss

    public init(model: AppModel, work: SavedWork) {
        self.model = model
        _change = State(initialValue: ToolChangeModel(work: work))
    }

    public var body: some View {
        @Bindable var change = change
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text(model.display.localized("てざわりを変える")).inkuFont(16, weight: .semibold)
                    Spacer()
                    Button(model.display.localized(change.hasUnsaved ? "破棄して閉じる" : "閉じる")) {
                        Task { await change.stop(app: model); change.discardCandidates(); dismiss() }
                    }.keyboardShortcut(.cancelAction).disabled(change.stopping || model.isBusy && !change.running)
                }
                HStack(alignment: .top, spacing: 14) {
                    ArtworkThumbnail(work: change.work, thumbnails: model.thumbnails).frame(width: 150, height: 130)
                    VStack(alignment: .leading, spacing: 8) {
                        Text(model.display.localized("元の作品")).inkuFont(14, weight: .semibold)
                        Text(change.work.effectiveSourceText).textSelection(.enabled)
                        Text(model.display.localized("てざわり（筆記具）だけを替えます。配置・色・支持体は保ちます。てざわりを書いていない文には、新しい語を書き足します。"))
                            .inkuFont(12).foregroundStyle(.secondary)
                    }
                }
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
                HStack {
                    Button(model.display.localized("4案を作る"), systemImage: "square.grid.2x2") { Task { await change.generate(app: model) } }
                        .buttonStyle(.borderedProminent).disabled(change.running || model.isBusy)
                    Text(model.display.localized("超高速（LLM不要）")).inkuFont(12).foregroundStyle(.secondary)
                    Spacer()
                    Button(model.display.localizedFormat("選択した%ld案を採用して閉じる", change.selectedCount), systemImage: "checkmark.circle") {
                        Task { if await change.saveSelected(app: model) { dismiss() } }
                    }.buttonStyle(.borderedProminent).disabled(change.selectedCount == 0 || change.running || model.isBusy)
                }
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
                if change.candidates.isEmpty {
                    Text(model.display.localized("替え方を選んで「4案を作る」を押すと、筆記具を替えた4案を並べます。もう一度押すと、並んでいる案を捨てて新しい4案に替えます。"))
                        .inkuFont(12).foregroundStyle(.secondary)
                }
                if change.hasUnsaved {
                    Button(model.display.localized("候補を破棄"), role: .destructive) { change.discardCandidates() }.disabled(change.running || model.isBusy)
                }
                candidates
                if let error = change.errorText { Text(model.display.message(error)).foregroundStyle(.red).textSelection(.enabled) }
                ForEach(Array(change.failures.enumerated()), id: \.offset) { _, failure in
                    Text(model.display.message(failure)).inkuFont(12).foregroundStyle(.red)
                }
            }.padding(20)
        }
        #if os(macOS)
        .frame(minWidth: 540, idealWidth: 850, minHeight: 550)
        #endif
        .interactiveDismissDisabled(change.running || change.hasUnsaved || model.isBusy)
        .onDisappear { Task { await change.stop(app: model); change.discardCandidates() } }
    }

    private var candidates: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 210))], alignment: .leading, spacing: 16) {
            ForEach(change.candidates) { candidate in
                VStack(alignment: .leading, spacing: 10) {
                    ArtworkThumbnail(work: candidate.work, thumbnails: model.thumbnails).frame(height: 185)
                    Text(candidate.plan.mode == .uniform
                        ? candidate.plan.toolName(candidate.plan.tools.values.first ?? "", language: model.display.preferences.language)
                        : model.display.localizedFormat("文ごと %ld", candidate.number)).inkuFont(14, weight: .semibold)
                    if candidate.plan.mode == .perSentence {
                        ForEach(candidate.plan.changes, id: \.index) { item in
                            Text("\(item.index + 1): \(candidate.plan.toolName(item.from, language: model.display.preferences.language)) → \(candidate.plan.toolName(item.to, language: model.display.preferences.language))")
                                .inkuFont(12).textSelection(.enabled)
                        }
                    }
                    if candidate.savedWork != nil {
                        Label(model.display.localized("保存済み"), systemImage: "checkmark.circle").inkuFont(12).foregroundStyle(.secondary)
                    } else {
                        Toggle(model.display.localized("この候補を保存"), isOn: Binding(get: { candidate.selected },
                            set: { change.selectCandidate(candidate.id, selected: $0) })).disabled(change.running || model.isBusy)
                        Text(model.display.localized("未保存")).inkuFont(12).foregroundStyle(.secondary)
                    }
                }.padding(12).background(.quaternary.opacity(0.3), in: RoundedRectangle(cornerRadius: 10))
            }
        }
    }
}
