import Foundation
import InkuPersistence
import Observation
#if os(macOS)
import AppKit
#elseif os(iOS)
import UIKit
#endif

public enum LibraryLayout: String, CaseIterable, Sendable {
    case grid, list, lineage
}

@MainActor
@Observable
public final class LibraryModel {
    public var query = "" { didSet { if query != oldValue { changedFilter() } } }
    public var starredOnly = false { didSet { if starredOnly != oldValue { changedFilter() } } }
    public var revisionOnly = false { didSet { if revisionOnly != oldValue { changedFilter() } } }
    public var shareOnly = false { didSet { if shareOnly != oldValue { changedFilter() } } }
    public var isTrash = false { didSet { if isTrash != oldValue { changedFilter() } } }
    public var order: LibraryOrder = .newest { didSet { if order != oldValue { changedFilter() } } }
    public var layout: LibraryLayout = .grid { didSet { if layout != oldValue { changedFilter() } } }
    public var grouped = false { didSet { if grouped != oldValue { changedFilter() } } }
    public var pageSize = 30 {
        didSet {
            let bounded = min(1000, max(1, pageSize))
            if pageSize != bounded { pageSize = bounded; return }
            if pageSize != oldValue { changedFilter() }
        }
    }
    public var selectedIDs: Set<String> = []
    public private(set) var works: [SavedWork] = []
    public private(set) var annotations: [String: LibraryAnnotation] = [:]
    public private(set) var selectedAnnotationID: String?
    public private(set) var selectedAnnotation: LibraryAnnotation?
    public private(set) var selectedAnnotationLoading = false
    public private(set) var groups: [LibraryGroup] = []
    public private(set) var groupMembers: [String: [InkuPersistence.LibraryItem]] = [:]
    public private(set) var groupMemberTotals: [String: Int] = [:]
    public private(set) var expandedGroups: Set<String> = []
    public private(set) var page = 0
    public private(set) var total = 0
    public private(set) var trashTotal = 0
    public private(set) var loading = false
    public private(set) var mutating = false
    public private(set) var errorText: String?
    public private(set) var status = ""
    public private(set) var graph: LineageGraph?
    public private(set) var lineageLoading = false
    public private(set) var lineageError: String?
    public var lineageDepth = 2
    public var lineagePathOnly = false
    public var lineageVertical = false
    @ObservationIgnored public var onMutation: (@MainActor () async -> Void)?
    @ObservationIgnored private var database: InkuDatabase?
    @ObservationIgnored private var refreshTask: Task<Void, Never>?
    @ObservationIgnored private var refreshToken = UUID()
    @ObservationIgnored private var selectedAnnotationToken = UUID()
    @ObservationIgnored private var lineageToken = UUID()
    @ObservationIgnored private var lineageFocusID: String?
    @ObservationIgnored private var lineageOverviewRequested = false

    public init() {}

    public func connect(database: InkuDatabase) async {
        refreshTask?.cancel()
        self.database = database
        await refresh()
    }

    public var pageCount: Int { max(1, (total + pageSize - 1) / pageSize) }
    public var shownFrom: Int { total == 0 ? 0 : page * pageSize + 1 }
    public var shownTo: Int { min(total, (page + 1) * pageSize) }
    public var isGrouped: Bool { grouped || layout == .lineage }
    public var filter: LibraryQuery {
        LibraryQuery(text: query, trashed: isTrash, starred: starredOnly,
                     forRevision: revisionOnly, forShare: shareOnly, order: order)
    }

    private func changedFilter() {
        page = 0
        selectedIDs.removeAll()
        expandedGroups.removeAll()
        groupMembers.removeAll()
        groupMemberTotals.removeAll()
        refreshTask?.cancel()
        refreshTask = Task { @MainActor [weak self] in
            // Coalesce typing; cancellation never changes a database operation.
            try? await Task.sleep(for: .milliseconds(180))
            guard !Task.isCancelled else { return }
            await self?.refresh()
        }
    }

    public func setPage(_ value: Int) async {
        page = min(max(0, value), pageCount - 1)
        await refresh()
    }

    public func refresh() async {
        guard let database else { return }
        let token = UUID()
        refreshToken = token
        let requestedFilter = filter
        let requestedGrouping = isGrouped
        let requestedSize = pageSize
        let requestedPage = page
        loading = true
        errorText = nil
        do {
            let count = try await database.trashCount()
            if requestedGrouping {
                let result = try await database.libraryGroups(query: requestedFilter, limit: requestedSize,
                                                               offset: requestedPage * requestedSize)
                guard refreshToken == token, !Task.isCancelled else { return }
                groups = result.groups; total = result.total
                works = result.groups.map(\.representative.work)
                annotations = Dictionary(uniqueKeysWithValues: result.groups.map { ($0.representative.id, $0.representative.annotation) })
            } else {
                let result = try await database.libraryPage(query: requestedFilter, limit: requestedSize,
                                                             offset: requestedPage * requestedSize)
                guard refreshToken == token, !Task.isCancelled else { return }
                groups = []; total = result.total
                works = result.items.map(\.work)
                annotations = Dictionary(uniqueKeysWithValues: result.items.map { ($0.id, $0.annotation) })
            }
            trashTotal = count
            loading = false
            if page >= pageCount { page = pageCount - 1; await refresh(); return }
            for root in expandedGroups { await loadGroup(root: root, append: false) }
            if lineageFocusID != nil { await reloadLineage() }
        } catch {
            guard refreshToken == token, !Task.isCancelled else { return }
            loading = false; errorText = error.localizedDescription
        }
    }

    public func loadedAnnotation(for id: String) -> LibraryAnnotation? {
        if selectedAnnotationID == id { return selectedAnnotation }
        return annotations[id]
    }

    public func annotation(for id: String) -> LibraryAnnotation {
        loadedAnnotation(for: id) ?? LibraryAnnotation()
    }

    public func isAnnotationLoading(for id: String) -> Bool {
        selectedAnnotationID == id && selectedAnnotationLoading
    }

    public func clearSelectedAnnotation() {
        selectedAnnotationToken = UUID()
        selectedAnnotationID = nil
        selectedAnnotation = nil
        selectedAnnotationLoading = false
    }

    public func loadSelectedAnnotation(workID: String?) async {
        clearSelectedAnnotation()
        guard let workID else { return }
        selectedAnnotationID = workID
        selectedAnnotation = annotations[workID]
        guard let database else { return }
        let token = UUID()
        selectedAnnotationToken = token
        selectedAnnotationLoading = true
        defer {
            if selectedAnnotationToken == token { selectedAnnotationLoading = false }
        }
        do {
            let value = try await database.libraryAnnotation(id: workID)
            guard selectedAnnotationToken == token, selectedAnnotationID == workID, !Task.isCancelled else { return }
            selectedAnnotation = value
        } catch {
            guard selectedAnnotationToken == token, selectedAnnotationID == workID, !Task.isCancelled else { return }
            selectedAnnotation = nil
            errorText = error.localizedDescription
        }
    }

    private func rememberAnnotation(_ value: LibraryAnnotation, id: String) {
        annotations[id] = value
        if selectedAnnotationID == id {
            selectedAnnotationToken = UUID()
            selectedAnnotationLoading = false
            selectedAnnotation = value
        }
    }

    public func toggleSelection(_ id: String) {
        if selectedIDs.contains(id) { selectedIDs.remove(id) } else { selectedIDs.insert(id) }
    }

    public func selectVisible() {
        let visible = isGrouped
            ? groups.flatMap { groupMembers[$0.id]?.map(\.id) ?? [$0.representative.id] }
            : works.map(\.id)
        if !visible.isEmpty, visible.allSatisfy(selectedIDs.contains) { selectedIDs.subtract(visible) }
        else { selectedIDs.formUnion(visible) }
    }

    public func selectedWorks() async throws -> [SavedWork] {
        guard let database else { return [] }
        let result = try await database.exportWorks(ids: selectedIDs.sorted())
        return result.sorted { ($0.at, $0.id) < ($1.at, $1.id) }
    }

    public func lineagePathWorks() async throws -> [SavedWork] {
        guard let database, let focus = lineageFocusID,
              let path = try await database.lineage(focusNodeID: focus, pathOnly: true) else { return [] }
        return try await database.exportWorks(ids: path.nodes.compactMap { $0.work?.id })
    }

    public func toggleStar(_ work: SavedWork) async {
        await mutate { try await $0.setStarred(ids: [work.id], starred: !work.starred); return "お気に入りを更新しました" }
    }

    public func toggleRevision(_ work: SavedWork) async {
        await toggleAnnotation(work, mark: .revision, status: "推敲の印を更新しました")
    }

    public func toggleShare(_ work: SavedWork) async {
        await toggleAnnotation(work, mark: .share, status: "書き出し用の印を更新しました")
    }

    private func toggleAnnotation(_ work: SavedWork, mark: LibraryAnnotationMark, status: String) async {
        await mutate { database in
            let value = try await database.toggleAnnotation(id: work.id, mark: mark)
            self.rememberAnnotation(value, id: work.id)
            return status
        }
    }

    public func saveNote(id: String, note: String) async {
        await mutate { database in
            try await database.setAnnotation(id: id, note: note)
            let value = try await database.libraryAnnotation(id: id)
            self.rememberAnnotation(value, id: id)
            return "コメントを保存しました"
        }
    }

    public func trash(ids: [String]? = nil) async {
        let ids = ids ?? selectedIDs.sorted()
        if await mutate({ let count = try await $0.setTrashed(ids: ids, trashed: true); return "\(count) 件をごみ箱へ移しました" }) {
            selectedIDs.subtract(ids)
        }
    }

    public func restore(ids: [String]? = nil) async {
        let ids = ids ?? selectedIDs.sorted()
        if await mutate({ let count = try await $0.setTrashed(ids: ids, trashed: false); return "\(count) 件を戻しました" }) {
            selectedIDs.subtract(ids)
        }
    }

    public func permanentlyDelete(ids: [String]? = nil) async {
        let ids = ids ?? selectedIDs.sorted()
        if await mutate({ let count = try await $0.permanentlyDelete(ids: ids); return "\(count) 件を完全に削除しました" }) {
            selectedIDs.subtract(ids)
        }
    }

    public func emptyTrash() async {
        if await mutate({ let count = try await $0.emptyTrash(); return "\(count) 件を完全に削除しました" }) {
            selectedIDs.removeAll()
        }
    }

    @discardableResult
    private func mutate(_ operation: (InkuDatabase) async throws -> String) async -> Bool {
        guard let database, !mutating else { return false }
        mutating = true; errorText = nil
        defer { mutating = false }
        do { status = try await operation(database); await refresh(); await onMutation?(); return true }
        catch { errorText = error.localizedDescription; return false }
    }

    public func toggleGroup(_ root: String) async {
        if expandedGroups.contains(root) { expandedGroups.remove(root) }
        else { expandedGroups.insert(root); await loadGroup(root: root, append: false) }
    }

    public func loadGroup(root: String, append: Bool) async {
        guard let database else { return }
        let token = refreshToken
        let offset = append ? (groupMembers[root]?.count ?? 0) : 0
        do {
            let result = try await database.libraryPage(query: filter, limit: 100, offset: offset, rootNodeID: root)
            guard token == refreshToken else { return }
            let existing = append ? (groupMembers[root] ?? []) : []
            groupMembers[root] = existing + result.items
            groupMemberTotals[root] = result.total
            for item in result.items { annotations[item.id] = item.annotation }
        } catch { errorText = error.localizedDescription }
    }

    public func selectGroup(_ root: String) async {
        guard let database else { return }
        do {
            var offset = 0
            repeat {
                let result = try await database.libraryPage(query: filter, limit: 1000, offset: offset, rootNodeID: root)
                selectedIDs.formUnion(result.items.map(\.id))
                offset += result.items.count
                if result.items.isEmpty || offset >= result.total { break }
            } while true
        } catch { errorText = error.localizedDescription }
    }

    public func loadLineage(work: SavedWork) async {
        guard let id = work.lineageNodeID else { graph = nil; lineageFocusID = nil; return }
        await loadLineage(nodeID: id)
    }

    public func loadLineage(nodeID: String) async {
        guard let database else { return }
        lineageOverviewRequested = false
        let token = UUID()
        lineageToken = token; lineageFocusID = nodeID
        lineageLoading = true; lineageError = nil
        do {
            let result = try await database.lineage(focusNodeID: nodeID, descendantDepth: lineageDepth,
                                                   nodeLimit: 200, pathOnly: lineagePathOnly)
            guard lineageToken == token else { return }
            graph = result; lineageLoading = false
            for item in result?.nodes ?? [] { if let work = item.work { annotations[work.id] = item.annotation } }
        } catch {
            guard lineageToken == token else { return }
            lineageLoading = false; lineageError = error.localizedDescription
        }
    }

    public func loadLineageOverview() async {
        guard let database, let id = lineageFocusID else { return }
        let token = UUID()
        lineageToken = token; lineageOverviewRequested = true
        lineagePathOnly = false; lineageDepth = 200
        lineageLoading = true; lineageError = nil
        do {
            let result = try await database.lineageOverview(focusNodeID: id)
            guard lineageToken == token, lineageFocusID == id else { return }
            graph = result; lineageLoading = false
            for item in result?.nodes ?? [] { if let work = item.work { annotations[work.id] = item.annotation } }
        } catch {
            guard lineageToken == token, lineageFocusID == id else { return }
            lineageLoading = false; lineageError = error.localizedDescription
        }
    }

    public func reloadLineage() async {
        if lineageOverviewRequested && !lineagePathOnly && lineageDepth == 200 { await loadLineageOverview() }
        else if let id = lineageFocusID { await loadLineage(nodeID: id) }
    }

    public func promote(_ nodeID: String) async {
        await mutate { try await $0.promoteLineageNode(id: nodeID); return "作品をライブラリへ追加しました" }
    }

    public func copyHash(_ hash: String?) {
        guard let hash, !hash.isEmpty else { return }
        #if os(macOS)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(hash, forType: .string)
        #elseif os(iOS)
        UIPasteboard.general.string = hash
        #endif
        status = "ハッシュをコピーしました"
    }
}
