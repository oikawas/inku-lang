import InkuHost
import InkuPersistence
import SwiftUI

/// The library as Web `HistoryManager.svelte` (Build1162) lays it out: a heading row, a tool row, then the
/// listing with the preview column beside it. The thumbnail grid holds as many complete rows as fit and pages
/// instead of scrolling. The owner shows it over the whole window and passes `onClose`.
@MainActor
struct LibraryView: View {
    @Bindable var model: AppModel
    @Bindable var preview: LibraryPreviewModel
    let onEditWork: (SavedWork, WorkEditMode) -> Void
    let onAdjustWork: (SavedWork) -> Void
    let onReplayWork: (SavedWork) -> Void
    let onWorkAction: (SavedWork, String) -> Void
    var writingLocked = false
    /// Web `onClose` ("制作に戻る"). The button is shown only when the owner can close the library.
    var onClose: (() -> Void)? = nil
    @State private var deletion: LibraryDeletion?
    @State private var loadingGroups: Set<String> = []
    @State private var providers: [ProviderSettings] = []
    @State private var gridViewport: CGSize = .zero
    @State private var pageSizeCeiling = LibraryGridPaging.maximumPageSize
    @State private var cardHeights: [String: CGFloat] = [:]
    @FocusState private var focusedWorkID: String?
    private var library: LibraryModel { model.library }
    private var display: DisplaySettings { model.display }
    private var naming: ModelNaming { ModelNaming(providers: providers) }
    private var writingDisabled: Bool { model.isBusy || writingLocked }
    private var hasFilters: Bool {
        !library.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || library.starredOnly || library.revisionOnly || library.shareOnly
    }
    private var visibleIDs: [String] {
        library.isGrouped
            ? library.groups.flatMap { library.groupMembers[$0.id]?.map(\.id) ?? [$0.representative.id] }
            : library.works.map(\.id)
    }
    private var allVisibleSelected: Bool { !visibleIDs.isEmpty && visibleIDs.allSatisfy(library.selectedIDs.contains) }
    /// Web `lineageGroupPageSize` (HistoryManager.svelte:326).
    private static let lineageGroupPageSize = 8

    var body: some View {
        VStack(spacing: 0) {
            head.padding(.vertical, 9).padding(.horizontal, 12)
            Divider()
            tools.padding(.vertical, 7).padding(.horizontal, 12)
            Divider()
            statusRows
            HStack(spacing: 0) {
                listing.frame(maxWidth: .infinity, maxHeight: .infinity)
                if preview.work != nil {
                    Divider()
                    previewContent.frame(minWidth: 280, idealWidth: 360, maxWidth: 360, maxHeight: .infinity)
                }
            }
        }
        .background(LibraryChrome.panel2)
        .task(id: PreviewReadKey(workID: preview.work?.id, mutating: library.mutating)) {
            guard !library.mutating else { return }
            await preview.loadAnnotation(using: { id in
                try await model.auxiliaryDatabase().libraryAnnotation(id: id)
            }, readWork: { id in try await model.auxiliaryDatabase().work(id: id) })
        }
        .task(id: model.providerSettingsRevision) { providers = await model.hostSettings().providers }
        .onAppear { applyGroupedPageSize() }
        .onChange(of: library.isGrouped) { _, _ in applyGroupedPageSize() }
        #if os(macOS)
        .onExitCommand { onClose?() }
        #endif
        .alert(item: $deletion) { request in
          if request.movesToTrash {
            return Alert(title: Text(display.localizedFormat("%ld件をごみ箱に移動しますか？", request.ids.count)),
                  primaryButton: .default(Text(display.localized("実行"))) {
                      guard !library.mutating, !writingDisabled else { return }
                      Task { await library.trash(ids: request.ids) }
                  }, secondaryButton: .cancel(Text(display.localized("キャンセル"))))
          } else {
            return Alert(title: Text(display.localized(request.empty ? "ごみ箱を空にしますか？" : "選択した作品を完全に削除しますか？")),
                  message: Text(display.localized("作品を復元することはできません。系譜には削除済みの節点が残ります。")),
                  primaryButton: .destructive(Text(display.localized("完全に削除"))) {
                      guard !library.mutating, !writingDisabled else { return }
                      Task { if request.empty { await library.emptyTrash() } else { await library.permanentlyDelete(ids: request.ids) } }
                  }, secondaryButton: .cancel(Text(display.localized("キャンセル"))))
          }
        }
    }

    // MARK: Heading (Web .modal-head)

    private var head: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) { headLeft; Spacer(minLength: 8); headActions }
            VStack(alignment: .leading, spacing: 7) { headLeft; HStack { Spacer(minLength: 0); headActions } }
        }
        .disabled(library.mutating || model.isBrowsingLocked)
    }

    private var headLeft: some View {
        HStack(spacing: 8) {
            Text(display.webCopy("historyLibraryTitle", fallback: "ライブラリ"))
                .inkuFont(15, weight: .light).tracking(0.75).fixedSize()
            controlGroup(display.webCopy("historyDisplayFormat", fallback: "表示形式")) {
                LibrarySegmentTabs(options: [
                    (LibraryLayout.grid, display.webCopy("historyThumbsTab", fallback: "サムネイル"),
                     display.tooltip("作品をサムネイルで並べます", serverKey: "tooltipHistoryThumbsTab")),
                    (LibraryLayout.list, display.webCopy("historyListTab", fallback: "リスト"),
                     display.tooltip("保存情報を一覧表で見比べます", serverKey: "tooltipHistoryListTab")),
                ], selection: Binding(get: { library.layout == .list ? .list : .grid }, set: { library.layout = $0 }))
            }
            controlGroup(display.webCopy("historyGrouping", fallback: "まとめ方")) {
                LibrarySegmentTabs(options: [
                    (false, display.webCopy("historyChronologicalMode", fallback: "時系列"),
                     display.tooltip("系譜をまたいで、新しい順に並べます", serverKey: "tooltipHistoryChronological")),
                    (true, display.webCopy("historyLineageMode", fallback: "系譜ごと"),
                     display.tooltip(library.layout == .grid ? "2作品以上の系譜を、起点から世代順に並べます。単独作品は時系列で表示できます。" : "同じ系譜の作品をまとめて表示します。",
                                     serverKey: "tooltipHistoryLineageGrouped")),
                ], selection: Binding(get: { library.grouped }, set: { library.grouped = $0 }))
            }
            Text(countText).inkuFont(12).monospacedDigit().foregroundStyle(.secondary).lineLimit(1).fixedSize()
            if library.loading { ProgressView().controlSize(.small) }
        }
    }

    private func controlGroup<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        HStack(spacing: 5) {
            Text(title).inkuFont(12).foregroundStyle(.secondary).fixedSize()
            content()
        }
    }

    private var countText: String {
        if library.isGrouped {
            // The thumbnail tab lists only lineages with a derivation (minimum two works).
            return "\(library.total) " + display.webCopy("historyLineageGroups", fallback: "系譜")
                + (library.layout == .grid ? display.webCopy("historyLineageGroupsDerivedOnly", fallback: "（派生のある系譜のみ）") : "")
        }
        return library.total == 0 ? "0 / 0" : "\(library.shownFrom)-\(library.shownTo) / \(library.total)"
    }

    private var headActions: some View {
        HStack(spacing: 8) {
            pager
            if let onClose {
                Button(display.webCopy("historyLibraryReturn", fallback: "制作に戻る")) { onClose() }
                    .buttonStyle(LibraryGhostButtonStyle())
                    .help(display.tooltip("制作に戻る", serverKey: "historyLibraryReturn"))
            }
        }
    }

    private var pager: some View {
        HStack(spacing: 6) {
            Button(display.webCopy("historyLatest", fallback: "最新")) { Task { await library.setPage(0) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 54))
                .disabled(library.page <= 0 || library.loading)
                .help(display.tooltip("先頭ページ", serverKey: "tooltipHistoryLatestPage"))
            Button(display.webCopy("historyNewer", fallback: "← 新しい")) { Task { await library.setPage(library.page - 1) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 74))
                .disabled(library.page <= 0 || library.loading)
                .help(display.tooltip("前のページ", serverKey: "tooltipHistoryNewerPage"))
            Text(library.loading ? display.webCopy("historyLoading", fallback: "読み込み中") : "\(library.page + 1) / \(library.pageCount)")
                .inkuFont(12).monospacedDigit().foregroundStyle(.secondary).fixedSize()
            Button(display.webCopy("historyOlder", fallback: "古い →")) { Task { await library.setPage(library.page + 1) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 74))
                .disabled(library.page + 1 >= library.pageCount || library.loading)
                .help(display.tooltip("次のページ", serverKey: "tooltipHistoryOlderPage"))
            Button(display.webCopy("historyOldest", fallback: "最古")) { Task { await library.setPage(library.pageCount - 1) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 54))
                .disabled(library.page + 1 >= library.pageCount || library.loading)
                .help(display.tooltip("最終ページ", serverKey: "tooltipHistoryOldestPage"))
        }
        .disabled(library.mutating)
    }

    // MARK: Tools (Web .history-tools)

    private var tools: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) { toolGroup; Spacer(minLength: 8); searchField }
            VStack(alignment: .leading, spacing: 7) { toolGroup; searchField }
        }
        .disabled(library.mutating || model.isBrowsingLocked)
    }

    private var toolGroup: some View {
        @Bindable var library = library
        return HStack(spacing: 8) {
            Button(allVisibleSelected ? display.localized("表示中のチェックを外す") : display.webCopy("historySelectAll", fallback: "すべて選択")) {
                library.selectVisible()
            }
            .buttonStyle(LibraryGhostButtonStyle())
            .disabled(visibleIDs.isEmpty || library.loading)
            .help(display.tooltip("このページの作品をすべて選択します", serverKey: "tooltipHistorySelectAll"))
            if !library.selectedIDs.isEmpty {
                Button(display.localized("解除")) { library.selectedIDs.removeAll() }
                    .buttonStyle(LibraryGhostButtonStyle())
                    .help(tip("ページをまたいでチェックした作品をすべて解除します。"))
            }
            HStack(spacing: 4) {
                Text(display.webCopy("historyFilterLabel", fallback: "絞り込み")).inkuFont(12).foregroundStyle(.tertiary).fixedSize()
                filterButton(display.webCopy("historyStarredOnly", fallback: "スターのみ"), isOn: $library.starredOnly,
                             tooltip: display.tooltip("お気に入りの作品に絞り込みます。", serverKey: "tooltipHistoryStarredOnly"))
                filterButton(display.webCopy("historyForRevisionOnly", fallback: "推敲マークのみ"), isOn: $library.revisionOnly,
                             tooltip: display.tooltip("推敲の印を付けた作品に絞り込みます。", serverKey: "tooltipHistoryForRevisionOnly"))
                filterButton(display.localized("書き出し用のみ"), isOn: $library.shareOnly,
                             tooltip: display.tooltip("書き出し用の印を付けた作品に絞り込みます。", serverKey: "tooltipHistoryForShareOnly"))
            }
            .padding(.leading, 10)
            .overlay(alignment: .leading) { Rectangle().fill(LibraryChrome.border).frame(width: 1) }
            Button(display.label("ごみ箱 (\(library.trashTotal))", "trash (\(library.trashTotal))")) { library.isTrash.toggle() }
                .buttonStyle(LibraryGhostButtonStyle(active: library.isTrash))
                .help(display.tooltip("ごみ箱の作品を表示・復元できます。", serverKey: "tooltipHistoryTrashView"))
            selectionActions
            Picker(display.localized("順序"), selection: $library.order) {
                Text(display.localized("新しい順")).tag(LibraryOrder.newest)
                Text(display.localized("古い順")).tag(LibraryOrder.oldest)
            }
            .labelsHidden().pickerStyle(.menu).fixedSize().controlSize(.small)
            .help(tip("保存日時の順序を切り替えます。"))
            Button { Task { await library.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                .buttonStyle(LibraryGhostButtonStyle())
                .accessibilityLabel(display.localized("更新"))
                .disabled(library.loading)
                .help(tip("ライブラリを読み直します。"))
        }
    }

    private func filterButton(_ title: String, isOn: Binding<Bool>, tooltip: String) -> some View {
        Button { isOn.wrappedValue.toggle() } label: {
            HStack(spacing: 2) {
                Text("✓").fontWeight(.bold).opacity(isOn.wrappedValue ? 1 : 0)
                Text(title)
            }
        }
        .buttonStyle(LibraryGhostButtonStyle(active: isOn.wrappedValue))
        .accessibilityAddTraits(isOn.wrappedValue ? .isSelected : [])
        .help(tooltip)
    }

    @ViewBuilder private var selectionActions: some View {
        if library.isTrash {
            Button(display.webCopy("historyRestoreSelected", fallback: "選択復元")) { Task { await library.restore() } }
                .buttonStyle(LibraryGhostButtonStyle())
                .disabled(library.selectedIDs.isEmpty || writingDisabled)
                .help(display.tooltip("選択した作品をごみ箱から戻します", serverKey: "tooltipHistoryRestoreSelected"))
            Button(display.webCopy("historyPermanentDelete", fallback: "完全削除")) { deletion = LibraryDeletion(ids: library.selectedIDs.sorted()) }
                .buttonStyle(LibraryGhostButtonStyle(danger: true))
                .disabled(library.selectedIDs.isEmpty || writingDisabled)
                .help(display.tooltip("選択した作品を完全に削除します。元に戻せません", serverKey: "tooltipHistoryPermanentDelete"))
            Menu {
                Button(display.localized("ごみ箱を空にする"), role: .destructive) { deletion = LibraryDeletion(ids: [], empty: true) }
                    .disabled(library.trashTotal == 0)
            } label: { Image(systemName: "ellipsis") }
                .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                .accessibilityLabel(display.localized("ごみ箱の操作"))
                .disabled(writingDisabled)
        } else {
            Button { deletion = LibraryDeletion(ids: library.selectedIDs.sorted(), movesToTrash: true) } label: {
                HStack(spacing: 4) {
                    Image(systemName: "trash")
                    if !library.selectedIDs.isEmpty { Text("\(library.selectedIDs.count)").monospacedDigit() }
                }
            }
            .buttonStyle(LibraryGhostButtonStyle(minWidth: 38))
            .disabled(library.selectedIDs.isEmpty || writingDisabled)
            .accessibilityLabel(display.webCopy("historyMoveToTrash", fallback: "選択削除"))
            .help(display.tooltip("選択した作品をごみ箱へ移します。あとで戻せます", serverKey: "tooltipHistoryMoveToTrash"))
        }
    }

    private var searchField: some View {
        @Bindable var library = library
        return HStack(spacing: 6) {
            Text(display.localized("検索")).inkuFont(12).foregroundStyle(.secondary).fixedSize()
            TextField(display.localized("記述・DDL・モデル・色・ハッシュを検索"), text: $library.query)
                .textFieldStyle(.roundedBorder).inkuFont(12)
                .frame(minWidth: 120, maxWidth: 240)
        }
    }

    // MARK: Status rows (Web .history-selection-status, .history-selection-reset)

    @ViewBuilder private var statusRows: some View {
        if !library.selectedIDs.isEmpty {
            Text(display.label("選択 \(library.selectedIDs.count)件", "\(library.selectedIDs.count) selected"))
                .inkuFont(12).foregroundStyle(Color.accentColor)
                .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 5).padding(.horizontal, 12)
            Divider()
        }
        if let error = library.errorText, library.total > 0 {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "exclamationmark.triangle").foregroundStyle(.red)
                Text(error).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                Button(display.localized("再読込")) { Task { await library.refresh() } }.buttonStyle(LibraryGhostButtonStyle())
            }
            .inkuFont(12).padding(.vertical, 5).padding(.horizontal, 12)
            Divider()
        } else if library.mutating {
            HStack(spacing: 8) { ProgressView().controlSize(.small); Text(display.localized("変更を保存中")) }
                .inkuFont(12).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 5).padding(.horizontal, 12)
            Divider()
        } else if !library.status.isEmpty {
            Text(display.message(library.status)).inkuFont(12).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 5).padding(.horizontal, 12)
            Divider()
        }
    }

    // MARK: Listing

    @ViewBuilder
    private var listing: some View {
        if library.loading && library.works.isEmpty {
            ProgressView(display.localized("ライブラリを読み込み中")).frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = library.errorText, library.total == 0 {
            ContentUnavailableView {
                Label(display.localized("ライブラリを読み込めません"), systemImage: "exclamationmark.triangle")
            } description: {
                Text(error).textSelection(.enabled)
            } actions: {
                Button(display.localized("再読込")) { Task { await library.refresh() } }
            }
        } else if library.total == 0 {
            emptyLibrary
        } else if library.isGrouped {
            lineageList
        } else if library.layout == .list {
            alignedList
        } else {
            thumbGrid
        }
    }

    /// Web `.history-thumb-grid-wrap` (padding 8/10/6) holding `repeat(auto-fill, minmax(142px, 1fr))`, gap 8.
    private var thumbGrid: some View {
        GeometryReader { geometry in
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: LibraryGridPaging.minCardWidth), spacing: LibraryGridPaging.gap, alignment: .top)],
                          alignment: .leading, spacing: LibraryGridPaging.gap) {
                    ForEach(library.works, id: \.id) { work in gridCard(work) }
                }
                .padding(.top, 8).padding(.horizontal, 10).padding(.bottom, 6)
            }
            // A page holds only complete rows; an always-on scroller would also take width from the columns.
            .scrollIndicators(.hidden)
            .focusSection()
            .onAppear { reportPageSize(viewport: geometry.size) }
            .onChange(of: geometry.size) { _, size in reportPageSize(viewport: size) }
        }
    }

    /// Web `calculatePageSize` and its ResizeObserver (HistoryManager.svelte:644-700): a new viewport starts again
    /// from 100; within one viewport the size only shrinks, so different cards cannot make two sizes alternate.
    private func reportPageSize(viewport size: CGSize) {
        let viewport = CGSize(width: (size.width * 2).rounded() / 2, height: (size.height * 2).rounded() / 2)
        if viewport != gridViewport {
            gridViewport = viewport
            pageSizeCeiling = LibraryGridPaging.maximumPageSize
        }
        guard !library.isGrouped, library.layout != .list, viewport.width > 0, viewport.height > 0 else { return }
        let shown = Set(library.works.map(\.id))
        let heights = cardHeights.filter { shown.contains($0.key) }.map { Double($0.value) }
        let fitted = LibraryGridPaging.pageSize(width: viewport.width - 20, height: viewport.height - 14, cardHeights: heights)
        pageSizeCeiling = min(pageSizeCeiling, fitted)
        if library.pageSize != pageSizeCeiling { library.pageSize = pageSizeCeiling }
    }

    private func recordCardHeight(_ height: CGFloat, for id: String) {
        guard abs((cardHeights[id] ?? 0) - height) > 0.5 else { return }
        cardHeights[id] = height
        reportPageSize(viewport: gridViewport)
    }

    /// Lineage groups page by eight (Web); leaving them hands the size back to the measured grid.
    private func applyGroupedPageSize() {
        if library.isGrouped {
            if library.pageSize != Self.lineageGroupPageSize { library.pageSize = Self.lineageGroupPageSize }
        } else if gridViewport != .zero {
            pageSizeCeiling = LibraryGridPaging.maximumPageSize
            reportPageSize(viewport: gridViewport)
        }
    }

    // MARK: Cards (Web .manager-thumb-wrap)

    private func gridCard(_ work: SavedWork) -> some View {
        let selected = library.selectedIDs.contains(work.id)
        return VStack(alignment: .leading, spacing: 5) {
            Button { openWork(work) } label: {
                ArtworkThumbnail(work: work, renderer: model.renderer)
                    .aspectRatio(82.0 / 58.0, contentMode: .fit)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.plain).disabled(model.isBrowsingLocked)
            .accessibilityLabel(display.localizedFormat("%@ を開く", LibraryWorkPresentation.title(work, untitled: display.localized("無題"))))
            .help(display.tooltip("作品をプレビューします。制作中の内容は変わりません。"))
            .overlay(alignment: .topLeading) { selectionCheck(work).padding(1) }
            .overlay(alignment: .bottomTrailing) { if model.selectedWorkID == work.id { currentBadge.padding(3) } }
            VStack(alignment: .leading, spacing: 4) {
                if LibraryWorkPresentation.usesDDLTitle(work) {
                    Text("DDL").inkuFont(12, weight: .semibold).foregroundStyle(.tertiary)
                }
                LibraryWorkTitle(work: work, untitled: display.localized("無題"), lineLimit: 3, size: 14)
                    .foregroundStyle(.secondary)
                if let note = library.annotation(for: work.id).note, !note.isEmpty {
                    (Text(display.webCopy("historyPreviewCommentLabel", fallback: "作品へのコメント") + " ").fontWeight(.semibold) + Text(note))
                        .inkuFont(10).foregroundStyle(.tertiary).lineLimit(1)
                }
                savedFacts(work)
                LibraryModelLinesView(work: work, display: display, naming: naming)
                cardActions(work)
            }
            .frame(minHeight: 64, alignment: .top)
        }
        .padding(5)
        .modifier(LibraryCardSurface(current: selected || preview.work?.id == work.id, focused: focusedWorkID == work.id, cornerRadius: 4))
        .background {
            GeometryReader { proxy in
                Color.clear
                    .onAppear { recordCardHeight(proxy.size.height, for: work.id) }
                    .onChange(of: proxy.size.height) { _, height in recordCardHeight(height, for: work.id) }
            }
        }
        .contextMenu { workMenu(work) }
        .task(id: work.id) { await model.loadWorkActionState(work) }
        .focusable().focused($focusedWorkID, equals: work.id)
        .onKeyPress(.return) {
            guard focusedWorkID == work.id, !model.isBrowsingLocked else { return .ignored }
            openWork(work); return .handled
        }
        .onKeyPress(.space) {
            guard focusedWorkID == work.id, !library.mutating, !model.isBrowsingLocked else { return .ignored }
            library.toggleSelection(work.id); return .handled
        }
    }

    /// Native facts the Web card does not print: saved time and SVG size, with the colour catalog on hover.
    private func savedFacts(_ work: SavedWork) -> some View {
        (Text(Date(timeIntervalSince1970: Double(work.at) / 1000).formatted(date: .numeric, time: .shortened))
            + Text(" · " + ByteCountFormatter.string(fromByteCount: SavedWorkFacts.svgBytes(work), countStyle: .file)))
            .inkuFont(10).monospacedDigit().foregroundStyle(.tertiary).lineLimit(1)
            .help(display.tooltipValue(display.localized("色") + ": " + (work.renderColorCatalogName ?? work.catalogID ?? display.localized("未記録"))))
    }

    /// Web `.thumb-action-row`: star, revision mark, hash; the native share mark, lineage and menu follow.
    private func cardActions(_ work: SavedWork) -> some View {
        HStack(spacing: 4) {
            LibraryWorkMarks(model: model, work: work, spacing: 4).disabled(writingDisabled)
            if let hash = work.renderHash {
                Button("#\(hash.suffix(4))") { library.copyHash(hash) }
                    .inkuFont(10, design: .monospaced)
                    .help(display.tooltip("描画ハッシュ全体をコピー", serverKey: "historyHashCopyTitle"))
            }
            if work.lineageNodeID != nil {
                Button { openLineage(work) } label: { Image(systemName: "point.3.connected.trianglepath.dotted") }
                    .accessibilityLabel(display.localized("系譜")).disabled(model.isBrowsingLocked)
                    .help(display.tooltip("この作品の系譜を開きます。"))
            }
            Spacer(minLength: 0)
            Menu { workMenu(work) } label: { Image(systemName: "ellipsis") }
                #if os(macOS)
                .menuStyle(.borderlessButton).menuIndicator(.hidden)
                #endif
                .fixedSize().accessibilityLabel(display.localized("作品の操作"))
                .help(tip("作品の操作"))
        }
        .inkuFont(12).buttonStyle(.borderless)
    }

    private var currentBadge: some View {
        Text(display.webCopy("historyCurrentBadge", fallback: "表示中"))
            .inkuFont(9).foregroundStyle(.white)
            .padding(.vertical, 1).padding(.horizontal, 4)
            .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 2))
    }

    private func selectionCheck(_ work: SavedWork) -> some View {
        let selected = library.selectedIDs.contains(work.id)
        return Button { library.toggleSelection(work.id) } label: { LibrarySelectionBox(selected: selected) }
            .buttonStyle(.plain)
            .accessibilityLabel(display.localizedFormat("%@ を選択", LibraryWorkPresentation.title(work, untitled: display.localized("無題"))))
            .accessibilityValue(display.localized(selected ? "選択済み" : "未選択"))
            .help(display.tooltip(selected ? "作品の選択を解除" : "作品を選択"))
            .disabled(library.mutating || model.isBrowsingLocked)
    }

    // MARK: List (Web .history-table)

    @ViewBuilder private var alignedList: some View {
        #if os(macOS)
        Table(library.works.map { LibraryTableRow(work: $0) }, selection: Binding<String?>(
            get: { preview.work?.id },
            set: { id in if let work = library.works.first(where: { $0.id == id }) { openWork(work) } }
        )) {
            TableColumn("") { row in selectionCheck(row.work) }.width(32)
            TableColumn(display.webCopy("historyImageHeader", fallback: "画像")) { row in
                ArtworkThumbnail(work: row.work, renderer: model.renderer).frame(width: 48, height: 36)
                    .overlay(alignment: .topTrailing) {
                        if row.work.starred { Image(systemName: "star.fill").font(.system(size: 9)).foregroundStyle(.yellow).padding(2) }
                    }
            }.width(62)
            TableColumn(display.webCopy("historyDescriptionHeader", fallback: "記述")) { row in
                VStack(alignment: .leading, spacing: 3) {
                    LibraryWorkTitle(work: row.work, untitled: display.localized("無題"), lineLimit: 2, size: 14)
                    if let note = library.loadedAnnotation(for: row.id)?.note, !note.isEmpty {
                        Text(note).inkuFont(10).foregroundStyle(.secondary).lineLimit(1)
                    }
                }.padding(.vertical, 3)
            }.width(min: 170, ideal: 300)
            TableColumn(display.webCopy("historyCreatedAtHeader", fallback: "作成日時")) { row in
                Text(Date(timeIntervalSince1970: Double(row.work.at) / 1000).formatted(date: .numeric, time: .shortened))
                    .inkuFont(12)
            }.width(min: 105, ideal: 116)
            TableColumn(display.webCopy("historyModelHeader", fallback: "モデル")) { row in
                LibraryModelLinesView(work: row.work, display: display, naming: naming)
            }.width(min: 130, ideal: 190)
            TableColumn(display.webCopy("historyCatalogHeader", fallback: "色カタログ")) { row in
                Text(row.work.renderColorCatalogName ?? row.work.catalogID ?? display.localized("未記録"))
                    .inkuFont(12).lineLimit(1)
            }.width(min: 70, ideal: 100)
            TableColumn(display.webCopy("historySvgSizeHeader", fallback: "SVGサイズ")) { row in
                Text(ByteCountFormatter.string(fromByteCount: SavedWorkFacts.svgBytes(row.work), countStyle: .file))
                    .inkuFont(12).monospacedDigit()
            }.width(74)
            TableColumn(display.webCopy("historyHashHeader", fallback: "ハッシュ")) { row in
                if let hash = row.work.renderHash {
                    Button("#\(hash.suffix(4))") { library.copyHash(hash) }.buttonStyle(.borderless)
                        .inkuFont(11, design: .monospaced)
                        .help(display.tooltip("描画ハッシュ全体をコピー", serverKey: "historyHashCopyTitle"))
                }
            }.width(72)
            TableColumn(display.webCopy("historyActionHeader", fallback: "操作")) { row in
                HStack(spacing: 4) {
                    LibraryWorkMarks(model: model, work: row.work, spacing: 4).disabled(writingDisabled)
                    Menu { workMenu(row.work) } label: { Image(systemName: "ellipsis") }
                        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                        .help(tip("作品の操作"))
                }
            }.width(min: 110, ideal: 120)
        }
        .contextMenu(forSelectionType: String.self) { ids in
            if let id = ids.first, let work = library.works.first(where: { $0.id == id }) { workMenu(work) }
        }
        #else
        ScrollView {
            LazyVStack(spacing: 8) {
                ForEach(library.works, id: \.id) { work in gridCard(work) }
            }.padding(.top, 8).padding(.horizontal, 10).padding(.bottom, 6)
        }
        #endif
    }

    private var emptyLibrary: some View {
        ContentUnavailableView {
            Label(display.localized(hasFilters ? "一致する作品がありません" : library.isTrash ? "ごみ箱は空です" : "ライブラリに作品がありません"),
                  systemImage: library.isTrash ? "trash" : "square.grid.2x2")
        } description: {
            Text(display.localized(hasFilters ? "検索や印の条件を変えてください。" : library.isTrash
                                         ? "ごみ箱へ移した作品をここから戻せます。" : "制作画面で保存した作品がここに表示されます。"))
        } actions: {
            if hasFilters {
                Button(display.localized("検索条件を解除")) {
                    library.query = ""; library.starredOnly = false; library.revisionOnly = false; library.shareOnly = false
                }
            } else if !library.isTrash {
                Button(display.localized("制作へ")) {
                    onClose?()
                    NotificationCenter.default.post(name: .inkuOpenSection, object: "create")
                }
            }
        }
    }

    // MARK: Lineage groups (Web .lineage-history-list)

    private var lineageList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                ForEach(library.groups) { group in groupCard(group) }
            }
            .padding(.top, 10).padding(.horizontal, 12).padding(.bottom, 16)
        }
        .focusSection()
    }

    private func groupCard(_ group: LibraryGroup) -> some View {
        let thumbs = library.layout != .list
        let open = thumbs || library.expandedGroups.contains(group.id)
        let members = library.groupMembers[group.id] ?? []
        let current = model.selectedWorkID.map { id in members.contains { $0.id == id } || group.representative.id == id } ?? false
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                if !thumbs {
                    Button { openWork(group.representative.work) } label: {
                        ArtworkThumbnail(work: group.representative.work, renderer: model.renderer).frame(width: 56, height: 56)
                    }
                    .buttonStyle(.plain)
                    .help(display.webCopy("historyPreviewTitle", fallback: "作品プレビュー"))
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text(LibraryWorkPresentation.title(group.representative.work, untitled: display.localized("無題")))
                        .inkuFont(12, weight: .semibold).lineLimit(1)
                    Text(groupSummary(group)).inkuFont(10).foregroundStyle(.tertiary).lineLimit(1)
                    if current {
                        Text(display.webCopy("historyCurrentLineage", fallback: "表示中作品の系譜"))
                            .inkuFont(10).foregroundStyle(Color.accentColor)
                            .padding(.vertical, 2).padding(.horizontal, 6)
                            .background(Color.accentColor.opacity(0.14), in: Capsule())
                    }
                }
                Spacer(minLength: 0)
                if loadingGroups.contains(group.id) { ProgressView().controlSize(.small) }
                if !thumbs {
                    Button(display.webCopy(open ? "historyLineageCollapse" : "historyLineageExpand", fallback: open ? "閉じる" : "作品を表示")) {
                        toggleGroup(group.id)
                    }
                    .buttonStyle(LibraryGhostButtonStyle())
                    .disabled(loadingGroups.contains(group.id))
                    .help(display.tooltip("この系譜の作品を開いて一覧します", serverKey: "historyLineageExpandTitle"))
                }
            }
            .padding(.vertical, 9).padding(.horizontal, 10)
            if open {
                Divider()
                HStack(spacing: 6) {
                    Spacer(minLength: 0)
                    Button(display.localized("系譜")) { openLineage(group.representative.work) }
                        .buttonStyle(LibraryGhostButtonStyle())
                        .disabled(model.isBrowsingLocked || group.representative.work.lineageNodeID == nil)
                        .help(display.tooltip("この作品の系譜を開きます。"))
                    Button(display.webCopy("historySelectLineage", fallback: "この系譜をすべて選択")) {
                        Task { await library.selectGroup(group.id) }
                    }
                    .buttonStyle(LibraryGhostButtonStyle())
                    .disabled(library.mutating || model.isBrowsingLocked || library.loading)
                    .help(display.tooltip("この系譜の作品をすべて選択します", serverKey: "historySelectLineageTitle"))
                }
                .padding(.vertical, 6).padding(.horizontal, 10)
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    if loadingGroups.contains(group.id), members.isEmpty {
                        ProgressView(display.localized("作品を読み込み中")).frame(maxWidth: .infinity).padding(12)
                    } else if thumbs {
                        // Web wraps the generations with minmax(132px, 1fr) rather than a horizontal lane.
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 132), spacing: 8, alignment: .top)], alignment: .leading, spacing: 8) {
                            ForEach(members) { item in memberCard(item.work) }
                        }
                    } else {
                        ForEach(members) { item in memberRow(item.work) }
                    }
                    HStack {
                        Text(display.localizedFormat("%ld / %ld 作品", members.count, library.groupMemberTotals[group.id] ?? group.itemCount))
                            .inkuFont(10).monospacedDigit().foregroundStyle(.secondary)
                        Spacer()
                        if members.count < (library.groupMemberTotals[group.id] ?? 0) {
                            Button(display.localized("さらに表示")) { loadMore(group.id) }
                                .buttonStyle(LibraryGhostButtonStyle()).disabled(loadingGroups.contains(group.id))
                        }
                    }
                }
                .padding(.top, 8).padding(.horizontal, 10).padding(.bottom, 12)
                .background(Color.accentColor.opacity(thumbs ? 0.05 : 0))
            }
        }
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8).stroke(current ? Color.accentColor : LibraryChrome.border, lineWidth: current ? 2 : 1)
        }
        .overlay(alignment: .leading) {
            if thumbs { UnevenRoundedRectangle(topLeadingRadius: 8, bottomLeadingRadius: 8).fill(current ? Color.accentColor : LibraryChrome.border).frame(width: 3) }
        }
        .contextMenu {
            Button(display.webCopy("historySelectLineage", fallback: "この系譜をすべて選択"), systemImage: "checkmark.square") { Task { await library.selectGroup(group.id) } }
                .disabled(library.mutating || model.isBrowsingLocked)
            Button(display.localized("系譜"), systemImage: "point.3.connected.trianglepath.dotted") { openLineage(group.representative.work) }
                .disabled(model.isBrowsingLocked || group.representative.work.lineageNodeID == nil)
        }
    }

    private func groupSummary(_ group: LibraryGroup) -> String {
        let latest = Date(timeIntervalSince1970: Double(group.latestAt) / 1000).formatted(date: .numeric, time: .shortened)
        return display.label("作品 \(group.itemCount)件 · スター \(group.starredCount)件 · 推敲マーク \(group.revisionCount)件 · \(latest)",
                             "\(group.itemCount) work\(group.itemCount == 1 ? "" : "s") · \(group.starredCount) starred · \(group.revisionCount) revision mark\(group.revisionCount == 1 ? "" : "s") · \(latest)")
    }

    /// Web `.lineage-member`: padding 5, the picture at most 110 high, a 10px one-line description, then its marks.
    private func memberCard(_ work: SavedWork) -> some View {
        let selected = library.selectedIDs.contains(work.id)
        return VStack(alignment: .leading, spacing: 4) {
            Button { openWork(work) } label: {
                VStack(alignment: .leading, spacing: 4) {
                    ArtworkThumbnail(work: work, renderer: model.renderer)
                        .aspectRatio(82.0 / 58.0, contentMode: .fit)
                        .frame(maxWidth: .infinity, maxHeight: 110)
                    Text(LibraryWorkPresentation.title(work, untitled: display.localized("無題")))
                        .inkuFont(10).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            .buttonStyle(.plain).disabled(model.isBrowsingLocked)
            .help(display.webCopy("historyPreviewTitle", fallback: "作品プレビュー"))
            .overlay(alignment: .topLeading) { selectionCheck(work).padding(3) }
            .overlay(alignment: .topTrailing) { if model.selectedWorkID == work.id { currentBadge.padding(3) } }
            HStack(spacing: 4) {
                LibraryWorkMarks(model: model, work: work, spacing: 4).disabled(writingDisabled)
                Spacer(minLength: 0)
                Menu { workMenu(work) } label: { Image(systemName: "ellipsis") }
                    #if os(macOS)
                    .menuStyle(.borderlessButton).menuIndicator(.hidden)
                    #endif
                    .fixedSize().accessibilityLabel(display.localized("作品の操作"))
            }
            .inkuFont(12).buttonStyle(.borderless)
        }
        .padding(5)
        .modifier(LibraryCardSurface(current: selected || model.selectedWorkID == work.id, focused: focusedWorkID == work.id, cornerRadius: 4))
        .contextMenu { workMenu(work) }
        .task(id: work.id) { await model.loadWorkActionState(work) }
    }

    /// Web list-mode `.lineage-member`: check, 48px picture, description, actions on one row.
    private func memberRow(_ work: SavedWork) -> some View {
        HStack(spacing: 8) {
            selectionCheck(work)
            Button { openWork(work) } label: {
                HStack(spacing: 8) {
                    ArtworkThumbnail(work: work, renderer: model.renderer).frame(width: 48, height: 48)
                    Text(LibraryWorkPresentation.title(work, untitled: display.localized("無題")))
                        .inkuFont(10).foregroundStyle(.secondary).lineLimit(1)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }.contentShape(Rectangle())
            }
            .buttonStyle(.plain).disabled(model.isBrowsingLocked)
            LibraryWorkMarks(model: model, work: work, spacing: 4).disabled(writingDisabled)
            Menu { workMenu(work) } label: { Image(systemName: "ellipsis") }
                #if os(macOS)
                .menuStyle(.borderlessButton).menuIndicator(.hidden)
                #endif
                .fixedSize().accessibilityLabel(display.localized("作品の操作"))
        }
        .inkuFont(12)
        .padding(5)
        .modifier(LibraryCardSurface(current: library.selectedIDs.contains(work.id) || model.selectedWorkID == work.id, cornerRadius: 4))
        .contextMenu { workMenu(work) }
        .task(id: work.id) { await model.loadWorkActionState(work) }
    }

    // MARK: Actions

    private func openWork(_ work: SavedWork) {
        guard !model.isBrowsingLocked else { return }
        preview.show(work)
    }

    private func openInCreate(_ work: SavedWork) {
        guard preview.work?.id == work.id, !model.isBrowsingLocked else { return }
        Task {
            do {
                if try await preview.openInCreate(app: model) {
                    onClose?()
                    NotificationCenter.default.post(name: .inkuOpenSection, object: "create", userInfo: ["workID": work.id])
                }
            } catch { model.errorText = error.localizedDescription }
        }
    }

    private func openLineage(_ work: SavedWork) {
        guard !model.isBrowsingLocked else { return }
        Task {
            await model.selectWork(work); await library.loadLineage(work: work)
            onClose?()
            NotificationCenter.default.post(name: .inkuOpenSection, object: "lineage", userInfo: ["workID": work.id])
        }
    }

    @ViewBuilder
    private func workMenu(_ work: SavedWork) -> some View {
        Button(display.localized("作品プレビュー"), systemImage: "eye") { openWork(work) }.disabled(model.isBrowsingLocked)
        Button(display.localized("生成情報"), systemImage: "info.circle") { onWorkAction(work, "info") }.disabled(model.isBrowsingLocked || work.trashed)
        Button(display.localized("制作で開く"), systemImage: "pencil") {
            openWork(work); openInCreate(work)
        }.disabled(model.isBrowsingLocked || work.trashed)
        SavedWorkRefinementActions(model: model, work: work, onAction: onWorkAction, writingLocked: writingDisabled)
        Button(display.localized("書き出す"), systemImage: "square.and.arrow.up") { onWorkAction(work, "export") }.disabled(writingDisabled || work.trashed)
        if work.lineageNodeID != nil { Button(display.localized("系譜"), systemImage: "point.3.connected.trianglepath.dotted") { openLineage(work) }.disabled(model.isBrowsingLocked) }
        Divider()
        Button(display.localized(library.selectedIDs.contains(work.id) ? "チェックを外す" : "複数選択に追加"), systemImage: "checkmark.square") { library.toggleSelection(work.id) }
            .disabled(library.mutating || model.isBrowsingLocked)
        Button(display.localized(work.starred ? "お気に入りを解除" : "お気に入り"), systemImage: "star") { Task { await library.toggleStar(work) } }
            .disabled(library.mutating || writingDisabled)
        Button(display.localized("推敲の印"), systemImage: library.annotation(for: work.id).forRevision ? "pencil.circle.fill" : "pencil.circle") { Task { await library.toggleRevision(work) } }
            .disabled(library.mutating || writingDisabled)
        Button(display.localized("書き出し用の印"), systemImage: library.annotation(for: work.id).forShare ? "square.and.arrow.up.fill" : "square.and.arrow.up") { Task { await library.toggleShare(work) } }
            .disabled(library.mutating || writingDisabled)
        if let hash = work.renderHash { Button(display.localized("描画ハッシュ全体をコピー"), systemImage: "doc.on.doc") { library.copyHash(hash) } }
        Divider()
        if work.trashed {
            Button(display.localized("戻す"), systemImage: "arrow.uturn.backward") { Task { await library.restore(ids: [work.id]) } }.disabled(library.mutating || writingDisabled)
            Button(display.localized("完全に削除"), role: .destructive) { deletion = LibraryDeletion(ids: [work.id]) }.disabled(library.mutating || writingDisabled)
        } else {
            Button(display.localized("ごみ箱へ"), systemImage: "trash") {
                deletion = LibraryDeletion(ids: [work.id], movesToTrash: true)
            }.disabled(library.mutating || writingDisabled)
        }
    }

    private func toggleGroup(_ id: String) {
        loadingGroups.insert(id)
        Task { await library.toggleGroup(id); loadingGroups.remove(id) }
    }

    private func loadMore(_ id: String) {
        loadingGroups.insert(id)
        Task { await library.loadGroup(root: id, append: true); loadingGroups.remove(id) }
    }

    // MARK: Preview (Web .history-preview, minmax(280px, 360px))

    @ViewBuilder
    private var previewContent: some View {
        if let work = preview.work {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(display.webCopy("historyPreviewTitle", fallback: "作品プレビュー")).inkuFont(13, weight: .semibold)
                        Spacer()
                        Button(display.webCopy("closeLabel", fallback: "閉じる")) { preview.close() }
                            .buttonStyle(LibraryGhostButtonStyle())
                            .accessibilityLabel(display.localized("プレビューを閉じる"))
                            .help(tip("プレビューを閉じる"))
                    }
                    LibraryWorkDetails(model: model, work: work, onReplayWork: onReplayWork,
                                       annotationSource: preview.annotationState,
                                       onAnnotationSaved: { id, value in preview.adoptAnnotation(value, workID: id) },
                                       onOpenInCreate: openInCreate,
                                       onAdjustWork: onAdjustWork, onWorkAction: onWorkAction,
                                       onOpenLineage: openLineage, writingLocked: writingDisabled)
                        .id(work.id)
                    if let error = preview.errorText {
                        Text(error).inkuFont(12).foregroundStyle(.red).textSelection(.enabled)
                        Button(display.localized("再試行")) {
                            Task { await preview.loadAnnotation(using: { id in try await model.auxiliaryDatabase().libraryAnnotation(id: id) }) }
                        }.buttonStyle(LibraryGhostButtonStyle())
                    }
                }.padding(12)
            }
            .background(LibraryChrome.panel2)
        }
    }

    private func tip(_ key: String) -> String { display.tooltip(key) }

    private struct PreviewReadKey: Equatable {
        let workID: String?
        let mutating: Bool
    }
}


private struct LibraryDeletion: Identifiable {
    let id = UUID()
    let ids: [String]
    var empty = false
    var movesToTrash = false
}

private struct LibraryTableRow: Identifiable {
    let work: SavedWork
    var id: String { work.id }
}

@MainActor
struct LibraryWorkDetails: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let onReplayWork: (SavedWork) -> Void
    var annotationSource: LibraryAnnotationState? = nil
    var onAnnotationSaved: ((String, LibraryAnnotation) -> Void)? = nil
    var onOpenInCreate: ((SavedWork) -> Void)? = nil
    var onAdjustWork: ((SavedWork) -> Void)? = nil
    var onWorkAction: ((SavedWork, String) -> Void)? = nil
    var onOpenLineage: ((SavedWork) -> Void)? = nil
    var writingLocked = false
    @State private var comment = LibraryNoteEditorModel()
    private var library: LibraryModel { model.library }
    private var writingDisabled: Bool { model.isBusy || writingLocked }
    private var annotationState: LibraryAnnotationState {
        if let annotationSource { return annotationSource }
        if library.isAnnotationLoading(for: work.id) { return .loading }
        if let value = library.loadedAnnotation(for: work.id) { return .available(value) }
        return .unavailable
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 14) { heading; Spacer(minLength: 12); workActions }
                VStack(alignment: .leading, spacing: 10) { heading; workActions }
            }
            ArtworkCanvas(svg: work.svg, renderer: model.renderer, caption: work.effectiveSourceText)
                .frame(height: 280)
            LibraryModelFactsView(work: work, display: model.display)
            if let onWorkAction {
                ViewThatFits(in: .horizontal) {
                    HStack { previewActions(onWorkAction) }
                    VStack(alignment: .leading, spacing: 8) { previewActions(onWorkAction) }
                }.controlSize(.small).disabled(model.isBrowsingLocked || work.trashed)
            }
            LabeledContent(model.display.localized("SVG容量"), value: ByteCountFormatter.string(fromByteCount: SavedWorkFacts.svgBytes(work), countStyle: .file))
                .inkuFont(12).foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label(model.display.localized("コメント"), systemImage: "text.bubble").inkuFont(12, weight: .medium)
                    Spacer()
                    Text("\(comment.text.utf16.count) / \(LibraryNoteEditorModel.limit)").inkuFont(12).monospacedDigit().foregroundStyle(.secondary)
                    Button(model.display.localized("保存")) { saveNote() }
                        .disabled(writingDisabled || library.mutating || !comment.canSave)
                        .help(model.display.tooltip("この作品のコメントを保存します。"))
                }
                // Typing stops at the limit, as the Web textarea's maxlength does.
                TextField(model.display.localized("コメント（240文字まで）"), text: Binding(
                    get: { comment.text }, set: { comment.text = LibraryNoteEditorModel.limited($0) }), axis: .vertical)
                    .lineLimit(2...4).textFieldStyle(.roundedBorder)
                    .disabled(writingDisabled || annotationState.annotation == nil || comment.saving)
                if annotationState == .loading {
                    HStack(spacing: 6) { ProgressView().controlSize(.small); Text(model.display.localized("コメントを読み込み中")) }
                        .inkuFont(12).foregroundStyle(.secondary)
                } else if annotationState == .unavailable {
                    Text(model.display.localized("コメントを取得できません")).inkuFont(12).foregroundStyle(.secondary)
                }
                if let error = comment.errorText { Text(error).inkuFont(12).foregroundStyle(.red).textSelection(.enabled) }
            }
            DisclosureGroup(model.display.localized("DDL・Score・保存情報")) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        OutputView(ddl: work.ddl ?? "", score: work.score).frame(height: 160)
                        if !work.effectiveSourceText.isEmpty { Text(model.display.localizedFormat("記述: %@", work.effectiveSourceText)).textSelection(.enabled) }
                        Text(Date(timeIntervalSince1970: Double(work.at) / 1000), format: .dateTime.year().month().day().hour().minute().second())
                            .inkuFont(12).foregroundStyle(.secondary)
                        Text(model.display.localizedFormat("作品 ID: %@", work.id)).inkuFont(12, design: .monospaced).textSelection(.enabled)
                        Text(model.display.localizedFormat("用紙: %@ · シード: %@", work.renderCanvasAspectID ?? "—", work.renderSeed ?? "—"))
                            .inkuFont(12).textSelection(.enabled)
                        Text(model.display.localizedFormat("色: %@ · 描画: %@ %@", work.renderColorCatalogName ?? work.catalogID ?? "—", work.renderEngineID ?? "—", work.renderEngineVersion ?? ""))
                            .inkuFont(12).textSelection(.enabled)
                        Text(model.display.localizedFormat("SVG: %ld bytes · 生成: %@", work.svg.utf8.count, work.elapsedMS.map { model.display.localizedFormat("%.3f 秒", Double($0) / 1000) } ?? "—"))
                            .inkuFont(12).textSelection(.enabled)
                        hashRow("描画", hash: work.renderHash)
                        hashRow("記述", hash: work.descriptionHash)
                    }
                }.frame(maxHeight: 260).padding(.top, 8)
            }
        }.task(id: work.id) {
            comment.receive(workID: work.id, state: annotationState)
            await model.loadWorkActionState(work)
        }
        .onChange(of: annotationState) { _, value in
            comment.receive(workID: work.id, state: value)
        }
    }

    private var heading: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(model.display.localized(work.trashed ? "ごみ箱の作品" : annotationSource == nil ? "表示中の作品" : "作品プレビュー"), systemImage: work.trashed ? "trash" : "eye")
                .inkuFont(12, weight: .medium).foregroundStyle(.secondary)
            LibraryWorkTitle(work: work, untitled: model.display.localized("無題"), size: 14)
        }
    }

    @ViewBuilder private func previewActions(_ action: @escaping (SavedWork, String) -> Void) -> some View {
        Button(model.display.localized("生成情報"), systemImage: "info.circle") { action(work, "info") }
        if let onOpenLineage {
            Button(model.display.localized("系譜"), systemImage: "point.3.connected.trianglepath.dotted") { onOpenLineage(work) }
                .disabled(work.lineageNodeID == nil)
        }
        if let onAdjustWork {
            Button(model.display.localized("推敲する"), systemImage: "slider.horizontal.3") { onAdjustWork(work) }
                .disabled(writingDisabled)
        }
        Menu(model.display.localized("作品の操作"), systemImage: "ellipsis.circle") {
            SavedWorkRefinementActions(model: model, work: work, onAction: action, writingLocked: writingDisabled)
        }.disabled(writingDisabled)
        Button(model.display.localized("書き出す"), systemImage: "square.and.arrow.up") { action(work, "export") }.disabled(writingDisabled)
    }

    private var workActions: some View {
        HStack(spacing: 10) {
            Button(model.display.localized(onOpenInCreate == nil ? "制作で編集" : "制作で開く"), systemImage: "pencil") {
                if let onOpenInCreate { onOpenInCreate(work) }
                else { Task { await model.selectWork(work); NotificationCenter.default.post(name: .inkuOpenSection, object: "create", userInfo: ["workID": work.id]) } }
            }.disabled(model.isBrowsingLocked || work.trashed)
                .help(model.display.tooltip("保存作品を制作に開きます。制作中の内容が置き換わります。"))
            Button(model.display.localized("再演奏"), systemImage: "arrow.clockwise") { onReplayWork(work) }.disabled(writingDisabled || work.trashed)
                .help(model.display.tooltip("保存時と現行の描画を比較します。"))
        }.controlSize(.small).fixedSize()
    }

    private func saveNote() {
        guard !writingDisabled, !library.mutating else { return }
        Task {
            let id = work.id
            let value = await comment.save { id, submitted in
                await library.saveNote(id: id, note: submitted)
                if let error = library.errorText {
                    throw NSError(domain: "InkuLibraryNote", code: 1, userInfo: [NSLocalizedDescriptionKey: error])
                }
                return try await model.auxiliaryDatabase().libraryAnnotation(id: id)
            }
            if let value { onAnnotationSaved?(id, value) }
        }
    }

    private func hashRow(_ label: String, hash: String?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(model.display.localizedFormat("%@ハッシュ: %@", model.display.localized(label), "")).inkuFont(12).foregroundStyle(.secondary)
                Spacer()
                if hash != nil { Button(model.display.localized("コピー")) { library.copyHash(hash) }.inkuFont(12).buttonStyle(.borderless) }
            }
            Text(hash ?? "—").inkuFont(12, design: .monospaced).textSelection(.enabled)
        }
    }
}
