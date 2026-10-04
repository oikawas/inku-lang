import Foundation
import InkuPersistence
import Observation

public enum LibraryAnnotationState: Sendable, Equatable {
    case loading, available(LibraryAnnotation), unavailable

    public var annotation: LibraryAnnotation? {
        if case .available(let value) = self { return value }
        return nil
    }
}

/// Inspecting saved work has no authority over the document being edited in Create.
@MainActor @Observable
public final class LibraryPreviewModel {
    public private(set) var work: SavedWork?
    public private(set) var annotationState: LibraryAnnotationState = .unavailable
    public private(set) var errorText: String?
    @ObservationIgnored private var selectionToken = UUID()
    @ObservationIgnored private var readToken = UUID()

    public init() {}

    public func show(_ work: SavedWork) {
        selectionToken = UUID()
        readToken = UUID()
        self.work = work
        annotationState = .loading
        errorText = nil
    }

    public func close() {
        selectionToken = UUID()
        readToken = UUID()
        work = nil
        annotationState = .unavailable
        errorText = nil
    }

    public func loadAnnotation(using read: (String) async throws -> LibraryAnnotation,
                               readWork: ((String) async throws -> SavedWork?)? = nil) async {
        guard let id = work?.id else { return }
        let selection = selectionToken
        let token = UUID()
        readToken = token
        annotationState = .loading
        errorText = nil
        do {
            let value = try await read(id)
            guard selectionToken == selection, readToken == token, work?.id == id, !Task.isCancelled else { return }
            let refreshedWork = try await readWork?(id)
            guard selectionToken == selection, readToken == token, work?.id == id, !Task.isCancelled else { return }
            if let refreshedWork, refreshedWork.id == id { work = refreshedWork }
            annotationState = .available(value)
        } catch {
            guard selectionToken == selection, readToken == token, work?.id == id, !Task.isCancelled else { return }
            annotationState = .unavailable
            errorText = error.localizedDescription
        }
    }

    public func adoptAnnotation(_ value: LibraryAnnotation, workID: String) {
        guard work?.id == workID else { return }
        readToken = UUID()
        annotationState = .available(value)
        errorText = nil
    }

    @discardableResult
    public func openInCreate(app: AppModel) async throws -> Bool {
        guard !app.isBusy, let id = work?.id else { return false }
        let selection = selectionToken
        let database = try app.auxiliaryDatabase()
        guard let saved = try await database.work(id: id), !saved.trashed else { return false }
        guard selectionToken == selection, work?.id == id, !app.isBusy, !Task.isCancelled else { return false }
        await app.selectWork(saved)
        return selectionToken == selection && work?.id == id && app.selectedWorkID == id && !app.isBusy && !Task.isCancelled
    }

    public func exportWorks(app: AppModel) async throws -> [SavedWork] {
        guard let id = work?.id else { return [] }
        let selection = selectionToken
        let database = try app.auxiliaryDatabase()
        let saved = try await database.exportWorks(ids: [id])
        guard selectionToken == selection, work?.id == id, !Task.isCancelled else { return [] }
        return saved
    }
}
