import Foundation
import InkuCore
import InkuHost
import InkuPersistence
import Observation

public struct AutonomousRun: Codable, Sendable, Identifiable {
    public var id = UUID().uuidString
    public var sourceID: String
    public var state = "running"
    public var stopReason: String?
    public var moves: Int
    public var kinds: [String]
    public var note: String?
    public var model: String
    public var language: String
    public var wild: Bool?
    private var turnsJSON = Data("[]".utf8)
    private var currentJSON: Data?
    public var turns: [ExactJSON] {
        get { (try? ExactJSON(data: turnsJSON).array) ?? [] }
        set { turnsJSON = ExactJSON.array(newValue).data }
    }
    public var current: ExactJSON? {
        get { currentJSON.flatMap { try? ExactJSON(data: $0) } }
        set { currentJSON = newValue?.data }
    }
    public var pendingChildID: String?
    public var lastKeptID: String?
    public var error: String?
    public var acknowledged: Bool?

    public init(sourceID: String, moves: Int, kinds: [String], note: String?, model: String, language: String, wild: Bool?) {
        self.sourceID = sourceID; self.moves = moves; self.kinds = kinds; self.note = note
        self.model = model; self.language = language; self.wild = wild
    }
}

/// The app owns the task; the sheet only reads it. The core owns all decisions.
@MainActor @Observable
public final class AutonomousRefinementModel {
    public static let kinds = ["laws", "juxtaposition"]
    public var moves = 5
    public var enabledKinds: Set<String> = Set(kinds)
    public var note = "" { didSet { if note.utf16.count > 1000 { note = Self.bounded(note) } } }
    public var modelReference = ""
    public var inheritWild = true
    public var wild = false
    public private(set) var source: SavedWork?
    public private(set) var sourceLocked = false
    public private(set) var run: AutonomousRun?
    public private(set) var children: [String: SavedWork] = [:]
    public private(set) var stopping = false
    public private(set) var errorText: String?
    @ObservationIgnored private var storeURL: URL?
    @ObservationIgnored private var database: InkuDatabase?
    @ObservationIgnored private var runs: [AutonomousRun] = []
    @ObservationIgnored private var operation: Task<Void, Never>?
    @ObservationIgnored private var ownsAppOperation = false
    @ObservationIgnored private var provider: AuxiliaryProvider?
    @ObservationIgnored private var connected = false
    private var starting = false
    public var running: Bool { operation != nil || starting }

    public init(provider: AuxiliaryProvider? = nil) { self.provider = provider }

    public func restore(database: InkuDatabase) async {
        do { try await connect(database: database) } catch { errorText = error.localizedDescription }
    }

    public static func bounded(_ value: String) -> String {
        var result = ""
        for character in value {
            guard result.utf16.count + String(character).utf16.count <= 1000 else { break }
            result.append(character)
        }
        return result
    }

    /// The journal is operational state only; the work's record remains its lineage edge.
    public func connect(database: InkuDatabase) async throws {
        guard !connected else { return }
        self.database = database
        storeURL = database.url.deletingPathExtension().appendingPathExtension("autonomous-runs.json")
        if let storeURL, FileManager.default.fileExists(atPath: storeURL.path) {
            runs = try JSONDecoder().decode([AutonomousRun].self, from: Data(contentsOf: storeURL))
        }
        for index in runs.indices {
            var saved = runs[index]
            if saved.state == "running" {
                // Reconcile the small gap between writing an edge and updating the journal.
                if let id = saved.pendingChildID, let work = try await database.work(id: id),
                   let node = work.lineageNodeID, let edge = try await database.edge(childNodeID: node),
                   let metadata = try? ExactJSON(data: Data(edge.metadataJSON.utf8)),
                   metadata["ai_move"]["run"].string == saved.id,
                   metadata["ai_move"]["outcome"].string == "kept" { saved.lastKeptID = id }
                saved.state = "interrupted"; saved.stopReason = "interrupted"; saved.current = nil
                runs[index] = saved
            }
            if saved.state != "running" { try await promote(saved) }
        }
        try persist()
        connected = true
    }

    public func initialize(app: AppModel, work: SavedWork?) async {
        guard !running else { return }
        do {
            let database = try app.auxiliaryDatabase()
            try await connect(database: database)
            source = work ?? app.selectedWork
            sourceLocked = false
            inheritWild = true; wild = source?.renderWild ?? false
            if let source { sourceLocked = try await app.savedConfiguration(workID: source.id).authority == "ddl_authoritative" }
            let latest = runs.last { $0.sourceID == source?.id }
            run = latest?.state == "interrupted" && latest?.acknowledged != true ? latest : nil
            children = [:]
            if let run {
                for turn in run.turns {
                    for attempt in turn["attempts"].array ?? [] {
                        if let id = attempt["history_id"].string, let child = try await database.work(id: id) { children[id] = child }
                    }
                }
            }
            if let saved = app.display.preferences.autonomousRefine {
                moves = min(10, max(1, saved.moves)); enabledKinds = Set(saved.kinds.filter(Self.kinds.contains)); note = saved.note
            }
            modelReference = AuxiliaryModel.defaultVisionModel(saved: app.display.preferences.visionModelReference, settings: await app.hostSettings())
            if provider == nil { provider = try app.auxiliaryProvider() }
            errorText = nil
        } catch { errorText = error.localizedDescription }
    }

    public func selectModel(_ reference: String, app: AppModel) async throws {
        guard !running, SettingsModel.isRegisteredModelAvailable(reference, purpose: "vision", settings: await app.hostSettings()) else {
            throw HostError("vision_model_not_available")
        }
        modelReference = reference
        app.display.preferences.visionModelReference = reference
    }

    public func remember(app: AppModel) {
        app.display.preferences.autonomousRefine = .init(moves: moves, kinds: Self.kinds.filter(enabledKinds.contains), note: note)
    }

    public func start(app: AppModel) async {
        guard !running, !app.isBusy, connected, let source, !source.trashed, let provider, database != nil else { return }
        starting = true
        defer { starting = false }
        guard !source.svg.isEmpty else { errorText = "autonomous_source_has_no_image"; return }
        let kinds = Self.kinds.filter(enabledKinds.contains)
        guard !kinds.isEmpty else { errorText = "aiRefineKindsError"; return }
        var settings = await app.hostSettings()
        guard !stopping else { stopping = false; return }
        guard SettingsModel.isRegisteredModelAvailable(modelReference, purpose: "vision", settings: settings) else {
            errorText = "vision_model_not_available"; return
        }
        settings.models.stage1Model = modelReference; settings.models.stage2Model = modelReference
        let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
        run = AutonomousRun(sourceID: source.id, moves: min(10, max(1, moves)), kinds: kinds,
            note: trimmed.isEmpty ? nil : trimmed, model: modelReference, language: app.display.preferences.language,
            wild: inheritWild ? nil : wild)
        children = [:]; stopping = false; errorText = nil
        remember(app: app)
        do { try checkpoint() } catch { errorText = error.localizedDescription; run = nil; return }
        let pending = Task { @MainActor [self] in
            var parent = source
            var answers: [Int: Juxtaposition.Result] = [:]
            var session: ChatGPTPlanSession?
            do {
                while let current = run {
                    try Task.checkCancellation()
                    let context = try await app.savedConfiguration(workID: parent.id)
                    let records = try context.lawsRecords.map { try ExactJSON(data: $0) } ?? .object([:])
                    let basis = records["laws_basis"]
                    let main = basis["main_law"].string
                    var names = basis["laws"].object?.keys.sorted() ?? basis["laws"].array?.compactMap { $0.string ?? $0["law"].string } ?? []
                    if let main { names.removeAll { $0 == main }; names.insert(main, at: 0) }
                    var facts: ExactJSON = .object(["description_locked": .bool(context.authority == "ddl_authoritative"),
                        "ddl_work": .bool(context.origin == "user_authored_ddl" || InkuCore.descriptionWithoutLabels(parent.effectiveSourceText).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty),
                        "laws": .array(names.map(ExactJSON.string))])
                    if let main { facts["main_law"] = .string(main) }
                    let next = try await Self.core(.object(["action": .string("next"), "moves": .integer(current.moves),
                        "kinds": .array(current.kinds.map(ExactJSON.string)), "parent": facts,
                        "note": current.note.map(ExactJSON.string) ?? .null, "turns": .array(Self.coreTurns(current.turns))]))
                    try Task.checkCancellation()
                    if let reason = next["stop"]["reason"].string { try await finish(reason: reason, app: app); return }
                    let step = next["next"]
                    run?.current = step; try checkpoint()
                    let kind = try step.requiredString("kind")
                    let turn = try Self.int(step["turn"])
                    var attempt: ExactJSON = .object(["kind": .string(kind), "attempt": step["attempt"]])
                    var moved: ExactJSON = .object([:])
                    var record: ExactJSON = .object([:])
                    do {
                        var request: GenerationRequest
                        if kind == "laws" {
                            request = try await app.makeSavedLawsRequest(work: parent, direction: step["direction"], settings: settings, wild: current.wild)
                        } else {
                            if step["reuse"].bool != true || answers[turn] == nil {
                                let inputs: JuxtapositionInputs
                                let candidates: [ExactJSON]
                                do {
                                    inputs = try await app.juxtapositionInputs(work: parent)
                                    candidates = try Juxtaposition.gather(sources: inputs.sources, description: inputs.description,
                                        lineage: inputs.lineage, added: inputs.added, exclude: step["exclude"].array?.compactMap(\.string) ?? [], seed: UInt64.random(in: .min ... .max))
                                    guard candidates.count >= Juxtaposition.choices else { throw HostError("too_few_candidates") }
                                } catch {
                                    attempt["outcome"] = .string("unavailable"); attempt["reason"] = .string(Self.code(error))
                                    throw AttemptFinished()
                                }
                                guard let png = try await AuxiliaryModel.png(svgs: [parent.svg], visionAdvice: true) else { throw HostError("source_has_no_image") }
                                try Task.checkCancellation()
                                var answer: Juxtaposition.Result?
                                ownsAppOperation = true
                                let ran = await app.performSerialized(status: "一文を選んでいます…", allowsBrowsing: true) { _ in
                                    answer = try await provider.juxtaposition(description: inputs.description, written: inputs.written,
                                        lineage: inputs.lineage, candidates: candidates, png: png, modelReference: current.model,
                                        language: current.language, settings: settings)
                                }
                                ownsAppOperation = false
                                try Task.checkCancellation()
                                guard ran, let answer else { throw HostError("unusable_answer") }
                                answers[turn] = answer
                            }
                            guard let answer = answers[turn], let choice = answer.choices.first(where: { $0.rank == (try? Self.int(step["rank"])) }) else { throw HostError("unusable_answer") }
                            moved = answer.metadata(choice)
                            moved["edited_from_history_id"] = .string(parent.id)
                            var juxtaposition = moved["juxtaposition"]
                            if var fields = juxtaposition.object { fields.removeValue(forKey: "model"); juxtaposition = .object(fields) }
                            record["juxtaposition"] = juxtaposition
                            attempt["sentence"] = .string(choice.sentence); attempt["rank"] = .integer(choice.rank)
                            request = try await app.makeSavedWorkEditRequest(work: parent, mode: .description, description: choice.joined,
                                wildOverride: current.wild, metadata: moved.object ?? [:], drawingSettings: settings)
                        }
                        request.historyVisibility = "lineage_only"
                        if let session, let pinned = request.chatGPTSession, session != pinned { throw HostError("chatgpt_session_changed") }
                        if session == nil { session = request.chatGPTSession }
                        try Task.checkCancellation()
                        ownsAppOperation = true
                        let child = try await app.runAutonomousMove(request: request)
                        ownsAppOperation = false
                        // A saved child is journaled before cancellation is observed or its gate is measured.
                        children[child.id] = child; run?.pendingChildID = child.id; try checkpoint()
                        let measured = try await Self.core(.object(["action": .string("measure"), "before": .string(parent.svg), "after": .string(child.svg)]))
                        let outcome = measured["passes"].bool == true ? "kept" : "not_visible"
                        if kind == "laws" {
                            let childContext = try await app.savedConfiguration(workID: child.id)
                            let childRecords = try childContext.lawsRecords.map { try ExactJSON(data: $0) } ?? .object([:])
                            let basis = childRecords["laws_basis"]
                            guard basis.object != nil else { throw HostError("laws_child_without_basis") }
                            record["laws"] = .object(["main_law": basis["main_law"], "main_layer": basis["main_layer"],
                                "laws": basis["laws"], "reason": basis["reason"], "excluded": step["direction"]["exclude"], "cards": step["direction"]["cards"]])
                            attempt["main_law"] = basis["main_law"]
                        }
                        record["action"] = .string("record"); record["run"] = .string(current.id)
                        record["turn"] = step["turn"]; record["moves"] = .integer(current.moves); record["attempt"] = step["attempt"]
                        record["kind"] = .string(kind); record["model"] = .string(current.model); record["outcome"] = .string(outcome)
                        record["share"] = measured["share"]; record["note"] = current.note.map(ExactJSON.string) ?? .null
                        let recorded = try await Self.core(record)
                        guard let node = child.lineageNodeID, let database else { throw HostError("autonomous_child_without_edge") }
                        var metadata = moved.object ?? [:]
                        metadata.merge(recorded["metadata"].object ?? [:]) { _, new in new }
                        try await database.setLineageEdgeMetadata(childNodeID: node, metadata: ExactJSON.object(metadata).data)
                        attempt["history_id"] = .string(child.id); attempt["lineage_node_id"] = .string(node)
                        attempt["outcome"] = .string(outcome); attempt["share"] = measured["share"]
                        if outcome == "kept" { run?.lastKeptID = child.id; parent = child }
                    } catch is AttemptFinished { }
                    catch is CancellationError { throw CancellationError() }
                    catch {
                        ownsAppOperation = false
                        try Task.checkCancellation()
                        let reason = Self.code(error)
                        if run?.pendingChildID != nil { throw error }
                        attempt["outcome"] = .string(kind == "laws" && !["laws_refused", "laws_compile", "laws_unavailable"].contains(reason) ? "unavailable" : "failed")
                        attempt["reason"] = .string(reason)
                    }
                    while (run?.turns.count ?? 0) < turn { run?.turns.append(.object(["attempts": .array([])])) }
                    if var turns = run?.turns {
                        var attempts = turns[turn - 1]["attempts"].array ?? []
                        attempts.append(attempt); turns[turn - 1]["attempts"] = .array(attempts); run?.turns = turns
                    }
                    run?.current = nil; run?.pendingChildID = nil; try checkpoint()
                }
            } catch is CancellationError {
                do { try await finish(reason: "stopped", app: app) } catch { errorText = error.localizedDescription }
            } catch {
                run?.error = Self.code(error)
                do { try await finish(reason: "failed", app: app) } catch { errorText = error.localizedDescription }
            }
        }
        operation = pending
        await pending.value
        operation = nil; stopping = false; ownsAppOperation = false
    }

    public func stop(app: AppModel) async {
        guard running, !stopping else { return }
        stopping = true; operation?.cancel()
        guard let operation else { return }
        if ownsAppOperation { await app.cancel() }
        await operation.value
    }

    public func openLast(app: AppModel) async {
        guard !running, let id = run?.lastKeptID, let database, let work = try? await database.work(id: id) else { return }
        await app.selectWork(work)
    }

    /// Web reopens a completed work with the controls for a new run. A recovered interruption is shown once.
    public func didClose() {
        guard !running else { return }
        if run?.state == "interrupted" {
            run?.acknowledged = true
            do { try checkpoint() } catch { errorText = error.localizedDescription; return }
        }
        run = nil
    }

    private func finish(reason: String, app: AppModel) async throws {
        run?.stopReason = reason; run?.state = ["stopped", "failed", "interrupted"].contains(reason) ? reason : "done"
        run?.current = nil
        try checkpoint()
        if let run { try await promote(run) }
        await app.refreshWorks()
    }

    private func promote(_ run: AutonomousRun) async throws {
        guard let database, let id = run.lastKeptID, let work = try await database.work(id: id),
              !work.trashed, work.historyVisibility == "lineage_only", let node = work.lineageNodeID else { return }
        try await database.promoteLineageNode(id: node)
    }

    private func checkpoint() throws {
        if let run {
            if let index = runs.firstIndex(where: { $0.id == run.id }) { runs[index] = run } else { runs.append(run) }
        }
        try persist()
    }
    private func persist() throws {
        guard let storeURL else { throw HostError("autonomous_store_unavailable") }
        try JSONEncoder().encode(runs).write(to: storeURL, options: .atomic)
    }
    private struct AttemptFinished: Error { }
    private static func code(_ error: Error) -> String { (error as? HostError)?.code ?? (error is JuxtapositionAnswerError ? "unusable_answer" : "autonomous_failed") }
    private static func int(_ value: ExactJSON) throws -> Int {
        guard let result = value.number.flatMap(Int.init) else { throw HostError("autonomous_core_shape") }
        return result
    }
    private static func coreTurns(_ turns: [ExactJSON]) -> [ExactJSON] {
        turns.map { turn in .object(["attempts": .array((turn["attempts"].array ?? []).map { attempt in
            .object((attempt.object ?? [:]).filter { ["kind", "outcome", "reason", "share", "main_law", "sentence", "rank"].contains($0.key) })
        })]) }
    }
    private static func core(_ request: ExactJSON) async throws -> ExactJSON {
        let answer = try await Task.detached { try ExactJSON(data: InkuCore.autonomousRefine(request.data)) }.value
        guard answer["schema"].string == "inku.autonomous-refine.v1", answer["outcome"].string == "ok" else {
            throw HostError("autonomous_core_" + (answer["reason"].string ?? "invalid_request"))
        }
        return answer
    }
}
