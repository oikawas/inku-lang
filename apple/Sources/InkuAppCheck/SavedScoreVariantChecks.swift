import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

/// Failures: repeated/identity assignments, changed placement, a draft used as parent, or an unreplayable saved child.
@MainActor
func runSavedScoreVariantChecks(folder: URL) async throws {
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let url = folder.appendingPathComponent("works.sqlite")
    guard !FileManager.default.fileExists(atPath: url.path) else { throw CheckFailure.message("Refusing to overwrite variant fixture") }
    let colors = Data(##"{"palette:1":"#000000","palette:2":"#808080","palette:3":"#ffffff"}"##.utf8)
    let sequence = try ColorArrangementIndex(svg: ##"<svg><path fill="#000000"/><path style="stroke:#808080"/><stop stop-color="#fff"/></svg>"##,
        colorMap: colors, workID: "swift-color-parity")
    // Fixed outputs observed from Server color_arrangements.py, independently of Swift ranking.
    let expected = [["#000000":"#808080", "#808080":"#000000", "#ffffff":"#ffffff"],
                    ["#000000":"#ffffff", "#808080":"#808080", "#ffffff":"#000000"],
                    ["#000000":"#808080", "#808080":"#ffffff", "#ffffff":"#000000"],
                    ["#000000":"#000000", "#808080":"#ffffff", "#ffffff":"#808080"],
                    ["#000000":"#ffffff", "#808080":"#000000", "#ffffff":"#808080"]]
    guard sequence.total == 5 else { throw CheckFailure.message("Color assignment count is not P(3,3)-1") }
    for (index, assignment) in expected.enumerated() {
        guard try sequence.substitution(at: UInt64(index)) == assignment else { throw CheckFailure.message("Color spread differs from Server") }
    }
    let previous = Data(##"{"palette:1":"#000000","palette:2":"#808080","palette:3":"#ffffff","recolor:#000000":"#808080","recolor:#808080":"#ffffff"}"##.utf8)
    let composed = try ExactJSON(data: sequence.colorMap(previous, at: 0))
    guard composed["recolor:#000000"].string == nil, composed["recolor:#808080"].string == "#ffffff",
          composed["recolor:#ffffff"].string == nil else { throw CheckFailure.message("Recolor was cascaded instead of composed once") }

    let transport = SavedVariantNoProvider()
    let app = AppModel(databaseURL: url, transport: transport)
    await app.initialize()
    app.language = "ja"; app.seedText = "42"
    let ddl = "カンバス。\n背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな円を1個置く。"
    guard await app.drawNewDDL(ddl), let parent = app.selectedWork else { throw CheckFailure.message("Variant parent failed: \(app.errorText ?? app.status)") }
    let db = try InkuDatabase(url: url)
    let context = try await app.savedConfiguration(workID: parent.id)
    let score = try ExactJSON(data: Data(parent.score.utf8))
    app.descriptionText = "UNRELATED_DESCRIPTION_DRAFT"
    app.ddlText = "UNRELATED_DDL_DRAFT"; app.setDdlBoxText(app.ddlText, for: parent)
    app.sketchText = "UNRELATED_SKETCH_DRAFT"
    let ground = SavedScoreVariantModel(work: parent, kind: .ground)
    await ground.initialize(app: app)
    guard ground.errorText == nil, ground.failures.isEmpty, ground.candidates.count == 6 else {
        throw CheckFailure.message("Expected six support options: \(ground.errorText ?? ground.failures.joined(separator: "; "))")
    }
    guard ground.candidates.compactMap { $0.plan.ground?.value } == ["paper", "washi", "ink_wash", "charcoal_ground", "drawing_paper", "mezzotint"] else {
        throw CheckFailure.message("Ground order differs from Saijiki")
    }
    for candidate in ground.candidates {
        var changed = try ExactJSON(data: Data(candidate.work.score.utf8))
        guard changed["canvas"]["ground"]["material"].string == candidate.plan.ground?.value else { throw CheckFailure.message("Ground option names another material") }
        changed["canvas"]["ground"]["material"] = score["canvas"]["ground"]["material"]
        guard changed == score, candidate.work.renderColorMap == parent.renderColorMap,
              candidate.work.ddl?.components(separatedBy: "\n").dropFirst().joined(separator: "\n") == ddl.components(separatedBy: "\n").dropFirst().joined(separator: "\n") else {
            throw CheckFailure.message("Ground changed another Score field or DDL sentence")
        }
        try sameSavedFacts(candidate.work, parent)
    }
    let firstGround = ground.candidates[0]
    ground.preview(firstGround.id)
    guard ground.selectedCount == 0 else { throw CheckFailure.message("Ground preview selected the option") }
    ground.selectCandidate(firstGround.id, selected: true); ground.preview(nil)
    guard ground.selectedCount == 1 else { throw CheckFailure.message("Returning to grid lost ground selection") }
    guard try await db.list().count == 1, await transport.calls == 0 else { throw CheckFailure.message("Preparing options saved or called provider") }
    guard await ground.saveSelected(app: app), let groundChild = try await db.work(id: firstGround.work.id),
          let groundEdge = try await db.edge(childNodeID: groundChild.lineageNodeID!),
          groundEdge.parentNodeID == parent.lineageNodeID, groundEdge.derivationKind == "ground_change",
          groundChild.ddl?.hasPrefix("紙。\n") == true else { throw CheckFailure.message("Ground saved with wrong parent or source") }
    let groundMetadata = try ExactJSON(data: Data(groundEdge.metadataJSON.utf8))
    guard groundMetadata["ground_material"].string == "paper", groundMetadata["parent_ground_material"].string == "canvas" else { throw CheckFailure.message("Ground metadata lost provenance") }

    let color = SavedScoreVariantModel(work: parent, kind: .colorArrangement)
    await color.initialize(app: app)
    guard color.candidates.count == 8, color.errorText == nil, color.failures.isEmpty else { throw CheckFailure.message("Color first page failed: \(color.errorText ?? color.failures.joined(separator: "; "))") }
    let firstPage = color.candidates
    color.preview(firstPage[0].id); color.selectCandidate(firstPage[0].id, selected: true)
    await color.generate(app: app)
    guard color.candidates.count == 8, color.previewID == nil, color.selectedCount == 0,
          color.candidates.compactMap(\.plan.index) == Array(UInt64(8)..<UInt64(16)),
          Set(firstPage.map(\.id)).isDisjoint(with: color.candidates.map(\.id)) else {
        throw CheckFailure.message("Next color page appended, repeated, or kept old selection/preview")
    }
    let reopened = SavedScoreVariantModel(work: parent, kind: .colorArrangement)
    await reopened.initialize(app: app)
    guard reopened.candidates.first?.plan.index == 16 else { throw CheckFailure.message("Reopening reset the work's color cursor") }
    for candidate in firstPage + color.candidates + reopened.candidates {
        guard candidate.work.score == parent.score, candidate.work.ddl == parent.ddl,
              candidate.work.renderColorMap != parent.renderColorMap else { throw CheckFailure.message("Color option changed instructions/Score or kept identity map") }
        try sameSavedFacts(candidate.work, parent)
    }
    let picked = color.candidates[0]
    color.selectCandidate(picked.id, selected: true)
    guard await color.saveSelected(app: app), let colorChild = try await db.work(id: picked.work.id),
          let colorEdge = try await db.edge(childNodeID: colorChild.lineageNodeID!),
          colorEdge.parentNodeID == parent.lineageNodeID, colorEdge.derivationKind == "color_arrangement_change" else {
        throw CheckFailure.message("Color saved the wrong lineage")
    }
    guard try ExactJSON(data: Data(colorEdge.metadataJSON.utf8))["color_arrangement_index"].number == "8" else { throw CheckFailure.message("Color metadata index changed") }
    let host = PipelineHost(database: db, transport: transport)
    let page = try await host.makeColorArrangementPage(workID: parent.id, cursor: 0)
    let lastPage = try await host.makeColorArrangementPage(workID: parent.id, cursor: page.total - 2)
    let afterLast = try await host.makeColorArrangementPage(workID: parent.id, cursor: page.total)
    guard lastPage.plans.count == 2, lastPage.nextCursor == nil, afterLast.plans.isEmpty, afterLast.nextCursor == nil else {
        throw CheckFailure.message("Color exhaustion repeated or padded its final page")
    }
    for child in [groundChild, colorChild] {
        let replay = try await host.prepareReplayComparison(work: child)
        guard replay.replayedSVG == child.svg else { throw CheckFailure.message("Saved variant cannot replay its exact drawing") }
    }
    _ = try await host.makeColorArrangementPage(workID: colorChild.id, cursor: 0)
    guard try await db.list().count == 3, try await db.work(id: parent.id) == parent,
          try await app.savedConfiguration(workID: parent.id).document == context.document,
          app.descriptionText == "UNRELATED_DESCRIPTION_DRAFT", app.ddlText == "UNRELATED_DDL_DRAFT", await transport.calls == 0 else {
        throw CheckFailure.message("Variants replaced draft/parent or called provider")
    }
    await app.showSavedRefinement(groundChild)
    guard app.selectedWorkID == groundChild.id, app.descriptionText == "UNRELATED_DESCRIPTION_DRAFT",
          app.library.lineageDisplayGraph?.focusNodeID == groundChild.lineageNodeID else { throw CheckFailure.message("Committed option did not focus its lineage or replaced the next description") }

    app.language = "en"
    guard await app.drawNewDDL("Place 1 red circle."), let plain = app.selectedWork else { throw CheckFailure.message("Plain parent failed") }
    let plainGround = SavedScoreVariantModel(work: plain, kind: .ground)
    await plainGround.initialize(app: app)
    guard plainGround.candidates.count == 7, plainGround.candidates.first?.work.ddl?.hasPrefix("Paper.\n") == true else { throw CheckFailure.message("Plain/English ground did not offer seven named supports") }
    print("Saved Score variants PASS: Server's five spread assignments; one-pass recolor composition; 8-option replacement and reopen cursor; 6/7 Saijiki grounds; only ground material changes; seeds/options/input/models preserved; separate preview/selection; selected-only history and correct parent/metadata; exact child replay; parent/drafts unchanged; provider=0. Isolated SQLite only.")
}

private func sameSavedFacts(_ child: SavedWork, _ parent: SavedWork) throws {
    guard child.input == parent.input, child.sourceText == parent.sourceText, child.sketchText == parent.sketchText,
          child.renderSeed == parent.renderSeed, child.compositionSeed == parent.compositionSeed,
          child.renderWild == parent.renderWild, child.renderCanvasAspectID == parent.renderCanvasAspectID,
          child.renderLimits == parent.renderLimits, child.stage1Model == parent.stage1Model, child.stage2Model == parent.stage2Model else {
        throw CheckFailure.message("Saved Score variant changed unrelated facts")
    }
}

private actor SavedVariantNoProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1; throw CheckFailure.message("Saved Score variants must not call a provider")
    }
}

/// Three real saved authority states for read-only GUI acceptance, using a local synthetic interpreter.
@MainActor
func makeRefinementUIFixture(folder: URL) async throws {
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let url = folder.appendingPathComponent("works.sqlite")
    guard !FileManager.default.fileExists(atPath: url.path) else { throw CheckFailure.message("Refusing to overwrite GUI fixture") }
    let app = AppModel(databaseURL: url, transport: RefinementUIProvider())
    await app.initialize()
    let provider = ProviderSettings(id: "check", baseURL: URL(string: "http://127.0.0.1:18885/v1")!, requiresAPIKey: false, label: "Local UI fixture",
        models: ["m1", "m2", "m3"].map { ProviderModelSettings(id: $0) })
    try await app.updateHostSettings(HostSettings(providers: [provider], models: ModelSelection(stage1Model: "check:m1", stage2Model: "check:m1")))
    app.language = "en"; app.seedText = "42"; app.inputMode = "description"
    app.descriptionText = "A red circle, the synthetic description parent."
    await app.generate()
    guard let described = app.selectedWork, app.errorText == nil else { throw CheckFailure.message("GUI description fixture failed") }
    app.ddlText = "Place 1 blue circle."
    await app.commitDDL()
    guard app.errorText == nil, app.selectedWorkID != described.id else { throw CheckFailure.message("GUI locked-description fixture failed") }
    app.language = "ja"
    guard await app.drawNewDDL("カンバス。\n背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな円を1個置く。") else { throw CheckFailure.message("GUI DDL fixture failed") }
    print("GUI fixture ready: three saved works (description, locked description, direct DDL), synthetic transport only; future model options use the named loopback fixture.")
}

private actor RefinementUIProvider: ProviderTransport {
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": input["identity"],
            "response": .string(#"{"normalized_ddl":"Place 1 red circle."}"#), "elapsed_ms": .string("1")]).data
    }
}
