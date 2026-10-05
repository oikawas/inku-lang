import InkuHost
import InkuPersistence
import SwiftUI

/// The history strip as Web `HistoryStrip.svelte` (Build1162) draws it: padding 8/16/10, 82×58 thumbnails 7 apart,
/// `floor((window width − 40) / 89)` of them, and up to three 10px fact lines under each.
@MainActor struct HistoryStripView: View {
    @Bindable var model: AppModel
    @Bindable var history: HistoryModel
    var displayedWorkID: String? = nil
    var onSelectWork: (SavedWork) -> Void = { _ in }
    /// Web `onOpenManager`, the 履歴 button. Without it the button opens the library section as before.
    var onOpenLibrary: (() -> Void)? = nil
    /// The window width the thumbnail count is taken from. Without it the strip reads its own right edge in the window.
    var windowWidth: CGFloat? = nil
    @State private var collapsed = false
    @State private var measuredWindowWidth: CGFloat = 0
    @State private var providers: [ProviderSettings] = []
    private var library: LibraryModel { history.library }
    private var display: DisplaySettings { model.display }
    private var selectionID: String? { displayedWorkID ?? model.selectedWorkID }
    private var locked: Bool { model.isBrowsingLocked }
    private var hasFilters: Bool { library.starredOnly || library.revisionOnly || library.shareOnly }
    /// Web `visibleThumbCount` (+page.svelte:1246).
    private var capacity: Int? {
        let width = windowWidth ?? measuredWindowWidth
        guard width > 0 else { return nil }
        return max(1, Int(((width - 40) / 89).rounded(.down)))
    }

    var body: some View {
        // The container stays mounted so its tasks are never cancelled by an empty listing.
        VStack(alignment: .leading, spacing: 0) {
            // Web renders nothing until there is a work to list.
            if library.total > 0 || hasFilters {
                VStack(alignment: .leading, spacing: 0) {
                    head.padding(.bottom, collapsed ? 0 : 7)
                    if let error = library.errorText { Text(error).inkuFont(12).foregroundStyle(.red).padding(.bottom, 7) }
                    if let error = history.generationError {
                        Text(display.localizedFormat("世代を読み込めませんでした: %@", error)).inkuFont(12).foregroundStyle(.red).padding(.bottom, 7)
                    }
                    if !collapsed { thumbs }
                }
                .padding(.top, collapsed ? 6 : 8).padding(.horizontal, 16).padding(.bottom, collapsed ? 6 : 10)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            GeometryReader { proxy in
                Color.clear
                    .onAppear { measuredWindowWidth = proxy.frame(in: .global).maxX }
                    .onChange(of: proxy.frame(in: .global).maxX) { _, value in measuredWindowWidth = value }
            }
        }
        .task(id: capacity) {
            guard let capacity else { return }
            await history.updateCapacity(capacity, app: model, workID: selectionID)
        }
        .task(id: GenerationRequest(nodeIDs: library.works.compactMap(\.lineageNodeID), loading: library.loading)) {
            guard !library.loading else { return }
            await history.refreshGenerations()
        }
        .task(id: selectionID) { await history.locate(app: model, workID: selectionID) }
        .task(id: model.providerSettingsRevision) { providers = await model.hostSettings().providers }
    }

    // MARK: Head (Web .history-head)

    private var head: some View {
        // Web wraps the head under 920px; the native strip wraps whenever the row does not fit.
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) { headLeft; Spacer(minLength: 8); headActions }
            VStack(alignment: .leading, spacing: 7) { headLeft; HStack { Spacer(minLength: 0); headActions } }
        }
    }

    private var headLeft: some View {
        HStack(spacing: 6) {
            Button { openLibrary() } label: {
                Text(display.webCopy("historyTitle", fallback: "履歴"))
                    + Text(" (\(library.total))").fontWeight(.regular).foregroundStyle(.tertiary)
                    + Text(" ▸")
            }
            .buttonStyle(HistoryTitleButtonStyle())
            .disabled(locked)
            .inkuTooltip(tip("ライブラリを開き、検索や複数選択を使えます。"))
            if !collapsed { filters.padding(.leading, 12) }
            if locked {
                HStack(spacing: 6) {
                    Text("◇").inkuFont(10).foregroundStyle(.tertiary)
                    Text(display.webCopy("historyLockedDuringDemo", fallback: "デモ実行中は履歴操作をロックしています"))
                }
                .inkuFont(12).foregroundStyle(.secondary)
                .padding(.vertical, 4).padding(.horizontal, 10)
                .background(Color.brown.opacity(0.09), in: Capsule())
                .overlay(Capsule().stroke(Color.brown.opacity(0.28)))
                .padding(.leading, 10)
            }
        }
    }

    private var headActions: some View {
        HStack(spacing: 8) {
            if !collapsed { pageNavigation }
            Button(collapsed ? "⌄" : "⌃") { collapsed.toggle() }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 28))
                .accessibilityLabel(display.webCopy(collapsed ? "historyExpand" : "historyCollapse", fallback: collapsed ? "履歴エリアを表示" : "履歴エリアを仕舞う"))
                .inkuTooltip(display.tooltipValue(display.webCopy(collapsed ? "historyExpand" : "historyCollapse", fallback: collapsed ? "履歴エリアを表示" : "履歴エリアを仕舞う")))
        }
    }

    private var filters: some View {
        HStack(spacing: 4) {
            Text(display.webCopy("historyFilterLabel", fallback: "絞り込み")).inkuFont(12).foregroundStyle(.tertiary).fixedSize()
            filterButton(display.webCopy("historyStarredOnly", fallback: "スターのみ"),
                         isOn: Binding(get: { library.starredOnly }, set: { library.starredOnly = $0 }),
                         tooltip: display.tooltip("お気に入りの作品に絞り込みます。", serverKey: "tooltipHistoryStarredOnly"))
            filterButton(display.webCopy("historyForRevisionOnly", fallback: "推敲マークのみ"),
                         isOn: Binding(get: { library.revisionOnly }, set: { library.revisionOnly = $0 }),
                         tooltip: display.tooltip("推敲の印を付けた作品に絞り込みます。", serverKey: "tooltipHistoryForRevisionOnly"))
            filterButton(display.localized("書き出し用のみ"),
                         isOn: Binding(get: { library.shareOnly }, set: { library.shareOnly = $0 }),
                         tooltip: display.tooltip("書き出し用の印を付けた作品に絞り込みます。", serverKey: "tooltipHistoryForShareOnly"))
        }
        .disabled(locked)
    }

    private func filterButton(_ title: String, isOn: Binding<Bool>, tooltip: String) -> some View {
        Button { isOn.wrappedValue.toggle() } label: {
            HStack(spacing: 2) {
                Text("✓").fontWeight(.bold).opacity(isOn.wrappedValue ? 1 : 0)
                Text(title)
            }
        }
        .buttonStyle(LibraryGhostButtonStyle(active: isOn.wrappedValue, minWidth: 76, minHeight: 28))
        .accessibilityAddTraits(isOn.wrappedValue ? .isSelected : [])
        .inkuTooltip(tooltip)
    }

    private var pageNavigation: some View {
        HStack(spacing: 6) {
            Button(display.webCopy("historyLatest", fallback: "最新")) { Task { await library.setPage(0) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 54))
                .disabled(locked || library.page == 0)
                .accessibilityLabel(display.localized("最新の履歴"))
                .inkuTooltip(display.tooltip("先頭ページ", serverKey: "tooltipHistoryLatestPage"))
            Button(display.label("← 新しい\(library.pageSize)件", "← newer \(library.pageSize)")) { Task { await library.setPage(library.page - 1) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 92))
                .disabled(locked || library.page == 0)
                .inkuTooltip(display.tooltip("前のページ", serverKey: "tooltipHistoryNewerPage"))
            Text("\(library.page + 1) / \(library.pageCount)")
                .inkuFont(11).monospacedDigit().foregroundStyle(.tertiary).frame(minWidth: 30)
            Button(display.label("古い\(library.pageSize)件 →", "older \(library.pageSize) →")) { Task { await library.setPage(library.page + 1) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 92))
                .disabled(locked || library.page + 1 >= library.pageCount)
                .inkuTooltip(display.tooltip("次のページ", serverKey: "tooltipHistoryOlderPage"))
            Button(display.webCopy("historyOldest", fallback: "最古")) { Task { await library.setPage(library.pageCount - 1) } }
                .buttonStyle(LibraryGhostButtonStyle(minWidth: 54))
                .disabled(locked || library.page + 1 >= library.pageCount)
                .accessibilityLabel(display.localized("最古の履歴"))
                .inkuTooltip(display.tooltip("最終ページ", serverKey: "tooltipHistoryOldestPage"))
        }
    }

    // MARK: Thumbnails (Web .thumb-strip, .thumb)

    private var thumbs: some View {
        // The count follows the window width (Web); a narrower strip clips the last tiles instead of widening the window.
        HStack(alignment: .top, spacing: 7) {
            ForEach(library.works, id: \.id) { work in tile(work) }
        }
        .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
        .clipped()
    }

    private func tile(_ work: SavedWork) -> some View {
        let current = selectionID == work.id
        let lines = metadata(work)
        return Button {
            guard !locked else { return }
            onSelectWork(work)
            Task { await model.selectWork(work) }
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                ArtworkThumbnail(work: work, renderer: model.renderer)
                    .frame(width: 82, height: 58)
                    .overlay(alignment: .topLeading) {
                        // HistoryStrip.svelte:264-266: a work held by its edited DDL carries a lock, a mark rather than a control.
                        if model.workActionState(for: work) == .lockedDescription {
                            let mark = display.webCopy("descriptionLockedMark", fallback: "ロック")
                            Image(systemName: "lock.fill").font(.system(size: 8 * display.preferences.textScale))
                                .foregroundStyle(.secondary)
                                .padding(2)
                                .background(.background.opacity(0.85), in: RoundedRectangle(cornerRadius: 3))
                                .padding(3)
                                .accessibilityLabel(mark)
                                .inkuTooltip(display.tooltipValue(mark))
                        }
                    }
                    .overlay(alignment: .bottomTrailing) {
                        if current {
                            Text(display.webCopy("historyCurrentBadge", fallback: "表示中"))
                                .inkuFont(9).foregroundStyle(.white)
                                .padding(.vertical, 1).padding(.horizontal, 4)
                                .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 2))
                                .padding(3)
                        }
                    }
                if !lines.isEmpty {
                    Rectangle().fill(LibraryChrome.border).frame(height: 1)
                    VStack(alignment: .leading, spacing: 1) {
                        ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                            // The first line is the tile's heading, whatever fact sits there.
                            Text(line.short)
                                .inkuFont(10, weight: index == 0 ? .semibold : .regular)
                                .foregroundStyle(.secondary)
                                .lineLimit(1).truncationMode(.tail)
                                .frame(height: 13 * display.preferences.textScale, alignment: .leading)
                                // HistoryStrip.svelte:282: each field names itself in full.
                                .inkuTooltip(display.tooltipValue(line.full))
                        }
                    }
                    .padding(.vertical, 3).padding(.horizontal, 5)
                }
            }
            .frame(width: 82, alignment: .leading)
            .background(.background)
            .clipShape(RoundedRectangle(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(current ? Color.accentColor : Color.clear, lineWidth: 2))
            .opacity(locked ? 0.58 : 1)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .overlay(alignment: .topTrailing) { starButton(work).padding(3) }
        .task(id: work.id) { await model.loadWorkActionState(work) }
        .inkuTooltip(display.tooltipValue(detailsTip(work)))
        .accessibilityLabel(display.localizedFormat("作品を開く: %@", title(work)))
    }

    /// Web `.thumb-star`: an 18px plate on the picture that stars or unstars the work.
    private func starButton(_ work: SavedWork) -> some View {
        Button {
            Task { await model.library.toggleStar(work); await library.refresh() }
        } label: {
            Text("★").font(.system(size: 13 * display.preferences.textScale))
                .foregroundStyle(work.starred ? Color.yellow : Color.secondary)
                .frame(width: 18, height: 18)
                .background(.background.opacity(0.85), in: Circle())
                .overlay(Circle().stroke(LibraryChrome.border))
        }
        .buttonStyle(.plain)
        .disabled(locked || model.isBusy || model.library.mutating)
        .accessibilityLabel(display.webCopy(work.starred ? "starOn" : "starOff", fallback: work.starred ? "スターを外す" : "スターを付ける"))
        .inkuTooltip(display.tooltip(work.starred ? "スターを外す" : "スターを付ける", serverKey: work.starred ? "starOn" : "starOff"))
    }

    private func metadata(_ work: SavedWork) -> [(short: String, full: String)] {
        let fields = display.preferences.historyStripFields
        let naming = ModelNaming(providers: providers)
        var output: [(short: String, full: String)] = []
        if fields.contains("generation") { let label = generationLabel(work); output.append((label, label)) }
        if fields.contains("model") {
            let stage1 = SavedWorkFacts.recordedModel(work.stage1Model)
            output.append((naming.stripModel(stage1), stage1.map(naming.displayName) ?? "-"))
        }
        if fields.contains("engine") { let version = engineVersion(work); output.append((version, version)) }
        if fields.contains("size") { let size = Self.fileSize(SavedWorkFacts.svgBytes(work)); output.append((size, size)) }
        return Array(output.prefix(3))
    }

    /// Web `formatHistoryStripEngineVersion`.
    private func engineVersion(_ work: SavedWork) -> String {
        let version = (work.renderEngineVersion ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !version.isEmpty else { return display.webCopy("historyVersionNotRecorded", fallback: "記録なし") }
        let bare = version.replacingOccurrences(of: #"^Ver\.\s*"#, with: "", options: [.regularExpression, .caseInsensitive])
        return "Ver.\(bare)"
    }

    /// Web `fileSizeLabel`.
    static func fileSize(_ bytes: Int64) -> String {
        if bytes < 1024 { return "\(bytes) B" }
        if bytes < 1024 * 1024 { return "\(Int((Double(bytes) / 1024).rounded())) KB" }
        return String(format: "%.1f MB", Double(bytes) / (1024 * 1024))
    }

    private func generationLabel(_ work: SavedWork) -> String {
        if let nodeID = work.lineageNodeID {
            if let generation = history.generations[nodeID] { return display.localizedFormat("第%ld世代", generation) }
            if history.generationLoading || history.generationError != nil { return "—" }
        }
        return display.localized("独立作品")
    }

    private func title(_ work: SavedWork) -> String {
        let source = work.effectiveSourceText
        if !source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return source }
        if let ddl = work.ddl, !ddl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return ddl }
        return work.id
    }

    private func openLibrary() {
        if let onOpenLibrary { onOpenLibrary() } else { NotificationCenter.default.post(name: .inkuOpenSection, object: "library") }
    }

    private func tip(_ key: String) -> String { display.tooltip(key) }

    /// Web `.thumb-tooltip` rows, with the native SVG size.
    private func detailsTip(_ work: SavedWork) -> String {
        let naming = ModelNaming(providers: providers)
        let unrecorded = display.localized("未記録")
        let saved = Date(timeIntervalSince1970: Double(work.at) / 1000).formatted(date: .numeric, time: .shortened)
        return [title(work),
                "Stage 1: " + (SavedWorkFacts.recordedModel(work.stage1Model).map(naming.displayName) ?? unrecorded),
                "Stage 2: " + (SavedWorkFacts.recordedModel(work.stage2Model).map(naming.displayName) ?? unrecorded),
                display.webCopy("historyTooltipSavedAt", fallback: "保存時間") + ": " + saved,
                display.webCopy("historyStripFieldGeneration", fallback: "世代") + ": " + generationLabel(work),
                display.webCopy("historyTooltipColorCatalog", fallback: "色カタログ") + ": " + (work.renderColorCatalogName ?? work.catalogID ?? unrecorded),
                "Render: " + (work.renderEngineVersion ?? display.webCopy("historyVersionNotRecorded", fallback: "記録なし")),
                display.localized("SVG容量") + ": " + ByteCountFormatter.string(fromByteCount: SavedWorkFacts.svgBytes(work), countStyle: .file)]
            .joined(separator: "\n")
    }

    private struct GenerationRequest: Equatable {
        let nodeIDs: [String]
        let loading: Bool
    }
}

/// Web `.history-title-btn`: a pill, 12px weight 500, padding 5×12.
private struct HistoryTitleButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .inkuFont(12, weight: .medium)
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .padding(.vertical, 5).padding(.horizontal, 12)
            .background(configuration.isPressed ? AnyShapeStyle(Color.accentColor.opacity(0.15)) : AnyShapeStyle(.background), in: Capsule())
            .overlay(Capsule().stroke(LibraryChrome.border))
            .shadow(color: .black.opacity(0.06), radius: 1.5, y: 1)
            .opacity(isEnabled ? 1 : 0.45)
            .contentShape(Capsule())
    }
}
