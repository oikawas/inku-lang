import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

/// Failure: touch options borrow a draft, change other Score facts, lose their source or save without adoption.
@MainActor
func runToolChangeChecks(folder: URL) async throws {
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let url = folder.appendingPathComponent("works.sqlite")
    guard !FileManager.default.fileExists(atPath: url.path) else { throw CheckFailure.message("Refusing to overwrite a touch fixture") }
    let transport = ToolChangeNoProvider()
    let app = AppModel(databaseURL: url, transport: transport)
    await app.initialize()
    app.language = "ja"; app.seedText = "42"
    let source = "背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな円を1個置く。"
    guard await app.drawNewDDL(source), let parent = app.selectedWork, parent.ddl == source else {
        throw CheckFailure.message("Touch parent failed: \(app.errorText ?? app.status)")
    }
    let db = try InkuDatabase(url: url)
    let parentContext = try await app.savedConfiguration(workID: parent.id)
    let originalScore = try ExactJSON(data: Data(parent.score.utf8))
    app.descriptionText = "DRAFT_MUST_NOT_REACH_TOUCH_OPTIONS"
    app.ddlText = "DRAFT_MUST_NOT_REACH_TOUCH_OPTIONS"
    app.setDdlBoxText(app.ddlText, for: parent)
    app.sketchText = "DRAFT_MUST_NOT_REACH_TOUCH_OPTIONS"
    let beforeOpening = try await db.listExecutionIDs()
    let change = ToolChangeModel(work: parent)
    guard change.mode == .uniform else { throw CheckFailure.message("Touch mode is not uniform by default") }
    guard change.candidates.isEmpty, !change.hasUnsaved, !change.running,
          try await db.listExecutionIDs() == beforeOpening, try await db.list().count == 1,
          await transport.calls == 0 else { throw CheckFailure.message("Opening drew or saved touch options") }
    await change.generate(app: app)
    guard change.errorText == nil, change.failures.isEmpty, change.candidates.count == 4,
          try await db.list().count == 1 else { throw CheckFailure.message("Button did not draw four private options: \(change.errorText ?? change.failures.joined(separator: "; "))") }
    let uniformCandidates = change.candidates
    let firstIDs = change.candidates.map(\.id)
    guard change.candidates.allSatisfy({ Set($0.plan.tools.values).count == 1 }),
          Set(change.candidates.compactMap { $0.plan.tools.values.first }).count == 4,
          change.candidates.allSatisfy({ !$0.plan.changes.isEmpty }) else {
        throw CheckFailure.message("Uniform options offered duplicates or an unchanged whole")
    }
    change.mode = .perSentence
    change.preview(firstIDs[0])
    guard change.selectedCount == 0 else { throw CheckFailure.message("Touch enlargement adopted its option") }
    change.selectCandidate(firstIDs[0], selected: true)
    guard change.selectedCount == 1 else { throw CheckFailure.message("Prior option could not be selected") }
    await change.generate(app: app)
    guard change.errorText == nil, change.failures.isEmpty, change.candidates.count == 4,
          change.candidates.allSatisfy({ !firstIDs.contains($0.id) }), change.selectedCount == 0, change.previewID == nil,
          change.candidates.map(\.number) == Array(1...4),
          change.candidates.allSatisfy({ $0.plan.mode == .perSentence && $0.plan.changes.count == $0.plan.tools.count && $0.plan.changes.allSatisfy { $0.from != $0.to } }) else {
        throw CheckFailure.message("Second press retained earlier options/selection or reused a sentence's current tool")
    }
    for candidate in uniformCandidates + change.candidates {
        let work = candidate.work
        let score = try ExactJSON(data: Data(work.score.utf8))
        var restored = score
        let oldInstructions = originalScore["instructions"].array ?? []
        let instructions = score["instructions"].array ?? []
        guard instructions.count == oldInstructions.count else { throw CheckFailure.message("Touch changed instruction count") }
        restored["instructions"] = .array(try zip(oldInstructions, instructions).map { original, next in
            var next = next
            let owner = original["arrangement"]["resolved"]["owner"]
            if owner["kind"].string == "source_instruction", let index = owner["instruction_index"].number,
               let wanted = candidate.plan.tools[index] {
                guard next["weight"].string == wanted else { throw CheckFailure.message("Touch missed its source owner") }
                next["weight"] = original["weight"]
            }
            return next
        })
        guard restored == originalScore, work.ddl == candidate.plan.source, work.ddl != parent.ddl,
              work.input == parent.input, work.sourceText == parent.sourceText, work.sketchText == parent.sketchText,
              work.renderSeed == parent.renderSeed, work.compositionSeed == parent.compositionSeed,
              work.renderWild == parent.renderWild, work.renderColorMap == parent.renderColorMap,
              work.renderCanvasAspectID == parent.renderCanvasAspectID, work.renderLimits == parent.renderLimits,
              work.stage1Model == parent.stage1Model, work.stage2Model == parent.stage2Model,
              !work.ddl!.contains("DRAFT_MUST_NOT_REACH_TOUCH_OPTIONS"), !work.svg.isEmpty else {
            throw CheckFailure.message("Touch changed unrelated Score/source/render facts")
        }
        let read = try ExactJSON(data: InkuCore.retouch(ExactJSON.object(["config": try ExactJSON(data: parentContext.configuration),
            "source": .string(work.ddl!), "tools": .object([:])]).data))
        guard read["outcome"].string == "read", read["tools"].array?.count == 12 else {
            throw CheckFailure.message("Touch candidate cannot be read with the parent's saved configuration")
        }
        for sentence in read["sentences"].array ?? [] {
            if let index = sentence["index"].number, let wanted = candidate.plan.tools[index] {
                guard sentence["tool"].string == wanted else { throw CheckFailure.message("DDL disagrees with drawn tool") }
            }
        }
    }
    guard try await db.list().count == 1, try await db.work(id: parent.id) == parent,
          try await app.savedConfiguration(workID: parent.id).document == parentContext.document,
          await transport.calls == 0, app.selectedWorkID == parent.id,
          app.descriptionText == "DRAFT_MUST_NOT_REACH_TOUCH_OPTIONS" else {
        throw CheckFailure.message("Private touch options saved, changed the parent/draft or called an LLM")
    }
    let chosen = change.candidates[0]
    change.selectCandidate(chosen.id, selected: true)
    guard await change.saveSelected(app: app), let saved = try await db.work(id: chosen.work.id),
          try await db.list().count == 2, let edge = try await db.edge(childNodeID: saved.lineageNodeID!),
          edge.parentNodeID == parent.lineageNodeID, edge.derivationKind == "tool_change" else {
        throw CheckFailure.message("Touch adoption lost its saved target or lineage")
    }
    let metadata = try ExactJSON(data: Data(edge.metadataJSON.utf8))
    guard metadata["tool_mode"].string == "per_sentence",
          metadata["tools"] == .object(chosen.plan.tools.mapValues(ExactJSON.string)),
          metadata["changes"].array?.count == chosen.plan.changes.count else { throw CheckFailure.message("Touch metadata lost its assignments") }
    let savedContext = try await app.savedConfiguration(workID: saved.id)
    guard try ExactJSON(data: savedContext.document!)["source"].string == saved.ddl,
          savedContext.renderOptions == parentContext.renderOptions,
          try await db.work(id: parent.id) == parent, await transport.calls == 0 else {
        throw CheckFailure.message("Saved touch child kept the old document or changed the parent options")
    }
    // Failure: the changed Score's acknowledgement still hashes the parent's Score, making later replay fail.
    let host = PipelineHost(database: db, transport: transport)
    _ = try await host.makeSavedScoreReplayPlan(workID: saved.id)
    let descendants = try await host.makeToolVariantPlans(workID: saved.id, mode: .uniform)
    guard descendants.count == 4 else { throw CheckFailure.message("Saved touch child cannot be retouched again") }
    let configuration = try ExactJSON(data: parentContext.configuration)
    let uniformRead = try ExactJSON(data: InkuCore.retouch(ExactJSON.object(["config": configuration,
        "source": .string("赤のペンの円を1個置く。"), "tools": .object([:])]).data))
    guard uniformRead["outcome"].string == "read" else { throw CheckFailure.message("Pen fixture unreadable") }
    guard await app.drawNewDDL("赤のペンの円を1個置く。"), let pen = app.selectedWork else { throw CheckFailure.message("Pen parent failed") }
    let penPlans = try await app.makeToolVariantPlans(work: pen, mode: .uniform)
    guard penPlans.count == 4, penPlans.allSatisfy({ !$0.tools.values.contains("pen") }) else { throw CheckFailure.message("Uniform offers the tool every sentence already has") }
    guard await app.drawNewDDL("背景を白で埋める。"), let background = app.selectedWork else { throw CheckFailure.message("Background parent failed") }
    guard try await app.makeToolVariantPlans(work: background, mode: .uniform).isEmpty,
          await transport.calls == 0 else { throw CheckFailure.message("Unchangeable work offered touch options") }
    try metadata.data.write(to: folder.appendingPathComponent("saved-metadata.json"))
    try Data(saved.ddl!.utf8).write(to: folder.appendingPathComponent("saved.ddl"))
    print("Touch changes PASS: opening=0 with execution/history unchanged; button uniform=4; second press replaces with per_sentence=4, new IDs, prior selection=0 and numbers=1...4; 12 core tools; only owned Score weights change; DDL reads back; parent seeds/colors/ground/options/model/input preserved; draft ignored; preview history=1; selected adoption=2 with tool_change metadata; saved child replay/retouch works; all-pen skips pen; no shape offers no options; provider=0. Isolated SQLite only.")
}

private actor ToolChangeNoProvider: ProviderTransport {
    private(set) var calls = 0
    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        calls += 1
        throw CheckFailure.message("Touch changes must never call an LLM")
    }
}
