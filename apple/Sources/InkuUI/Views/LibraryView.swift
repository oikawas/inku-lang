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
    var onSelectionExport: ([String], String) -> Void = { _, _ in }
    @State private var deletion: LibraryDeletion?
    @State private var loadingGroups: Set<String> = []
    @State private var providers: [ProviderSettings] = []
    // Measurement bookkeeping is not view state. A height notification for every new card
    // used to invalidate the whole library; only an actual page-size change needs a redraw.
    @State private var measurements = LibraryGridMeasurements()
    @State private var modelLines = LibraryModelLineMemo()
    /// Keyboard focus by the reused card slot: a page turn changes no focus binding, only what the slot shows.
    @FocusState private var focusedSlot: Int?
    @FocusState private var searchFocused: Bool
    @State private var previewComment = LibraryNoteEditorModel()
    private var library: LibraryModel { model.library }
    private var display: DisplaySettings { model.display }
    private var naming: ModelNaming { ModelNaming(providers: providers) }
    private var writingDisabled: Bool { model.isBusy || writingLocked }
    private var hasFilters: Bool {
        !library.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || library.starredOnly || library.revisionOnly
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
        .task(id: PreviewReadKey(workID: preview.work?.id, shows: preview.shows, mutating: library.mutating)) {
            guard !library.mutating else { return }
            await preview.loadAnnotation(using: { id in
                try await model.auxiliaryDatabase().libraryAnnotation(id: id)
            }, readWork: { id in try await model.auxiliaryDatabase().work(id: id) })
        }
        .task(id: model.providerSettingsRevision) { providers = await model.hostSettings().providers }
        .task(id: visibleIDs) { await model.loadWorkActionStates(workIDs: visibleIDs) }
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
            LibraryLoadingIndicator(library: library)
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
            // The thumbnail tab lists the lineages with a derivation (minimum two works) and the opened work's.
            return "\(library.total) " + display.webCopy("historyLineageGroups", fallback: "系譜")
                + (library.layout == .grid ? display.webCopy("historyLineageGroupsDerivedOnly", fallback: "（派生のある系譜と選択作品の系譜）") : "")
        }
        return library.total == 0 ? "0 / 0" : "\(library.shownFrom)-\(library.shownTo) / \(library.total)"
    }

    private var headActions: some View {
        HStack(spacing: 8) {
            pager
            if let onClose {
                Button(display.webCopy("historyLibraryReturn", fallback: "制作に戻る")) { onClose() }
                    .buttonStyle(LibraryGhostButtonStyle())
                    .inkuTooltip(display.tooltip("制作に戻る", serverKey: "historyLibraryReturn"), placement: .bottom)
            }
        }
    }

    private var pager: some View { LibraryPager(library: library, display: display) }

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
            LibraryDisabledWhileLoading(library: library, disabled: visibleIDs.isEmpty) {
                Button(allVisibleSelected ? display.localized("表示中のチェックを外す") : display.webCopy("historySelectAll", fallback: "すべて選択")) {
                    library.selectVisible()
                }
                .buttonStyle(LibraryGhostButtonStyle())
            }
            .inkuTooltip(display.tooltip("このページの作品をすべて選択します", serverKey: "tooltipHistorySelectAll"), placement: .bottom)
            if !library.selectedIDs.isEmpty {
                Button(display.localized("解除")) { library.selectedIDs.removeAll() }
                    .buttonStyle(LibraryGhostButtonStyle())
                    .inkuTooltip(tip("ページをまたいでチェックした作品をすべて解除します。"), placement: .bottom)
            }
            HStack(spacing: 4) {
                Text(display.webCopy("historyFilterLabel", fallback: "絞り込み")).inkuFont(12).foregroundStyle(.tertiary).fixedSize()
                filterButton(display.webCopy("historyStarredOnly", fallback: "スターのみ"), isOn: $library.starredOnly,
                             tooltip: display.tooltip("お気に入りの作品に絞り込みます。", serverKey: "tooltipHistoryStarredOnly"))
                filterButton(display.webCopy("historyForRevisionOnly", fallback: "推敲マークのみ"), isOn: $library.revisionOnly,
                             tooltip: display.tooltip("推敲の印を付けた作品に絞り込みます。", serverKey: "tooltipHistoryForRevisionOnly"))
            }
            .padding(.leading, 10)
            .overlay(alignment: .leading) { Rectangle().fill(LibraryChrome.border).frame(width: 1) }
            Button(display.label("ごみ箱 (\(library.trashTotal))", "trash (\(library.trashTotal))")) { library.isTrash.toggle() }
                .buttonStyle(LibraryGhostButtonStyle(active: library.isTrash))
                .inkuTooltip(display.tooltip("ごみ箱の作品を表示・復元できます。", serverKey: "tooltipHistoryTrashView"), placement: .bottom)
            selectionActions
            Picker(display.localized("順序"), selection: $library.order) {
                Text(display.localized("新しい順")).tag(LibraryOrder.newest)
                Text(display.localized("古い順")).tag(LibraryOrder.oldest)
            }
            .labelsHidden().pickerStyle(.menu).fixedSize().controlSize(.small)
            .inkuTooltip(tip("保存日時の順序を切り替えます。"), placement: .bottom)
            LibraryDisabledWhileLoading(library: library, disabled: false) {
                Button { Task { await library.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(LibraryGhostButtonStyle())
                    .accessibilityLabel(display.localized("更新"))
            }
            .inkuTooltip(tip("ライブラリを読み直します。"), placement: .bottom)
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
        .inkuTooltip(tooltip, placement: .bottom)
    }

    @ViewBuilder private var selectionActions: some View {
        if library.isTrash {
            Button(display.webCopy("historyRestoreSelected", fallback: "選択復元")) { Task { await library.restore() } }
                .buttonStyle(LibraryGhostButtonStyle())
                .disabled(library.selectedIDs.isEmpty || writingDisabled)
                .inkuTooltip(display.tooltip("選択した作品をごみ箱から戻します", serverKey: "tooltipHistoryRestoreSelected"), placement: .bottom)
            Button(display.webCopy("historyPermanentDelete", fallback: "完全削除")) { deletion = LibraryDeletion(ids: library.selectedIDs.sorted()) }
                .buttonStyle(LibraryGhostButtonStyle(danger: true))
                .disabled(library.selectedIDs.isEmpty || writingDisabled)
                .inkuTooltip(display.tooltip("選択した作品を完全に削除します。元に戻せません", serverKey: "tooltipHistoryPermanentDelete"), placement: .bottom)
            Menu {
                Button(display.localized("ごみ箱を空にする"), role: .destructive) { deletion = LibraryDeletion(ids: [], empty: true) }
                    .disabled(library.trashTotal == 0)
            } label: { Image(systemName: "ellipsis") }
                .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                .accessibilityLabel(display.localized("ごみ箱の操作"))
                .disabled(writingDisabled)
        } else {
            let exportIDs = library.selectedIDs.sorted()
            SavedWorkExportMenu(model: model, count: exportIDs.count,
                                title: display.webCopy("exportLabel", "書き出す")) { action in
                onSelectionExport(exportIDs, action)
            }.disabled(exportIDs.isEmpty || writingDisabled)
            Button { deletion = LibraryDeletion(ids: library.selectedIDs.sorted(), movesToTrash: true) } label: {
                HStack(spacing: 4) {
                    Image(systemName: "trash")
                    if !library.selectedIDs.isEmpty { Text("\(library.selectedIDs.count)").monospacedDigit() }
                }
            }
            .buttonStyle(LibraryGhostButtonStyle(minWidth: 38))
            .disabled(library.selectedIDs.isEmpty || writingDisabled)
            .accessibilityLabel(display.webCopy("historyMoveToTrash", fallback: "選択削除"))
            .inkuTooltip(display.tooltip("選択した作品をごみ箱へ移します。あとで戻せます", serverKey: "tooltipHistoryMoveToTrash"), placement: .bottom)
        }
    }

    private var searchField: some View {
        @Bindable var library = library
        return HStack(spacing: 6) {
            Text(display.webCopy("historySearchLabel", "検索（記述 / ハッシュ値 / 作品ID）:"))
                .inkuFont(12).foregroundStyle(.secondary).fixedSize()
            HStack(spacing: 0) {
                TextField("", text: $library.query).textFieldStyle(.plain).focused($searchFocused)
                    .accessibilityLabel(display.webCopy("historySearchLabel", "検索（記述 / ハッシュ値 / 作品ID）:"))
                    .padding(.leading, 7)
                Button { library.query = ""; searchFocused = true } label: { Text("×").frame(width: 28, height: 26) }
                    .buttonStyle(.plain).disabled(library.query.isEmpty)
                    .accessibilityLabel(display.webCopy("historySearchClear", "検索をクリア"))
            }
            .inkuFont(12).frame(minWidth: 120, maxWidth: 240, minHeight: 28)
            .background(LibraryChrome.panel2, in: RoundedRectangle(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(LibraryChrome.border))
            .inkuTooltip(display.webCopy("historySearchHint", "ハッシュ値と作品IDは全体か先頭部分、ハッシュ値は下位4桁でも検索できます。"), focus: .text)
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
        // Works first: while a page is shown, the loading flag is not read here, so loading does not redraw the grid.
        if library.works.isEmpty && library.loading {
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
                    // Reuse the finite page's native card slots instead of destroying every
                    // button/menu on each turn. Work-specific state has its own identity below.
                    ForEach(Array(library.works.enumerated()), id: \.offset) { slot, work in gridCard(work, slot: slot) }
                }
                .padding(.top, 8).padding(.horizontal, 10).padding(.bottom, 6)
            }
            // A page holds only complete rows; an always-on scroller would also take width from the columns.
            .scrollIndicators(.hidden)
            .focusSection()
            .background { focusFollower(scroll: nil) }
            .onAppear { reportPageSize(viewport: geometry.size) }
            .onChange(of: geometry.size) { _, size in reportPageSize(viewport: size) }
        }
    }

    private func focusFollower(scroll: ScrollViewProxy?) -> some View {
        LibraryFocusFollower(library: library, preview: preview, focus: $focusedSlot, scroll: scroll)
    }

    /// Web `calculatePageSize` and its ResizeObserver (HistoryManager.svelte:644-700): a new viewport starts again
    /// from 100; within one viewport the size only shrinks, so different cards cannot make two sizes alternate.
    /// Every new size keeps the first work, as Web `setPageSize` does: a new viewport (the window, or the preview
    /// column opening and closing) and taller cards on the shown page alike.
    private func reportPageSize(viewport size: CGSize) {
        let viewport = CGSize(width: (size.width * 2).rounded() / 2, height: (size.height * 2).rounded() / 2)
        if viewport != measurements.viewport {
            measurements.viewport = viewport
            measurements.ceiling = LibraryGridPaging.maximumPageSize
        }
        guard !library.isGrouped, library.layout != .list, viewport.width > 0, viewport.height > 0 else { return }
        let heights = library.works.map { Double(measurements.cardHeights[$0.id] ?? 0) }
        let fitted = LibraryGridPaging.pageSize(width: size.width - 20, height: size.height - 14, cardHeights: heights)
        measurements.ceiling = min(measurements.ceiling, fitted)
        library.resizePageKeepingFirstWork(to: measurements.ceiling)
    }

    private func recordCardHeight(_ height: CGFloat, for id: String) {
        guard height.isFinite, height > 0, measurements.cardHeights[id] != height else { return }
        measurements.cardHeights[id] = height
        reportPageSize(viewport: measurements.viewport)
    }

    /// Lineage groups page by eight (Web); leaving them hands the size back to the measured grid.
    private func applyGroupedPageSize() {
        if library.isGrouped {
            if library.pageSize != Self.lineageGroupPageSize { library.pageSize = Self.lineageGroupPageSize }
        } else if measurements.viewport != .zero {
            measurements.ceiling = LibraryGridPaging.maximumPageSize
            reportPageSize(viewport: measurements.viewport)
        }
    }

    // MARK: Cards (Web .manager-thumb-wrap)

    /// The card takes values read here, so SwiftUI rebuilds a slot only when what it shows changed.
    private func gridCard(_ work: SavedWork, slot: Int) -> some View {
        LibraryGridCard(
            model: model, work: work, slot: slot,
            label: model.savedDisplayLabels[work.id],
            note: library.annotation(for: work.id).note,
            generation: work.lineageNodeID.flatMap { library.generations[$0] },
            selected: library.selectedIDs.contains(work.id),
            previewed: preview.work?.id == work.id,
            shown: model.selectedWorkID == work.id,
            focused: focusedSlot == slot,
            browsingLocked: model.isBrowsingLocked,
            writingDisabled: writingDisabled,
            mutating: library.mutating,
            hashCopied: work.renderHash != nil && library.copiedHash == work.renderHash,
            modelLines: modelLines.lines(for: work, providers: providers),
            focus: $focusedSlot,
            actions: LibraryGridCardActions(open: openWork, openLineage: openLineage, recordHeight: recordCardHeight,
                                            menu: menuActions))
            .equatable()
    }

    /// Native facts the Web card does not print: saved time and SVG size, with the colour catalog on hover.
    private func savedFacts(_ work: SavedWork) -> some View {
        (Text(Date(timeIntervalSince1970: Double(work.at) / 1000).formatted(date: .numeric, time: .shortened))
            + Text(" · " + ByteCountFormatter.string(fromByteCount: svgBytes(work), countStyle: .file)))
            .inkuFont(10).monospacedDigit().foregroundStyle(.tertiary).lineLimit(1)
            .inkuTooltip(display.tooltipValue(display.localized("色") + ": " + (work.renderColorCatalogName ?? work.catalogID ?? display.localized("未記録"))), focus: .none)
    }

    private var currentBadge: some View { LibraryCurrentBadge(display: display) }

    private func selectionCheck(_ work: SavedWork) -> some View {
        let selected = library.selectedIDs.contains(work.id)
        return Button { library.toggleSelection(work.id) } label: { LibrarySelectionBox(selected: selected) }
            .buttonStyle(.plain)
            .accessibilityLabel(display.localizedFormat("%@ を選択", LibraryWorkPresentation.title(work, untitled: display.localized("無題"))))
            .accessibilityValue(display.localized(selected ? "選択済み" : "未選択"))
            .disabled(library.mutating || model.isBrowsingLocked)
            .inkuTooltip(display.tooltip(selected ? "作品の選択を解除" : "作品を選択"))
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
                HStack(spacing: 6) {
                    ArtworkThumbnail(work: row.work, thumbnails: model.thumbnails).frame(width: 48, height: 36)
                        .inkuTooltip(display.tooltip("作品プレビュー", serverKey: "historyPreviewTitle"))
                    LibraryWorkMarks(model: model, work: row.work, showRevision: false).disabled(writingDisabled)
                }
            }.width(88)
            TableColumn(display.webCopy("historyDescriptionHeader", fallback: "記述")) { row in
                VStack(alignment: .leading, spacing: 3) {
                    if let label = model.savedDisplayLabels[row.work.id] {
                        Text(label).inkuFont(11, weight: .semibold).foregroundStyle(.secondary)
                    }
                    LibraryExpandableTitle(work: row.work, display: display, size: 14)
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
                Text(row.work.renderColorCatalogName ?? model.catalogs.first { $0.id == (row.work.renderColorCatalogID ?? row.work.catalogID) }?.name
                     ?? row.work.renderColorCatalogID ?? row.work.catalogID ?? display.localized("未記録"))
                    .inkuFont(12).lineLimit(1)
            }.width(min: 70, ideal: 100)
            TableColumn(display.webCopy("historySvgSizeHeader", fallback: "SVGサイズ")) { row in
                Text(ByteCountFormatter.string(fromByteCount: svgBytes(row.work), countStyle: .file))
                    .inkuFont(12).monospacedDigit()
            }.width(74)
            TableColumn(display.webCopy("historyHashHeader", fallback: "ハッシュ")) { row in
                if let hash = row.work.renderHash {
                    Button("#\(hash.suffix(4))") { library.copyHash(hash) }.buttonStyle(.borderless)
                        .inkuFont(11, design: .monospaced)
                        .inkuTooltip(hashCopyTooltip(hash))
                }
            }.width(72)
            TableColumn(display.webCopy("historyActionHeader", fallback: "操作")) { row in
                HStack(spacing: 4) {
                    LibraryWorkMarks(model: model, work: row.work, spacing: 4, showStar: false).disabled(writingDisabled)
                    if !library.isTrash {
                        Button { deletion = LibraryDeletion(ids: [row.work.id], movesToTrash: true) } label: { Image(systemName: "trash") }
                            .buttonStyle(.borderless)
                            .accessibilityLabel(display.localized("ごみ箱に移動"))
                            .disabled(library.mutating || writingDisabled)
                    }
                    Menu { workMenu(row.work) } label: { Image(systemName: "ellipsis") }
                        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                        .inkuTooltip(tip("作品の操作"))
                }
            }.width(min: 110, ideal: 120)
        }
        .contextMenu(forSelectionType: String.self) { ids in
            if let id = ids.first, let work = library.works.first(where: { $0.id == id }) { workMenu(work) }
        }
        .background { focusFollower(scroll: nil) }
        #else
        ScrollView {
            LazyVStack(spacing: 8) {
                ForEach(Array(library.works.enumerated()), id: \.element.id) { slot, work in gridCard(work, slot: slot) }
            }.padding(.top, 8).padding(.horizontal, 10).padding(.bottom, 6)
        }
        .background { focusFollower(scroll: nil) }
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
                    library.query = ""; library.starredOnly = false; library.revisionOnly = false
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
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(library.groups) { group in groupCard(group) }
                }
                .padding(.top, 10).padding(.horizontal, 12).padding(.bottom, 16)
            }
            .focusSection()
            .background { focusFollower(scroll: proxy) }
        }
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
                        ArtworkThumbnail(work: group.representative.work, thumbnails: model.thumbnails).frame(width: 56, height: 56)
                    }
                    .buttonStyle(.plain)
                    .inkuTooltip(display.tooltip("作品プレビュー", serverKey: "historyPreviewTitle"))
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
                    .inkuTooltip(display.tooltip("この系譜の作品を開いて一覧します", serverKey: "historyLineageExpandTitle"))
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
                        .inkuTooltip(display.tooltip("この作品の系譜を開きます。"))
                    Button(display.webCopy("historySelectLineage", fallback: "この系譜をすべて選択")) {
                        Task { await library.selectGroup(group.id) }
                    }
                    .buttonStyle(LibraryGhostButtonStyle())
                    .disabled(library.mutating || model.isBrowsingLocked || library.loading)
                    .inkuTooltip(display.tooltip("この系譜の作品をすべて選択します", serverKey: "historySelectLineageTitle"))
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
                    ArtworkThumbnail(work: work, thumbnails: model.thumbnails)
                        .aspectRatio(82.0 / 58.0, contentMode: .fit)
                        .frame(maxWidth: .infinity, maxHeight: 110)
                    Text(LibraryWorkPresentation.title(work, untitled: display.localized("無題")))
                        .inkuFont(10).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            .buttonStyle(.plain).disabled(model.isBrowsingLocked)
            .inkuTooltip(display.tooltip("作品プレビュー", serverKey: "historyPreviewTitle"))
            .overlay(alignment: .topLeading) { selectionCheck(work).padding(3) }
            .overlay(alignment: .topTrailing) {
                // HistoryManager.svelte:1054 `.lineage-generation-badge`, in the thumbnail lane only.
                if model.selectedWorkID == work.id { currentBadge.padding(3) }
                else if library.layout != .list { generationBadge(work, plate: false).padding(8) }
            }
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
        .modifier(LibraryCardSurface(current: selected || model.selectedWorkID == work.id, cornerRadius: 4))
        .contextMenu { workMenu(work) }
    }

    /// Web list-mode `.lineage-member`: check, 48px picture, description, actions on one row.
    private func memberRow(_ work: SavedWork) -> some View {
        HStack(spacing: 8) {
            selectionCheck(work)
            Button { openWork(work) } label: {
                HStack(spacing: 8) {
                    ArtworkThumbnail(work: work, thumbnails: model.thumbnails).frame(width: 48, height: 48)
                    Text(LibraryWorkPresentation.title(work, untitled: display.localized("無題")))
                        .inkuFont(10).foregroundStyle(.secondary).lineLimit(1)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }.contentShape(Rectangle())
            }
            .buttonStyle(.plain).disabled(model.isBrowsingLocked)
            .inkuTooltip(display.tooltip("作品プレビュー", serverKey: "historyPreviewTitle"))
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
            do {
                let saved = try await library.fullWork(id: work.id)
                guard !model.isBrowsingLocked, !Task.isCancelled else { return }
                await model.selectWork(saved); await library.loadLineage(work: saved)
                onClose?()
                NotificationCenter.default.post(name: .inkuOpenSection, object: "lineage", userInfo: ["workID": saved.id])
            } catch { model.errorText = error.localizedDescription }
        }
    }

    private func svgBytes(_ work: SavedWork) -> Int64 {
        library.svgSizes[work.id] ?? SavedWorkFacts.svgBytes(work)
    }

    private func performWorkAction(_ work: SavedWork, _ action: String) {
        Task {
            do {
                let saved = try await library.fullWork(id: work.id)
                guard !Task.isCancelled else { return }
                onWorkAction(saved, action)
            } catch { model.errorText = error.localizedDescription }
        }
    }

    private func workMenu(_ work: SavedWork) -> some View {
        LibraryWorkMenu(model: model, work: work, writingDisabled: writingDisabled, actions: menuActions)
    }

    private var menuActions: LibraryWorkMenuActions {
        LibraryWorkMenuActions(open: openWork, openInCreate: openInCreate, perform: performWorkAction, openLineage: openLineage,
                               delete: { deletion = $0 })
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
                            .inkuTooltip(tip("プレビューを閉じる"))
                    }
                    LibraryPreviewPanel(model: model, preview: preview, comment: previewComment, work: work,
                                        naming: naming, onOpen: openInCreate, onLineage: openLineage,
                                        onWorkAction: performWorkAction, writingLocked: writingDisabled, storedSVGBytes: svgBytes(work))
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

    /// HistoryManager.svelte:1134,1198: "copied" for 1.2 s after the click.
    private func hashCopyTooltip(_ hash: String) -> String {
        library.copiedHash == hash ? display.tooltip("コピーしました", serverKey: "historyHashCopied")
            : display.tooltip("描画ハッシュ全体をコピー", serverKey: "historyHashCopyTitle")
    }

    @ViewBuilder private func generationBadge(_ work: SavedWork, plate: Bool) -> some View {
        if let generation = work.lineageNodeID.flatMap({ library.generations[$0] }) {
            Text("\(generation)")
                .font(.system(size: (plate ? 10 : 9) * display.preferences.textScale, weight: plate ? .semibold : .regular))
                .monospacedDigit()
                .foregroundStyle(plate ? Color.secondary : Color.accentColor)
                .padding(.horizontal, plate ? 3 : 5).padding(.vertical, plate ? 0 : 1)
                .frame(minWidth: 16, minHeight: plate ? 16 : nil)
                .background(plate ? AnyShapeStyle(.background.opacity(0.9)) : AnyShapeStyle(Color.accentColor.opacity(0.14)),
                            in: RoundedRectangle(cornerRadius: plate ? 3 : 8))
                .overlay(RoundedRectangle(cornerRadius: plate ? 3 : 8).stroke(plate ? LibraryChrome.border : Color.clear))
                .inkuTooltip(display.tooltip("世代番号", serverKey: "historyGenerationTitle"), focus: .none)
        }
    }

    private struct PreviewReadKey: Equatable {
        let workID: String?
        let shows: Int
        let mutating: Bool
    }
}

@MainActor
private final class LibraryGridMeasurements {
    var viewport: CGSize = .zero
    var ceiling = LibraryGridPaging.maximumPageSize
    var cardHeights: [String: CGFloat] = [:]
}

/// Web `modelLines` of each card resolves both references against every connection and the bundled catalog; a
/// page repeats a few model pairs, so they are worked out once per pair until the connections change.
@MainActor
private final class LibraryModelLineMemo {
    private var providers: [ProviderSettings] = []
    private var naming = ModelNaming()
    private var lines: [String: [ModelNaming.Line]] = [:]

    func lines(for work: SavedWork, providers: [ProviderSettings]) -> [ModelNaming.Line] {
        if providers != self.providers {
            self.providers = providers
            naming = ModelNaming(providers: providers)
            lines.removeAll()
        }
        let key = (work.stage1Model ?? "") + "\u{0}" + (work.stage2Model ?? "")
        if let known = lines[key] { return known }
        let computed = naming.cardLines(stage1: work.stage1Model, stage2: work.stage2Model)
        lines[key] = computed
        return computed
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

/// The pager reads the loading flag itself, so the start and end of a page read redraw these buttons and not the
/// whole library.
@MainActor
private struct LibraryPager: View {
    let library: LibraryModel
    let display: DisplaySettings

    var body: some View {
        HStack(spacing: 6) {
            Button(display.webCopy("historyLatest", fallback: "最新")) { Task { await library.setLatestPage() } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 54))
                .disabled(!library.hasNewer || library.loading)
                .inkuTooltip(display.tooltip("先頭ページ", serverKey: "tooltipHistoryLatestPage"), placement: .bottom)
            Button(display.webCopy("historyNewer", fallback: "← 新しい")) { Task { await library.setPage(library.page - 1) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 74))
                .disabled(!library.hasNewer || library.loading)
                .inkuTooltip(display.tooltip("前のページ", serverKey: "tooltipHistoryNewerPage"), placement: .bottom)
            Text(library.loading ? display.webCopy("historyLoading", fallback: "読み込み中") : "\(library.page + 1) / \(library.pageCount)")
                .inkuFont(12).monospacedDigit().foregroundStyle(.secondary).fixedSize()
            Button(display.webCopy("historyOlder", fallback: "古い →")) { Task { await library.setPage(library.page + 1) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 74))
                .disabled(library.page + 1 >= library.pageCount || library.loading)
                .inkuTooltip(display.tooltip("次のページ", serverKey: "tooltipHistoryOlderPage"), placement: .bottom)
            Button(display.webCopy("historyOldest", fallback: "最古")) { Task { await library.setPage(library.pageCount - 1) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 54))
                .disabled(library.page + 1 >= library.pageCount || library.loading)
                .inkuTooltip(display.tooltip("最終ページ", serverKey: "tooltipHistoryOldestPage"), placement: .bottom)
        }
        .disabled(library.mutating)
    }
}

/// Web `focusWork` (HistoryManager.svelte:328-344): once the page that holds the opened work is read and shown, its
/// grid card takes the keyboard focus (a lineage view scrolls its card into view), and a preview already open follows
/// it; a closed preview stays closed. A visit applies once in each grouping and layout. It reads the loading flag in a
/// view of its own, as the pager does.
@MainActor
private struct LibraryFocusFollower: View {
    let library: LibraryModel
    let preview: LibraryPreviewModel
    let focus: FocusState<Int?>.Binding
    let scroll: ScrollViewProxy?

    private struct Target: Equatable {
        let visit: Int
        let work: SavedWork
        let slot: Int?
    }

    private var target: Target? {
        guard let request = library.focusRequest, !library.loading else { return nil }
        if library.isGrouped {
            for group in library.groups {
                if let item = library.groupMembers[group.id]?.first(where: { $0.id == request.workID }) {
                    return Target(visit: request.visit, work: item.work, slot: nil)
                }
            }
            return nil
        }
        guard let slot = library.works.firstIndex(where: { $0.id == request.workID }) else { return nil }
        return Target(visit: request.visit, work: library.works[slot], slot: slot)
    }

    var body: some View {
        Color.clear.onChange(of: target, initial: true) { _, target in apply(target) }
    }

    private func apply(_ target: Target?) {
        guard let target, target.visit != library.focusedVisit else { return }
        library.focusedVisit = target.visit
        if let shown = preview.work, shown.id != target.work.id { preview.show(target.work) }
        let scroll = scroll
        // After this update has put the cards in place.
        Task { @MainActor in
            if let slot = target.slot { focus.wrappedValue = slot }
            scroll?.scrollTo(target.work.id, anchor: nil)
        }
    }
}

@MainActor
private struct LibraryLoadingIndicator: View {
    let library: LibraryModel

    var body: some View {
        if library.loading { ProgressView().controlSize(.small) }
    }
}

/// Applies the loading flag in a view of its own, for the same reason as the pager.
@MainActor
private struct LibraryDisabledWhileLoading<Content: View>: View {
    let library: LibraryModel
    let disabled: Bool
    @ViewBuilder let content: Content

    var body: some View {
        content.disabled(disabled || library.loading)
    }
}

private struct LibraryWorkMenuActions {
    let open: (SavedWork) -> Void
    let openInCreate: (SavedWork) -> Void
    let perform: (SavedWork, String) -> Void
    let openLineage: (SavedWork) -> Void
    let delete: (LibraryDeletion) -> Void
}

/// A work's menu, as the context menu and the ⋯ button. A view of its own, so the state it reads (checks, marks,
/// action states) rebuilds the menu alone and not the card around it.
@MainActor
private struct LibraryWorkMenu: View {
    @Bindable var model: AppModel
    let work: SavedWork
    let writingDisabled: Bool
    let actions: LibraryWorkMenuActions
    private var library: LibraryModel { model.library }
    private var display: DisplaySettings { model.display }

    var body: some View {
        let _ = LibraryPerformanceProbe.menuBody()
        Button(display.localized("作品プレビュー"), systemImage: "eye") { actions.open(work) }.disabled(model.isBrowsingLocked)
        Button(display.localized("生成情報"), systemImage: "info.circle") { actions.perform(work, "info") }.disabled(model.isBrowsingLocked || work.trashed)
        Button(display.localized("制作で開く"), systemImage: "pencil") {
            actions.open(work); actions.openInCreate(work)
        }.disabled(model.isBrowsingLocked || work.trashed)
        SavedWorkRefinementActions(model: model, work: work, onAction: actions.perform, writingLocked: writingDisabled)
        Button(display.localized("書き出す"), systemImage: "square.and.arrow.up") { actions.perform(work, "export") }.disabled(writingDisabled || work.trashed)
        if work.lineageNodeID != nil { Button(display.localized("系譜"), systemImage: "point.3.connected.trianglepath.dotted") { actions.openLineage(work) }.disabled(model.isBrowsingLocked) }
        Divider()
        Button(display.localized(library.selectedIDs.contains(work.id) ? "チェックを外す" : "複数選択に追加"), systemImage: "checkmark.square") { library.toggleSelection(work.id) }
            .disabled(library.mutating || model.isBrowsingLocked)
        Button(display.localized(work.starred ? "お気に入りを解除" : "お気に入り"), systemImage: "star") { Task { await library.toggleStar(work) } }
            .disabled(library.mutating || writingDisabled)
        Button(display.localized("推敲の印"), systemImage: library.annotation(for: work.id).forRevision ? "pencil.circle.fill" : "pencil.circle") { Task { await library.toggleRevision(work) } }
            .disabled(library.mutating || writingDisabled)
        if let hash = work.renderHash { Button(display.localized("描画ハッシュ全体をコピー"), systemImage: "doc.on.doc") { library.copyHash(hash) } }
        Divider()
        if work.trashed {
            // HistoryManager.svelte:1069-1070,1215-1226: the per-work buttons' titles, on the menu items that replace them.
            Button(display.localized("戻す"), systemImage: "arrow.uturn.backward") { Task { await library.restore(ids: [work.id]) } }.disabled(library.mutating || writingDisabled)
                .help(display.tooltip("ごみ箱から元に戻します", serverKey: "historyRestoreTitle"))
            Button(display.localized("完全に削除"), role: .destructive) { actions.delete(LibraryDeletion(ids: [work.id])) }.disabled(library.mutating || writingDisabled)
                .help(display.tooltip("完全に削除します。元に戻せません", serverKey: "historyPermanentDeleteTitle"))
        } else {
            Button(display.localized("ごみ箱へ"), systemImage: "trash") {
                actions.delete(LibraryDeletion(ids: [work.id], movesToTrash: true))
            }.disabled(library.mutating || writingDisabled)
                .help(display.tooltip("この作品をごみ箱へ移します", serverKey: "historyTrashItemTitle"))
        }
    }
}

/// HistoryManager.svelte `.current-badge`: the work shown in Create.
@MainActor
struct LibraryCurrentBadge: View {
    let display: DisplaySettings

    var body: some View {
        Text(display.webCopy("historyCurrentBadge", fallback: "表示中"))
            .inkuFont(9).foregroundStyle(.white)
            .padding(.vertical, 1).padding(.horizontal, 4)
            .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 2))
    }
}

private struct LibraryGridCardActions {
    let open: (SavedWork) -> Void
    let openLineage: (SavedWork) -> Void
    let recordHeight: (CGFloat, String) -> Void
    let menu: LibraryWorkMenuActions
}

/// One card of the thumbnail grid (Web `.manager-thumb-wrap`). It is given values rather than reading the models, and
/// compares them, so a page turn rebuilds each slot once and a change that leaves a card as it was (the page loading,
/// labels of other works) rebuilds none. Its menus and marks read the models in views of their own.
@MainActor
private struct LibraryGridCard: View, Equatable {
    let model: AppModel
    let work: SavedWork
    let slot: Int
    let label: String?
    let note: String?
    let generation: Int?
    let selected: Bool
    let previewed: Bool
    let shown: Bool
    let focused: Bool
    let browsingLocked: Bool
    let writingDisabled: Bool
    let mutating: Bool
    let hashCopied: Bool
    let modelLines: [ModelNaming.Line]
    let focus: FocusState<Int?>.Binding
    let actions: LibraryGridCardActions
    private var display: DisplaySettings { model.display }
    private var library: LibraryModel { model.library }

    nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.slot == rhs.slot && lhs.work == rhs.work && lhs.label == rhs.label && lhs.note == rhs.note
            && lhs.generation == rhs.generation && lhs.selected == rhs.selected && lhs.previewed == rhs.previewed
            && lhs.shown == rhs.shown && lhs.focused == rhs.focused && lhs.browsingLocked == rhs.browsingLocked
            && lhs.writingDisabled == rhs.writingDisabled && lhs.mutating == rhs.mutating && lhs.hashCopied == rhs.hashCopied
            && lhs.modelLines == rhs.modelLines
    }

    var body: some View {
        LibraryPerformanceProbe.cardBody()
        let title = LibraryWorkPresentation.title(work, untitled: display.localized("無題"))
        return VStack(alignment: .leading, spacing: 5) {
            Button { actions.open(work) } label: {
                ArtworkThumbnail(work: work, thumbnails: model.thumbnails)
                    .aspectRatio(82.0 / 58.0, contentMode: .fit)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.plain).disabled(browsingLocked)
            .accessibilityLabel(display.localizedFormat("%@ を開く", title))
            .inkuTooltip(display.tooltip("作品プレビュー", serverKey: "historyPreviewTitle"))
            .overlay(alignment: .topLeading) { selectionCheck(title: title).padding(1) }
            // HistoryManager.svelte:1100-1102 `.manager-generation`: under the check, 30pt from the top.
            .overlay(alignment: .topLeading) { generationBadge.padding(.top, 30).padding(.leading, 6) }
            .overlay(alignment: .bottomTrailing) { if shown { LibraryCurrentBadge(display: display).padding(3) } }
            VStack(alignment: .leading, spacing: 4) {
                if let label {
                    Text(label).inkuFont(12, weight: .semibold).foregroundStyle(.tertiary)
                }
                LibraryExpandableTitle(work: work, display: display, size: 14)
                    .id(work.id)
                    .foregroundStyle(.secondary)
                if let note, !note.isEmpty {
                    (Text(display.webCopy("historyPreviewCommentLabel", fallback: "作品へのコメント") + " ").fontWeight(.semibold) + Text(note))
                        .inkuFont(10).foregroundStyle(.tertiary).lineLimit(1)
                }
                LibraryModelLinesView(lines: modelLines, display: display)
                cardActions
            }
            .frame(minHeight: 64, alignment: .top)
        }
        .padding(5)
        .modifier(LibraryCardSurface(current: selected || previewed, focused: focused, cornerRadius: 4))
        .background {
            GeometryReader { proxy in
                Color.clear
                    .onAppear { actions.recordHeight(proxy.size.height, work.id) }
                    .onChange(of: work.id) { _, _ in actions.recordHeight(proxy.size.height, work.id) }
                    .onChange(of: proxy.size.height) { _, height in actions.recordHeight(height, work.id) }
            }
        }
        .contextMenu { LibraryWorkMenu(model: model, work: work, writingDisabled: writingDisabled, actions: actions.menu) }
        .focusable().focused(focus, equals: slot)
        .onKeyPress(.return) {
            guard focus.wrappedValue == slot, !model.isBrowsingLocked else { return .ignored }
            actions.open(work); return .handled
        }
        .onKeyPress(.space) {
            guard focus.wrappedValue == slot, !library.mutating, !model.isBrowsingLocked else { return .ignored }
            library.toggleSelection(work.id); return .handled
        }
    }

    /// Web `.thumb-action-row`: star, revision mark, hash; the native share mark, lineage and menu follow.
    private var cardActions: some View {
        HStack(spacing: 4) {
            LibraryWorkMarks(model: model, work: work, spacing: 4).disabled(writingDisabled)
            if let hash = work.renderHash {
                Button("#\(hash.suffix(4))") { library.copyHash(hash) }
                    .inkuFont(10, design: .monospaced)
                    // HistoryManager.svelte:1134,1198: "copied" for 1.2 s after the click.
                    .inkuTooltip(hashCopied ? display.tooltip("コピーしました", serverKey: "historyHashCopied")
                                 : display.tooltip("描画ハッシュ全体をコピー", serverKey: "historyHashCopyTitle"))
            }
            if work.lineageNodeID != nil {
                Button { actions.openLineage(work) } label: { Image(systemName: "point.3.connected.trianglepath.dotted") }
                    .accessibilityLabel(display.localized("系譜")).disabled(browsingLocked)
                    .inkuTooltip(display.tooltip("この作品の系譜を開きます。"))
            }
            Spacer(minLength: 0)
            Menu { LibraryWorkMenu(model: model, work: work, writingDisabled: writingDisabled, actions: actions.menu) } label: { Image(systemName: "ellipsis") }
                #if os(macOS)
                .menuStyle(.borderlessButton).menuIndicator(.hidden)
                #endif
                .fixedSize().accessibilityLabel(display.localized("作品の操作"))
                .inkuTooltip(display.tooltip("作品の操作"))
        }
        .inkuFont(12).buttonStyle(.borderless)
    }

    private func selectionCheck(title: String) -> some View {
        Button { library.toggleSelection(work.id) } label: { LibrarySelectionBox(selected: selected) }
            .buttonStyle(.plain)
            .accessibilityLabel(display.localizedFormat("%@ を選択", title))
            .accessibilityValue(display.localized(selected ? "選択済み" : "未選択"))
            .disabled(mutating || browsingLocked)
            .inkuTooltip(display.tooltip(selected ? "作品の選択を解除" : "作品を選択"))
    }

    @ViewBuilder private var generationBadge: some View {
        if let generation {
            Text("\(generation)")
                .font(.system(size: 10 * display.preferences.textScale, weight: .semibold))
                .monospacedDigit()
                .foregroundStyle(Color.secondary)
                .padding(.horizontal, 3).padding(.vertical, 0)
                .frame(minWidth: 16, minHeight: 16)
                .background(AnyShapeStyle(.background.opacity(0.9)), in: RoundedRectangle(cornerRadius: 3))
                .overlay(RoundedRectangle(cornerRadius: 3).stroke(LibraryChrome.border))
                .inkuTooltip(display.tooltip("世代番号", serverKey: "historyGenerationTitle"), focus: .none)
        }
    }
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
            ArtworkCanvas(svg: work.svg, renderer: model.displayRenderer, caption: work.effectiveSourceText)
                .frame(height: 280)
                // HistoryManager.svelte:915-921: a double click on the preview opens the work.
                .simultaneousGesture(TapGesture(count: 2).onEnded {
                    guard let onOpenInCreate, !model.isBrowsingLocked, !work.trashed else { return }
                    onOpenInCreate(work)
                })
                .inkuTooltip(onOpenInCreate == nil || work.trashed ? ""
                             : model.display.tooltip("ダブルクリックで作品を開く", serverKey: "historyPreviewOpenHint"))
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
                        .inkuTooltip(model.display.tooltip("この作品のコメントを保存します。"))
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
                .inkuTooltip(model.display.tooltip("保存作品を制作に開きます。制作中の内容が置き換わります。"))
            Button(model.display.localized("再演奏"), systemImage: "arrow.clockwise") { onReplayWork(work) }.disabled(writingDisabled || work.trashed)
                .inkuTooltip(model.display.tooltip("保存時と現行の描画を比較します。"))
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
                if let hash {
                    // HistoryManager.svelte:975: the copy button names what it copies, then that it did.
                    Button(model.display.localized("コピー")) { library.copyHash(hash) }.inkuFont(12).buttonStyle(.borderless)
                        .inkuTooltip(library.copiedHash == hash ? model.display.tooltip("コピーしました", serverKey: "historyHashCopied")
                                     : model.display.tooltip("描画ハッシュ全体をコピー", serverKey: "historyHashCopyTitle"))
                }
            }
            Text(hash ?? "—").inkuFont(12, design: .monospaced).textSelection(.enabled)
        }
    }
}
