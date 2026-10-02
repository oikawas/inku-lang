import InkuPersistence
import SwiftUI

@MainActor
struct LibraryView: View {
    @Bindable var model: AppModel
    @State private var deletion: LibraryDeletion?
    @State private var loadingGroups: Set<String> = []
    @FocusState private var focusedWorkID: String?
    private var library: LibraryModel { model.library }
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

    var body: some View {
        VStack(spacing: 0) {
            controls.padding(16)
            selectionControls.padding(.horizontal, 16).padding(.vertical, 10).background(.bar)
            Divider()
            GeometryReader { geometry in
                if geometry.size.width >= 900 {
                    HStack(spacing: 0) {
                        listing.frame(width: min(560, max(360, geometry.size.width * 0.42)))
                        Divider()
                        selected.padding(20).frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 16) {
                            listing.frame(height: 380)
                            Divider()
                            selected.padding(16).frame(minHeight: 580)
                        }
                    }
                }
            }
            Divider()
            pagination.padding(.horizontal, 16).padding(.vertical, 10).background(.bar)
        }
        .searchable(text: Binding(get: { library.query }, set: { library.query = $0 }), prompt: model.display.localized("記述・DDL・モデル・色・ハッシュを検索"))
        .alert(item: $deletion) { request in
            Alert(title: Text(model.display.localized(request.empty ? "ごみ箱を空にしますか？" : "選択した作品を完全に削除しますか？")),
                  message: Text(model.display.localized("作品を復元することはできません。系譜には削除済みの節点が残ります。")),
                  primaryButton: .destructive(Text(model.display.localized("完全に削除"))) {
                      Task { if request.empty { await library.emptyTrash() } else { await library.permanentlyDelete(ids: request.ids) } }
                  }, secondaryButton: .cancel(Text(model.display.localized("キャンセル"))))
        }
    }

    private var controls: some View {
        @Bindable var library = library
        return VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Text(model.display.localized(library.isTrash ? "ごみ箱" : "ライブラリ")).font(.title2.weight(.semibold))
                Spacer(minLength: 8)
                Toggle(isOn: $library.isTrash) {
                    Label(model.display.localizedFormat("ごみ箱 (%ld)", library.trashTotal), systemImage: "trash")
                }.toggleStyle(.button).fixedSize()
                Button(model.display.localized("更新"), systemImage: "arrow.clockwise") { Task { await library.refresh() } }
                    .disabled(library.loading)
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 20) { displayControls; Spacer(minLength: 12); filters }
                VStack(alignment: .leading, spacing: 10) { displayControls; filters }
            }
            if let error = library.errorText {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "exclamationmark.triangle").foregroundStyle(.red)
                    Text(error).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    Button(model.display.localized("再試行")) { Task { await library.refresh() } }
                }.font(.caption)
            } else if library.mutating {
                HStack(spacing: 8) { ProgressView().controlSize(.small); Text(model.display.localized("変更を保存中")) }.font(.caption)
            } else if !library.status.isEmpty {
                Text(model.display.message(library.status)).font(.caption).foregroundStyle(.secondary)
            }
        }
        .disabled(library.mutating || model.isBusy)
    }

    private var displayControls: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) { layoutPicker; groupingToggle }
            VStack(alignment: .leading, spacing: 8) { layoutPicker; groupingToggle }
        }.controlSize(.small)
    }

    private var layoutPicker: some View {
        @Bindable var library = library
        return Picker(model.display.localized("表示"), selection: $library.layout) {
            Label(model.display.localized("サムネイル"), systemImage: "square.grid.2x2").tag(LibraryLayout.grid)
            Label(model.display.localized("一覧"), systemImage: "list.bullet").tag(LibraryLayout.list)
        }.pickerStyle(.segmented).frame(width: 250)
    }

    private var groupingToggle: some View {
        @Bindable var library = library
        return Toggle(isOn: $library.grouped) { Label(model.display.localized("系譜ごと"), systemImage: "point.3.connected.trianglepath.dotted") }
            .toggleStyle(.button).fixedSize()
    }

    private var filters: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) { markFilters; orderPicker }
            VStack(alignment: .leading, spacing: 8) { markFilters; orderPicker }
        }.controlSize(.small)
    }

    private var markFilters: some View {
        @Bindable var library = library
        return HStack(spacing: 6) {
            Toggle(isOn: $library.starredOnly) { Label(model.display.localized("お気に入り"), systemImage: "star") }
            Toggle(isOn: $library.revisionOnly) { Label(model.display.localized("推敲"), systemImage: "pencil.circle") }
            Toggle(isOn: $library.shareOnly) { Label(model.display.localized("書き出し用"), systemImage: "square.and.arrow.up") }
        }.toggleStyle(.button).fixedSize()
            .help(model.display.preferences.showTooltips ? model.display.localized("複数の印はすべての条件を満たす作品に絞り込みます。") : "")
    }

    private var orderPicker: some View {
        @Bindable var library = library
        return Picker(model.display.localized("順序"), selection: $library.order) {
            Text(model.display.localized("新しい順")).tag(LibraryOrder.newest)
            Text(model.display.localized("古い順")).tag(LibraryOrder.oldest)
        }.fixedSize()
    }

    private var selectionControls: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 14) { selectionSummary; Spacer(minLength: 8); selectionActions }
            VStack(alignment: .leading, spacing: 10) { selectionSummary; selectionActions }
        }.controlSize(.small).disabled(library.mutating || model.isBusy)
    }

    private var selectionSummary: some View {
        HStack(spacing: 10) {
            Label(model.display.localizedFormat("チェックした作品: %ld 件", library.selectedIDs.count), systemImage: "checkmark.square")
                .font(.caption.weight(.medium)).monospacedDigit().fixedSize()
            Button(model.display.localized(allVisibleSelected ? "表示中のチェックを外す" : "表示中を選択")) { library.selectVisible() }
                .disabled(visibleIDs.isEmpty || library.loading)
            Button(model.display.localized("解除")) { library.selectedIDs.removeAll() }.disabled(library.selectedIDs.isEmpty)
        }
    }

    private var selectionActions: some View {
        HStack(spacing: 10) {
            if library.isTrash {
                Button(model.display.localized("戻す"), systemImage: "arrow.uturn.backward") { Task { await library.restore() } }.disabled(library.selectedIDs.isEmpty)
                Button(model.display.localized("完全に削除"), role: .destructive) { deletion = LibraryDeletion(ids: library.selectedIDs.sorted()) }
                    .disabled(library.selectedIDs.isEmpty)
                Menu {
                    Button(model.display.localized("ごみ箱を空にする"), role: .destructive) { deletion = LibraryDeletion(ids: [], empty: true) }
                        .disabled(library.trashTotal == 0)
                } label: { Image(systemName: "ellipsis") }.accessibilityLabel(model.display.localized("ごみ箱の操作"))
            } else {
                Button(model.display.localized("ごみ箱へ"), systemImage: "trash") { Task { await library.trash() } }.disabled(library.selectedIDs.isEmpty)
            }
        }.fixedSize()
    }

    @ViewBuilder
    private var listing: some View {
        if library.loading && library.works.isEmpty {
            ProgressView(model.display.localized("ライブラリを読み込み中")).frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = library.errorText, library.total == 0 {
            ContentUnavailableView {
                Label(model.display.localized("ライブラリを読み込めません"), systemImage: "exclamationmark.triangle")
            } description: {
                Text(error).textSelection(.enabled)
            } actions: {
                Button(model.display.localized("再試行")) { Task { await library.refresh() } }
            }
        } else if library.total == 0 {
            emptyLibrary
        } else {
            ScrollView {
                if library.isGrouped {
                    LazyVStack(alignment: .leading, spacing: 14) {
                        ForEach(library.groups) { group in groupCard(group) }
                    }.padding(16)
                } else if library.layout == .grid {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 12)], spacing: 12) {
                        ForEach(library.works, id: \.id) { work in workCard(work, grid: true) }
                    }.padding(16)
                } else {
                    LazyVStack(spacing: 10) {
                        ForEach(library.works, id: \.id) { work in workCard(work, grid: false) }
                    }.padding(16)
                }
            }.focusSection()
                .overlay(alignment: .topTrailing) {
                    if library.loading { ProgressView().controlSize(.small).padding(10).background(.regularMaterial, in: Capsule()).padding(12) }
                }
        }
    }

    private var emptyLibrary: some View {
        ContentUnavailableView {
            Label(model.display.localized(hasFilters ? "一致する作品がありません" : library.isTrash ? "ごみ箱は空です" : "ライブラリに作品がありません"),
                  systemImage: library.isTrash ? "trash" : "square.grid.2x2")
        } description: {
            Text(model.display.localized(hasFilters ? "検索や印の条件を変えてください。" : library.isTrash
                                         ? "ごみ箱へ移した作品をここから戻せます。" : "制作画面で保存した作品がここに表示されます。"))
        } actions: {
            if hasFilters {
                Button(model.display.localized("検索条件を解除")) {
                    library.query = ""; library.starredOnly = false; library.revisionOnly = false; library.shareOnly = false
                }
            } else if !library.isTrash {
                Button(model.display.localized("制作へ")) { NotificationCenter.default.post(name: .inkuOpenSection, object: "create") }
            }
        }
    }

    private func workCard(_ work: SavedWork, grid: Bool) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                selectionCheck(work)
                if LibraryWorkPresentation.usesDDLTitle(work) { Text("DDL").font(.caption2.monospaced()).foregroundStyle(.secondary) }
                Spacer(minLength: 0)
                if model.selectedWorkID == work.id {
                    Label(model.display.localized("表示中"), systemImage: "eye")
                        .font(.caption2.weight(.medium)).foregroundStyle(Color.accentColor)
                        .fixedSize(horizontal: true, vertical: false)
                }
                Menu { workMenu(work) } label: { Image(systemName: "ellipsis") }
                    #if os(macOS)
                    .menuStyle(.borderlessButton).menuIndicator(.hidden)
                    #endif
                    .fixedSize().accessibilityLabel(model.display.localized("作品の操作"))
            }
            Button { openWork(work) } label: {
                if grid {
                    VStack(alignment: .leading, spacing: 6) {
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(height: 142)
                        summary(work)
                    }
                } else {
                    HStack(spacing: 12) {
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(width: 88, height: 82)
                        summary(work)
                        Spacer(minLength: 0)
                    }
                }
            }.buttonStyle(.plain).disabled(model.isBusy)
                .accessibilityLabel(model.display.localizedFormat("%@ を開く", LibraryWorkPresentation.title(work, untitled: model.display.localized("無題"))))
            if let note = library.annotation(for: work.id).note {
                Label { Text(note).lineLimit(2) } icon: { Image(systemName: "text.bubble") }.font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                LibraryWorkMarks(model: model, work: work)
                Spacer(minLength: 6)
                if let hash = work.renderHash {
                    Button("…\(hash.suffix(4))") { library.copyHash(hash) }.font(.caption.monospaced())
                        .help(model.display.preferences.showTooltips ? model.display.localized("描画ハッシュ全体をコピー") : "")
                }
                if work.lineageNodeID != nil {
                    Button { openLineage(work) } label: { Image(systemName: "point.3.connected.trianglepath.dotted") }
                        .accessibilityLabel(model.display.localized("系譜")).disabled(model.isBusy)
                }
            }.font(.caption).buttonStyle(.borderless)
        }
        .padding(12)
        .modifier(LibraryCardSurface(current: model.selectedWorkID == work.id, focused: focusedWorkID == work.id))
        .contextMenu { workMenu(work) }
        .focusable().focused($focusedWorkID, equals: work.id)
        .onKeyPress(.return) {
            guard focusedWorkID == work.id, !model.isBusy else { return .ignored }
            openWork(work); return .handled
        }
        .onKeyPress(.space) {
            guard focusedWorkID == work.id, !library.mutating, !model.isBusy else { return .ignored }
            library.toggleSelection(work.id); return .handled
        }
        .accessibilityHint(model.display.localized("Returnで作品を表示、Spaceで複数選択のチェックを切り替えます。"))
    }

    private func selectionCheck(_ work: SavedWork) -> some View {
        Button { library.toggleSelection(work.id) } label: {
            Image(systemName: library.selectedIDs.contains(work.id) ? "checkmark.square.fill" : "square")
        }.buttonStyle(.plain).foregroundStyle(library.selectedIDs.contains(work.id) ? Color.accentColor : Color.secondary)
            .accessibilityLabel(model.display.localizedFormat("%@ を選択", LibraryWorkPresentation.title(work, untitled: model.display.localized("無題"))))
            .accessibilityValue(model.display.localized(library.selectedIDs.contains(work.id) ? "選択済み" : "未選択"))
            .help(model.display.preferences.showTooltips ? model.display.localized("複数選択のチェック") : "")
            .disabled(library.mutating || model.isBusy)
    }

    private func summary(_ work: SavedWork) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            LibraryWorkTitle(work: work, untitled: model.display.localized("無題"))
            Text(Date(timeIntervalSince1970: Double(work.at) / 1000), format: .dateTime.year().month().day().hour().minute())
                .font(.caption).foregroundStyle(.secondary)
            Text([work.renderColorCatalogName ?? work.catalogID, work.stage1Model, work.stage2Model].compactMap { $0 }.joined(separator: " · "))
                .font(.caption2).foregroundStyle(.secondary).lineLimit(1)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func openWork(_ work: SavedWork) { Task { await model.selectWork(work) } }

    private func openLineage(_ work: SavedWork) {
        Task {
            await model.selectWork(work); await library.loadLineage(work: work)
            NotificationCenter.default.post(name: .inkuOpenSection, object: "lineage")
        }
    }

    @ViewBuilder
    private func workMenu(_ work: SavedWork) -> some View {
        Button(model.display.localized("作品を開く"), systemImage: "eye") { openWork(work) }.disabled(model.isBusy)
        Button(model.display.localized("制作で編集"), systemImage: "pencil") {
            Task { await model.selectWork(work); NotificationCenter.default.post(name: .inkuOpenSection, object: "create") }
        }.disabled(model.isBusy || work.trashed)
        if work.lineageNodeID != nil { Button(model.display.localized("系譜"), systemImage: "point.3.connected.trianglepath.dotted") { openLineage(work) }.disabled(model.isBusy) }
        Divider()
        Button(model.display.localized(library.selectedIDs.contains(work.id) ? "チェックを外す" : "複数選択に追加"), systemImage: "checkmark.square") { library.toggleSelection(work.id) }
            .disabled(library.mutating || model.isBusy)
        Button(model.display.localized(work.starred ? "お気に入りを解除" : "お気に入り"), systemImage: "star") { Task { await library.toggleStar(work) } }
            .disabled(library.mutating || model.isBusy)
        Button(model.display.localized("推敲の印"), systemImage: library.annotation(for: work.id).forRevision ? "pencil.circle.fill" : "pencil.circle") { Task { await library.toggleRevision(work) } }
            .disabled(library.mutating || model.isBusy)
        Button(model.display.localized("書き出し用の印"), systemImage: library.annotation(for: work.id).forShare ? "square.and.arrow.up.fill" : "square.and.arrow.up") { Task { await library.toggleShare(work) } }
            .disabled(library.mutating || model.isBusy)
        if let hash = work.renderHash { Button(model.display.localized("描画ハッシュ全体をコピー"), systemImage: "doc.on.doc") { library.copyHash(hash) } }
        Divider()
        if work.trashed {
            Button(model.display.localized("戻す"), systemImage: "arrow.uturn.backward") { Task { await library.restore(ids: [work.id]) } }.disabled(library.mutating || model.isBusy)
            Button(model.display.localized("完全に削除"), role: .destructive) { deletion = LibraryDeletion(ids: [work.id]) }.disabled(library.mutating || model.isBusy)
        } else {
            Button(model.display.localized("ごみ箱へ"), systemImage: "trash") { Task { await library.trash(ids: [work.id]) } }.disabled(library.mutating || model.isBusy)
        }
    }

    private func groupCard(_ group: LibraryGroup) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Button { toggleGroup(group.id) } label: {
                HStack(spacing: 10) {
                    Image(systemName: library.expandedGroups.contains(group.id) ? "chevron.down" : "chevron.right")
                        .font(.caption.weight(.semibold)).foregroundStyle(.secondary).frame(width: 12)
                    ArtworkThumbnail(work: group.representative.work, renderer: model.renderer).frame(width: 60, height: 56)
                    VStack(alignment: .leading, spacing: 4) {
                        LibraryWorkTitle(work: group.representative.work, untitled: model.display.localized("無題"), lineLimit: 1)
                        Text(model.display.localizedFormat("%ld 作品 · お気に入り %ld · 推敲 %ld", group.itemCount, group.starredCount, group.revisionCount))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    if loadingGroups.contains(group.id) { ProgressView().controlSize(.small) }
                }.contentShape(Rectangle())
            }.buttonStyle(.plain).disabled(loadingGroups.contains(group.id))
                .accessibilityLabel(model.display.localized(library.expandedGroups.contains(group.id) ? "系譜を折りたたむ" : "系譜を展開"))
            HStack(spacing: 12) {
                Button(model.display.localized("この系譜を選択"), systemImage: "checkmark.square") {
                    Task { await library.selectGroup(group.id) }
                }.disabled(library.mutating || model.isBusy || library.loading)
                Spacer(minLength: 0)
                Button(model.display.localized("系譜"), systemImage: "point.3.connected.trianglepath.dotted") { openLineage(group.representative.work) }
                    .disabled(model.isBusy || group.representative.work.lineageNodeID == nil)
            }.buttonStyle(.borderless).font(.caption)
                .help(model.display.preferences.showTooltips ? model.display.localized("この系譜の検索条件に合う作品を、ページをまたいですべてチェックします。") : "")
            if library.expandedGroups.contains(group.id) {
                Divider()
                if loadingGroups.contains(group.id), (library.groupMembers[group.id] ?? []).isEmpty {
                    ProgressView(model.display.localized("作品を読み込み中")).frame(maxWidth: .infinity).padding(12)
                }
                groupContents(group)
            }
        }.padding(12).background(.thinMaterial, in: RoundedRectangle(cornerRadius: 14))
            .contextMenu {
                Button(model.display.localized("この系譜を選択"), systemImage: "checkmark.square") { Task { await library.selectGroup(group.id) } }
                    .disabled(library.mutating || model.isBusy)
                Button(model.display.localized("系譜"), systemImage: "point.3.connected.trianglepath.dotted") { openLineage(group.representative.work) }
                    .disabled(model.isBusy || group.representative.work.lineageNodeID == nil)
            }
    }

    @ViewBuilder
    private func groupContents(_ group: LibraryGroup) -> some View {
        if library.layout == .grid {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 10)], spacing: 10) {
                ForEach(library.groupMembers[group.id] ?? []) { item in workCard(item.work, grid: true) }
            }
        } else {
            ForEach(library.groupMembers[group.id] ?? []) { item in workCard(item.work, grid: false) }
        }
        HStack {
            Text(model.display.localizedFormat("%ld / %ld 作品", library.groupMembers[group.id]?.count ?? 0, library.groupMemberTotals[group.id] ?? group.itemCount))
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            Spacer()
            if (library.groupMembers[group.id]?.count ?? 0) < (library.groupMemberTotals[group.id] ?? 0) {
                Button(model.display.localized("さらに表示")) { loadMore(group.id) }.disabled(loadingGroups.contains(group.id))
            }
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

    @ViewBuilder
    private var selected: some View {
        if let work = model.selectedWork { LibraryWorkDetails(model: model, work: work).id(work.id) }
        else {
            ContentUnavailableView(model.display.localized("表示する作品を選択"), systemImage: "photo",
                                   description: Text(model.display.localized("作品をクリックすると詳細を表示します。チェックは書き出しやごみ箱への複数選択に使います。")))
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var pagination: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 16) { pageSummary; Spacer(minLength: 8); pageNavigation }
            VStack(spacing: 10) { HStack { pageSummary; Spacer() }; pageNavigation }
        }.controlSize(.small).disabled(library.loading || library.mutating)
    }

    private var pageSummary: some View {
        @Bindable var library = library
        return HStack(spacing: 12) {
            Text("\(library.shownFrom)–\(library.shownTo) / \(library.total) " + model.display.localized(library.isGrouped ? "系譜" : "作品"))
                .font(.caption.monospacedDigit()).fixedSize()
            Picker(model.display.localized("件数"), selection: $library.pageSize) {
                ForEach([12, 24, 30, 48, 96], id: \.self) { Text(model.display.localizedFormat("%ld 件", $0)).tag($0) }
            }.fixedSize()
        }
    }

    private var pageNavigation: some View {
        HStack(spacing: 12) {
            Button { Task { await library.setPage(0) } } label: { Image(systemName: "backward.end") }.accessibilityLabel(model.display.localized("先頭ページ"))
                .disabled(library.page == 0)
            Button { Task { await library.setPage(library.page - 1) } } label: { Image(systemName: "chevron.left") }.accessibilityLabel(model.display.localized("前のページ"))
                .disabled(library.page == 0)
            Text("\(library.page + 1) / \(library.pageCount)").font(.caption.monospacedDigit())
            Button { Task { await library.setPage(library.page + 1) } } label: { Image(systemName: "chevron.right") }.accessibilityLabel(model.display.localized("次のページ"))
                .disabled(library.page + 1 >= library.pageCount)
            Button { Task { await library.setPage(library.pageCount - 1) } } label: { Image(systemName: "forward.end") }.accessibilityLabel(model.display.localized("最終ページ"))
                .disabled(library.page + 1 >= library.pageCount)
        }.buttonStyle(.borderless)
    }
}

private struct LibraryDeletion: Identifiable {
    let id = UUID()
    let ids: [String]
    var empty = false
}

@MainActor
struct LibraryWorkDetails: View {
    @Bindable var model: AppModel
    let work: SavedWork
    @State private var note = ""
    @State private var savedNote = ""
    private var library: LibraryModel { model.library }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 14) { heading; Spacer(minLength: 12); workActions }
                VStack(alignment: .leading, spacing: 10) { heading; workActions }
            }
            ArtworkCanvas(svg: work.svg, renderer: model.renderer, caption: work.effectiveSourceText)
                .frame(minHeight: 280, maxHeight: .infinity)
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label(model.display.localized("コメント"), systemImage: "text.bubble").font(.caption.weight(.medium))
                    Spacer()
                    Text("\(note.unicodeScalars.count) / 240").font(.caption.monospacedDigit()).foregroundStyle(note.unicodeScalars.count > 240 ? Color.red : Color.secondary)
                    Button(model.display.localized("保存")) { saveNote() }
                        .disabled(library.mutating || note.unicodeScalars.count > 240 || note == savedNote)
                }
                TextField(model.display.localized("コメント（240文字まで）"), text: $note, axis: .vertical)
                    .lineLimit(2...4).textFieldStyle(.roundedBorder)
            }
            DisclosureGroup(model.display.localized("DDL・Score・保存情報")) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        OutputView(ddl: work.ddl ?? "", score: work.score).frame(height: 160)
                        if !work.effectiveSourceText.isEmpty { Text(model.display.localizedFormat("記述: %@", work.effectiveSourceText)).textSelection(.enabled) }
                        Text(Date(timeIntervalSince1970: Double(work.at) / 1000), format: .dateTime.year().month().day().hour().minute().second())
                            .font(.caption).foregroundStyle(.secondary)
                        Text(model.display.localizedFormat("作品 ID: %@", work.id)).font(.caption.monospaced()).textSelection(.enabled)
                        Text(model.display.localizedFormat("用紙: %@ · シード: %@", work.renderCanvasAspectID ?? "—", work.renderSeed ?? "—"))
                            .font(.caption).textSelection(.enabled)
                        Text(model.display.localizedFormat("モデル: %@", [work.stage1Model, work.stage2Model].compactMap { $0 }.joined(separator: " / ")))
                            .font(.caption).textSelection(.enabled)
                        Text(model.display.localizedFormat("色: %@ · 描画: %@ %@", work.renderColorCatalogName ?? work.catalogID ?? "—", work.renderEngineID ?? "—", work.renderEngineVersion ?? ""))
                            .font(.caption).textSelection(.enabled)
                        Text(model.display.localizedFormat("SVG: %ld bytes · 生成: %@", work.svg.utf8.count, work.elapsedMS.map { model.display.localizedFormat("%.3f 秒", Double($0) / 1000) } ?? "—"))
                            .font(.caption).textSelection(.enabled)
                        hashRow("描画", hash: work.renderHash)
                        hashRow("記述", hash: work.descriptionHash)
                    }
                }.frame(maxHeight: 260).padding(.top, 8)
            }
        }.task(id: work.id) {
            savedNote = library.annotation(for: work.id).note ?? ""; note = savedNote
        }
        .onChange(of: library.annotation(for: work.id).note) { _, value in
            // A different page may omit this displayed work from its annotations.
            guard library.annotations[work.id] != nil else { return }
            if note == savedNote { note = value ?? "" }
            savedNote = value ?? ""
        }
    }

    private var heading: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(model.display.localized(work.trashed ? "ごみ箱の作品" : "表示中の作品"), systemImage: work.trashed ? "trash" : "eye")
                .font(.caption.weight(.medium)).foregroundStyle(.secondary)
            LibraryWorkTitle(work: work, untitled: model.display.localized("無題"))
        }
    }

    private var workActions: some View {
        HStack(spacing: 10) {
            Button(model.display.localized("制作で編集"), systemImage: "pencil") {
                Task { await model.selectWork(work); NotificationCenter.default.post(name: .inkuOpenSection, object: "create") }
            }.disabled(model.isBusy || work.trashed)
            Button(model.display.localized("再演奏"), systemImage: "arrow.clockwise") { Task { await model.replay(work) } }.disabled(model.isBusy || work.trashed)
        }.controlSize(.small).fixedSize()
    }

    private func saveNote() {
        let submitted = note
        Task {
            await library.saveNote(id: work.id, note: submitted)
            guard library.errorText == nil else { return }
            savedNote = library.annotations[work.id]?.note ?? submitted.trimmingCharacters(in: .whitespacesAndNewlines)
            if note == submitted { note = savedNote }
        }
    }

    private func hashRow(_ label: String, hash: String?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(model.display.localizedFormat("%@ハッシュ: %@", model.display.localized(label), "")).font(.caption).foregroundStyle(.secondary)
                Spacer()
                if hash != nil { Button(model.display.localized("コピー")) { library.copyHash(hash) }.font(.caption).buttonStyle(.borderless) }
            }
            Text(hash ?? "—").font(.caption.monospaced()).textSelection(.enabled)
        }
    }
}
