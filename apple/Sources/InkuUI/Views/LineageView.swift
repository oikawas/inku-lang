import InkuPersistence
import SwiftUI

@MainActor
struct LineageView: View {
    @Bindable var model: AppModel
    let onEditWork: (SavedWork, WorkEditMode) -> Void
    let onAdjustWork: (SavedWork) -> Void
    @State private var details: LineageItem?
    @State private var scrollToFocus = 0
    @FocusState private var focusedNodeID: String?
    private var library: LibraryModel { model.library }

    var body: some View {
        VStack(spacing: 0) {
            toolbar.padding(16)
            Divider()
            if let graph = library.graph, !graph.nodes.isEmpty {
                ScrollViewReader { proxy in
                    ScrollView([.horizontal, .vertical]) {
                        if library.lineageVertical {
                            VStack(alignment: .leading, spacing: 24) {
                                ForEach(generations(graph), id: \.self) { generation in generationRow(graph, generation: generation) }
                            }.padding(24)
                        } else {
                            HStack(alignment: .top, spacing: 24) {
                                ForEach(generations(graph), id: \.self) { generation in generationColumn(graph, generation: generation) }
                            }.padding(24)
                        }
                    }
                    .focusSection()
                    .onChange(of: viewportKey(graph), initial: true) { _, _ in proxy.scrollTo(graph.focusNodeID, anchor: .center) }
                    .onChange(of: scrollToFocus) { _, _ in withAnimation { proxy.scrollTo(graph.focusNodeID, anchor: .center) } }
                }
                graphSummary(graph).padding(.horizontal, 16).padding(.vertical, 10).background(.bar)
            } else if library.lineageLoading {
                ProgressView(model.display.localized("系譜を読み込み中")).frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = library.lineageError {
                ContentUnavailableView {
                    Label(model.display.localized("系譜を読み込めません"), systemImage: "exclamationmark.triangle")
                } description: { Text(error).textSelection(.enabled) } actions: {
                    Button(model.display.localized("再試行")) { Task { await library.reloadLineage() } }
                }
            } else {
                ContentUnavailableView(model.display.localized("系譜を選択"), systemImage: "point.3.connected.trianglepath.dotted",
                                       description: Text(model.display.localized("ライブラリまたは制作画面で作品を選択してください。")))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .overlay(alignment: .topTrailing) {
            if library.lineageLoading, library.graph != nil {
                ProgressView(model.display.localized("系譜を読み込み中")).controlSize(.small)
                    .padding(10).background(.regularMaterial, in: Capsule()).padding(16)
            }
        }
        .task(id: model.selectedWorkID) { if let work = model.selectedWork { await library.loadLineage(work: work) } }
        .sheet(item: $details) { item in nodeDetails(item) }
    }

    private var toolbar: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Text(model.display.localized("系譜")).font(.title2.weight(.semibold))
                if let graph = library.graph {
                    Text(model.display.localizedFormat("%ld 節点 · %ld 接続", graph.nodes.count, graph.edges.count)).font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength: 8)
                Button(model.display.localized("中心へ"), systemImage: "scope") { scrollToFocus += 1 }.disabled(library.graph == nil)
                Button(model.display.localized("更新"), systemImage: "arrow.clockwise") { Task { await library.reloadLineage() } }
                    .disabled(library.graph == nil || library.lineageLoading)
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 20) { navigation; Spacer(minLength: 8); depthControls }
                VStack(alignment: .leading, spacing: 10) { navigation; depthControls }
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 14) { selectionControls; Spacer(minLength: 0); selectionLegend }
                VStack(alignment: .leading, spacing: 8) { selectionControls; selectionLegend }
            }
            if let error = library.lineageError ?? library.errorText {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "exclamationmark.triangle").foregroundStyle(.red)
                    Text(error).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    Button(model.display.localized("再試行")) { Task { await library.refresh(); await library.reloadLineage() } }
                }.font(.caption)
            } else if library.mutating {
                HStack(spacing: 8) { ProgressView().controlSize(.small); Text(model.display.localized("変更を保存中")) }.font(.caption)
            } else if !library.status.isEmpty {
                Text(model.display.message(library.status)).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var navigation: some View {
        @Bindable var library = library
        return HStack(spacing: 8) {
            Toggle(isOn: Binding(get: { library.lineagePathOnly }, set: { value in
                library.lineagePathOnly = value; Task { await library.reloadLineage() }
            })) { Label(model.display.localized("起点からの道筋"), systemImage: "point.topleft.down.to.point.bottomright.curvepath") }.toggleStyle(.button)
            Toggle(model.display.localized("縦に並べる"), isOn: $library.lineageVertical).toggleStyle(.button)
            Button(model.display.localized("全体"), systemImage: "point.3.connected.trianglepath.dotted") { Task { await library.loadLineageOverview() } }
                .help(model.display.preferences.showTooltips ? model.display.localized("起点から分岐を含む系譜全体を表示します。最大200節点。") : "")
        }.controlSize(.small).fixedSize().disabled(library.graph == nil || library.lineageLoading)
    }

    private var depthControls: some View {
        Stepper(model.display.localizedFormat("子孫 %ld 世代", library.lineageDepth), value: Binding(get: { library.lineageDepth }, set: { value in
            library.lineageDepth = value; Task { await library.reloadLineage() }
        }), in: 0...200)
        .fixedSize().disabled(library.lineagePathOnly || library.graph == nil || library.lineageLoading)
        .help(model.display.preferences.showTooltips ? model.display.localized("中心の節点から表示する子孫の深さ。親への道筋も表示します。") : "")
    }

    private var selectionControls: some View {
        HStack(spacing: 10) {
            Label(model.display.localizedFormat("チェックした作品: %ld 件", library.selectedIDs.count), systemImage: "checkmark.square")
                .font(.caption.weight(.medium)).monospacedDigit().fixedSize()
            Button(model.display.localized("表示中を選択")) { library.selectedIDs.formUnion(library.graph?.nodes.compactMap { $0.work?.id } ?? []) }
                .disabled(library.graph?.nodes.contains(where: { $0.work != nil }) != true)
            Button(model.display.localized("解除")) { library.selectedIDs.removeAll() }.disabled(library.selectedIDs.isEmpty)
        }.controlSize(.small).disabled(library.mutating || model.isBusy || library.lineageLoading)
    }

    private var selectionLegend: some View {
        Text(model.display.localized("中心は系譜の表示範囲、チェックは作品の複数選択です。"))
            .font(.caption).foregroundStyle(.secondary)
    }

    private func graphSummary(_ graph: LineageGraph) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: graph.truncated ? "ellipsis.circle" : "scope").foregroundStyle(.secondary)
            Text(model.display.localized(graph.truncated
                                         ? "表示範囲の外にも節点があります。深さを増やすか、節点を中心に表示して続きを確認できます。最大200節点。"
                                         : "節点を中心に表示して、親や子の分岐をたどれます。"))
                .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private struct ViewportKey: Equatable { let focus: String; let nodes: [String]; let vertical: Bool }
    private func viewportKey(_ graph: LineageGraph) -> ViewportKey { ViewportKey(focus: graph.focusNodeID, nodes: graph.nodes.map(\.id), vertical: library.lineageVertical) }

    private func generations(_ graph: LineageGraph) -> [Int] { Set(graph.nodes.map(\.generation)).sorted() }

    private func generationColumn(_ graph: LineageGraph, generation: Int) -> some View {
        LazyVStack(alignment: .leading, spacing: 12) {
            generationHeading(graph, generation: generation)
            ForEach(graph.nodes.filter { $0.generation == generation }) { item in nodeCard(item, graph: graph) }
        }.frame(width: 250)
    }

    private func generationRow(_ graph: LineageGraph, generation: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            generationHeading(graph, generation: generation)
            LazyHStack(alignment: .top, spacing: 12) {
                ForEach(graph.nodes.filter { $0.generation == generation }) { item in nodeCard(item, graph: graph).frame(width: 250) }
            }
        }
    }

    private func generationHeading(_ graph: LineageGraph, generation: Int) -> some View {
        HStack(spacing: 8) {
            Text(model.display.localizedFormat("第 %ld 世代", generation)).font(.caption.weight(.semibold))
            Text("\(graph.nodes.filter { $0.generation == generation }.count)").font(.caption.monospacedDigit())
                .padding(.horizontal, 6).padding(.vertical, 2).background(.quaternary, in: Capsule())
        }.foregroundStyle(.secondary)
    }

    private func nodeCard(_ item: LineageItem, graph: LineageGraph) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                if let work = item.work {
                    Button { library.toggleSelection(work.id) } label: {
                        Image(systemName: library.selectedIDs.contains(work.id) ? "checkmark.square.fill" : "square")
                    }.buttonStyle(.plain).foregroundStyle(library.selectedIDs.contains(work.id) ? Color.accentColor : Color.secondary)
                        .accessibilityLabel(model.display.localized("複数選択のチェック"))
                        .accessibilityValue(model.display.localized(library.selectedIDs.contains(work.id) ? "選択済み" : "未選択"))
                        .disabled(library.mutating || model.isBusy)
                }
                Text(operation(graph.edges.first { $0.childNodeID == item.id }?.derivationKind)).font(.caption.weight(.semibold)).lineLimit(1)
                Spacer(minLength: 0)
                if item.id == graph.focusNodeID { Label(model.display.localized("中心"), systemImage: "scope").font(.caption2).foregroundStyle(Color.accentColor) }
                Menu { nodeMenu(item, graph: graph) } label: { Image(systemName: "ellipsis") }
                    .fixedSize().accessibilityLabel(model.display.localized("節点の操作"))
            }
            if let work = item.work {
                Button { openWork(item) } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(height: 148)
                        LibraryWorkTitle(work: work, untitled: model.display.localized("無題"), lineLimit: 3)
                    }
                }.buttonStyle(.plain).disabled(model.isBusy)
                HStack(spacing: 8) {
                    if model.selectedWorkID == work.id { Label(model.display.localized("表示中"), systemImage: "eye").foregroundStyle(Color.accentColor) }
                    if LibraryWorkPresentation.usesDDLTitle(work) { Text("DDL").monospaced() }
                    if work.trashed { Label(model.display.localized("ごみ箱の作品"), systemImage: "trash") }
                }.font(.caption2).foregroundStyle(.secondary)
                HStack {
                    LibraryWorkMarks(model: model, work: work)
                    Spacer(minLength: 6)
                    if let hash = work.renderHash {
                        Button("…\(hash.suffix(4))") { library.copyHash(hash) }.font(.caption.monospaced())
                            .help(model.display.preferences.showTooltips ? model.display.localized("描画ハッシュ全体をコピー") : "")
                    }
                }.buttonStyle(.borderless).font(.caption)
                if let note = library.annotation(for: work.id).note {
                    Label { Text(note).lineLimit(2) } icon: { Image(systemName: "text.bubble") }.font(.caption).foregroundStyle(.secondary)
                }
                if item.node.state == "lineage_only" {
                    Button(model.display.localized("ライブラリへ追加"), systemImage: "plus") { Task { await library.promote(item.id) } }
                        .controlSize(.small).disabled(library.mutating || model.isBusy)
                }
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "trash.slash").font(.title)
                    Text(model.display.localized(item.node.state == "tombstone" ? "削除された作品" : "保存作品がありません"))
                }.frame(maxWidth: .infinity, minHeight: 148).foregroundStyle(.secondary)
            }
            HStack(spacing: 8) {
                Text(Date(timeIntervalSince1970: Double(item.node.at) / 1000), format: .dateTime.year().month().day().hour().minute())
                Spacer(minLength: 0)
                Text("…\(item.id.suffix(6))").monospaced()
            }.font(.caption2).foregroundStyle(.secondary)
            Divider()
            branchNavigation(item, graph: graph)
            HStack {
                Button { focusNode(item.id) } label: { Label(model.display.localized("中心に表示"), systemImage: "scope") }
                    .disabled(item.id == graph.focusNodeID || library.lineageLoading)
                Spacer(minLength: 0)
                Button { details = item } label: { Image(systemName: "info.circle") }
                    .accessibilityLabel(model.display.localized("保存情報・コメント"))
                    .help(model.display.preferences.showTooltips ? model.display.localized("保存情報・コメント") : "")
            }
            .font(.caption).buttonStyle(.borderless)
        }
        .padding(12)
        .modifier(LibraryCardSurface(current: item.id == graph.focusNodeID, focused: focusedNodeID == item.id, tombstone: item.node.state == "tombstone"))
        .contextMenu { nodeMenu(item, graph: graph) }
        .focusable().focused($focusedNodeID, equals: item.id)
        .onKeyPress(.return) {
            guard focusedNodeID == item.id, !model.isBusy, !library.lineageLoading else { return .ignored }
            if item.work != nil { openWork(item) } else { focusNode(item.id) }
            return .handled
        }
        .onKeyPress(.space) {
            guard focusedNodeID == item.id, let work = item.work, !library.mutating, !model.isBusy else { return .ignored }
            library.toggleSelection(work.id); return .handled
        }
        .accessibilityHint(model.display.localized("Returnで作品を表示、Spaceで複数選択のチェックを切り替えます。"))
        .id(item.id)
    }

    private func branchNavigation(_ item: LineageItem, graph: LineageGraph) -> some View {
        HStack(alignment: .top, spacing: 10) {
            if let parent = graph.edges.first(where: { $0.childNodeID == item.id }) {
                Button { focusNode(parent.parentNodeID) } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Label(model.display.localized("親の節点"), systemImage: "arrow.left")
                        Text("…\(parent.parentNodeID.suffix(6))").font(.caption2.monospaced()).foregroundStyle(.secondary)
                    }
                }
            } else {
                Text(model.display.localized(item.id == item.node.rootNodeID ? "起点" : "親は表示範囲外"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            if item.childCount > 0 {
                Menu {
                    Button(model.display.localized("子の節点を表示")) { focusNode(item.id, revealChildren: true) }
                    Divider()
                    ForEach(graph.edges.filter { $0.parentNodeID == item.id }, id: \.childNodeID) { edge in
                        Button(childTitle(edge.childNodeID, graph: graph)) { focusNode(edge.childNodeID) }
                    }
                } label: {
                    Label(model.display.localizedFormat("子の節点 (%ld)", item.childCount), systemImage: "arrow.right")
                }
            }
        }.font(.caption).buttonStyle(.borderless).disabled(library.lineageLoading)
    }

    private func childTitle(_ id: String, graph: LineageGraph) -> String {
        guard let item = graph.nodes.first(where: { $0.id == id }) else { return "…" + String(id.suffix(6)) }
        let title = item.work.map { LibraryWorkPresentation.title($0, untitled: model.display.localized("無題")) }
            ?? model.display.localized(item.node.state == "tombstone" ? "削除された作品" : "保存作品がありません")
        let firstLine = title.split(whereSeparator: \.isNewline).first.map(String.init) ?? title
        return String(firstLine.prefix(60)) + " · …" + String(id.suffix(6))
    }

    private func openWork(_ item: LineageItem) {
        guard let work = item.work else { return }
        Task { await model.selectWork(work); await library.loadLineage(nodeID: item.id) }
    }

    private func focusNode(_ id: String, revealChildren: Bool = false) {
        if revealChildren { library.lineagePathOnly = false; library.lineageDepth = max(1, library.lineageDepth) }
        Task { await library.loadLineage(nodeID: id) }
    }

    @ViewBuilder
    private func nodeMenu(_ item: LineageItem, graph: LineageGraph) -> some View {
        Button(model.display.localized("この節点を中心に表示"), systemImage: "scope") { focusNode(item.id) }.disabled(library.lineageLoading)
        if let root = item.node.rootNodeID, root != item.id {
            Button(model.display.localized("起点を中心に表示"), systemImage: "arrow.up.backward") { focusNode(root) }.disabled(library.lineageLoading)
        }
        if let parent = graph.edges.first(where: { $0.childNodeID == item.id }) {
            Button(model.display.localized("親の節点"), systemImage: "arrow.left") { focusNode(parent.parentNodeID) }.disabled(library.lineageLoading)
        }
        if item.childCount > 0 { Button(model.display.localized("子の節点を表示"), systemImage: "arrow.right") { focusNode(item.id, revealChildren: true) }.disabled(library.lineageLoading) }
        Button(model.display.localized("保存情報・コメント"), systemImage: "info.circle") { details = item }
        if let work = item.work {
            Divider()
            Button(model.display.localized("作品を開く"), systemImage: "eye") { openWork(item) }.disabled(model.isBusy)
            Button(model.display.localized("制作で編集"), systemImage: "pencil") {
                Task { await model.selectWork(work); NotificationCenter.default.post(name: .inkuOpenSection, object: "create") }
            }.disabled(model.isBusy || work.trashed)
            Button(model.display.localized("描画パラメータの編集"), systemImage: "slider.horizontal.3") { onAdjustWork(work) }
                .disabled(model.isBusy || work.trashed)
            Button(model.display.localized("記述を変える"), systemImage: "text.cursor") { onEditWork(work, .description) }
                .disabled(model.isBusy || work.trashed)
            Button(model.display.localized("写生なし／ありで描き直す"), systemImage: "pencil.and.outline") { onEditWork(work, .sketch) }
                .disabled(model.isBusy || work.trashed)
            Button(model.display.localized(library.selectedIDs.contains(work.id) ? "チェックを外す" : "複数選択に追加"), systemImage: "checkmark.square") { library.toggleSelection(work.id) }
                .disabled(library.mutating || model.isBusy)
            Button(model.display.localized(work.starred ? "お気に入りを解除" : "お気に入り"), systemImage: "star") { Task { await library.toggleStar(work) } }
                .disabled(library.mutating || model.isBusy)
            Button(model.display.localized("推敲の印"), systemImage: library.annotation(for: work.id).forRevision ? "pencil.circle.fill" : "pencil.circle") { Task { await library.toggleRevision(work) } }
                .disabled(library.mutating || model.isBusy)
            Button(model.display.localized("書き出し用の印"), systemImage: library.annotation(for: work.id).forShare ? "square.and.arrow.up.fill" : "square.and.arrow.up") { Task { await library.toggleShare(work) } }
                .disabled(library.mutating || model.isBusy)
            if let hash = work.renderHash { Button(model.display.localized("描画ハッシュ全体をコピー"), systemImage: "doc.on.doc") { library.copyHash(hash) } }
            if item.node.state == "lineage_only" {
                Button(model.display.localized("ライブラリへ追加"), systemImage: "plus") { Task { await library.promote(item.id) } }.disabled(library.mutating || model.isBusy)
            }
            Divider()
            if work.trashed {
                Button(model.display.localized("戻す"), systemImage: "arrow.uturn.backward") { Task { await library.restore(ids: [work.id]) } }.disabled(library.mutating || model.isBusy)
            } else {
                Button(model.display.localized("ごみ箱へ"), systemImage: "trash") { Task { await library.trash(ids: [work.id]) } }.disabled(library.mutating || model.isBusy)
            }
        }
    }

    private func nodeDetails(_ item: LineageItem) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(model.display.localized("系譜の保存情報")).font(.title2.weight(.semibold))
                Spacer()
                Button(model.display.localized("閉じる")) { details = nil }.keyboardShortcut(.cancelAction)
            }
            Text(model.display.localizedFormat("節点 ID: %@", item.id)).font(.caption.monospaced()).textSelection(.enabled)
            Text(model.display.localizedFormat("第 %ld 世代 · 子の節点 %ld · 状態 %@", item.generation, item.childCount, stateLabel(item.node.state))).font(.caption)
            if let deleted = item.node.deletedAt {
                Text(model.display.localizedFormat("削除日時: %@", Date(timeIntervalSince1970: Double(deleted) / 1000).formatted())).font(.caption)
            }
            if let work = item.work { LibraryWorkDetails(model: model, work: work).id(work.id) }
            else { Text(model.display.localized("元の節点と接続を保持しています。作品本文は削除されています。")).foregroundStyle(.secondary) }
        }.padding(24).frame(minWidth: 340, idealWidth: 700, minHeight: item.work == nil ? 240 : 660)
    }

    private func stateLabel(_ state: String) -> String {
        switch state {
        case "tombstone": model.display.localized("削除済み")
        case "lineage_only": model.display.localized("系譜のみ")
        case "active": model.display.localized("保存作品")
        default: state
        }
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
