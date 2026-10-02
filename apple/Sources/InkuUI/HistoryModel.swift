import Foundation
import InkuPersistence
import Observation

@MainActor @Observable
public final class HistoryModel {
    public let library = LibraryModel()
    public private(set) var generations: [String: Int] = [:]
    public private(set) var generationLoading = true
    public private(set) var generationError: String?
    @ObservationIgnored private var database: InkuDatabase?
    @ObservationIgnored private var generationToken = UUID()
    public init() { library.pageSize = 20 }
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

    public func locate(app: AppModel) async {
        guard let database, let id = app.selectedWorkID else { return }
        do {
            guard let position = try await database.libraryIndex(id: id, query: library.filter), app.selectedWorkID == id else { return }
            if library.page != position / library.pageSize { await library.setPage(position / library.pageSize) }
        } catch { app.errorText = error.localizedDescription }
    }
    public func navigate(app: AppModel, delta: Int = 0, boundary: String? = nil) async {
        guard let database, !app.isBusy, library.total > 0 else { return }
        do {
            let current: Int?
            if let id = app.selectedWorkID { current = try await database.libraryIndex(id: id, query: library.filter) }
            else { current = nil }
            let index: Int
            if boundary == "latest" { index = 0 }
            else if boundary == "oldest" { index = library.total - 1 }
            else { index = min(library.total - 1, max(0, (current ?? 0) + delta)) }
            await library.setPage(index / library.pageSize)
            guard library.works.indices.contains(index % library.pageSize) else { return }
            await app.selectWork(library.works[index % library.pageSize])
        } catch { app.errorText = error.localizedDescription }
    }
}
