import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import InkuUI

/// Failure: the native binding returns a different next move, gate or edge record from the shared table.
func runSharedAutonomousRefineChecks(casesURL: URL) throws {
    let table = try ExactJSON(data: Data(contentsOf: casesURL))
    var count = 0
    for section in ["next", "record", "refused", "invalid", "measure"] {
        guard let rows = table[section].array, !rows.isEmpty else { throw CheckFailure.message("Missing autonomous section \(section)") }
        for row in rows {
            var answer = try ExactJSON(data: InkuCore.autonomousRefine(row["request"].data))
            // The table omits refusal prose; Server's table check also requires and removes it.
            if answer["outcome"].string == "refused" {
                guard answer["detail"].string?.isEmpty == false else { throw CheckFailure.message("Missing refusal detail") }
                if var fields = answer.object { fields.removeValue(forKey: "detail"); answer = .object(fields) }
            }
            guard answer == row["answer"] else {
                throw CheckFailure.message("Shared autonomous \(section): \(row["why"].string ?? ""): \(answer.text), expected \(row["answer"].text)")
            }
            count += 1
        }
    }
    print("Shared autonomous refinement passed: \(count) next/record/refused/invalid/measure rows through UniFFI")
}

/// Failure: saved_laws drops the parent's colors stage or sends Stage 1 / composition again.
@MainActor
func runSavedLawsStageChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-saved-laws-stages-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let service = ProviderSettings(id: "laws-check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false,
        models: [.init(id: "parent"), .init(id: "pinned")])
    let drawing = HostSettings(providers: [service], models: .init(stage1Model: "laws-check:pinned", stage2Model: "laws-check:pinned"))
    let next = try ExactJSON(data: InkuCore.autonomousRefine(ExactJSON.object([
        "action": .string("next"), "moves": .integer(1), "kinds": .array([.string("laws")]),
        "parent": .object(["description_locked": .bool(false), "ddl_work": .bool(false), "laws": .array([])])
    ]).data))
    guard next["next"]["kind"].string == "laws" else { throw CheckFailure.message("Missing laws step: \(next.text)") }
    for hasColors in [false, true] {
        let transport = LawsColorsCheckProvider(refuseColors: true)
        let app = AppModel(databaseURL: folder.appendingPathComponent("colors-\(hasColors).sqlite"), transport: transport)
        await app.initialize()
        try await app.updateHostSettings(HostSettings(providers: [service], models: .init(stage1Model: "laws-check:parent", stage2Model: "laws-check:parent")))
        app.inputMode = "description"; app.language = "ja"; app.seedText = "7"; app.sketchMode = "off"
        app.descriptionText = "円がひとつ浮かび、下に点が散らばる"
        var parentRequest = try app.requestForCurrentInput()
        var config = try ExactJSON(data: parentRequest.configuration)
        // A composed parent without laws records can take its first laws move without excluding the fixture's law.
        if var fields = config.object {
            fields.removeValue(forKey: "laws")
            if !hasColors { fields.removeValue(forKey: "colors") }
            config = .object(fields)
        }
        parentRequest.configuration = config.data
        guard let parent = await app.runAutomation(request: parentRequest) else {
            throw CheckFailure.message("Saved laws stage parent: \(app.errorText ?? app.status)")
        }
        let saved = try await app.savedConfiguration(workID: parent.id)
        let savedColors = try ExactJSON(data: saved.configuration)["colors"]
        guard (savedColors != .null) == hasColors else { throw CheckFailure.message("Parent colors fixture was not saved") }
        let request = try await app.makeSavedLawsRequest(work: parent, direction: next["next"]["direction"], settings: drawing, wild: nil)
        guard try ExactJSON(data: request.configuration)["colors"] == savedColors else {
            throw CheckFailure.message("The saved_laws request changed the parent's colors configuration")
        }
        // Keep the parent's original colors, so the child's D5 answer is still an available choice.
        await transport.allowColors()
        let sentBefore = await transport.actions.count
        _ = try await app.runAutonomousMove(request: request)
        let sent = await transport.actions.dropFirst(sentBefore).map { $0["tag"].string ?? "" }
        let selectedModels = await transport.selectedModels.dropFirst(sentBefore).map { $0 }
        let expected = hasColors ? ["choose_laws", "choose_colors"] : ["choose_laws"]
        guard sent == expected,
              selectedModels == Array(repeating: "laws-check:pinned", count: expected.count) else {
            let corrections = await transport.actions.dropFirst(sentBefore).filter { $0["tag"].string == "choose_colors" }
                .map { String(($0["payload"]["prompt"]["message"].string ?? "").suffix(900)) }
            throw CheckFailure.message("Saved laws colors=\(hasColors): sent \(sent), expected \(expected); Stage 1 and composition must not be sent again; colors prompts: \(corrections)")
        }
        print("Saved laws colors=\(hasColors): \(sent); parent colors preserved, chosen model pinned, no Stage 1 or composition request")
    }
    print("Saved laws stages passed: both saved-configuration branches through the macOS request helper and real core. Fake provider and temporary SQLite only.")
}

/// Failure: a move uses the old Vision path, loses its record, promotes a rejected child, or fails to recover.
@MainActor
func runAuxiliaryProvenanceChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-autonomous-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("works.sqlite")
    let transport = AutonomousCheckProvider()
    let app = AppModel(databaseURL: databaseURL, transport: transport)
    await app.initialize()
    let service = ProviderSettings(id: "auto-check", baseURL: URL(string: "http://127.0.0.1:1/v1")!, requiresAPIKey: false,
        models: [.init(id: "parent"), .init(id: "one", purposes: ["llm", "vision"])])
    try await app.updateHostSettings(HostSettings(providers: [service], models: .init(stage1Model: "auto-check:parent", stage2Model: "auto-check:parent")))
    let database = try app.auxiliaryDatabase()
    app.inputMode = "description"; app.language = "ja"; app.seedText = "7"; app.sketchMode = "off"

    func parent(_ text: String) async throws -> SavedWork {
        app.descriptionText = text
        var request = try app.requestForCurrentInput()
        // A legacy composed parent lets saved_laws choose its first law without an exclusion.
        var config = try ExactJSON(data: request.configuration)
        if var fields = config.object { fields.removeValue(forKey: "laws"); fields.removeValue(forKey: "colors"); config = .object(fields) }
        request.configuration = config.data
        guard let work = await app.runAutomation(request: request) else { throw CheckFailure.message("Autonomous fixture: \(app.errorText ?? app.status)") }
        return work
    }
    let first = try await parent("円がひとつ浮かび、下に点が散らばる")
    let before = try await app.savedConfiguration(workID: first.id)
    let runner = AutonomousRefinementModel(provider: AuxiliaryProvider(transport: transport, credentials: AutonomousCheckCredentials()))
    await runner.initialize(app: app, work: first)
    runner.moves = 1; runner.enabledKinds = ["laws"]; runner.modelReference = "auto-check:one"; runner.note = "  余白を動かす  "
    await runner.start(app: app)
    guard let lawsRun = runner.run, lawsRun.stopReason == "moves_done", lawsRun.error == nil,
          let keptID = lawsRun.lastKeptID, let kept = try await database.work(id: keptID),
          kept.historyVisibility == "normal", let keptNode = kept.lineageNodeID,
          let lawsEdge = try await database.edge(childNodeID: keptNode), lawsEdge.derivationKind == "laws_change",
          lawsEdge.parentNodeID == first.lineageNodeID else {
        throw CheckFailure.message("Laws move: \(runner.run?.stopReason ?? "nil") / \(runner.run?.error ?? runner.errorText ?? "nil") / \(runner.run?.turns.map(\.text) ?? [])")
    }
    let lawsMetadata = try ExactJSON(data: Data(lawsEdge.metadataJSON.utf8))
    let lawsContext = try await app.savedConfiguration(workID: keptID)
    guard lawsContext.authority == "ddl_authoritative",
          let lawsRecords = try lawsContext.lawsRecords.map(ExactJSON.init(data:)),
          lawsRecords["laws_basis"].object?["main_layer"] == ExactJSON.null,
          lawsMetadata["ai_move"]["laws"].object?["main_layer"] == ExactJSON.null,
          lawsMetadata["ai_move"]["kind"].string == "laws", lawsMetadata["ai_move"]["outcome"].string == "kept",
          lawsMetadata["ai_move"]["model"].string == "auto-check:one", lawsMetadata["ai_move"]["note"].string == "余白を動かす",
          lawsMetadata["autonomous_refine_mode"] == .null,
          await transport.lawsModels == ["auto-check:one"],
          try await database.work(id: first.id) == first,
          try await app.savedConfiguration(workID: first.id).configuration == before.configuration else {
        throw CheckFailure.message("Laws child lost saved_laws authority, basis/null main_layer, run record or pinned model: \(lawsMetadata.text)")
    }

    // Juxtaposition uses other normal works, then the same one model draws its child.
    for text in ["夜の港に灯台が立つ。", "古い駅に時計が残る。", "森の奥で水が光る。", "遠い街で窓が開く。", "雪の庭に足跡が続く。", "秋の川に橋が架かる。"] { _ = try await parent(text) }
    await transport.changeDrawing(true)
    runner.inheritWild = false
    await runner.initialize(app: app, work: first)
    guard runner.run == nil, runner.moves == 1, runner.enabledKinds == ["laws"], runner.note == "  余白を動かす  ", runner.inheritWild else {
        throw CheckFailure.message("Reopening a finished run must restore choices and offer a new run, with wild inherited")
    }
    runner.moves = 1; runner.enabledKinds = ["juxtaposition"]; runner.note = ""
    await runner.start(app: app)
    guard let juxtaposeRun = runner.run, juxtaposeRun.stopReason == "moves_done", juxtaposeRun.error == nil,
          let childID = juxtaposeRun.lastKeptID, let child = try await database.work(id: childID),
          child.historyVisibility == "normal", let childNode = child.lineageNodeID,
          let edge = try await database.edge(childNodeID: childNode), edge.derivationKind == "description_edit" else {
        throw CheckFailure.message("Juxtaposition move: \(runner.run?.error ?? runner.errorText ?? "nil") / \(runner.run?.turns.map(\.text) ?? [])")
    }
    let moved = try ExactJSON(data: Data(edge.metadataJSON.utf8))
    guard moved["ai_move"]["kind"].string == "juxtaposition", moved["ai_move"]["outcome"].string == "kept",
          moved["juxtaposition"]["sentence"].string != nil, moved["juxtaposition"]["model"].string == "auto-check:one",
          moved["edited_from_history_id"].string == first.id,
          child.effectiveSourceText.hasPrefix(first.effectiveSourceText),
          await transport.auxiliaryModels == ["auto-check:one"], await transport.lastDrawingModel == "auto-check:one" else {
        throw CheckFailure.message("Juxtaposition child lost its sentence, ai_move or model: \(moved.text)")
    }
    // An identical draw stays only in the lineage and never becomes the next parent.
    await runner.initialize(app: app, work: child)
    runner.moves = 1; runner.enabledKinds = ["juxtaposition"]
    await runner.start(app: app)
    guard runner.run?.lastKeptID == nil, !runner.children.isEmpty else { throw CheckFailure.message("Identical draw fixture: \(runner.run?.turns.map(\.text) ?? []) / \(runner.run?.error ?? "nil")") }
    for generated in runner.children.values {
        guard try await database.work(id: generated.id)?.historyVisibility == "lineage_only",
              let node = generated.lineageNodeID, let edge = try await database.edge(childNodeID: node),
              edge.parentNodeID == childNode,
              try ExactJSON(data: Data(edge.metadataJSON.utf8))["ai_move"]["outcome"].string == "not_visible" else {
            throw CheckFailure.message("Not-visible child was promoted or became a parent")
        }
    }

    // The second laws request waits, so stop and crash recovery both have a kept, still-hidden first child.
    await transport.changeDrawing(false)
    await transport.pauseLaws(after: 1)
    await runner.initialize(app: app, work: first)
    runner.moves = 2; runner.enabledKinds = ["laws"]
    let task = Task { await runner.start(app: app) }
    let deadline = ContinuousClock.now.advanced(by: .seconds(10))
    while !(await transport.waiting) && ContinuousClock.now < deadline { try await Task.sleep(for: .milliseconds(10)) }
    guard await transport.waiting, let interrupted = runner.run, let last = interrupted.lastKeptID,
          try await database.work(id: last)?.historyVisibility == "lineage_only" else {
        task.cancel(); await runner.stop(app: app)
        throw CheckFailure.message("Stop fixture never reached a second laws request: \(runner.run?.error ?? "nil")")
    }
    runner.didClose()
    await runner.initialize(app: app, work: first)
    await runner.start(app: app)
    guard runner.running, runner.run?.id == interrupted.id else {
        throw CheckFailure.message("Closing/reopening the sheet cancelled or replaced the active run")
    }
    let recoveredURL = folder.appendingPathComponent("recovered.sqlite")
    try await database.backup(to: recoveredURL)
    try JSONEncoder().encode([interrupted]).write(to: recoveredURL.deletingPathExtension().appendingPathExtension("autonomous-runs.json"), options: .atomic)
    let recoveredDatabase = try InkuDatabase(url: recoveredURL)
    let recovered = AutonomousRefinementModel()
    try await recovered.connect(database: recoveredDatabase)
    let recoveryJournal = try JSONDecoder().decode([AutonomousRun].self, from: Data(contentsOf: recoveredURL.deletingPathExtension().appendingPathExtension("autonomous-runs.json")))
    guard recoveryJournal.first?.stopReason == "interrupted", try await recoveredDatabase.work(id: last)?.historyVisibility == "normal" else {
        throw CheckFailure.message("Interrupted run did not promote its last kept child")
    }
    await runner.stop(app: app); await task.value
    guard runner.run?.stopReason == "stopped", !runner.running, !app.isBusy,
          try await database.work(id: last)?.historyVisibility == "normal" else {
        throw CheckFailure.message("Stopped run did not cancel and promote its last kept child")
    }
    print("Autonomous host passed: saved_laws + laws_change + basis + ai_move with explicit null main_layer through the run's record; juxtaposition + description_edit + both records; one pinned model; invisible children stay lineage-only and never parent; stop cancels, restart interrupts, both promote last kept. Fake providers and temporary SQLite only.")
}

private actor AutonomousCheckCredentials: CredentialStore {
    func key(for credentialID: String) -> String? { nil }
}

private actor AutonomousCheckProvider: ProviderTransport, AuxiliaryTransport {
    let base = LawsColorsCheckProvider(refuseColors: true)
    private var changed = false
    private var lawsCount = 0
    private var pauseAfter: Int?
    private(set) var waiting = false
    private(set) var lawsModels: [String] = []
    private(set) var auxiliaryModels: [String] = []
    private(set) var lastDrawingModel = ""
    func changeDrawing(_ value: Bool) { changed = value }
    func pauseLaws(after count: Int) { pauseAfter = count; lawsCount = 0 }

    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        if input["tag"].string == "choose_laws" {
            lawsCount += 1; lawsModels.append(models.stage1Model)
            if let pauseAfter, lawsCount > pauseAfter {
                waiting = true
                defer { waiting = false }
                try await Task.sleep(for: .seconds(30))
            }
        }
        lastDrawingModel = models.stage1Model
        var answer = try ExactJSON(data: await base.perform(action: action, models: models, providers: providers, credentials: credentials, onBytes: onBytes))
        if input["tag"].string == "generate_normalized_ddl", let response = answer["response"].string {
            let large = response.replacingOccurrences(of: "\"size\":\"small\"", with: "\"size\":\"large\"")
            answer["response"] = .string(changed ? large.replacingOccurrences(of: "circle", with: "square").replacingOccurrences(of: "red", with: "blue") : large)
        }
        return answer.data
    }
    func performAuxiliary(prompt: AuxiliaryPrompt, modelReference: String, settings: HostSettings,
                          credentials: any CredentialStore, onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        auxiliaryModels.append(modelReference)
        let ids = prompt.message.split(separator: "\n").compactMap { line -> String? in
            guard line.hasPrefix("c"), let colon = line.firstIndex(of: "：") else { return nil }
            return String(line[..<colon])
        }
        return ExactJSON.object(["choices": .array(ids.prefix(4).map { .object(["id": .string($0), "reason": .string("理由 \($0)")]) })]).text
    }
}
