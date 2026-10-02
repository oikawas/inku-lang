import InkuPersistence
import SwiftUI

@MainActor
struct LineageView: View {
    @Bindable var model: AppModel
    @State private var details: LineageItem?
    private var library: LibraryModel { model.library }

    var body: some View {
        VStack(spacing: 0) {
            toolbar.padding(12)
            Divider()
            if let error = library.lineageError {
                ContentUnavailableView(model.display.localized("系譜を読み込めません"), systemImage: "exclamationmark.triangle", description: Text(error))
                Button(model.display.localized("再試行")) { Task { await library.reloadLineage() } }
            } else if let graph = library.graph {
                ScrollView([.horizontal, .vertical]) {
                    if library.lineageVertical {
                        VStack(alignment: .leading, spacing: 20) {
                            ForEach(generations(graph), id: \.self) { generation in generationRow(graph, generation: generation) }
                        }.padding(20)
                    } else {
                        HStack(alignment: .top, spacing: 20) {
                            ForEach(generations(graph), id: \.self) { generation in generationColumn(graph, generation: generation) }
                        }.padding(20)
                    }
                }
                if graph.truncated {
                    Text(model.display.localized("表示範囲の外にも系譜があります。節点を選ぶか、子孫の深さを増やしてください。"))
                        .font(.caption).foregroundStyle(.secondary).padding(8)
                }
            } else if library.lineageLoading {
                ProgressView(model.display.localized("系譜を読み込み中")).frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ContentUnavailableView(model.display.localized("系譜を選択"), systemImage: "point.3.connected.trianglepath.dotted",
                                       description: Text(model.display.localized("ライブラリまたは制作画面で作品を選択してください。")))
            }
        }
        .overlay(alignment: .topTrailing) { if library.lineageLoading { ProgressView().padding(16) } }
        .task(id: model.selectedWorkID) { if let work = model.selectedWork { await library.loadLineage(work: work) } }
        .sheet(item: $details) { item in nodeDetails(item) }
    }

    private var toolbar: some View {
        @Bindable var library = library
        return ViewThatFits(in: .horizontal) {
            HStack { navigation; depthControls }
            VStack(alignment: .leading, spacing: 8) { navigation; depthControls }
        }
    }

    private var navigation: some View {
        @Bindable var library = library
        return HStack {
            Text(model.display.localized("系譜")).font(.title2.weight(.semibold))
            Toggle(model.display.localized("起点からの道筋"), isOn: $library.lineagePathOnly).toggleStyle(.button)
                .onChange(of: library.lineagePathOnly) { _, _ in Task { await library.reloadLineage() } }
            Toggle(model.display.localized("縦に並べる"), isOn: $library.lineageVertical).toggleStyle(.button)
            Button(model.display.localized("全体")) {
                Task { await library.loadLineageOverview() }
            }
            Button(model.display.localized("更新"), systemImage: "arrow.clockwise") { Task { await library.reloadLineage() } }
        }.controlSize(.small)
    }

    private var depthControls: some View {
        @Bindable var library = library
        return HStack {
            Stepper(model.display.localizedFormat("子孫 %ld 世代", library.lineageDepth), value: $library.lineageDepth, in: 0...200)
                .frame(width: 190).disabled(library.lineagePathOnly)
                .onChange(of: library.lineageDepth) { _, _ in Task { await library.reloadLineage() } }
            Button(model.display.localized("表示中を選択")) { library.selectedIDs.formUnion(library.graph?.nodes.compactMap { $0.work?.id } ?? []) }
            if !library.selectedIDs.isEmpty {
                Text(model.display.localizedFormat("%ld 件選択", library.selectedIDs.count)).font(.caption)
                Button(model.display.localized("解除")) { library.selectedIDs.removeAll() }
            }
        }.controlSize(.small)
    }

    private func generations(_ graph: LineageGraph) -> [Int] { Set(graph.nodes.map(\.generation)).sorted() }

    private func generationColumn(_ graph: LineageGraph, generation: Int) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.display.localizedFormat("第 %ld 世代", generation)).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            ForEach(graph.nodes.filter { $0.generation == generation }) { item in nodeCard(item, graph: graph) }
        }.frame(width: 225)
    }

    private func generationRow(_ graph: LineageGraph, generation: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.display.localizedFormat("第 %ld 世代", generation)).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            HStack(alignment: .top, spacing: 12) {
                ForEach(graph.nodes.filter { $0.generation == generation }) { item in nodeCard(item, graph: graph).frame(width: 225) }
            }
        }
    }

    private func nodeCard(_ item: LineageItem, graph: LineageGraph) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if let work = item.work {
                    Button { library.toggleSelection(work.id) } label: {
                        Image(systemName: library.selectedIDs.contains(work.id) ? "checkmark.square.fill" : "square")
                    }.buttonStyle(.plain).accessibilityLabel(model.display.localized("作品を選択"))
                }
                Text(operation(graph.edges.first { $0.childNodeID == item.id }?.derivationKind)).font(.caption.weight(.semibold))
                Spacer()
                if item.id == graph.focusNodeID { Text(model.display.localized("現在")).font(.caption).foregroundStyle(Color.accentColor) }
            }
            if let work = item.work {
                Button { Task { await model.selectWork(work); await library.loadLineage(nodeID: item.id) } } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(height: 132)
                        Text(work.effectiveSourceText.isEmpty ? model.display.localized("無題") : work.effectiveSourceText).lineLimit(3)
                    }
                }.buttonStyle(.plain).disabled(model.isBusy)
                HStack {
                    Button { Task { await library.toggleStar(work) } } label: { Image(systemName: work.starred ? "star.fill" : "star") }
                        .accessibilityLabel(model.display.localized("お気に入り"))
                    Button { Task { await library.toggleRevision(work) } } label: {
                        Image(systemName: library.annotation(for: work.id).forRevision ? "pencil.circle.fill" : "pencil.circle")
                    }.accessibilityLabel(model.display.localized("推敲の印"))
                    Spacer()
                    if let hash = work.renderHash { Button("…\(hash.suffix(4))") { library.copyHash(hash) }.help(model.display.preferences.showTooltips ? model.display.localized("描画ハッシュ全体をコピー") : "") }
                }.buttonStyle(.borderless).font(.caption).disabled(library.mutating || model.isBusy)
                if work.trashed { Text(model.display.localized("ごみ箱の作品")).font(.caption).foregroundStyle(.secondary) }
                if item.node.state == "lineage_only" {
                    Button(model.display.localized("ライブラリへ追加")) { Task { await library.promote(item.id) } }.disabled(library.mutating)
                }
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "trash.slash").font(.title)
                    Text(model.display.localized(item.node.state == "tombstone" ? "削除された作品" : "保存作品がありません"))
                }.frame(maxWidth: .infinity, minHeight: 132).foregroundStyle(.secondary)
                Button(model.display.localized("この節点を中心に表示")) { Task { await library.loadLineage(nodeID: item.id) } }
            }
            Text(Date(timeIntervalSince1970: Double(item.node.at) / 1000), format: .dateTime.year().month().day().hour().minute())
                .font(.caption2).foregroundStyle(.secondary)
            if let parent = graph.edges.first(where: { $0.childNodeID == item.id }) {
                Button(model.display.localized("← 親の節点")) { Task { await library.loadLineage(nodeID: parent.parentNodeID) } }.font(.caption)
            }
            if item.childCount > 0 {
                Button(model.display.localizedFormat("子の節点 (%ld) →", item.childCount)) {
                    library.lineagePathOnly = false; library.lineageDepth = max(1, library.lineageDepth)
                    Task { await library.loadLineage(nodeID: item.id) }
                }.font(.caption)
            }
            Button(model.display.localized("保存情報・コメント")) { details = item }.font(.caption)
        }
        .padding(12)
        .background(item.id == graph.focusNodeID ? Color.accentColor.opacity(0.08) : Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(item.id == graph.focusNodeID ? Color.accentColor : Color.secondary.opacity(0.3),
                                                         style: StrokeStyle(lineWidth: 1, dash: item.node.state == "tombstone" ? [5, 4] : [])))
    }

    private func nodeDetails(_ item: LineageItem) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack { Text(model.display.localized("系譜の保存情報")).font(.title2); Spacer(); Button(model.display.localized("閉じる")) { details = nil } }
            Text(model.display.localizedFormat("節点 ID: %@", item.id)).font(.caption.monospaced()).textSelection(.enabled)
            Text(model.display.localizedFormat("第 %ld 世代 · 子の節点 %ld · 状態 %@", item.generation, item.childCount, item.node.state)).font(.caption)
            if let deleted = item.node.deletedAt {
                Text(model.display.localizedFormat("削除日時: %@", Date(timeIntervalSince1970: Double(deleted) / 1000).formatted())).font(.caption)
            }
            if let work = item.work { LibraryWorkDetails(model: model, work: work) }
            else { Text(model.display.localized("元の節点と接続を保持しています。作品本文は削除されています。")).foregroundStyle(.secondary) }
        }.padding(20).frame(minWidth: 440, idealWidth: 650, minHeight: item.work == nil ? 200 : 600)
    }

    private func operation(_ kind: String?) -> String {
        let labels = ["touch_change": "タッチ", "layout_change": "構図", "catalog_change": "色",
                      "reinterpretation": "解釈", "model_comparison": "モデル", "language_comparison": "言語",
                      "ddl_edit": "DDL編集", "description_edit": "記述編集", "replay": "再描画",
                      "canvas_aspect_change": "キャンバス変更", "variation": "変奏", "sketch_grain_change": "写生の有無",
                      "render_engine_change": "描画エンジン", "external_seed_change": "シード", "renga_reply": "連歌"]
        return model.display.localized(kind.flatMap { labels[$0] ?? $0 } ?? "起点")
    }
}
