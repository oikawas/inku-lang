import Foundation
import InkuPersistence
import Observation

/// Web `HistoryStrip.svelte` (Builds 1265–1267: `c265e28bb`, `f62812ed3`, `72cc0ca77`): the one empty tile the history
/// strip shows where thumbnails would be, so the strip, its filters and its search stay on screen.
public enum HistoryStripPlaceholder: Equatable, Sendable {
    /// "No matches": a search or a mark found nothing, and the answer is in (Web `noCandidates`).
    case noCandidates
    /// "Searching…": a filtered strip with no thumbnails awaits its answer (Web `searching` while `filtered`).
    case searching
    /// "Loading": a strip that has held works awaits its answer with no thumbnails, as after clearing a search
    /// (Web `searching` while not `filtered`).
    case loading

    public init?(filtered: Bool, total: Int, showsNoWorks: Bool, awaiting: Bool, failed: Bool, heldWorks: Bool) {
        if (filtered || heldWorks) && showsNoWorks && awaiting { self = filtered ? .searching : .loading }
        else if filtered && total == 0 && !awaiting && !failed { self = .noCandidates }
        else { return nil }
    }
}

@MainActor @Observable
public final class HistoryModel {
    public let library = LibraryModel()
    public private(set) var generations: [String: Int] = [:]
    public private(set) var generationLoading = true
    public private(set) var generationError: String?
    public private(set) var selectedIndex: Int?
    @ObservationIgnored private var database: InkuDatabase?
    @ObservationIgnored private var generationToken = UUID()
    @ObservationIgnored private var locationToken = UUID()
    @ObservationIgnored private var navigationToken = UUID()
    public init() { library.pageSize = 20; library.canvasSearch = true }

    public var canMoveNewer: Bool { (selectedIndex ?? 0) > 0 }
    public var canMoveOlder: Bool { library.total > 0 && (selectedIndex ?? 0) < library.total - 1 }

    /// Web `filtered`: a search or a mark narrows the strip, so none found is an answer, not an empty history.
    public var filtered: Bool {
        library.starredOnly || library.revisionOnly || !library.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// The strip's empty tile now. `heldWorks` is whether the strip has held works since it appeared (Web `heldWorks`).
    public func placeholder(heldWorks: Bool) -> HistoryStripPlaceholder? {
        HistoryStripPlaceholder(filtered: filtered, total: library.total, showsNoWorks: library.works.isEmpty,
                                awaiting: library.awaitingRead, failed: library.errorText != nil, heldWorks: heldWorks)
    }

    public func updateCapacity(_ value: Int, app: AppModel, workID: String? = nil) async {
        let capacity = max(1, value)
        guard library.pageSize != capacity else { return }
        library.pageSize = capacity
        await locate(app: app, workID: workID)
        await library.setPage(library.page)
    }
    public func connect(app: AppModel) async {
        guard database == nil else { return }
        do {
            let database = try app.auxiliaryDatabase()
            self.database = database
            await library.connect(database: database)
            await locate(app: app)
        } catch { app.errorText = error.localizedDescription }
    }

    /// Fetch page metadata independently of the selected work or visible ancestors.
    public func refreshGenerations() async {
        guard let database else { return }
        let nodeIDs = library.works.compactMap(\.lineageNodeID)
        let token = UUID()
        generationToken = token
        generationLoading = true
        generationError = nil
        generations = [:]
        do {
            let result = try await database.lineageGenerations(nodeIDs: nodeIDs)
            guard generationToken == token, !Task.isCancelled,
                  library.works.compactMap(\.lineageNodeID) == nodeIDs else { return }
            generations = result
            generationLoading = false
        } catch {
            guard generationToken == token, !Task.isCancelled,
                  library.works.compactMap(\.lineageNodeID) == nodeIDs else { return }
            generationLoading = false
            generationError = error.localizedDescription
        }
    }

    public func locate(app: AppModel, workID: String? = nil) async {
        let token = UUID(); locationToken = token
        guard let database, let id = workID ?? app.selectedWorkID else { selectedIndex = nil; return }
        do {
            let position = try await database.libraryIndex(id: id, query: library.filter)
            guard locationToken == token, workID != nil || app.selectedWorkID == id else { return }
            selectedIndex = position
            guard let position else { return }
            if library.page != position / library.pageSize { await library.setPage(position / library.pageSize) }
        } catch { if locationToken == token { app.errorText = error.localizedDescription } }
    }
    @discardableResult
    public func navigate(app: AppModel, fromWorkID: String? = nil, delta: Int = 0, boundary: String? = nil,
                         selectWork: Bool = true) async -> SavedWork? {
        guard let database, !app.isBrowsingLocked, library.total > 0 else { return nil }
        let token = UUID(); navigationToken = token
        let initialSelection = app.selectedWorkID
        let query = library.filter
        do {
            let current: Int?
            if let id = fromWorkID ?? app.selectedWorkID { current = try await database.libraryIndex(id: id, query: library.filter) }
            else { current = nil }
            guard navigationToken == token, !app.isBrowsingLocked,
                  app.selectedWorkID == initialSelection, library.filter == query else { return nil }
            let index: Int
            if boundary == "latest" { index = 0 }
            else if boundary == "oldest" { index = library.total - 1 }
            else { index = min(library.total - 1, max(0, (current ?? 0) + delta)) }
            await library.setPage(index / library.pageSize)
            guard navigationToken == token, !app.isBrowsingLocked,
                  app.selectedWorkID == initialSelection, library.filter == query else { return nil }
            guard library.works.indices.contains(index % library.pageSize) else { return nil }
            let work = library.works[index % library.pageSize]
            if selectWork {
                await app.selectWork(work)
                guard navigationToken == token, !app.isBrowsingLocked,
                      app.selectedWorkID == work.id, library.filter == query else { return nil }
            }
            selectedIndex = index
            return work
        } catch { if navigationToken == token { app.errorText = error.localizedDescription }; return nil }
    }
}
