import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

@MainActor
func runAuthoringChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-authoring-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let transport = AuthoringProvider()
    let model = AppModel(databaseURL: folder.appendingPathComponent("works.sqlite"), transport: transport)
    await model.initialize()
    guard model.errorText == nil else { throw CheckFailure.message("Authoring initialization: \(model.errorText ?? model.status)") }

    // Failure: the installation sent an empty macro registry, silently omitting Nature's words.
    model.language = "ja"
    model.ddlText = "Nature.若葉 を置く"
    model.seedText = "42"
    await model.generate()
    guard model.errorText == nil, let macroWork = model.selectedWork,
          model.pluginWords.count == 7, !model.saijiki.isEmpty else {
        throw CheckFailure.message("Bundled macro did not draw: \(model.errorText ?? model.status)")
    }
    let savedContext = try await model.savedConfiguration(workID: macroWork.id)
    let config = try ExactJSON(data: savedContext.configuration)
    let document = try ExactJSON(data: savedContext.document ?? Data("{}".utf8))
    guard config["definitions"].array?.count == 7, document["macro_locks"].array?.count == 7,
          try ExactJSON(data: Data(macroWork.score.utf8))["instructions"].array?.isEmpty == false,
          await transport.calls == 0 else {
        throw CheckFailure.message("Bundled definitions, pinned digests or pure DDL drawing missing")
    }
    let rowCount = model.works.count
    await model.checkDDL()
    guard model.errorText == nil, model.works.count == rowCount else { throw CheckFailure.message("Draft inspection mutated history") }

    // Failure: replay copied the old image and ignored the requested catalog/canvas.
    model.catalogID = model.catalogs.first(where: { $0.id != macroWork.catalogID })!.id
    model.canvasID = model.canvases.first(where: { $0.widthRatio != $0.heightRatio })!.id
    model.seedText = "43"
    model.wild = true
    await model.replayWithCurrentOptions()
    guard model.errorText == nil, let replayed = model.selectedWork,
          replayed.id != macroWork.id, replayed.score == macroWork.score,
          replayed.renderSeed == "43", replayed.renderWild == true,
          replayed.renderColorCatalogID == model.catalogID, replayed.renderCanvasAspectID == model.canvasID else {
        throw CheckFailure.message("Saved Score replay ignored explicit conditions: \(model.errorText ?? model.status)")
    }
    let db = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
    guard try await db.work(id: macroWork.id) == macroWork else { throw CheckFailure.message("Replay changed its canonical parent") }

    // Failure: committing a generated draft lost its revision, source lock or immediate lineage parent.
    model.newWork()
    model.inputMode = "description"
    model.descriptionText = "a red circle"
    model.language = "en"
    model.catalogID = "default"
    model.canvasID = "square"
    model.wild = false
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false)
    try await model.updateHostSettings(HostSettings(providers: [provider],
        models: ModelSelection(stage1Model: "check:model", stage2Model: "check:model")))
    await model.generate()
    guard let parent = model.selectedWork, model.errorText == nil, !model.sourceLocked else {
        throw CheckFailure.message("Description did not retain authoring authority: \(model.errorText ?? model.status)")
    }
    let revision = model.authoringRevision
    model.ddlText = "place one blue circle at center."
    await model.commitDDL()
    guard let edited = model.selectedWork, model.errorText == nil, edited.id != parent.id,
          model.sourceLocked, model.authoringRevision != revision, edited.ddl == model.ddlText,
          let nodeID = edited.lineageNodeID else {
        throw CheckFailure.message("Committed mutation did not lock/save its revision: \(model.errorText ?? model.status)")
    }
    let edge = try await db.edge(childNodeID: nodeID)
    guard edge?.parentNodeID == parent.lineageNodeID, try await db.work(id: parent.id) == parent,
          await transport.calls == 1 else { throw CheckFailure.message("DDL mutation lost lineage or sent an unnecessary model request") }

    // Failure: hole proposals changed visible DDL before approval, or decline could not be retried explicitly.
    model.newWork()
    model.inputMode = "ddl"
    model.ddlText = "place one red circle at center. many square."
    await model.generate()
    guard model.errorText == nil, model.authoringPhase == "awaiting_patch_approval",
          model.visibleDDL.contains("many"), model.patchCandidate.contains("8"), !model.holeIDs.isEmpty else {
        throw CheckFailure.message("Hole proposal did not await approval: \(model.errorText ?? model.status)")
    }
    await model.declinePatch()
    guard model.authoringPhase == "needs_user_edit", model.patchProposalJSON.isEmpty,
          model.visibleDDL.contains("many") else { throw CheckFailure.message("Decline mutated committed source") }
    await model.completeHoles()
    guard model.authoringPhase == "awaiting_patch_approval" else { throw CheckFailure.message("Explicit completion retry did not propose a patch") }
    await model.approvePatch()
    guard model.errorText == nil, model.authoringPhase == "completed", model.selectedWork?.ddl?.contains("8 square") == true,
          model.sourceLocked, !model.promptJSON.isEmpty else {
        throw CheckFailure.message("Approved patch did not commit/render: \(model.errorText ?? model.status)")
    }
    print("Authoring passed: 7 canonical macros and digest locks; read-only draft check; saved Score replay conditions; committed revision/source lock/lineage; hole propose/decline/retry/approve; sent prompts. No external provider calls.")
}

private actor AuthoringProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        let input = try ExactJSON(data: action)
        let isHole = input["tag"].string == "complete_visible_ddl_holes"
        let response = isHole ? #"{"results":[{"id":"h1","status":"proposed","replacement":"8"}]}"#
            : #"{"normalized_ddl":"place one red circle at center."}"#
        return ExactJSON.object(["tag": .string(isHole ? "visible_ddl_hole_patch_generated" : "normalized_ddl_generated"),
            "identity": input["identity"], "response": .string(response), "elapsed_ms": .string("1")]).data
    }
}
