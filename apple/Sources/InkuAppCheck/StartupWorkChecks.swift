import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runStartupWorkChecks() async throws {
    // Failure: initialize loaded history but left the work canvas empty, unlike Web's first history item.
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-startup-work-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let url = folder.appendingPathComponent("works.sqlite")
    let database = try InkuDatabase(url: url)
    let provider = StartupWorkNoProvider()
    let empty = AppModel(databaseURL: url, transport: provider)
    await empty.initialize()
    guard empty.errorText == nil, empty.selectedWorkID == nil, empty.currentSVG.isEmpty else {
        throw CheckFailure.message("An empty library did not start with an empty work canvas")
    }
    let older = SavedWork(id: "startup-older", at: 1, input: "Older description", score: "{}", svg: "<svg>older</svg>",
                          ddl: "Older DDL", lineageNodeID: "startup-older-node")
    let newest = SavedWork(id: "startup-newest", at: 2, input: "Stored input", score: "{}", svg: "<svg>newest</svg>",
                           sourceText: "Newest source", ddl: "Newest DDL", lineageNodeID: "startup-newest-node")
    let trashed = SavedWork(id: "startup-trashed", at: 3, input: "Trash", score: "{}", svg: "<svg>trash</svg>",
                            trashed: true, lineageNodeID: "startup-trashed-node")
    let hidden = SavedWork(id: "startup-hidden", at: 4, input: "Lineage only", score: "{}", svg: "<svg>hidden</svg>",
                           historyVisibility: "lineage_only", lineageNodeID: "startup-hidden-node")
    for work in [older, newest, trashed, hidden] {
        try await database.save(work, node: LineageNode(id: work.lineageNodeID!, historyID: work.id, at: work.at))
    }
    try await database.setAnnotation(id: newest.id, note: "Newest note")
    let rows = try await database.list()
    let app = AppModel(databaseURL: url, transport: provider)
    await app.initialize()
    guard app.errorText == nil, app.selectedWork == newest, app.currentSVG == newest.svg,
          app.visibleDDL == newest.ddl, app.ddlText == newest.ddl, app.scoreJSON == newest.score,
          app.descriptionText == newest.effectiveSourceText, app.library.selectedAnnotation?.note == "Newest note" else {
        throw CheckFailure.message("Startup did not open the latest normal saved work with its own image, instructions, source and note")
    }
    // Selection is a startup action, never a fallback inside the ordinary history refresh.
    app.newWork()
    app.descriptionText = "Unsaved new description"
    await app.refreshWorks()
    await app.initialize()
    guard app.selectedWorkID == nil, app.currentSVG.isEmpty, app.descriptionText == "Unsaved new description",
          try await database.list() == rows, await provider.calls == 0 else {
        throw CheckFailure.message("Refreshing after New reopened a saved work, changed history, or called a provider")
    }
    let trashURL = folder.appendingPathComponent("trash-only.sqlite")
    let trashDatabase = try InkuDatabase(url: trashURL)
    for work in [trashed, hidden] {
        try await trashDatabase.save(work, node: LineageNode(id: work.lineageNodeID!, historyID: work.id, at: work.at))
    }
    let trashOnly = AppModel(databaseURL: trashURL, transport: provider)
    await trashOnly.initialize()
    guard trashOnly.errorText == nil, trashOnly.selectedWorkID == nil, trashOnly.currentSVG.isEmpty,
          await provider.calls == 0 else {
        throw CheckFailure.message("Startup opened a trashed or lineage-only work when no normal work existed")
    }
    print("Startup work passed: latest normal work opens with its own SVG/DDL/source/note; newer trash and lineage-only works excluded; empty libraries stay empty; New plus refresh stays detached; saved rows unchanged; provider0.")
}

private actor StartupWorkNoProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw CheckFailure.message("Startup must not call a provider")
    }
}
