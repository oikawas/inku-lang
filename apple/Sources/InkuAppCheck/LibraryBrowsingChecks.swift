import Foundation
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runLibraryBrowsingChecks() async throws {
    // Mapped failures: browsing replaced the Create draft; off-page delayed notes were
    // ignored/overwritten; missing interpretation metadata was mislabeled as DDL.
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-library-browsing-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let url = folder.appendingPathComponent("works.sqlite")
    let database = try InkuDatabase(url: url)
    let original = SavedWork(id: "browsing-create", at: 2, input: "Create A", score: "{}", svg: "<svg>A</svg>",
                             ddl: "A", stage1Model: "check:interpretation", lineageNodeID: "browsing-create-node")
    let inspected = SavedWork(id: "browsing-preview", at: 1, input: "Preview B", score: "{}", svg: "<svg>春B</svg>",
                              ddl: "B", stage2Model: "check:drawing", lineageNodeID: "browsing-preview-node")
    for work in [original, inspected] {
        try await database.save(work, node: LineageNode(id: work.lineageNodeID!, historyID: work.id, at: work.at))
    }
    try await database.setAnnotation(id: original.id, note: "A note")
    try await database.setAnnotation(id: inspected.id, note: "Saved B note")
    let provider = LibraryBrowsingNoProvider()
    let app = AppModel(databaseURL: url, transport: provider)
    app.library.pageSize = 1
    await app.initialize()
    await app.selectWork(original)
    app.ddlText = "Unsaved A DDL"
    app.descriptionText = "Unsaved A description"
    let draftDDL = app.ddlText
    let draftDescription = app.descriptionText
    let svg = app.currentSVG
    let score = app.scoreJSON
    let rows = try await database.list()
    let lineage = try await database.lineage(focusNodeID: original.lineageNodeID!)
    guard app.errorText == nil, app.library.works.map(\.id) == [original.id],
          app.library.annotations[inspected.id] == nil else {
        throw CheckFailure.message("Library browsing fixture did not keep B outside its one-work page")
    }

    let preview = LibraryPreviewModel()
    preview.show(inspected)
    await preview.loadAnnotation(using: { id in try await database.libraryAnnotation(id: id) })
    let export = try await preview.exportWorks(app: app)
    preview.close()
    guard preview.work == nil, export.map(\.id) == [inspected.id],
          app.selectedWorkID == original.id, app.ddlText == draftDDL, app.descriptionText == draftDescription,
          app.currentSVG == svg, app.scoreJSON == score,
          try await database.list() == rows, try await database.lineage(focusNodeID: original.lineageNodeID!) == lineage,
          await provider.calls == 0 else {
        throw CheckFailure.message("Library preview/close/export changed Create A or borrowed its export target")
    }

    // A closed preview cannot adopt an annotation read that finishes afterward.
    let closeGate = LibraryBrowsingReadGate()
    preview.show(inspected)
    let pendingClose = Task { @MainActor in
        await preview.loadAnnotation(using: { id in
            await closeGate.pause()
            return try await database.libraryAnnotation(id: id)
        })
    }
    await closeGate.waitUntilEntered()
    preview.close()
    await closeGate.release()
    await pendingClose.value
    guard preview.work == nil, preview.annotationState == .unavailable else {
        throw CheckFailure.message("A late annotation read reopened a closed Library preview")
    }

    let editor = LibraryNoteEditorModel()
    editor.receive(workID: inspected.id, state: .loading)
    editor.text = "Must not save unknown note"
    var unknownWrites = 0
    _ = await editor.save { _, _ in unknownWrites += 1; return LibraryAnnotation() }
    guard !editor.canSave, unknownWrites == 0 else { throw CheckFailure.message("An unrecorded comment was writable before its saved-ID read") }
    // A real delayed SQLite read must fill an untouched off-page editor.
    editor.receive(workID: original.id, state: .unavailable)
    editor.receive(workID: inspected.id, state: .loading)
    preview.show(inspected)
    let noteGate = LibraryBrowsingReadGate()
    let pendingNote = Task { @MainActor in
        await preview.loadAnnotation(using: { id in
            await noteGate.pause()
            return try await database.libraryAnnotation(id: id)
        })
    }
    await noteGate.waitUntilEntered()
    await noteGate.release()
    await pendingNote.value
    editor.receive(workID: inspected.id, state: preview.annotationState)
    guard editor.text == "Saved B note", !editor.dirty, !editor.canSave else {
        throw CheckFailure.message("A delayed off-page annotation did not initialize the comment editor")
    }
    editor.text = "Edited B note"
    editor.receive(workID: inspected.id, state: .loading)
    try await database.setAnnotation(id: inspected.id, note: "Later saved B note")
    await preview.loadAnnotation(using: { id in try await database.libraryAnnotation(id: id) })
    editor.receive(workID: inspected.id, state: preview.annotationState)
    guard editor.text == "Edited B note", editor.savedText == "Later saved B note", editor.canSave else {
        throw CheckFailure.message("A later annotation replaced a dirty comment draft")
    }
    var writtenIDs: [String] = []
    let saved = await editor.save { id, note in
        writtenIDs.append(id)
        await app.library.saveNote(id: id, note: note)
        if let error = app.library.errorText { throw CheckFailure.message(error) }
        return try await database.libraryAnnotation(id: id)
    }
    let reopened = try InkuDatabase(url: url)
    guard saved?.note == "Edited B note", writtenIDs == [inspected.id], !editor.dirty,
          try await reopened.libraryAnnotation(id: inspected.id).note == "Edited B note",
          try await reopened.libraryAnnotation(id: original.id).note == "A note",
          try await reopened.list() == rows, app.selectedWorkID == original.id,
          app.ddlText == draftDDL, app.descriptionText == draftDescription else {
        throw CheckFailure.message("The off-page comment did not save durably to B alone")
    }

    let facts = SavedWorkFacts.models(inspected)
    guard facts.count == 2, facts[0].role == .interpretation, facts[0].reference == nil,
          facts[1].role == .drawing, facts[1].reference == "check:drawing",
          SavedWorkFacts.recordedModel(inspected.stage1Model) == nil,
          SavedWorkFacts.svgBytes(inspected) == Int64(inspected.svg.utf8.count) else {
        throw CheckFailure.message("Saved model roles/unknown interpretation/SVG UTF8 size were inferred or conflated")
    }
    guard try await preview.openInCreate(app: app), app.selectedWork == inspected,
          app.ddlText == inspected.ddl, app.descriptionText == inspected.effectiveSourceText,
          try await reopened.list() == rows, try await reopened.lineage(focusNodeID: original.lineageNodeID!) == lineage,
          await provider.calls == 0 else {
        throw CheckFailure.message("Only explicit Open in Create should select B without changing saved history")
    }
    print("Library browsing passed: independent preview/close/export preserve Create A; explicit open selects B; delayed off-page comments preserve dirty drafts and save only B; saved model roles/unknowns/SVG bytes remain facts. Two SQLite works/pageSize1, provider0.")
}

private actor LibraryBrowsingNoProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw CheckFailure.message("Library browsing must not call a provider")
    }
}

private actor LibraryBrowsingReadGate {
    private var entered = false
    private var entryWaiter: CheckedContinuation<Void, Never>?
    private var readWaiter: CheckedContinuation<Void, Never>?
    func pause() async {
        entered = true
        entryWaiter?.resume(); entryWaiter = nil
        await withCheckedContinuation { readWaiter = $0 }
    }
    func waitUntilEntered() async {
        if entered { return }
        await withCheckedContinuation { entryWaiter = $0 }
    }
    func release() { readWaiter?.resume(); readWaiter = nil }
}
