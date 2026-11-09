import Foundation
import CryptoKit
import InkuHost
import InkuPersistence
import InkuUI

@MainActor func runReadAndDrawChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-read-draw-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    for (composed, vision) in [(false, true), (true, true), (false, false)] {
        let provider = ReadAndDrawCheckProvider(composed: composed)
        let app = AppModel(databaseURL: folder.appendingPathComponent("\(composed)-\(vision).sqlite"), transport: provider)
        await app.initialize()
        let model = ProviderModelSettings(id: "fixture", purposes: vision ? ["llm", "vision"] : ["llm"])
        let service = ProviderSettings(id: "fixture", baseURL: URL(string: "https://fixture.invalid")!, requiresAPIKey: false, models: [model])
        try await app.updateHostSettings(HostSettings(providers: [service], models: .init(stage1Model: "fixture:fixture", stage2Model: "fixture:fixture")))
        app.selectNextDrawingModel("fixture:fixture")
        app.inputMode = "description"; app.descriptionText = "🌙 紫の にほへる妹 [大海人皇子] 人妻ゆゑに"; app.language = "ja"; app.seedText = "42"
        app.descriptionComposition = composed
        guard app.drawRoute == "read_and_draw", app.sketchMode == "on" else { throw CheckFailure.message("read and draw defaults") }
        let request = try app.requestForCurrentInput()
        guard request.descriptionReview == vision else { throw CheckFailure.message("Vision review availability") }
        await app.generate()
        let calls = await provider.actions
        let tags = calls.compactMap { $0["tag"].string }
        let expected = composed ? ["read_description", "compose_description", "write_description_ddl", "review_description_ddl", "choose_colors"] : vision ? ["read_description", "write_description_ddl", "review_description_ddl"] : ["read_description", "write_description_ddl"]
        guard tags == expected else { throw CheckFailure.message("read and draw stages: \(tags); \(calls.last?["payload"]["prompt"]["message"].string ?? ""); \(app.errorText ?? app.status)") }
        let firstMessage = try ExactJSON(data: Data((calls[0]["payload"]["prompt"]["message"].string ?? "").utf8))
        guard firstMessage["source_label"].string == "大海人皇子" else { throw CheckFailure.message("Unicode scalar source label") }
        for call in calls {
            let images = call["_transient_images"].array ?? []
            guard call["tag"].string == "review_description_ddl" ? (images.count == 1 && images[0].string?.hasPrefix("data:image/png;base64,") == true) : images.isEmpty else {
                throw CheckFailure.message("only review receives one PNG")
            }
        }
        let events = try ExactJSON(data: Data((await app.outputSnapshot()).events.utf8)).array ?? []
        guard events.contains(where: { $0["tag"].string == "visible_ddl_ready" && $0["payload"]["reason"].string == "description_ddl" }) else { throw CheckFailure.message("description commit reason missing") }
        guard let work = app.selectedWork else { throw CheckFailure.message("read and draw did not save") }
        let context = try await app.savedConfiguration(workID: work.id)
        guard context.drawRoute == "read_and_draw", let data = context.descriptionDDL,
              try ExactJSON(data: data)["reading_text"].string != nil, work.sketchText != nil else { throw CheckFailure.message("read and draw saved record") }
        let database = try InkuDatabase(url: folder.appendingPathComponent("\(composed)-\(vision).sqlite"))
        let before = try await database.work(id: work.id)
        guard let separator = work.id.lastIndex(of: "_"),
              let ack = try await database.acknowledgement(executionID: String(work.id[..<separator]), effectID: "save-render:" + String(work.id[work.id.index(after: separator)...])) else { throw CheckFailure.message("missing saved performance") }
        let performance = try ExactJSON(data: ack)["performance"]
        let expectedElapsed = composed ? "4" : vision ? "3" : "2"
        guard performance["elapsed_read_and_draw_ms"].number == expectedElapsed else { throw CheckFailure.message("read and draw elapsed not saved") }
        await app.selectWork(work)
        guard app.drawRoute == "read_and_draw", app.descriptionComposition == composed,
              try await database.work(id: work.id) == before else { throw CheckFailure.message("opening changed saved work or route") }
        let batch = try app.requestForBatchDescription("紫の にほへる妹", sketchMode: "on")
        let demo = try app.requestForDemoDescription("紫の にほへる妹", sketchMode: "on")
        guard batch.drawRoute == "read_and_draw", batch.descriptionComposition == composed,
              demo.drawRoute == "read_and_draw", demo.descriptionComposition == composed else { throw CheckFailure.message("batch or demo did not capture drawing conditions") }
        app.selectDrawRoute("stages")
        let nextDemo = try app.makeDemoRequest(template: demo, description: "次の作品", randomizeSeed: false)
        guard nextDemo.drawRoute == "read_and_draw", nextDemo.descriptionComposition == composed else { throw CheckFailure.message("demo template did not retain drawing conditions") }
        let stages = try app.requestForCurrentInput(parentWorkID: nil)
        guard stages.drawRoute == nil, stages.descriptionComposition == nil, stages.descriptionReview == nil else { throw CheckFailure.message("legacy stages gained route settings") }
        if composed && vision { try await checkCompositionForm(app: app, work: work, provider: provider, database: database) }
    }
    print("Read and draw: 3/5 fake calls with Vision, 2 without Vision, review PNG, saved reading and route, reopening; no provider calls.")
}

/// Web `generateCompositionFormCandidates` and `save_composition_form`: a candidate of a decided form is drawn unsaved,
/// with the work's sketch, models, catalog and seed, and saving it keeps that execution as the child (no new drawing).
@MainActor private func checkCompositionForm(app: AppModel, work: SavedWork, provider: ReadAndDrawCheckProvider,
                                             database: InkuDatabase) async throws {
    let form = CompositionFormModel(work: work)
    await form.initialize(app: app)
    guard form.contextAvailable, !form.sourceIsLocked, form.currentForm == "one_corner", !form.switchesComposition,
          form.selectedForm == "one_corner" else {
        throw CheckFailure.message("composition form did not open on the work's own form: \(form.errorText ?? "")")
    }
    form.selectedForm = "grid"
    let asked = await provider.actions.count
    let listed = try await database.list().count
    await form.generate(app: app, count: 1)
    let calls = Array(await provider.actions.dropFirst(asked))
    let compose = calls.first { $0["tag"].string == "compose_description" }
    let message = try ExactJSON(data: Data((compose?["payload"]["prompt"]["message"].string ?? "").utf8))
    guard form.candidates.count == 1, form.failures.isEmpty, form.errorText == nil, message["composition_form"].string == "grid",
          try await database.list().count == listed, app.selectedWork?.id == work.id else {
        throw CheckFailure.message("composition form candidate: \(form.failures) \(form.errorText ?? "") \(calls.compactMap { $0["tag"].string })")
    }
    let candidate = form.candidates[0]
    guard candidate.work.renderSeed == work.renderSeed, candidate.work.stage1Model == work.stage1Model,
          candidate.work.sketchText == work.sketchText,
          (candidate.work.renderColorCatalogID ?? candidate.work.catalogID) == (work.renderColorCatalogID ?? work.catalogID) else {
        throw CheckFailure.message("composition form candidate lost the work's seed, model, sketch or catalog")
    }
    form.selectCandidate(candidate.id, selected: true)
    let sent = await provider.actions.count
    guard await form.saveSelected(app: app), let child = form.candidates.first?.savedWork,
          await provider.actions.count == sent, try await database.list().count == listed + 1,
          let node = child.lineageNodeID, let edge = try await database.edge(childNodeID: node),
          edge.derivationKind == "composition_form_change", edge.parentNodeID == work.lineageNodeID else {
        throw CheckFailure.message("composition form save drew again or lost its edge: \(form.errorText ?? form.status)")
    }
    let metadata = try ExactJSON(data: Data(edge.metadataJSON.utf8))
    let context = try await app.savedConfiguration(workID: child.id)
    let record = try context.descriptionDDL.map(ExactJSON.init(data:))
    guard metadata["form_from"].string == "one_corner", metadata["form_to"].string == "grid",
          record?["composition"]["requested_form"].string == "grid", context.drawRoute == "read_and_draw" else {
        throw CheckFailure.message("composition form child record: \(edge.metadataJSON)")
    }
}

private actor ReadAndDrawCheckProvider: ProviderTransport {
    let composed: Bool
    private(set) var actions: [ExactJSON] = []
    init(composed: Bool) { self.composed = composed }
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let value = try ExactJSON(data: action), tag = try value.requiredString("tag")
        captureParityPrompt(value)
        actions.append(value)
        let response: String, result: String
        switch tag {
        case "read_description":
            result = "description_read"
            response = #"{"viewpoint":{"speaker":"我","speaker_quote":"我","eye":"妹の姿を見る。","addressee_quote":"妹","speaker_seen_quote":""},"core":["紫の姿"],"items":[{"kind":"scene","quote":"紫の にほへる妹","image":"紫の円"}],"reading":"紫の姿を読んだ。"}"#
        case "compose_description":
            result = "description_composed"
            // A decided form (the composition-form refinement) is the only one the answer may name.
            let message = try? ExactJSON(data: Data((value["payload"]["prompt"]["message"].string ?? "").utf8))
            let form = message?["composition_form"].string ?? "one_corner"
            response = #"{"thesis":"紫の妹を左上に置く。","form":""# + form + #"","#
                + #""things":[{"thing":1,"what":"妹","role":"focal","kind":"cluster","quote":"妹"},{"thing":2,"what":"紫の影","role":"accent","kind":"cluster","quote":"紫"}],"main_law":"B1","laws":{"B1":{"targets":[{"thing":1,"at":"point_ul"}]}},"reason":"妹を画の中心にする。"}"#
        case "write_description_ddl", "review_description_ddl":
            result = tag == "write_description_ddl" ? "description_ddl_written" : "description_ddl_reviewed"
            response = composed ? #"{"sentences":[{"thing":0,"text":"背景を白で埋める。"},{"thing":1,"text":"画面の横0.381966、縦0.381966の位置に、直径0.3の紫の塗りの円を1個置く。"},{"thing":2,"text":"画面の横0.6、縦0.6の位置に、幅0.2、高さ0.15の青の薄い塗りの三角を1個置く。"}],"figures":[]}"# : #"{"ddl":"赤い円を1個置く。","figures":[]}"#
        case "choose_colors":
            result = "colors_chosen"
            response = #"{"main_law":"C9","laws":{"C9":{"color":"red","layer":1,"area":"15-30","others":"keep"}},"reason":"影を赤くする。"}"#
        default: throw HostError("unexpected_fixture_action")
        }
        return ExactJSON.object(["tag": .string(result), "identity": value["identity"], "response": .string(response), "elapsed_ms": .string("1")]).data
    }
}

/// A work made by the untouched baseline is read and replayed only in its isolated temporary database.
@MainActor func runReadAndDrawBaselineReplay(databaseURL: URL) async throws {
    guard databaseURL.isFileURL, ["/private/tmp/", "/tmp/"].contains(where: { databaseURL.resolvingSymlinksInPath().path.hasPrefix($0) }) else { throw CheckFailure.message("Expected isolated temporary database") }
    let database = try InkuDatabase(url: databaseURL)
    guard let original = try await database.list().first else { throw CheckFailure.message("Baseline work missing") }
    let host = PipelineHost(database: database, credentials: ReadAndDrawReplayCredentials())
    let replay = try await host.replay(workID: original.id)
    guard replay.ddl == original.ddl, replay.score == original.score, replay.svg == original.svg,
          try await database.work(id: original.id) == original else { throw CheckFailure.message("Baseline replay changed DDL, Score, SVG or original") }
    func hash(_ text: String) -> String { SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined() }
    print("Baseline replay unchanged: DDL=\(hash(original.ddl ?? "")) Score=\(hash(original.score)) SVG=\(hash(original.svg)); no provider calls.")
}
private struct ReadAndDrawReplayCredentials: CredentialStore { func key(for credentialID: String) async throws -> String? { nil } }
