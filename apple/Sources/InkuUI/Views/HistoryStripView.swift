import InkuPersistence
import SwiftUI

@MainActor struct HistoryStripView: View {
    @Bindable var model: AppModel
    @Bindable var history: HistoryModel
    private var library: LibraryModel { history.library }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Button(model.display.localizedFormat("履歴 (%ld)", library.total)) { NotificationCenter.default.post(name: .inkuOpenSection, object: "library") }
                Toggle(model.display.localized("スター"), isOn: Binding(get: { library.starredOnly }, set: { library.starredOnly = $0 })).toggleStyle(.button)
                Toggle(model.display.localized("推敲"), isOn: Binding(get: { library.revisionOnly }, set: { library.revisionOnly = $0 })).toggleStyle(.button)
                Toggle(model.display.localized("書き出し用"), isOn: Binding(get: { library.shareOnly }, set: { library.shareOnly = $0 })).toggleStyle(.button)
                Spacer()
                Button { Task { await library.setPage(0) } } label: { Image(systemName: "backward.end") }.accessibilityLabel(model.display.localized("最新の履歴"))
                    .disabled(library.page == 0)
                Button { Task { await library.setPage(library.page - 1) } } label: { Image(systemName: "chevron.left") }.accessibilityLabel(model.display.localized("新しい20件"))
                    .disabled(library.page == 0)
                Text("\(library.page + 1) / \(library.pageCount)").font(.caption.monospacedDigit())
                Button { Task { await library.setPage(library.page + 1) } } label: { Image(systemName: "chevron.right") }.accessibilityLabel(model.display.localized("古い20件"))
                    .disabled(library.page + 1 >= library.pageCount)
                Button { Task { await library.setPage(library.pageCount - 1) } } label: { Image(systemName: "forward.end") }.accessibilityLabel(model.display.localized("最古の履歴"))
                    .disabled(library.page + 1 >= library.pageCount)
            }.controlSize(.small)
            if let error = library.errorText { Text(error).font(.caption).foregroundStyle(.red) }
            if let error = history.generationError {
                Text(model.display.localizedFormat("世代を読み込めませんでした: %@", error)).font(.caption).foregroundStyle(.red)
            }
            ScrollView(.horizontal) {
                LazyHStack(spacing: 10) {
                    ForEach(library.works, id: \.id) { work in
                        Button { Task { await model.selectWork(work) } } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                ArtworkThumbnail(work: work, renderer: model.renderer).frame(width: 90, height: 70)
                                    .overlay(alignment: .topTrailing) { if work.starred { Image(systemName: "star.fill").foregroundStyle(.yellow).padding(3) } }
                                ForEach(metadata(work), id: \.self) { Text($0).lineLimit(1) }
                            }.font(.caption2).frame(width: 90, alignment: .leading).padding(5)
                                .background(model.selectedWorkID == work.id ? Color.accentColor.opacity(0.15) : Color.clear, in: RoundedRectangle(cornerRadius: 6))
                                .overlay(RoundedRectangle(cornerRadius: 6).stroke(model.selectedWorkID == work.id ? Color.accentColor : .clear))
                        }.buttonStyle(.plain).help(model.display.preferences.showTooltips ? title(work) : "").accessibilityLabel(model.display.localizedFormat("作品を開く: %@", title(work)))
                    }
                }
            }
            .frame(height: CGFloat(84 + min(3, model.display.preferences.historyFields.count) * 13))
        }.disabled(model.isBusy || library.loading).padding(.horizontal, 16).padding(.vertical, 10)
            .task(id: GenerationRequest(nodeIDs: library.works.compactMap(\.lineageNodeID), loading: library.loading)) {
                guard !library.loading else { return }
                await history.refreshGenerations()
            }
    }
    private func metadata(_ work: SavedWork) -> [String] {
        let fields = model.display.preferences.historyFields
        var output: [String] = []
        if fields.contains("generation") { output.append(generationLabel(work)) }
        if fields.contains("model") { output.append(work.stage1Model ?? "DDL") }
        if fields.contains("engine") { output.append("Ver. \(work.renderEngineVersion ?? "—")") }
        if fields.contains("size") { output.append(ByteCountFormatter.string(fromByteCount: Int64(work.svg.utf8.count), countStyle: .file)) }
        return Array(output.prefix(3))
    }

    private func generationLabel(_ work: SavedWork) -> String {
        if let nodeID = work.lineageNodeID {
            if let generation = history.generations[nodeID] { return model.display.localizedFormat("第%ld世代", generation) }
            if history.generationLoading || history.generationError != nil { return "—" }
        }
        return model.display.localized("独立作品")
    }

    private func title(_ work: SavedWork) -> String {
        let source = work.effectiveSourceText
        if !source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return source }
        if let ddl = work.ddl, !ddl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return ddl }
        return work.id
    }

    private struct GenerationRequest: Equatable {
        let nodeIDs: [String]
        let loading: Bool
    }
}
