import InkuHost
import InkuPersistence
import SwiftUI

private struct LineageDetailsSession: Identifiable {
    let item: LineageItem
    let note: LibraryNoteEditorModel
    var id: String { item.id }
}

@MainActor
struct LineageView: View {
    @Bindable var model: AppModel
    let onWorkAction: (SavedWork, String) -> Void
    let onExport: (LineageExportRequest) -> Void
    var initialWork: SavedWork? = nil
    var writingLocked = false
    var onBrowseWork: (SavedWork) -> Void = { _ in }
    var onOpenInCanvas: (SavedWork) -> Void = { _ in }
    var onDetach: () -> Void = {}
    @Environment(\.inkuWindowSize) private var windowSize
    @State private var checkedIDs: Set<String> = []
    @State private var afterOverview: (() -> Void)?
    @State private var details: LineageDetailsSession?
    @State private var noteEditors: [String: LibraryNoteEditorModel] = [:]
    @State private var actionAfterDetails: (work: SavedWork, action: String)?
    @State private var trashConfirmation: LineageTrashConfirmation?
    @State private var providers: [ProviderSettings] = []
    @FocusState private var focusedNodeID: String?
    private var library: LibraryModel { model.library }
    private var naming: ModelNaming { ModelNaming(providers: providers) }
    private var focusWork: SavedWork? {
        library.graph.flatMap { graph in graph.nodes.first { $0.id == graph.focusNodeID }?.work }
    }
    private var writingDisabled: Bool { model.isBusy || writingLocked }

    private func panel(overview: Bool) -> some View {
        VStack(spacing: 0) {
            toolbar.padding(.horizontal, 16).padding(.vertical, 12)
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
                            .backgroundPreferenceValue(LineageCardBounds.self) { anchors in
                                GeometryReader { geometry in
                                    scrollBridge(overview: overview, cards: anchors.values.map { geometry[$0] })
                                }
                            }
                        }
                        .focusSection()
                        .onChange(of: graph.focusNodeID, initial: true) { _, _ in
                            if !library.lineageBrowsing.overviewOpen { proxy.scrollTo(graph.focusNodeID, anchor: .center) }
                        }
                    }
                }
                if graph.truncated { graphSummary(graph).padding(.horizontal, 16).padding(.vertical, 10) }
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
    }

    var body: some View {
        panel(overview: false)
        .sheet(isPresented: Binding(get: { library.lineageBrowsing.overviewOpen }, set: { if !$0 { library.closeLineageOverview() } }), onDismiss: {
            let action = afterOverview; afterOverview = nil; action?()
        }) {
            panel(overview: true)
                .frame(width: max(640, (windowSize?.width ?? 1000) - 36), height: max(500, (windowSize?.height ?? 760) - 70))
                .environment(\.inkuWindowSize, windowSize)
        }
        .task(id: initialWork?.id) {
            if let work = initialWork {
                if library.graph?.focusNodeID != work.lineageNodeID { await library.loadLineage(work: work) }
            } else if library.graph == nil, let work = model.selectedWork {
                await library.loadLineage(work: work)
            }
        }
        .sheet(item: $details, onDismiss: {
            if let pending = actionAfterDetails {
                actionAfterDetails = nil
                onWorkAction(pending.work, pending.action)
            }
        }) { session in nodeDetails(session) }
        .onChange(of: library.lineageSelectionGraph) { _, graph in
            checkedIDs.formIntersection(graph?.nodes.compactMap(\.work).filter { !$0.trashed }.map(\.id) ?? [])
        }
        .task(id: model.providerSettingsRevision) { providers = await model.hostSettings().providers }
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
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) { toolbarTitle; toolbarActions }
                VStack(alignment: .leading, spacing: 8) { toolbarTitle; toolbarActions }
            }.buttonStyle(InkuGhostButtonStyle()).inkuFont(12)
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
                }.inkuFont(12)
            } else if library.mutating {
                HStack(spacing: 8) { ProgressView().controlSize(.small); Text(model.display.localized("変更を保存中")) }.inkuFont(12)
            } else if !library.status.isEmpty {
                Text(model.display.message(library.status)).inkuFont(12).foregroundStyle(.secondary)
            }
        }
    }

    private var toolbarTitle: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(model.display.localized("作品の系譜")).inkuFont(14, weight: .semibold)
            if library.lineageBrowsing.overviewOpen {
                Text(model.display.localized(library.lineageVertical ? "全体を上から下へ見渡せます。" : "全体を左から右へ見渡せます。"))
                    .inkuFont(12).foregroundStyle(.secondary)
            }
        }.frame(minWidth: 90, alignment: .leading)
    }

    private var toolbarActions: some View {
        LineageToolbarLayout {
                    toolbarGroup(model.display.webCopy("lineageViewTools", "表示")) { navigation }
                    if let graph = library.lineageDisplayGraph {
                        toolbarGroup(model.display.webCopy("lineageFocusedWork", "表示中の作品")) {
                            Menu(model.display.localized("推敲する")) {
                                if let work = focusWork {
                                    SavedWorkRefinementActions(model: model, work: work, onAction: dispatchWorkAction, writingLocked: writingDisabled)
                                }
                            }.disabled(focusWork == nil || writingDisabled)
                            Button(model.display.localized("作品を大きく見る")) { if let work = focusWork { openInCanvas(work) } }
                                .disabled(focusWork == nil || model.isBrowsingLocked)
                            exportButton(LineageWorkScope.focused(graph))
                        }
                        toolbarGroup(model.display.localizedFormat("起点から表示中まで %ld 件", LineageWorkScope.path(graph).workIDs.count)) {
                            exportButton(LineageWorkScope.path(graph))
                        }
                        toolbarGroup(model.display.localizedFormat("選択 %ld 件", checkedScope.workIDs.count)) {
                            exportButton(checkedScope)
                            Button { trashConfirmation = LineageTrashConfirmation(ids: checkedScope.workIDs) } label: { Image(systemName: "trash") }
                                .disabled(checkedIDs.isEmpty || writingDisabled || library.mutating)
                                .accessibilityLabel(model.display.localized("チェックした作品をゴミ箱へ移動"))
                                .inkuTooltip(tip("チェックした作品をゴミ箱へ移動"))
                        }
                    }
                    HStack(spacing: 8) {
                        Button(model.display.webCopy("okugakiRead", "奥書を読む")) { if let work = focusWork { dispatchWorkAction(work, "colophon") } }
                            .disabled(focusWork == nil || writingDisabled)
                            .inkuTooltip(model.display.tooltip("表示中の作品までの枝を、一人称の読み手として朗読します", serverKey: "okugakiTooltip"))
                        Button(model.display.localized("新しい起点にする")) {
                            performAfterOverview(onDetach)
                        }.disabled(writingDisabled)
                    }
        }.frame(maxWidth: .infinity, alignment: .trailing)
    }

    private var checkedScope: LineageExportRequest {
        guard let graph = library.lineageSelectionGraph else { return LineageExportRequest(workIDs: [], preserveOrder: false) }
        return LineageWorkScope.checked(graph, ids: checkedIDs)
    }

    private func toolbarGroup<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        HStack(spacing: 8) {
            Rectangle().fill(InkuColor.border).frame(width: 1, height: 22)
            Text(label).foregroundStyle(.secondary).fixedSize()
            content()
        }.fixedSize(horizontal: true, vertical: false)
    }

    private func exportButton(_ request: LineageExportRequest) -> some View {
        Button(model.display.localized("書き出す"), systemImage: "square.and.arrow.down") { performAfterOverview { onExport(request) } }
            .disabled(request.workIDs.isEmpty || writingDisabled || library.lineageLoading)
    }

    private var navigation: some View {
        @Bindable var library = library
        return HStack(spacing: 8) {
            InkuSegmentedButtons(options: [(true, model.display.localized("縦")), (false, model.display.localized("横"))],
                                 selection: $library.lineageVertical)
                .accessibilityLabel(model.display.localized("系譜の方向"))
                .inkuTooltip(tip("親子のつながりを縦または横に並べます。"))
            if library.lineageBrowsing.overviewOpen {
                Button { changeMapScale(-0.1) } label: {
                    Image(systemName: "minus")
                }.accessibilityLabel(model.display.localized("縮小"))
                    .disabled(library.lineageBrowsing.overviewScale <= 0.4).inkuTooltip(tip("全体図を縮小します。最小40%。"))
                Text(library.lineageBrowsing.overviewScale, format: .percent.precision(.fractionLength(0)))
                    .inkuFont(12).monospacedDigit().frame(minWidth: 42)
                Button { changeMapScale(0.1) } label: {
                    Image(systemName: "plus")
                }.accessibilityLabel(model.display.localized("拡大"))
                    .disabled(library.lineageBrowsing.overviewScale >= 1.4).inkuTooltip(tip("全体図を拡大します。最大140%。"))
                Button(model.display.localized("全体図を閉じる")) { library.closeLineageOverview() }
                    .inkuTooltip(tip("枝の開閉とスクロール位置を保った通常表示に戻ります。"))
            } else {
                Button(model.display.localized("全体図"), systemImage: "point.3.connected.trianglepath.dotted") { Task { await library.loadLineageOverview() } }
                    .inkuTooltip(tip("起点から分岐を含む系譜全体を表示します。最大200節点。"))
            }
        }.buttonStyle(InkuGhostButtonStyle()).disabled(library.graph == nil || library.lineageLoading)
    }

    private func graphSummary(_ graph: LineageSnapshot) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: graph.truncated ? "ellipsis.circle" : "scope").foregroundStyle(.secondary)
            Text(model.display.localized(graph.truncated
                                         ? "表示範囲の外にも節点があります。子作品を開くか、節点を中心に表示して続きを確認できます。最大200節点。"
                                         : "節点を中心に表示して、親や子の分岐をたどれます。"))
                .inkuFont(12).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func tip(_ key: String) -> String { model.display.tooltip(key) }

    private func changeMapScale(_ delta: Double) {
        let value = library.lineageBrowsing.overviewScale + delta
        library.lineageBrowsing.setOverviewScale(value)
    }

    private func scrollBridge(overview: Bool, cards: [CGRect]) -> some View {
        // The covered normal view must reapply its own offset when the map closes.
        let key = LineageViewportKey(treeID: library.lineageBrowsing.treeID, overview: library.lineageBrowsing.overviewOpen, vertical: library.lineageVertical)
        return LineageScrollBridge(revision: key, position: library.lineageBrowsing.scroll, cards: cards) { position in
            guard overview == library.lineageBrowsing.overviewOpen else { return }
            if overview { library.lineageBrowsing.overviewScroll = position }
            else { library.lineageBrowsing.normalScroll = position }
        }
    }

    private func performAfterOverview(_ action: @escaping () -> Void) {
        if library.lineageBrowsing.overviewOpen { afterOverview = action; library.closeLineageOverview() }
        else { action() }
    }

    private func dispatchWorkAction(_ work: SavedWork, _ action: String) {
        performAfterOverview { onWorkAction(work, action) }
    }

    private func openInCanvas(_ work: SavedWork) {
        performAfterOverview { onOpenInCanvas(work) }
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
        Text(model.display.preferences.language == "ja" ? "第\(generation)世代" : "Generation \(generation)").inkuFont(12)
            .foregroundStyle(.secondary).frame(maxWidth: .infinity)
    }

    private func nodeCard(_ item: LineageItem, graph: LineageSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 5) {
                if let work = item.work {
                    if !work.trashed {
                        Toggle(model.display.localized("一括操作の対象にする"), isOn: Binding(get: { checkedIDs.contains(work.id) }, set: { value in
                            if value { checkedIDs.insert(work.id) } else { checkedIDs.remove(work.id) }
                        })).labelsHidden()
                            .accessibilityLabel(model.display.localized("一括操作の対象にする"))
                            .disabled(library.mutating || model.isBrowsingLocked)
                    }
                    Button { Task { await library.toggleStar(work) } } label: {
                        Text("★").inkuFont(19).frame(width: 22, height: 22)
                            .background(Color.secondary.opacity(0.08), in: Circle()).overlay(Circle().stroke(InkuColor.border))
                    }
                        .foregroundStyle(work.starred ? Color.orange : Color.secondary)
                        .accessibilityLabel(model.display.localized(work.starred ? "お気に入りを解除" : "お気に入り"))
                        .disabled(writingDisabled || library.mutating)
                    Button { Task { await library.toggleRevision(work) } } label: {
                        Image(systemName: "flag.fill").inkuFont(12).frame(width: 24, height: 24)
                            .background(Color.secondary.opacity(0.08), in: Circle()).overlay(Circle().stroke(InkuColor.border))
                    }
                        .foregroundStyle(library.annotation(for: work.id).forRevision ? Color.red : Color.secondary)
                        .accessibilityLabel(model.display.localized("推敲の印"))
                        .disabled(writingDisabled || library.mutating)
                }
                identityMarks(item, graph: graph)
                Spacer(minLength: 0)
                if let work = item.work, !work.trashed {
                    Menu {
                        Section {
                            SavedWorkRefinementActions(model: model, work: work, onAction: dispatchWorkAction, writingLocked: writingDisabled)
                        } header: {
                            Text(cardRefinementTitle(work))
                        }
                    } label: { Image(systemName: "ellipsis") }
                        .fixedSize().accessibilityLabel(model.display.webCopy("workActionOpenMenu", "作品編集メニューを開く"))
                        .disabled(writingDisabled)
                }
            }.buttonStyle(.borderless).frame(minHeight: 22)
            if let work = item.work {
                Button { openWork(item) } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        operationRow(item, graph: graph)
                        ArtworkThumbnail(work: work, thumbnails: model.thumbnails).frame(height: 118)
                        if work.trashed { Text(model.display.localized("ゴミ箱（復元可能）")).inkuFont(12).foregroundStyle(.secondary) }
                        LibraryWorkTitle(work: work, untitled: model.display.localized("無題"), lineLimit: 2, size: 14)
                            .inkuTooltip(model.display.tooltipValue(work.effectiveSourceText.isEmpty ? (work.descriptionHash ?? "") : work.effectiveSourceText))
                    }
                }.buttonStyle(.plain).disabled(model.isBrowsingLocked)
                    .simultaneousGesture(TapGesture(count: 2).onEnded { openInCanvas(work) })
            } else {
                operationRow(item, graph: graph)
                VStack(spacing: 8) {
                    Text(model.display.localized(item.node.state == "tombstone" ? "削除された作品" : "保存作品がありません"))
                }.frame(maxWidth: .infinity, minHeight: 118).foregroundStyle(.secondary)
            }
            if !library.lineageBrowsing.overviewOpen {
                if item.childCount > 0, !graph.pathOnly {
                    let expanded = library.lineageBrowsing.expandedNodeIDs.contains(item.id)
                    Button { Task { await library.toggleLineageBranch(item.id) } } label: {
                        Label(model.display.localizedFormat("子作品 %ld 件", item.childCount), systemImage: expanded ? "chevron.down" : "chevron.right")
                            .frame(maxWidth: .infinity)
                    }.accessibilityValue(model.display.localized(expanded ? "展開中" : "折りたたみ中"))
                        .disabled(library.lineageLoading).buttonStyle(InkuGhostButtonStyle()).inkuFont(12)
                }
                if item.work != nil {
                    Button { openDetails(item) } label: {
                        Text(model.display.localized("詳細")).frame(maxWidth: .infinity, alignment: .leading)
                    }.buttonStyle(InkuGhostButtonStyle())
                        .inkuFont(12).accessibilityLabel(model.display.localized("作品の詳細"))
                }
            }
            if item.node.state == "lineage_only" {
                Button(model.display.localized("通常履歴に保存")) { Task { await library.promote(item.id) } }
                    .buttonStyle(InkuGhostButtonStyle()).disabled(library.mutating || writingDisabled)
            }
        }
        .padding(8)
        .modifier(LibraryCardSurface(current: item.id == graph.focusNodeID, focused: focusedNodeID == item.id, tombstone: item.node.state == "tombstone", cornerRadius: 10))
        .opacity(item.work?.trashed == true ? 0.62 : 1)
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
            guard !work.trashed else { return .ignored }
            if checkedIDs.contains(work.id) { checkedIDs.remove(work.id) } else { checkedIDs.insert(work.id) }
            return .handled
        }
        .anchorPreference(key: LineageCardBounds.self, value: .bounds) { [item.id: $0] }
        .id(item.id)
    }

    private func operationRow(_ item: LineageItem, graph: LineageSnapshot) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            Text(operation(graph.edges.first { $0.childNodeID == item.id }?.derivationKind)).fixedSize()
            if let work = item.work, !stageModelNames(work).isEmpty {
                Text(stageModelNames(work)).lineLimit(1).truncationMode(.tail)
                    .inkuTooltip(model.display.tooltipValue(stageModelTitle(work)))
            }
        }.inkuFont(12).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
    }

    private func cardRefinementTitle(_ work: SavedWork) -> String {
        let title = model.display.webCopy("workActionMenuTitle", "作品編集")
        switch model.workActionState(for: work) {
        case .userDDL: return title + " " + model.display.webCopy("workActionDdlOrigin", "（DDL直接生成作品）")
        case .lockedDescription: return title + " " + model.display.webCopy("descriptionLockedMark", "ロック")
        default: return title
        }
    }

    private func identityMarks(_ item: LineageItem, graph: LineageSnapshot) -> some View {
        let focus = graph.nodes.first { $0.id == graph.focusNodeID }
        return VStack(alignment: .leading, spacing: 3) {
            if item.id == graph.focusNodeID { identityBadge("表示中", active: true) }
            if let work = item.work, model.workActionState(for: work) == .lockedDescription {
                Label(model.display.webCopy("descriptionLockedMark", "ロック"), systemImage: "lock.fill").inkuFont(10)
                    .inkuTooltip(model.display.tooltip("編集した指示書で確定した作品です。記述を読み直す操作は使えません。", serverKey: "descriptionLockedReason"))
            }
            if item.node.state == "lineage_only" { identityBadge("中間作品・履歴非表示") }
            if LineageWorkScope.sameText(item, focus: focus) { identityBadge("同じ記述") }
            if LineageWorkScope.sameEdition(item, focus: focus) { identityBadge("同じ版") }
        }
    }

    private func identityBadge(_ key: String, active: Bool = false) -> some View {
        Text(model.display.localized(key)).inkuFont(11, weight: active ? .semibold : .regular)
            .foregroundStyle(active ? Color.accentColor : Color.secondary)
            .padding(.horizontal, 5).padding(.vertical, 1)
            .background(active ? Color.accentColor.opacity(0.12) : Color.secondary.opacity(0.08), in: Capsule())
    }

    private func openWork(_ item: LineageItem) {
        guard let work = item.work, !model.isBrowsingLocked,
              work.id != model.selectedWorkID || item.id != library.lineageDisplayGraph?.focusNodeID else { return }
        onBrowseWork(work)
        Task {
            if work.id == model.selectedWorkID { await library.loadLineage(work: work) }
            else { await model.selectWork(work) }
        }
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
        if !library.lineageBrowsing.overviewOpen {
            Button(model.display.localized("保存情報・コメント"), systemImage: "info.circle") { openDetails(item) }
                .help(tip("作品の保存情報とコメントを開きます。"))
        }
        if let work = item.work {
            Divider()
            Button(model.display.localized("作品を大きく見る"), systemImage: "eye") { openInCanvas(work) }.disabled(model.isBrowsingLocked)
            Button(model.display.localized("生成情報"), systemImage: "info.circle") { dispatchWorkAction(work, "info") }.disabled(model.isBrowsingLocked || work.trashed)
            Button(model.display.localized("制作で編集"), systemImage: "pencil") {
                Task { await model.selectWork(work); NotificationCenter.default.post(name: .inkuOpenSection, object: "create", userInfo: ["workID": work.id]) }
            }.disabled(model.isBrowsingLocked || work.trashed)
            SavedWorkRefinementActions(model: model, work: work, onAction: dispatchWorkAction, writingLocked: writingDisabled)
            Button(model.display.localized("書き出す")) { dispatchWorkAction(work, "export") }.disabled(writingDisabled || work.trashed)
            Button(model.display.localized(checkedIDs.contains(work.id) ? "チェックを外す" : "複数選択に追加"), systemImage: "checkmark.square") {
                if checkedIDs.contains(work.id) { checkedIDs.remove(work.id) } else { checkedIDs.insert(work.id) }
            }.disabled(library.mutating || model.isBrowsingLocked || work.trashed)
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

    private func nodeDetails(_ session: LineageDetailsSession) -> some View {
        let item = session.item
        return LineageDetailsView(model: model, item: item,
                          operation: operation(library.lineageDisplayGraph?.edges.first { $0.childNodeID == item.id }?.derivationKind),
                          naming: naming, note: session.note, writingLocked: writingDisabled,
                          onAction: queueDetailsAction, onClose: { details = nil }).id(item.id)
    }

    private func openDetails(_ item: LineageItem) {
        let note = noteEditors[item.id] ?? LibraryNoteEditorModel()
        noteEditors[item.id] = note
        details = LineageDetailsSession(item: item, note: note)
    }

    private func queueDetailsAction(_ work: SavedWork, _ action: String) {
        actionAfterDetails = (work, action)
        details = nil
    }

    /// LineagePanel.svelte:297-309 `stageModelNames` / `stageModelTitle`.
    private func stageModelNames(_ work: SavedWork) -> String {
        let stage1 = naming.modelShortName(work.stage1Model)
        let stage2 = naming.modelShortName(work.stage2Model)
        if !stage1.isEmpty, !stage2.isEmpty, stage1 != stage2 { return stage1 + " / " + stage2 }
        return stage1.isEmpty ? stage2 : stage1
    }

    private func stageModelTitle(_ work: SavedWork) -> String {
        [naming.displayName(work.stage1Model), naming.displayName(work.stage2Model)].enumerated()
            .compactMap { $0.element.isEmpty ? nil : "Stage \($0.offset + 1): \($0.element)" }.joined(separator: "\n")
    }

    private func operation(_ kind: String?) -> String {
        if model.display.preferences.language == "en" {
            if kind == nil { return "Origin" }
            let labels = ["touch_change": "Touch", "layout_change": "Layout", "catalog_change": "Color",
                          "color_arrangement_change": "Color arrangement", "ground_change": "Ground", "tool_change": "Touches",
                          "reinterpretation": "Reading", "model_comparison": "Model", "language_comparison": "Language",
                          "ddl_edit": "DDL edit", "description_edit": "Description edit", "replay": "Replay",
                          "canvas_aspect_change": "Canvas change", "variation": "Variation (retired)", "sketch_grain_change": "Sketch from life"]
            if let kind, let label = labels[kind] { return label }
        }
        let labels = ["tool_change": "てざわり", "touch_change": "タッチ", "layout_change": "構図", "catalog_change": "色",
                      "color_arrangement_change": "配色", "ground_change": "支持体",
                      "reinterpretation": "解釈", "model_comparison": "モデル", "language_comparison": "言語",
                      "ddl_edit": "DDL編集", "description_edit": "記述編集", "replay": "再描画",
                      "canvas_aspect_change": "キャンバス変更", "variation": "変奏（旧）", "sketch_grain_change": "写生の有無",
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
