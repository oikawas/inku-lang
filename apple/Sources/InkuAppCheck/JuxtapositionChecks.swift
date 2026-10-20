import Foundation
import InkuHost
import InkuPersistence
import InkuUI

/// Failure: the requests this host builds for the shared core (the field names, the seed as a decimal string, the
/// resend) are not what the core reads, so it answers `invalid_request` or not what Server and Web answered.
/// `server/tests/data/juxtaposition-cases.json`; its `same`, `join`, `first_sentence` and `language` rows are the core's
/// own functions, which macOS does not ask for.
func runSharedJuxtapositionChecks(casesURL: URL) throws {
    let table = try ExactJSON(data: Data(contentsOf: casesURL))
    func strings(_ value: ExactJSON) -> [String] { value.array?.compactMap(\.string) ?? [] }
    func number(_ value: ExactJSON) -> Int? { value.number.flatMap { Int($0) } }
    let gathers = table["gather"].array ?? [], checks = table["check"].array ?? [], prompts = table["prompt"].array ?? []
    guard gathers.count == 5, checks.count == 8, prompts.count == 2 else {
        throw CheckFailure.message("Shared juxtaposition table changed: \(gathers.count)/\(checks.count)/\(prompts.count)")
    }
    for row in gathers {
        let request = row["request"]
        let sources = (request["sources"].array ?? []).map { (id: $0["id"].string ?? "", text: $0["text"].string ?? "") }
        func gather(_ limit: Int) throws -> [ExactJSON] {
            try Juxtaposition.gather(sources: sources, description: request["description"].string ?? "",
                lineage: strings(request["lineage"]), added: strings(request["added"]), exclude: strings(request["exclude"]),
                seed: 7, limit: limit)
        }
        guard let limit = number(request["limit"]), let count = number(row["count"]) else {
            throw CheckFailure.message("Shared gather row lacks its limit or count")
        }
        let drawn = try gather(limit)
        guard drawn.count == count, drawn.allSatisfy({ $0["history_ids"] == row["kept"][$0["sentence"].string ?? ""] }) else {
            throw CheckFailure.message("Shared gather differs (\(row["why"].string ?? "")): \(drawn.map(\.text))")
        }
        let everything = try gather(10_000)
        let kept = ExactJSON.object(Dictionary(everything.map { ($0["sentence"].string ?? "", $0["history_ids"]) }) { first, _ in first })
        guard everything.count == row["kept"].object?.count, kept == row["kept"] else {
            throw CheckFailure.message("Shared gather keeps other sentences (\(row["why"].string ?? "")): \(kept.text)")
        }
    }
    for row in checks {
        let request = row["request"]
        let checked = try Juxtaposition.check(language: request["language"].string ?? "", answer: request["answer"].string ?? "",
                                              candidates: request["candidates"].array ?? [], description: request["description"].string ?? "")
        switch checked {
        case .choices(let choices, let candidates):
            let expected = row["choices"].array ?? []
            let same = expected.count == choices.count && candidates == request["candidates"].array?.count
                && zip(choices, expected).allSatisfy { choice, item in
                    choice.sentence == item["sentence"].string && choice.reason == item["reason"].string
                        && choice.historyIDs == strings(item["history_ids"]) && choice.rank == number(item["rank"])
                        && choice.position.number.flatMap(Double.init) == item["position"].number.flatMap(Double.init)
                        && choice.joined == item["joined"].string
                }
            guard same else { throw CheckFailure.message("Shared check differs (\(row["why"].string ?? "")): \(choices)") }
        case .refused(_, let detail):
            guard row["choices"] == .null, detail == row["detail"].string else {
                throw CheckFailure.message("Shared check refusal differs (\(row["why"].string ?? "")): \(detail)")
            }
        }
    }
    for row in prompts {
        let request = row["request"]
        let prompt = try Juxtaposition.prompt(language: request["language"].string ?? "", description: request["description"].string ?? "",
            lineage: strings(request["lineage"]), candidates: request["candidates"].array ?? [], resend: request["resend"].string)
        guard prompt.system == row["system"].string, prompt.text == row["text"].string else {
            throw CheckFailure.message("Shared prompt differs (\(row["why"].string ?? ""))")
        }
    }
    print("Shared juxtaposition: \(gathers.count) gather, \(checks.count) check and \(prompts.count) prompt rows through the host's requests")
}

@MainActor
func runJuxtapositionChecks() async throws {
    try juxtapositionSourceChecks()
    try await juxtapositionStoreChecks()
    try await juxtapositionResendChecks()
    try await juxtapositionChildChecks()
    print("Juxtaposition: sources, store, resend and child record checks passed")
}

/// Failure: a labelled (DDL, demo), `test data`, DDL-held, unsaved-authority or empty work, or the work itself, lends
/// a sentence (Server `owned_description_sources` and `api_juxtaposition`).
private func juxtapositionSourceChecks() throws {
    let open = SavedAuthoringSummary(authority: "description_authoritative", origin: "stage1_generated")
    let rows: [(id: String, text: String, note: String?)] = [
        ("keep", "1. 夜の港。", "a note"), ("ddl", "1. 夜の港。", nil), ("demo", "1. 夜の港。", nil),
        ("test", "1. 夜の港。", "Test Data (AI)"), ("held", "1. 夜の港。", nil), ("unsaved", "1. 夜の港。", nil),
        ("current", "1. 夜の港。", nil), ("empty", " \n", nil)]
    let summaries = Dictionary(uniqueKeysWithValues: ["keep", "ddl", "demo", "test", "current", "empty"].map { ($0, open) })
        .merging(["held": SavedAuthoringSummary(authority: "ddl_authoritative", origin: "stage1_generated")]) { first, _ in first }
    let sources = AppModel.juxtapositionSources(rows: rows, labels: ["keep": "#3", "ddl": "DDL", "demo": "[demo]"],
                                                summaries: summaries, excluding: "current")
    guard sources.map(\.id) == ["keep"], sources.map(\.text) == ["夜の港。"] else {
        throw CheckFailure.message("Juxtaposition sources keep \(sources)")
    }
}

/// Failure: a work in the trash or kept only in a lineage lends a sentence, or the comment does not reach the filter.
private func juxtapositionStoreChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-juxtaposition-store-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let database = try InkuDatabase(url: folder.appendingPathComponent("works.sqlite"))
    let works = [SavedWork(id: "shown", at: 1, input: "input text", score: "{}", svg: "<svg/>", sourceText: "1. 夜の港。", lineageNodeID: "shown-node"),
                 SavedWork(id: "trashed", at: 2, input: "trashed text", score: "{}", svg: "<svg/>", trashed: true, lineageNodeID: "trashed-node"),
                 SavedWork(id: "lineage", at: 3, input: "lineage text", score: "{}", svg: "<svg/>", historyVisibility: "lineage",
                           lineageNodeID: "lineage-node"),
                 SavedWork(id: "plain", at: 4, input: "plain input", score: "{}", svg: "<svg/>", lineageNodeID: "plain-node")]
    for work in works { try await database.save(work, node: LineageNode(id: work.lineageNodeID!, historyID: work.id, at: work.at)) }
    try await database.setAnnotation(id: "shown", note: "test data")
    let rows = try await database.juxtapositionSources()
    guard rows.map(\.id) == ["shown", "plain"], rows.map(\.text) == ["1. 夜の港。", "plain input"],
          rows.map(\.note) == ["test data", nil] else {
        throw CheckFailure.message("Juxtaposition store rows \(rows)")
    }
}

/// Failure: an answer naming a sentence that was not offered is used, is not sent back with why, or is sent back more
/// than once; or the request leaves its image, temperature or budget behind (Server `suggest_juxtaposition`).
private func juxtapositionResendChecks() async throws {
    let sources = (1...6).map { (id: "w\($0)", text: "一文\($0)。続き。") }
    let candidates = try Juxtaposition.gather(sources: sources, description: "今の記述。", lineage: [], added: [], exclude: [], seed: 1)
    let ids = candidates.compactMap { $0["id"].string }
    guard ids.count == 6 else { throw CheckFailure.message("Juxtaposition fixture gathered \(ids)") }
    func answer(_ named: [String]) -> String {
        ExactJSON.object(["choices": .array(named.enumerated().map { .object(["id": .string($1), "reason": .string("理由\($0 + 1)")]) })]).text
    }
    let png = Data([137, 80, 78, 71, 13, 10, 26, 10, 0])
    let settings = HostSettings(providers: [], models: ModelSelection(stage1Model: "check:generation", stage2Model: "check:generation"))
    let picked = [ids[2], ids[0], ids[5], ids[1]]
    let resent = JuxtapositionVision(answers: [answer(["c9999"] + picked.prefix(3)), answer(picked)])
    let result = try await AuxiliaryProvider(transport: resent, credentials: JuxtapositionCredentials()).juxtaposition(
        description: "今の記述。", written: "1. 今の記述。", lineage: [], candidates: candidates, png: png,
        modelReference: "check:vision", language: "ja", settings: settings)
    let prompts = await resent.prompts
    let sentence = { (id: String) in candidates.first { $0["id"].string == id }?["sentence"].string ?? "" }
    guard prompts.count == 2, !prompts[0].message.contains("前の答えについて"),
          prompts[1].message.contains("前の答えは使えなかった：候補に無い番号（c9999。"),
          prompts.allSatisfy({ $0.images.count == 1 && $0.images[0].hasPrefix("data:image/png;base64,")
              && $0.temperature == 0.35 && $0.maximumTokens == 1200 }),
          result.choices.map(\.sentence) == picked.map(sentence), result.choices.map(\.rank) == [1, 2, 3, 4],
          result.choices.map(\.joined) == picked.map { "1. 今の記述。" + sentence($0) },
          result.choices.map(\.historyIDs) == picked.map { id in candidates.first { $0["id"].string == id }?["history_ids"].array?.compactMap(\.string) ?? [] },
          result.candidates == 6, result.model == "check:vision" else {
        throw CheckFailure.message("Juxtaposition resend: \(prompts.count) prompts, \(result)")
    }
    let repeated = JuxtapositionVision(answers: [answer(Array(repeating: ids[0], count: 4)), answer(Array(repeating: ids[0], count: 4))])
    do {
        _ = try await AuxiliaryProvider(transport: repeated, credentials: JuxtapositionCredentials()).juxtaposition(
            description: "今の記述。", written: "今の記述。", lineage: [], candidates: candidates, png: png,
            modelReference: "check:vision", language: "ja", settings: settings)
        throw CheckFailure.message("Juxtaposition used an answer that named one sentence four times")
    } catch let error as JuxtapositionAnswerError {
        let count = await repeated.prompts.count
        guard count == 2, error.detail.hasPrefix("同じ番号が2回以上ある") else {
            throw CheckFailure.message("Juxtaposition repeated answer: \(count) prompts, \(error.detail)")
        }
    }
}

/// Failure: the child carries no `juxtaposition` record (so the lineage offers its sentence again), loses the author's
/// labels (drawn from the label-free text), or takes other drawing settings than its parent.
@MainActor
private func juxtapositionChildChecks() async throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("inku-juxtaposition-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let databaseURL = folder.appendingPathComponent("inku.sqlite")
    let transport = JuxtapositionVision(answers: [])
    let app = AppModel(databaseURL: databaseURL, transport: transport)
    await app.initialize()
    let service = ProviderSettings(id: "check", baseURL: URL(string: "http://localhost:1/v1")!, requiresAPIKey: false,
                                   models: [.init(id: "generation"), .init(id: "vision", purposes: ["llm", "vision"])])
    try await app.updateHostSettings(HostSettings(providers: [service],
        models: ModelSelection(stage1Model: "check:generation", stage2Model: "check:generation")))
    app.inputMode = "description"; app.seedText = "42"
    for text in ["1. 夜の港で、灯台の光だけが揺れていた。", "雪原を渡るオオカミの群れ。", "廃駅のホームに時刻表だけが残った。",
                 "満月の塩田は一面の鏡になった。", "古い井戸の底で、空が小さく光っていた。"] {
        app.descriptionText = text
        app.wild = text.hasPrefix("1.")
        await app.generate()
        guard app.errorText == nil, app.selectedWork != nil else {
            throw CheckFailure.message("Juxtaposition fixture did not draw: \(app.errorText ?? app.status)")
        }
    }
    let reopened = AppModel(databaseURL: databaseURL, transport: transport)
    await reopened.initialize()
    let database = try InkuDatabase(url: databaseURL)
    guard let parent = try await database.list(limit: 10).first(where: { $0.effectiveSourceText.hasPrefix("1.") }) else {
        throw CheckFailure.message("Juxtaposition fixture lost its labelled parent")
    }
    await reopened.selectWork(parent)
    let dialog = JuxtaposeModel(work: parent)
    await dialog.initialize(app: reopened)
    dialog.modelReference = "check:vision"
    guard await dialog.ask(app: reopened), let result = dialog.result, result.candidates == 4 else {
        throw CheckFailure.message("Juxtaposition dialog did not offer four: \(dialog.errorText ?? "-")")
    }
    dialog.chosen = 1
    guard let choice = dialog.choice, await dialog.draw(app: reopened) else {
        throw CheckFailure.message("Juxtaposition child was not drawn: \(dialog.errorText ?? reopened.errorText ?? "-")")
    }
    guard let child = try await database.list(limit: 10).first(where: { $0.id != parent.id && $0.effectiveSourceText.contains(choice.sentence) && $0.effectiveSourceText.hasPrefix("1.") }),
          let nodeID = child.lineageNodeID, let branch = try await database.lineage(focusNodeID: nodeID, pathOnly: true),
          let edge = branch.edges.last else {
        throw CheckFailure.message("Juxtaposition child is not in the lineage")
    }
    let metadata = try ExactJSON(data: Data(edge.metadataJSON.utf8))
    let record = metadata["juxtaposition"]
    guard edge.derivationKind == "description_edit", metadata["edited_from_history_id"].string == parent.id,
          record.object.map({ Set($0.keys) }) == ["sentence", "history_ids", "rank", "reason", "position", "candidates", "model"],
          record["sentence"].string == choice.sentence, record["rank"].number == "2", record["candidates"].number == "4",
          record["model"].string == "check:vision", record["history_ids"].array?.compactMap(\.string) == choice.historyIDs,
          child.effectiveSourceText == "1. 夜の港で、灯台の光だけが揺れていた。" + choice.sentence,
          child.renderWild == parent.renderWild, child.renderColorCatalogID == parent.renderColorCatalogID,
          child.renderCanvasAspectID == parent.renderCanvasAspectID else {
        throw CheckFailure.message("Juxtaposition child record: \(edge.derivationKind) \(metadata.text); \(child.effectiveSourceText)")
    }
    // Asking again from the child leaves the added sentence out, though its work still lends it.
    let inputs = try await reopened.juxtapositionInputs(work: child)
    let again = try Juxtaposition.gather(sources: inputs.sources, description: inputs.description, lineage: inputs.lineage,
                                         added: inputs.added, exclude: [], seed: 3)
    guard inputs.added == [choice.sentence], inputs.sources.contains(where: { $0.text == choice.sentence }),
          !again.contains(where: { $0["sentence"].string == choice.sentence }) else {
        throw CheckFailure.message("Juxtaposition offers its added sentence again: \(again.map(\.text))")
    }
}

private actor JuxtapositionCredentials: CredentialStore {
    func key(for credentialID: String) -> String? { nil }
}

/// Drawing answers one red circle, in Japanese like every fixture description; Vision answers what it is given, or
/// the first four ids of the prompt.
private actor JuxtapositionVision: ProviderTransport, AuxiliaryTransport {
    private var answers: [String]
    private(set) var prompts: [AuxiliaryPrompt] = []
    init(answers: [String]) { self.answers = answers }

    func perform(action: Data, models: ModelSelection, providers: [ProviderSettings], credentials: any CredentialStore,
                 onBytes: @escaping @Sendable (Int) -> Void) async throws -> Data {
        let input = try ExactJSON(data: action)
        return ExactJSON.object(["tag": .string("normalized_ddl_generated"), "identity": input["identity"],
            "response": .string(#"{"normalized_ddl":"中心に赤い円を1個置く。"}"#), "elapsed_ms": .string("1")]).data
    }

    func performAuxiliary(prompt: AuxiliaryPrompt, modelReference: String, settings: HostSettings,
                          credentials: any CredentialStore, onBytes: @escaping @Sendable (Int) -> Void) async throws -> String {
        prompts.append(prompt)
        if !answers.isEmpty { return answers.removeFirst() }
        let ids = prompt.message.split(separator: "\n").compactMap { line -> String? in
            guard line.hasPrefix("c"), let colon = line.firstIndex(of: "：") else { return nil }
            return String(line[..<colon])
        }
        return ExactJSON.object(["choices": .array(ids.prefix(4).map { .object(["id": .string($0), "reason": .string("理由 \($0)")]) })]).text
    }
}
