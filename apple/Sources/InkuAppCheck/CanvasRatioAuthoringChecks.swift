import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

/// Host boundary only: choice/cancel, new-root declaration, and saved-Score child persistence.
@MainActor
func runCanvasRatioAuthoringChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-canvas-fit-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let url = folder.appendingPathComponent("works.sqlite")
    let transport = CanvasFitNoProvider()
    let app = AppModel(databaseURL: url, transport: transport)
    await app.initialize()
    app.language = "en"; app.seedText = "42"
    let db = try InkuDatabase(url: url)
    let host = PipelineHost(database: db, transport: transport)
    guard let square = app.canvases.first(where: { $0.widthRatio == $0.heightRatio }),
          let paper = app.canvases.first(where: { $0.widthRatio != $0.heightRatio }),
          app.saijiki.count > 2,
          app.saijiki.suffix(2).map(\.id) == ["gamen", "aida"],
          app.saijiki.first(where: { $0.id == "gamen" })?.words.first?.referenceOnly == true,
          !app.ddlCompletions.japanese.contains("画面比"), !app.ddlCompletions.english.contains("aspect ratio"),
          app.productReference?.versions["ddlSpec"]?.isEmpty == false,
          app.productReference?.versions["ddlEngine"]?.isEmpty == false else {
        throw CheckFailure.message("Canvas fit setup: categories=\(app.saijiki.map(\.id)); papers=\(app.canvases.map { "\($0.id):\($0.widthRatio):\($0.heightRatio)" }); versions=\(app.productReference?.versions ?? [:]); error=\(app.errorText ?? "none")")
    }
    guard CanvasRatio.declared(in: "画面比６：４。円を置く。") == CanvasRatio(width: 3, height: 2),
          CanvasRatio.declared(in: "Aspect ratio 0:2.") == nil,
          CanvasRatio.declared(in: "Aspect ratio 10001:2.") == nil else {
        throw CheckFailure.message("Canvas fit: screen-side declaration reading")
    }
    let answers = CanvasFitAnswers()
    app.canvasFitChoiceHandler = { question in answers.questions.append(question); return answers.choice }
    app.canvasID = square.id
    let body = "Paper.\nPlace one red circle at center."
    let declared = "Aspect ratio 3:2.\n" + body
    app.descriptionText = "KEEP_DESCRIPTION"
    app.ddlText = "KEEP_DDL"
    guard !(await app.drawNewDDL(declared)), answers.questions.count == 1,
          try await db.list().isEmpty, !app.isBusy, app.canvasFitQuestion == nil,
          app.descriptionText == "KEEP_DESCRIPTION", app.ddlText == "KEEP_DDL", app.canvasID == square.id else {
        throw CheckFailure.message("Canvas fit: cancelling new DDL started work or lost the draft")
    }
    answers.questions = []
    guard await app.drawNewDDL(body), let parent = app.selectedWork,
          CanvasRatio.declared(in: parent.ddl ?? "") == CanvasRatio(width: 1, height: 1), answers.questions.isEmpty else {
        throw CheckFailure.message("Canvas fit: a new direct DDL did not gain the paper declaration: \(app.errorText ?? app.status)")
    }
    let parentContext = try await app.savedConfiguration(workID: parent.id)
    let parentScore = try ExactJSON(data: Data(parent.score.utf8))
    let editor = DdlEditingSession(work: parent, draft: declared)
    let beforeCancelCount = try await db.list().count
    guard !(await editor.commit(to: app)), editor.draft == declared,
          try await db.list().count == beforeCancelCount, answers.questions.count == 1 else {
        throw CheckFailure.message("Canvas fit: cancelling an edited DDL lost its input or saved a child")
    }

    answers.questions = []; answers.choice = .contain
    app.canvasID = paper.id
    let fitQuestionCount = answers.questions.count
    guard await app.drawEditedDDL(work: parent, source: parent.ddl!, paperID: paper.id),
          let fitted = app.selectedWork, fitted.id != parent.id, answers.questions.count == fitQuestionCount + 1 else {
        throw CheckFailure.message("Canvas fit: unedited saved work did not fit: \(app.errorText ?? app.status)")
    }
    let edge = try await db.edge(childNodeID: fitted.lineageNodeID!)
    let expected = try SavedVariants.response(.object(["action": .string("fit_render"), "score": parentScore,
        "drawn_on": .optional(parent.renderCanvasAspectID), "paper": .string(paper.id)]))
    let fittedScore = try ExactJSON(data: Data(fitted.score.utf8))
    let fitContext = try await app.savedConfiguration(workID: fitted.id)
    guard edge?.parentNodeID == parent.lineageNodeID, edge?.derivationKind == "canvas_fit",
          fittedScore == expected["score"], parentScore["version"].string != nil, fittedScore["version"] == parentScore["version"],
          fitted.ddl == parent.ddl, fitted.renderSeed == parent.renderSeed, fitted.compositionSeed == parent.compositionSeed,
          fitted.renderColorMap == parent.renderColorMap, fitted.renderWild == parent.renderWild,
          fitted.renderCanvasAspectID == paper.id,
          fitContext.document == parentContext.document, fitContext.authorityJSON == parentContext.authorityJSON,
          fitContext.authority == parentContext.authority, fitContext.origin == parentContext.origin,
          fitContext.lawsRecords == parentContext.lawsRecords,
          try ExactJSON(data: Data(edge!.metadataJSON.utf8)) == expected["derivation_metadata"],
          try await db.work(id: parent.id) == parent else {
        throw CheckFailure.message("Canvas fit: saved child lost Score, source, saved facts, authority or lineage")
    }
    let comparison = try await host.prepareReplayComparison(work: fitted)
    guard comparison.replayedSVG == fitted.svg else { throw CheckFailure.message("Canvas fit: saved fitted Score cannot replay") }
    let fitConfig = try ExactJSON(data: fitContext.configuration)
    guard fitConfig["compiler"]["host"]["canvas_format_id"].string == paper.id,
          fitConfig["compiler"]["host"]["canvas_fit"].string == "contain" else {
        throw CheckFailure.message("Canvas fit: a saved child lost the paper and fit context for later edits")
    }
    let countBeforeRefusal = try await db.list().count
    let samePaper = ReplayOptions(catalogID: parent.catalogID ?? "default", colorMap: Data((parent.renderColorMap ?? "{}").utf8),
        canvasID: square.id, widthRatio: square.widthRatio, heightRatio: square.heightRatio, canvasWidth: 1080, canvasHeight: 1080)
    do {
        _ = try await host.fitSavedWork(workID: parent.id, paper: samePaper)
        throw CheckFailure.message("Canvas fit: same-ratio saved work was offered a fit")
    } catch let refusal as SavedVariantRefusal {
        guard refusal.reason == "same_ratio", try await db.list().count == countBeforeRefusal else { throw refusal }
    }

    app.canvasID = square.id; answers.questions = []; answers.choice = .contain
    guard await app.drawNewDDL(declared), let contained = app.selectedWork else {
        throw CheckFailure.message("Canvas fit: direct contain failed: \(app.errorText ?? app.status)")
    }
    let containedConfig = try ExactJSON(data: await app.savedConfiguration(workID: contained.id).configuration)
    guard containedConfig["compiler"]["host"]["canvas_fit"].string == "contain",
          CanvasRatio.declared(in: contained.ddl ?? "") == CanvasRatio(width: 3, height: 2) else {
        throw CheckFailure.message("Canvas fit: contain was not sent or the author's declaration was replaced")
    }
    answers.choice = .paper
    let editedSource = declared.replacingOccurrences(of: "red", with: "blue")
    guard await app.drawEditedDDL(work: contained, source: editedSource), let stretched = app.selectedWork else {
        throw CheckFailure.message("Canvas fit: edited draw-to-paper failed")
    }
    let stretchConfig = try ExactJSON(data: await app.savedConfiguration(workID: stretched.id).configuration)
    guard stretchConfig["compiler"]["host"]["canvas_fit"] == .null,
          stretched.ddl == editedSource else {
        throw CheckFailure.message("Canvas fit: a previous contain leaked or saved-parent edit gained a declaration")
    }

    // An older direct DDL has no declaration. Editing it must not add one; fitting uses its recorded paper.
    var oldRequest = try app.requestForCurrentInput(inputMode: "ddl", source: body, parentWorkID: nil, derivationKind: "new")
    oldRequest.declareCanvas = nil
    let oldView = try await host.generate(oldRequest)
    guard let oldID = oldView.savedWorkID, let legacy = try await db.work(id: oldID),
          CanvasRatio.declared(in: legacy.ddl ?? "") == nil else { throw CheckFailure.message("Canvas fit: legacy setup") }
    let legacyScore = try ExactJSON(data: Data(legacy.score.utf8))
    do {
        _ = try SavedVariants.response(.object(["action": .string("fit_render"), "score": legacyScore,
            "drawn_on": .null, "paper": .string(paper.id)]))
        throw CheckFailure.message("Canvas fit: missing recorded ratio was not refused")
    } catch let refusal as SavedVariantRefusal {
        guard refusal.reason == "no_recorded_ratio" else { throw refusal }
    }
    answers.questions = []; answers.choice = .contain
    guard await app.drawEditedDDL(work: legacy, source: legacy.ddl!, paperID: paper.id),
          let legacyFit = app.selectedWork, answers.questions.count == 1,
          legacyFit.ddl == legacy.ddl,
          try ExactJSON(data: Data(legacyFit.score.utf8))["canvas"]["fit"].string == "contain" else {
        throw CheckFailure.message("Canvas fit: undeclared saved work did not use its recorded paper")
    }
    answers.questions = []
    guard await app.drawEditedDDL(work: legacy, source: body + "\nPlace one blue square."),
          let legacyEdit = app.selectedWork, CanvasRatio.declared(in: legacyEdit.ddl ?? "") == nil, answers.questions.isEmpty,
          await transport.calls == 0 else {
        throw CheckFailure.message("Canvas fit: legacy/no-ratio edit gained a declaration, asked, or called a provider")
    }
    print("Canvas fit PASS: new-root declaration and authored ratio; editable/new cancellation keeps drafts and history; contain versus draw-to-paper; saved fit_render child has core Score/metadata, same DDL/version/seeds/authority/laws and unchanged parent; saved child replays; same_ratio/no_recorded_ratio; legacy edits do not declare; gamen before aida, reference-only; provider=0. Isolated SQLite only.")
}

@MainActor private final class CanvasFitAnswers {
    var questions: [CanvasFitQuestion] = []
    var choice = CanvasFitChoice.cancel
}

private actor CanvasFitNoProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw CheckFailure.message("Canvas fit checks must not call a provider")
    }
}
