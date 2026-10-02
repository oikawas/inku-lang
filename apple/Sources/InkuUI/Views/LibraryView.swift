import InkuPersistence
import SwiftUI

@MainActor
struct LibraryView: View {
    @Bindable var model: AppModel
    @State private var deletion: LibraryDeletion?
    private var library: LibraryModel { model.library }

    var body: some View {
        VStack(spacing: 0) {
            controls.padding(12)
            Divider()
            GeometryReader { geometry in
                if geometry.size.width >= 900 {
                    HStack(spacing: 0) {
                        listing.frame(minWidth: 350, maxWidth: geometry.size.width * 0.48)
                        Divider()
                        selected.padding(18)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 16) {
                            listing.frame(minHeight: 320, maxHeight: 500)
                            Divider()
                            selected.padding(16).frame(minHeight: 440)
                        }
                    }
                }
            }
            Divider()
            pagination.padding(10)
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
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Picker(model.display.localized("表示"), selection: $library.layout) {
                    Label(model.display.localized("サムネイル"), systemImage: "square.grid.2x2").tag(LibraryLayout.grid)
                    Label(model.display.localized("一覧"), systemImage: "list.bullet").tag(LibraryLayout.list)
                }.pickerStyle(.segmented).frame(maxWidth: 350)
                Toggle(model.display.localized("系譜ごと"), isOn: $library.grouped).toggleStyle(.button)
                Spacer()
                Toggle(model.display.localizedFormat("ごみ箱 (%ld)", library.trashTotal), isOn: $library.isTrash).toggleStyle(.button)
                Button(model.display.localized("更新"), systemImage: "arrow.clockwise") { Task { await library.refresh() } }
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 10) { filters; selectionControls }
                VStack(alignment: .leading, spacing: 8) { filters; selectionControls }
            }
            if let error = library.errorText {
                HStack { Text(error).foregroundStyle(.red).textSelection(.enabled); Button(model.display.localized("再試行")) { Task { await library.refresh() } } }
                    .font(.caption)
            } else if !library.status.isEmpty {
                Text(model.display.message(library.status)).font(.caption).foregroundStyle(.secondary)
            }
        }
        .disabled(library.mutating || model.isBusy)
    }

    private var filters: some View {
        @Bindable var library = library
        return HStack {
            Toggle(model.display.localized("お気に入り"), isOn: $library.starredOnly).toggleStyle(.button)
            Toggle(model.display.localized("推敲"), isOn: $library.revisionOnly).toggleStyle(.button)
            Toggle(model.display.localized("書き出し用"), isOn: $library.shareOnly).toggleStyle(.button)
            Picker(model.display.localized("順序"), selection: $library.order) {
                Text(model.display.localized("新しい順")).tag(LibraryOrder.newest)
                Text(model.display.localized("古い順")).tag(LibraryOrder.oldest)
            }.frame(width: 115)
        }.controlSize(.small)
    }

    private var selectionControls: some View {
        HStack {
            Button(model.display.localized("表示中を選択")) { library.selectVisible() }
            if !library.selectedIDs.isEmpty {
                Text(model.display.localizedFormat("%ld 件選択", library.selectedIDs.count)).font(.caption)
                Button(model.display.localized("解除")) { library.selectedIDs.removeAll() }
            }
            if library.isTrash {
                Button(model.display.localized("戻す")) { Task { await library.restore() } }.disabled(library.selectedIDs.isEmpty)
                Button(model.display.localized("完全に削除"), role: .destructive) { deletion = LibraryDeletion(ids: library.selectedIDs.sorted()) }
                    .disabled(library.selectedIDs.isEmpty)
                Button(model.display.localized("空にする"), role: .destructive) { deletion = LibraryDeletion(ids: [], empty: true) }.disabled(library.trashTotal == 0)
            } else {
                Button(model.display.localized("ごみ箱へ"), systemImage: "trash") { Task { await library.trash() } }.disabled(library.selectedIDs.isEmpty)
            }
        }.controlSize(.small)
    }

    @ViewBuilder
    private var listing: some View {
        if library.loading && library.works.isEmpty {
            ProgressView(model.display.localized("ライブラリを読み込み中")).frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if library.total == 0 {
            ContentUnavailableView(model.display.localized(library.isTrash ? "ごみ箱は空です" : "一致する作品がありません"),
                                   systemImage: library.isTrash ? "trash" : "square.grid.2x2",
                                   description: Text(model.display.localized("検索や印の条件を変えてください。")))
        } else {
            ScrollView {
                if library.isGrouped {
                    LazyVStack(alignment: .leading, spacing: 14) {
                        ForEach(library.groups) { group in groupCard(group) }
                    }.padding(12)
                } else if library.layout == .grid {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10)], spacing: 10) {
                        ForEach(library.works, id: \.id) { work in workCard(work, grid: true) }
                    }.padding(12)
                } else {
                    LazyVStack(spacing: 8) {
                        ForEach(library.works, id: \.id) { work in workCard(work, grid: false) }
                    }.padding(12)
                }
            }.overlay(alignment: .topTrailing) { if library.loading { ProgressView().padding(8) } }
        }
    }

    private func workCard(_ work: SavedWork, grid: Bool) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack { selectionCheck(work); Spacer(); marks(work) }
            Button { Task { await model.selectWork(work) } } label: {
                if grid {
                    VStack(alignment: .leading, spacing: 6) {
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(height: 120)
                        summary(work)
                    }
                } else {
                    HStack(spacing: 12) {
                        ArtworkThumbnail(work: work, renderer: model.renderer).frame(width: 72, height: 68)
                        summary(work)
                        Spacer(minLength: 0)
                    }
                }
            }.buttonStyle(.plain).disabled(model.isBusy)
            if let note = library.annotation(for: work.id).note { Text(note).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
            HStack {
                if let hash = work.renderHash {
                    Button("…\(hash.suffix(4))") { library.copyHash(hash) }.help(model.display.preferences.showTooltips ? model.display.localized("描画ハッシュ全体をコピー") : "")
                }
                Spacer()
                if work.lineageNodeID != nil {
                    Button(model.display.localized("系譜")) {
                        Task {
                            await model.selectWork(work); await library.loadLineage(work: work)
                            NotificationCenter.default.post(name: .inkuOpenSection, object: "lineage")
                        }
                    }.disabled(model.isBusy)
                }
            }.font(.caption).buttonStyle(.borderless)
        }
        .padding(10)
        .background(model.selectedWorkID == work.id ? Color.accentColor.opacity(0.1) : Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(library.selectedIDs.contains(work.id) ? Color.accentColor : Color.clear, lineWidth: 2))
    }

    private func selectionCheck(_ work: SavedWork) -> some View {
        Button { library.toggleSelection(work.id) } label: {
            Image(systemName: library.selectedIDs.contains(work.id) ? "checkmark.square.fill" : "square")
        }.buttonStyle(.plain).accessibilityLabel(model.display.localizedFormat("%@ を選択", work.effectiveSourceText))
            .accessibilityValue(model.display.localized(library.selectedIDs.contains(work.id) ? "選択済み" : "未選択"))
    }

    private func summary(_ work: SavedWork) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(work.effectiveSourceText.isEmpty ? model.display.localized("無題") : work.effectiveSourceText).lineLimit(2).foregroundStyle(.primary)
            Text(Date(timeIntervalSince1970: Double(work.at) / 1000), format: .dateTime.year().month().day().hour().minute())
                .font(.caption).foregroundStyle(.secondary)
            Text([work.renderColorCatalogName ?? work.catalogID, work.stage1Model, work.stage2Model].compactMap { $0 }.joined(separator: " · "))
                .font(.caption2).foregroundStyle(.secondary).lineLimit(1)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func marks(_ work: SavedWork) -> some View {
        HStack(spacing: 6) {
            Button { Task { await library.toggleStar(work) } } label: { Image(systemName: work.starred ? "star.fill" : "star") }
                .accessibilityLabel(model.display.localized(work.starred ? "お気に入りを解除" : "お気に入り"))
            Button { Task { await library.toggleRevision(work) } } label: {
                Image(systemName: library.annotation(for: work.id).forRevision ? "pencil.circle.fill" : "pencil.circle")
            }.accessibilityLabel(model.display.localized("推敲の印"))
            Button { Task { await library.toggleShare(work) } } label: {
                Image(systemName: library.annotation(for: work.id).forShare ? "square.and.arrow.up.fill" : "square.and.arrow.up")
            }.accessibilityLabel(model.display.localized("書き出し用の印"))
        }.buttonStyle(.borderless).disabled(library.mutating || model.isBusy)
    }

    private func groupCard(_ group: LibraryGroup) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                ArtworkThumbnail(work: group.representative.work, renderer: model.renderer).frame(width: 56, height: 52)
                VStack(alignment: .leading) {
                    Text(group.representative.work.effectiveSourceText).lineLimit(1)
                    Text(model.display.localizedFormat("%ld 作品 · お気に入り %ld · 推敲 %ld", group.itemCount, group.starredCount, group.revisionCount)).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button(model.display.localized(library.expandedGroups.contains(group.id) ? "閉じる" : "展開")) { Task { await library.toggleGroup(group.id) } }
            }
            if library.expandedGroups.contains(group.id) {
                Button(model.display.localized("この系譜を選択")) { Task { await library.selectGroup(group.id) } }
                if library.layout == .grid {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 150))]) {
                        ForEach(library.groupMembers[group.id] ?? []) { item in workCard(item.work, grid: true) }
                    }
                } else {
                    ForEach(library.groupMembers[group.id] ?? []) { item in workCard(item.work, grid: false) }
                }
                if (library.groupMembers[group.id]?.count ?? 0) < (library.groupMemberTotals[group.id] ?? 0) {
                    Button(model.display.localized("さらに表示")) { Task { await library.loadGroup(root: group.id, append: true) } }
                }
            }
        }.padding(12).background(.quaternary.opacity(0.3), in: RoundedRectangle(cornerRadius: 10))
    }

    @ViewBuilder
    private var selected: some View {
        if let work = model.selectedWork { LibraryWorkDetails(model: model, work: work) }
        else {
            ContentUnavailableView(model.display.localized("作品を選択"), systemImage: "photo", description: Text(model.display.localized("一覧から保存作品を選択してください。")))
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var pagination: some View {
        @Bindable var library = library
        return HStack {
            Text("\(library.shownFrom)–\(library.shownTo) / \(library.total) " + model.display.localized(library.isGrouped ? "系譜" : "作品"))
                .font(.caption.monospacedDigit())
            Spacer()
            Picker(model.display.localized("件数"), selection: $library.pageSize) {
                ForEach([12, 24, 30, 48, 96], id: \.self) { Text(model.display.localizedFormat("%ld 件", $0)).tag($0) }
            }.frame(width: 100)
            Button { Task { await library.setPage(0) } } label: { Image(systemName: "backward.end") }.accessibilityLabel(model.display.localized("先頭ページ"))
                .disabled(library.page == 0)
            Button { Task { await library.setPage(library.page - 1) } } label: { Image(systemName: "chevron.left") }.accessibilityLabel(model.display.localized("前のページ"))
                .disabled(library.page == 0)
            Text("\(library.page + 1) / \(library.pageCount)").font(.caption.monospacedDigit())
            Button { Task { await library.setPage(library.page + 1) } } label: { Image(systemName: "chevron.right") }.accessibilityLabel(model.display.localized("次のページ"))
                .disabled(library.page + 1 >= library.pageCount)
            Button { Task { await library.setPage(library.pageCount - 1) } } label: { Image(systemName: "forward.end") }.accessibilityLabel(model.display.localized("最終ページ"))
                .disabled(library.page + 1 >= library.pageCount)
        }.controlSize(.small).disabled(library.loading || library.mutating)
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
    private var library: LibraryModel { model.library }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(model.display.localized(work.trashed ? "ごみ箱の作品" : "保存作品")).font(.title2.weight(.semibold))
                Spacer()
                Button(model.display.localized("制作で編集"), systemImage: "pencil") {
                    Task { await model.selectWork(work); NotificationCenter.default.post(name: .inkuOpenSection, object: "create") }
                }.disabled(model.isBusy || work.trashed)
                Button(model.display.localized("再演奏"), systemImage: "arrow.clockwise") { Task { await model.replay(work) } }.disabled(model.isBusy || work.trashed)
            }
            ArtworkCanvas(svg: work.svg, renderer: model.renderer, caption: work.effectiveSourceText)
                .frame(minHeight: 280, maxHeight: .infinity)
            HStack {
                TextField(model.display.localized("コメント（240文字まで）"), text: $note, axis: .vertical).lineLimit(2...4)
                Button(model.display.localized("保存")) { Task { await library.saveNote(id: work.id, note: note); note = library.annotation(for: work.id).note ?? "" } }
                    .disabled(library.mutating)
            }
            DisclosureGroup(model.display.localized("DDL・Score・保存情報")) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        OutputView(ddl: work.ddl ?? "", score: work.score).frame(height: 160)
                        Text(model.display.localizedFormat("記述: %@", work.effectiveSourceText)).textSelection(.enabled)
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
                }.frame(maxHeight: 260)
            }
        }.task(id: work.id) { note = library.annotation(for: work.id).note ?? "" }
    }

    private func hashRow(_ label: String, hash: String?) -> some View {
        HStack {
            Text(model.display.localizedFormat("%@ハッシュ: %@", model.display.localized(label), hash.map { "…" + String($0.suffix(4)) } ?? "—")).font(.caption.monospaced())
            if hash != nil { Button(model.display.localized("コピー")) { library.copyHash(hash) }.font(.caption) }
        }
    }
}
