import Foundation
import InkuPersistence
import Observation

@MainActor @Observable
final class PhoneViewingEvents {
    var savedWork: SavedWork?
    var selectSavedWork = false
    var refinementWork: SavedWork?
}

/// A viewing session keeps its opening order even when the library filter changes underneath it.
struct PhoneViewingOrder: Equatable {
    private(set) var ids: [String]
    private(set) var currentID: String?

    init(ids: [String], currentID: String) {
        var seen = Set<String>()
        self.ids = ids.filter { seen.insert($0).inserted }
        if !seen.contains(currentID) { self.ids.append(currentID) }
        self.currentID = currentID
    }

    mutating func move(_ delta: Int) {
        guard let currentID, let index = ids.firstIndex(of: currentID) else { return }
        let next = index + delta
        guard ids.indices.contains(next) else { return }
        self.currentID = ids[next]
    }
    mutating func first() { currentID = ids.first }
    mutating func last() { currentID = ids.last }
    mutating func append(_ more: [String]) {
        var known = Set(ids)
        ids.append(contentsOf: more.filter { known.insert($0).inserted })
    }
    mutating func insertFirst(_ id: String, select: Bool) {
        ids.removeAll { $0 == id }; ids.insert(id, at: 0)
        if select { currentID = id }
    }
    mutating func remove(_ id: String) {
        guard let index = ids.firstIndex(of: id) else { return }
        ids.remove(at: index)
        if currentID == id { currentID = ids.isEmpty ? nil : ids[min(index, ids.count - 1)] }
    }
}

/// The timeline continues with the filter that was active when the viewer opened.
struct PhoneViewingPageReader {
    let query: LibraryQuery
    func page(database: InkuDatabase, offset: Int, limit: Int) async throws -> LibraryPage {
        try await database.libraryPage(query: query, limit: limit, offset: offset, includeSVG: false)
    }
}

/// The iPhone viewer's two read-only exceptions do not unlock other saved-work actions.
struct PhoneViewingPermissions {
    let browsingLocked: Bool
    let writingLocked: Bool
    let mutating: Bool
    let trashed: Bool
    let sharing: Bool
    var canStar: Bool { !mutating && !trashed }
    var canShare: Bool { !trashed && !sharing }
    var canBrowse: Bool { !browsingLocked && !trashed }
    var canWrite: Bool { !browsingLocked && !writingLocked && !trashed }
}
