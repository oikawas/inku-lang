import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runSavedAnnotationSelectionChecks() async throws {
    // Failure: a selected work's true mark became false when its page cache disappeared,
    // so one attempt to remove the mark saved true again instead of toggling the durable value.
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-saved-annotation-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let url = folder.appendingPathComponent("works.sqlite")
    let database = try InkuDatabase(url: url)
    let target = SavedWork(id: "annotation-selected", at: 2, input: "selected work", score: "{}", svg: "<svg/>",
                           lineageNodeID: "annotation-selected-node")
    let other = SavedWork(id: "annotation-other", at: 1, input: "other work", score: "{}", svg: "<svg/>",
                          lineageNodeID: "annotation-other-node")
    for work in [target, other] {
        try await database.save(work, node: LineageNode(id: work.lineageNodeID!, historyID: work.id, at: work.at))
    }
    try await database.setAnnotation(id: target.id, forRevision: true, forShare: true)

    let provider = SavedAnnotationNoProvider()
    let app = AppModel(databaseURL: url, transport: provider)
    app.library.pageSize = 1
    await app.initialize()
    guard app.errorText == nil, app.library.works.map(\.id) == [target.id] else {
        throw CheckFailure.message("Saved annotation fixture did not open its first one-work page")
    }
    await app.selectWork(target)
    await app.library.setPage(1)
    guard app.selectedWorkID == target.id, app.library.works.map(\.id) == [other.id],
          app.library.annotations[target.id] == nil,
          app.library.loadedAnnotation(for: target.id)?.forRevision == true,
          app.library.loadedAnnotation(for: target.id)?.forShare == true else {
        throw CheckFailure.message("Page refresh discarded the selected work's durable marks")
    }

    // Reopening the same saved ID outside the page must read SQLite, not infer an absent mark.
    await app.selectWork(target)
    guard app.library.selectedAnnotationID == target.id, !app.library.selectedAnnotationLoading,
          app.library.loadedAnnotation(for: target.id)?.forRevision == true else {
        throw CheckFailure.message("Off-page selection failed to read its saved annotation by ID")
    }
    await app.library.toggleRevision(target)
    let reopened = try InkuDatabase(url: url)
    let saved = try await reopened.libraryAnnotation(id: target.id)
    guard app.library.errorText == nil, !saved.forRevision, saved.forShare,
          app.library.loadedAnnotation(for: target.id) == saved,
          app.library.works.map(\.id) == [other.id], app.selectedWork == target,
          try await reopened.list().count == 2, await provider.calls == 0 else {
        throw CheckFailure.message("One off-page mark toggle did not persist true-to-false without changing the selected work")
    }
    app.newWork()
    guard app.library.selectedAnnotationID == nil, app.library.selectedAnnotation == nil else {
        throw CheckFailure.message("New work retained the previous saved annotation selection")
    }
    print("Saved annotation selection passed: two SQLite works/pageSize1; selected marks survive paging, off-page ID reload reads true, one toggle durably saves false and preserves the other mark. No provider calls or history additions.")
}

private actor SavedAnnotationNoProvider: ProviderTransport {
    private(set) var calls = 0

    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw CheckFailure.message("Saved annotation selection must not call a provider")
    }
}
