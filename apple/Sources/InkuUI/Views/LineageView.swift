import InkuPersistence
import SwiftUI

@MainActor
struct LineageView: View {
    @Bindable var model: AppModel
    let onEditWork: (SavedWork, WorkEditMode) -> Void
    let onAdjustWork: (SavedWork) -> Void
    let onReplayWork: (SavedWork) -> Void
    let onWorkAction: (SavedWork, String) -> Void
    let onExport: (String) -> Void
    var initialWork: SavedWork? = nil
    var writingLocked = false
    var onBrowseWork: (SavedWork) -> Void = { _ in }
    @State private var details: LineageItem?
    @State private var replayAfterDetails: SavedWork?
    @State private var actionAfterDetails: (work: SavedWork, action: String)?
    @State private var trashConfirmation: LineageTrashConfirmation?
    @State private var scrollToFocus = 0
    @FocusState private var focusedNodeID: String?
    private var library: LibraryModel { model.library }
    private var writingDisabled: Bool { model.isBusy || writingLocked }

    var body: some View {
        VStack(spacing: 0) {
            toolbar.padding(16)
            Divider()
            if let graph = library.lineageDisplayGraph, !graph.nodes.isEmpty {
                GeometryReader { viewport in
                    ScrollViewReader { proxy in
                        ScrollView([.horizontal, .vertical]) {
                            let scale = library.lineageBrowsing.overviewOpen ? library.lineageBrowsing.overviewScale : 1
                            LineageScaleLayout(scale: scale) {
                                treePlot(graph, width: max(210, (viewport.size.width - 48) / scale), scale: scale)
                                    .scaleEffect(scale, anchor: .topLeading)
                            }
                            .padding(24)
                            .background(scrollBridge)
                        }
                        .focusSection()
                        .onChange(of: graph.focusNodeID, initial: true) { _, _ in
                            if !library.lineageBrowsing.overviewOpen { proxy.scrollTo(graph.focusNodeID, anchor: .center) }
                        }
                        .onChange(of: scrollToFocus) { _, _ in withAnimation { proxy.scrollTo(graph.focusNodeID, anchor: .center) } }
                    }
                }
                graphSummary(graph).padding(.horizontal, 16).padding(.vertical, 10).background(.bar)
            } else if library.lineageLoading {
                ProgressView(model.display.localized("系譜を読み込み中")).frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = library.lineageError {
                ContentUnavailableView {
                    Label(model.display.localized("系譜を読み込めません"), systemImage: "exclamationmark.triangle")
                } description: { Text(error).textSelection(.enabled) } actions: {
                    Button(model.display.localized("再試行")) { Task { await library.retryLineage() } }
                        .disabled(library.lineageLoading || model.isBrowsingLocked)
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
        .task(id: initialWork?.id) {
            if let work = initialWork {
                if library.graph?.focusNodeID != work.lineageNodeID { await library.loadLineage(work: work) }
            } else if library.graph == nil, let work = model.selectedWork {
                await library.loadLineage(work: work)
            }
        }
        .sheet(item: $details, onDismiss: {
            if let work = replayAfterDetails {
                replayAfterDetails = nil
                onReplayWork(work)
            }
            if let pending = actionAfterDetails {
                actionAfterDetails = nil
                onWorkAction(pending.work, pending.action)
            }
        }) { item in nodeDetails(item) }
        .alert(item: $trashConfirmation) { request in
            Alert(title: Text(model.display.localizedFormat("%ld件をごみ箱に移動しますか？", request.ids.count)),
                  primaryButton: .default(Text(model.display.localized("実行"))) {
                      guard !library.mutating, !writingDisabled else { return }
                      Task { await library.trash(ids: request.ids) }
                  }, secondaryButton: .cancel(Text(model.display.localized("キャンセル"))))
        }
    }

    private var toolbar: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Text(model.display.localized("系譜")).font(.title2.weight(.semibold))
                if let graph = library.lineageDisplayGraph {
                    Text(model.display.localizedFormat("%ld 節点 · %ld 接続", graph.nodes.count, graph.edges.count)).font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength: 8)
                Button(model.display.localized("中心へ"), systemImage: "scope") { scrollToFocus += 1 }.disabled(library.graph == nil)
                    .help(tip("表示中の中心節点へスクロールします。"))
                Button(model.display.localized("更新"), systemImage: "arrow.clockwise") { Task { await library.reloadLineage() } }
                    .disabled(library.graph == nil || library.lineageLoading)
                    .help(tip("系譜と保存情報を読み直します。"))
                Menu(model.display.localized("書き出す"), systemImage: "square.and.arrow.up") {
                    Button(model.display.localized("中心の作品")) { onExport("center") }
                        .disabled(library.graph?.nodes.first(where: { $0.id == library.graph?.focusNodeID })?.work?.trashed != false)
                    Button(model.display.localized("起点からの道筋")) { onExport("path") }.disabled(library.graph == nil)
                    Button(model.display.localizedFormat("チェックした作品: %ld 件", library.selectedIDs.count)) { onExport("checked") }
                        .disabled(library.selectedIDs.isEmpty)
                }.disabled(writingDisabled || library.lineageLoading)
            }
            navigation
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 14) { selectionControls; Spacer(minLength: 0); selectionLegend }
                VStack(alignment: .leading, spacing: 8) { selectionControls; selectionLegend }
            }
            if let error = library.lineageError ?? library.errorText {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "exclamationmark.triangle").foregroundStyle(.red)
                    Text(error).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    Button(model.display.localized("再試行")) {
                        Task {
                            if library.lineageError != nil { await library.retryLineage() }
                            else { await library.refresh() }
                        }
                    }.disabled(library.lineageLoading || library.loading || model.isBrowsingLocked)
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
            })) { Label(model.display.localized("起点からの道筋"), systemImage: "point.topleft.down.to.point.bottomright.curvepath") }
                .toggleStyle(.button).disabled(library.lineageBrowsing.overviewOpen)
                .help(tip("中心の作品へ至る親の道筋だけを表示します。"))
            Picker(model.display.localized("系譜の方向"), selection: $library.lineageVertical) {
                Text(model.display.localized("縦")).tag(true)
                Text(model.display.localized("横")).tag(false)
            }.pickerStyle(.segmented).frame(width: 110)
                .help(tip("親子のつながりを縦または横に並べます。"))
            if library.lineageBrowsing.overviewOpen {
                Button { changeMapScale(-0.1) } label: {
                    Image(systemName: "minus")
                }.accessibilityLabel(model.display.localized("縮小"))
                    .disabled(library.lineageBrowsing.overviewScale <= 0.4).help(tip("全体図を縮小します。最小40%。"))
                Text(library.lineageBrowsing.overviewScale, format: .percent.precision(.fractionLength(0)))
                    .font(.caption).monospacedDigit().frame(minWidth: 42)
                Button { changeMapScale(0.1) } label: {
                    Image(systemName: "plus")
                }.accessibilityLabel(model.display.localized("拡大"))
                    .disabled(library.lineageBrowsing.overviewScale >= 1.4).help(tip("全体図を拡大します。最大140%。"))
                Button(model.display.localized("全体図を閉じる")) { library.closeLineageOverview() }
                    .help(tip("枝の開閉とスクロール位置を保った通常表示に戻ります。"))
            } else {
                Button(model.display.localized("全体図"), systemImage: "point.3.connected.trianglepath.dotted") { Task { await library.loadLineageOverview() } }
                    .help(tip("起点から分岐を含む系譜全体を表示します。最大200節点。"))
            }
        }.controlSize(.small).disabled(library.graph == nil || library.lineageLoading)
    }

    private var selectionControls: some View {
        HStack(spacing: 10) {
            Label(model.display.localizedFormat("チェックした作品: %ld 件", library.selectedIDs.count), systemImage: "checkmark.square")
                .font(.caption.weight(.medium)).monospacedDigit().fixedSize()
            Button(model.display.localized("表示中を選択")) {
                if let graph = library.lineageDisplayGraph { library.selectedIDs.formUnion(visibleNodes(graph).compactMap { $0.work?.id }) }
            }.disabled(library.lineageDisplayGraph?.nodes.contains(where: { $0.work != nil }) != true)
                .help(tip("今見えている作品を複数選択に追加します。"))
            Button(model.display.localized("解除")) { library.selectedIDs.removeAll() }.disabled(library.selectedIDs.isEmpty)
                .help(tip("作品の複数選択を解除します。"))
        }.controlSize(.small).disabled(library.mutating || model.isBrowsingLocked || library.lineageLoading)
    }

    private var selectionLegend: some View {
        Text(model.display.localized("中心は系譜の表示範囲、チェックは作品の複数選択です。"))
            .font(.caption).foregroundStyle(.secondary)
    }

    private func graphSummary(_ graph: LineageSnapshot) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: graph.truncated ? "ellipsis.circle" : "scope").foregroundStyle(.secondary)
            Text(model.display.localized(graph.truncated
                                         ? "表示範囲の外にも節点があります。子作品を開くか、節点を中心に表示して続きを確認できます。最大200節点。"
                                         : "節点を中心に表示して、親や子の分岐をたどれます。"))
                .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func tip(_ key: String) -> String { model.display.tooltip(key) }

    private func changeMapScale(_ delta: Double) {
        let value = library.lineageBrowsing.overviewScale + delta
        library.lineageBrowsing.setOverviewScale(value)
    }

    private var scrollBridge: some View {
        let overview = library.lineageBrowsing.overviewOpen
        let key = LineageViewportKey(treeID: library.lineageBrowsing.treeID, overview: overview, vertical: library.lineageVertical)
        return LineageScrollBridge(revision: key, position: library.lineageBrowsing.scroll) { position in
            if overview { library.lineageBrowsing.overviewScroll = position }
            else { library.lineageBrowsing.normalScroll = position }
        }
    }

    private func visibleNodes(_ graph: LineageSnapshot) -> [LineageItem] {
        let ids = LineagePresentation.visibleIDs(graph, browsing: library.lineageBrowsing)
        return graph.nodes.filter { ids.contains($0.id) }
    }

    private func treePlot(_ graph: LineageSnapshot, width: CGFloat, scale: CGFloat) -> some View {
        Group {
            if library.lineageVertical {
                VStack(alignment: .leading, spacing: 58) {
                    ForEach(generations(graph), id: \.self) { generation in generationRow(graph, generation: generation) }
                }.frame(width: width)
            } else {
                HStack(alignment: .top, spacing: 58) {
                    ForEach(generations(graph), id: \.self) { generation in generationColumn(graph, generation: generation) }
                }.fixedSize(horizontal: true, vertical: true)
            }
        }
        .backgroundPreferenceValue(LineageCardBounds.self) { anchors in
            GeometryReader { geometry in
                Canvas { context, _ in
                    let visible = LineagePresentation.visibleIDs(graph, browsing: library.lineageBrowsing)
                    for edge in LineagePresentation.edges(graph, visibleIDs: visible) {
                        guard let parent = anchors[edge.parentID], let child = anchors[edge.childID] else { continue }
                        let line = LineagePresentation.connection(parent: geometry[parent], child: geometry[child], vertical: library.lineageVertical)
                        var path = Path(); path.move(to: line.start)
                        path.addCurve(to: line.end, control1: line.control1, control2: line.control2)
                        let color = edge.starredPath ? Color.orange : Color.secondary.opacity(0.72)
                        context.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: (edge.starredPath ? 2 : 1.5) / scale,
                                                                                  dash: edge.tombstone ? [5 / scale, 4 / scale] : []))
                        var head = Path(); head.move(to: line.end)
                        if library.lineageVertical {
                            head.addLine(to: CGPoint(x: line.end.x - 3.5, y: line.end.y - 7))
                            head.addLine(to: CGPoint(x: line.end.x + 3.5, y: line.end.y - 7))
                        } else {
                            head.addLine(to: CGPoint(x: line.end.x - 7, y: line.end.y - 3.5))
                            head.addLine(to: CGPoint(x: line.end.x - 7, y: line.end.y + 3.5))
                        }
                        head.closeSubpath(); context.fill(head, with: .color(color))
                    }
                }.allowsHitTesting(false).accessibilityHidden(true)
            }
        }
    }

    private func generations(_ graph: LineageSnapshot) -> [Int] { Set(visibleNodes(graph).map(\.generation)).sorted() }

    private func generationColumn(_ graph: LineageSnapshot, generation: Int) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            generationHeading(graph, generation: generation)
            ForEach(visibleNodes(graph).filter { $0.generation == generation }) { item in nodeCard(item, graph: graph) }
        }.frame(width: 210)
    }

    private func generationRow(_ graph: LineageSnapshot, generation: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            generationHeading(graph, generation: generation)
            LineageWrappingRow {
                ForEach(visibleNodes(graph).filter { $0.generation == generation }) { item in nodeCard(item, graph: graph).frame(width: 210) }
            }
        }
    }

    private func generationHeading(_ graph: LineageSnapshot, generation: Int) -> some View {
        HStack(spacing: 8) {
            Text(model.display.localizedFormat("第 %ld 世代", generation)).font(.caption.weight(.semibold))
            Text("\(visibleNodes(graph).filter { $0.generation == generation }.count)").font(.caption.monospacedDigit())
                .padding(.horizontal, 6).padding(.vertical, 2).background(.quaternary, in: Capsule())
        }.foregroundStyle(.secondary)
    }

    private func nodeCard(_ item: LineageItem, graph: LineageSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                if let work = item.work {
                    Button { library.toggleSelection(work.id) } label: {
                        Image(systemName: library.selectedIDs.contains(work.id) ? "checkmark.square.fill" : "square")
                    }.buttonStyle(.plain).foregroundStyle(library.selectedIDs.contains(work.id) ? Color.accentColor : Color.secondary)
                        .accessibilityLabel(model.display.localized("複数選択のチェック"))
                        .accessibilityValue(model.display.localized(library.selectedIDs.contains(work.id) ? "選択済み" : "未選択"))
                        .disabled(library.mutating || model.isBrowsingLocked)
                }
                Text(operation(graph.edges.first { $0.childNodeID == item.id }?.derivationKind)).font(.caption.weight(.semibold)).lineLimit(1)
                Spacer(minLength: 0)
                if item.id == graph.focusNodeID {
                    Label(model.display.localized("中心"), systemImage: "scope")
                        .font(.caption2).foregroundStyle(Color.accentColor)
                        .lineLimit(1).fixedSize(horizontal: true, vertical: false)
                }
                Menu { nodeMenu(item, graph: graph) } label: { Image(systemName: "ellipsis") }
                    .fixedSize().accessibilityLabel(model.display.localized("節点の操作"))
            }
            if let work = item.work {
                Button { openWork(item) } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(height: 148)
                        LibraryWorkTitle(work: work, untitled: model.display.localized("無題"), lineLimit: 3)
                    }
                }.buttonStyle(.plain).disabled(model.isBrowsingLocked)
                HStack(spacing: 8) {
                    if model.selectedWorkID == work.id { Label(model.display.localized("表示中"), systemImage: "eye").foregroundStyle(Color.accentColor) }
                    if LibraryWorkPresentation.usesDDLTitle(work) { Text("DDL").monospaced() }
                    if work.trashed { Label(model.display.localized("ごみ箱の作品"), systemImage: "trash") }
                }.font(.caption2).foregroundStyle(.secondary)
                HStack {
                    LibraryWorkMarks(model: model, work: work).disabled(writingDisabled)
                    Spacer(minLength: 6)
                    if let hash = work.renderHash {
                        Button("…\(hash.suffix(4))") { library.copyHash(hash) }.font(.caption.monospaced())
                            .help(model.display.tooltip("描画ハッシュ全体をコピー", serverKey: "historyHashCopyTitle"))
                    }
                }.buttonStyle(.borderless).font(.caption)
                if let note = library.annotation(for: work.id).note {
                    Label { Text(note).lineLimit(2) } icon: { Image(systemName: "text.bubble") }.font(.caption).foregroundStyle(.secondary)
                }
                if item.node.state == "lineage_only" {
                    Button(model.display.localized("ライブラリへ追加"), systemImage: "plus") { Task { await library.promote(item.id) } }
                        .controlSize(.small).disabled(library.mutating || writingDisabled)
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
                    .help(tip("この節点を中心に系譜を表示します。"))
                Spacer(minLength: 0)
                Button { details = item } label: { Image(systemName: "info.circle") }
                    .accessibilityLabel(model.display.localized("保存情報・コメント"))
                    .help(tip("作品の保存情報とコメントを開きます。"))
            }
            .font(.caption).buttonStyle(.borderless)
        }
        .padding(12)
        .modifier(LibraryCardSurface(current: item.id == graph.focusNodeID, focused: focusedNodeID == item.id, tombstone: item.node.state == "tombstone"))
        .contextMenu { nodeMenu(item, graph: graph) }
        .task(id: item.work?.id) { if let work = item.work { await model.loadWorkActionState(work) } }
        .focusable().focused($focusedNodeID, equals: item.id)
        .onKeyPress(.return) {
            guard focusedNodeID == item.id, !model.isBrowsingLocked, !library.lineageLoading else { return .ignored }
            if item.work != nil { openWork(item) } else { focusNode(item.id) }
            return .handled
        }
        .onKeyPress(.space) {
            guard focusedNodeID == item.id, let work = item.work, !library.mutating, !model.isBrowsingLocked else { return .ignored }
            library.toggleSelection(work.id); return .handled
        }
        .anchorPreference(key: LineageCardBounds.self, value: .bounds) { [item.id: $0] }
        .id(item.id)
    }

    private func branchNavigation(_ item: LineageItem, graph: LineageSnapshot) -> some View {
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
            if item.childCount > 0, !library.lineageBrowsing.overviewOpen, !graph.pathOnly {
                let expanded = library.lineageBrowsing.expandedNodeIDs.contains(item.id)
                Button { Task { await library.toggleLineageBranch(item.id) } } label: {
                    Label(model.display.localizedFormat("子作品 %ld 件", item.childCount), systemImage: expanded ? "chevron.down" : "chevron.right")
                }.accessibilityValue(model.display.localized(expanded ? "展開中" : "折りたたみ中"))
                    .help(tip("中心の作品を変えずに子作品の枝を開閉します。"))
            }
        }.font(.caption).buttonStyle(.borderless).disabled(library.lineageLoading)
    }

    private func openWork(_ item: LineageItem) {
        guard let work = item.work, !model.isBrowsingLocked else { return }
        onBrowseWork(work)
        Task { await model.selectWork(work) }
    }

    private func focusNode(_ id: String) {
        Task { await library.loadLineage(nodeID: id) }
    }

    @ViewBuilder
    private func nodeMenu(_ item: LineageItem, graph: LineageSnapshot) -> some View {
        Button(model.display.localized("この節点を中心に表示"), systemImage: "scope") { focusNode(item.id) }.disabled(library.lineageLoading)
            .help(tip("この節点を中心に系譜を表示します。"))
        if let root = item.node.rootNodeID, root != item.id {
            Button(model.display.localized("起点を中心に表示"), systemImage: "arrow.up.backward") { focusNode(root) }.disabled(library.lineageLoading)
        }
        if let parent = graph.edges.first(where: { $0.childNodeID == item.id }) {
            Button(model.display.localized("親の節点"), systemImage: "arrow.left") { focusNode(parent.parentNodeID) }.disabled(library.lineageLoading)
        }
        if item.childCount > 0, !library.lineageBrowsing.overviewOpen, !graph.pathOnly {
            Button(model.display.localized("子の節点を表示"), systemImage: "arrow.right") {
                if !library.lineageBrowsing.expandedNodeIDs.contains(item.id) { Task { await library.toggleLineageBranch(item.id) } }
            }.disabled(library.lineageLoading).help(tip("中心の作品を変えずに子作品の枝を開閉します。"))
        }
        Button(model.display.localized("保存情報・コメント"), systemImage: "info.circle") { details = item }
            .help(tip("作品の保存情報とコメントを開きます。"))
        if let work = item.work {
            Divider()
            Button(model.display.localized("作品を開く"), systemImage: "eye") { openWork(item) }.disabled(model.isBrowsingLocked)
            Button(model.display.localized("生成情報"), systemImage: "info.circle") { onWorkAction(work, "info") }.disabled(model.isBrowsingLocked || work.trashed)
            Button(model.display.localized("制作で編集"), systemImage: "pencil") {
                Task { await model.selectWork(work); NotificationCenter.default.post(name: .inkuOpenSection, object: "create", userInfo: ["workID": work.id]) }
            }.disabled(model.isBrowsingLocked || work.trashed)
            SavedWorkRefinementActions(model: model, work: work, onAction: onWorkAction, writingLocked: writingDisabled)
            Button(model.display.localized("書き出す")) { onWorkAction(work, "export") }.disabled(writingDisabled || work.trashed)
            Button(model.display.localized(library.selectedIDs.contains(work.id) ? "チェックを外す" : "複数選択に追加"), systemImage: "checkmark.square") { library.toggleSelection(work.id) }
                .disabled(library.mutating || model.isBrowsingLocked)
            Button(model.display.localized(work.starred ? "お気に入りを解除" : "お気に入り"), systemImage: "star") { Task { await library.toggleStar(work) } }
                .disabled(library.mutating || writingDisabled)
            Button(model.display.localized("推敲の印"), systemImage: library.annotation(for: work.id).forRevision ? "pencil.circle.fill" : "pencil.circle") { Task { await library.toggleRevision(work) } }
                .disabled(library.mutating || writingDisabled)
            Button(model.display.localized("書き出し用の印"), systemImage: library.annotation(for: work.id).forShare ? "square.and.arrow.up.fill" : "square.and.arrow.up") { Task { await library.toggleShare(work) } }
                .disabled(library.mutating || writingDisabled)
            if let hash = work.renderHash { Button(model.display.localized("描画ハッシュ全体をコピー"), systemImage: "doc.on.doc") { library.copyHash(hash) } }
            if item.node.state == "lineage_only" {
                Button(model.display.localized("ライブラリへ追加"), systemImage: "plus") { Task { await library.promote(item.id) } }.disabled(library.mutating || writingDisabled)
            }
            Divider()
            if work.trashed {
                Button(model.display.localized("戻す"), systemImage: "arrow.uturn.backward") { Task { await library.restore(ids: [work.id]) } }.disabled(library.mutating || writingDisabled)
            } else {
                Button(model.display.localized("ごみ箱へ"), systemImage: "trash") {
                    trashConfirmation = LineageTrashConfirmation(ids: [work.id])
                }.disabled(library.mutating || writingDisabled)
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
            if let work = item.work {
                LibraryWorkDetails(model: model, work: work, onReplayWork: { parent in
                    replayAfterDetails = parent
                    details = nil
                }, onOpenInCreate: { parent in queueDetailsAction(parent, "create") },
                   onAdjustWork: { parent in queueDetailsAction(parent, "parameters") },
                   onWorkAction: queueDetailsAction,
                   onOpenLineage: { parent in queueDetailsAction(parent, "lineage") },
                   writingLocked: writingDisabled).id(work.id)
            }
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

    private func queueDetailsAction(_ work: SavedWork, _ action: String) {
        actionAfterDetails = (work, action)
        details = nil
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

private struct LineageTrashConfirmation: Identifiable {
    let id = UUID()
    let ids: [String]
}

private struct LineageCardBounds: PreferenceKey {
    static var defaultValue: [String: Anchor<CGRect>] { [:] }
    static func reduce(value: inout [String: Anchor<CGRect>], nextValue: () -> [String: Anchor<CGRect>]) {
        value.merge(nextValue(), uniquingKeysWith: { _, new in new })
    }
}
