import Foundation
import CryptoKit
import InkuCore
import InkuPersistence

/// Coordinates independent executions. Each driver serializes its own core and SQLite mutations.
public actor PipelineHost {
    public nonisolated let database: InkuDatabase
    private let transport: any ProviderTransport
    private let credentials: any CredentialStore
    private var executions: [String: ExecutionDriver] = [:]
    public init(database: InkuDatabase, transport: any ProviderTransport = URLSessionProviderTransport(),
                credentials: any CredentialStore = KeychainCredentialStore()) {
        self.database = database; self.transport = transport; self.credentials = credentials
    }

    public func generate(_ request: GenerationRequest, progress: @escaping PipelineProgressHandler = { _ in }) async throws -> PipelineView {
        let report = try ExactJSON(data: Data(InkuCore.versionReport.utf8))
        guard report["binding_version"].string == "1.1.0", report["protocol_version"].string == "1.0.0" else { throw HostError("binding_protocol_mismatch") }
        let driver = try ExecutionDriver(request: request, database: database, transport: transport, credentials: credentials)
        let started = try await driver.start(progress: progress)
        executions[started.executionID] = driver
        return try await withTaskCancellationHandler {
            try await driver.drive(progress: progress)
        } onCancel: {
            Task { _ = try? await driver.cancel(progress: progress) }
        }
    }

    public func perform(executionID: String, command: PipelineCommand, progress: @escaping PipelineProgressHandler = { _ in }) async throws -> PipelineView {
        let driver = try await execution(executionID)
        return try await withTaskCancellationHandler {
            try await driver.perform(command, progress: progress)
        } onCancel: {
            Task { _ = try? await driver.cancel(progress: progress) }
        }
    }
    public func cancel(executionID: String) async throws -> PipelineView {
        try await execution(executionID).cancel(progress: { _ in })
    }

    /// Restore is read-only: an unfinished paid call is never automatically repeated.
    public func restore(executionID: String) async throws -> PipelineView { try await execution(executionID).view() }

    /// An explicit resume finishes durable local effects only; provider work stays stopped.
    public func resume(executionID: String, progress: @escaping PipelineProgressHandler = { _ in }) async throws -> PipelineView {
        try await execution(executionID).resume(progress: progress)
    }

    /// Restores stored Score and SVG without starting a new performance.
    public func restoreSavedWork(workID: String) async throws -> SavedWork {
        guard let work = try await database.work(id: workID) else { throw HostError("work_not_found") }
        return work
    }

    /// Draws the saved Score with its attested policies and saves one new lineage child.
    public func replay(workID: String, renderSeed: String? = nil, wild: Bool? = nil) async throws -> SavedWork {
        let began = Date()
        let source = try await restoreSavedWork(workID: workID)
        let location = try WorkIdentity.location(workID)
        guard let acknowledgement = try await database.acknowledgement(executionID: location.executionID, effectID: location.effectID) else { throw HostError("saved_performance_context_unavailable") }
        let ack = try ExactJSON(data: acknowledgement)
        guard ack["work_id"].string == workID, let parentNodeID = source.lineageNodeID,
              let parentNode = try await database.node(id: parentNodeID) else { throw HostError("saved_performance_context_invalid") }
        let context = try ack.requiredObject("performance")
        let request = try SavedPerformance.renderRequest(work: source, context: context, renderSeed: renderSeed, wild: wild)
        try Task.checkCancellation()
        let rendered = try ExactJSON(data: InkuCore.renderSaved(request.data))
        if let code = rendered["error"].string { throw HostError(code) }
        let svg = try rendered.requiredString("svg")
        try Task.checkCancellation()
        let executionID = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        let id = WorkIdentity.savedID(executionID: executionID, sequence: "0")
        let nodeID = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        var work = source
        work.id = id; work.at = now; work.svg = svg; work.lineageNodeID = nodeID
        work.elapsedMS = max(0, Int64(Date().timeIntervalSince(began) * 1000))
        work.starred = false; work.trashed = false; work.historyVisibility = "normal"
        let options = request["request"]["options"]
        work.renderSeed = options["render_seed"].number ?? options["render_seed"].string
        work.renderWild = options["wild"].bool
        work.renderEngineID = rendered["metadata"]["render_engine_id"].string
        work.renderEngineVersion = rendered["metadata"]["render_engine_version"].string
        work.renderHash = WorkIdentity.render(score: request["request"]["score"], options: options, metadata: rendered["metadata"])
        let node = LineageNode(id: nodeID, historyID: id, at: now, descriptionHash: work.descriptionHash,
                               renderHash: work.renderHash, rootNodeID: parentNode.rootNodeID ?? parentNode.id)
        let edge = LineageEdge(id: UUID().uuidString, parentNodeID: parentNodeID, childNodeID: nodeID,
                               derivationKind: "render_seed_change", at: now)
        var nextContext = context
        var stringOptions = options
        for key in ["render_seed", "composition_seed"] { if let number = options[key].number { stringOptions[key] = .string(number) } }
        nextContext["options"] = stringOptions
        let initial = ExactJSON.object(["schema": .string("inku.swift-saved-performance-execution.v1"), "source_work_id": .string(workID), "request": request, "phase": .string("rendered")])
        let execution = try await database.compareAndSwapExecution(id: executionID, expectedRevision: nil, snapshot: initial.data)
        let completed = ExactJSON.object(["schema": .string("inku.swift-saved-performance-execution.v1"), "source_work_id": .string(workID), "saved_work_id": .string(id), "phase": .string("completed")])
        _ = try await database.commitEffect(id: executionID, expectedRevision: execution.revision, effectID: "save-render:0", snapshot: completed.data,
                                            acknowledgement: SavedPerformance.acknowledgement(workID: id, context: nextContext), work: work, node: node, edge: edge)
        return work
    }

    public func cancelAll() async throws {
        for driver in executions.values { _ = try await driver.cancel(progress: { _ in }) }
    }

    private func execution(_ id: String) async throws -> ExecutionDriver {
        if let current = executions[id] { return current }
        guard let record = try await database.loadExecution(id: id) else { throw HostError("execution_not_found") }
        // Another reentrant load may already have installed the current actor.
        if let current = executions[id] { return current }
        let driver = try ExecutionDriver(record: record, database: database, transport: transport, credentials: credentials)
        executions[id] = driver; return driver
    }
}

private struct StoredExecution: Codable, Sendable {
    var schema = "inku.swift-pipeline-execution.v1"
    var snapshot: Data
    var rendered: Data?
    var events: Data = Data("[]".utf8)
    var models: ModelSelection
    var providers: [ProviderSettings]
    var renderOptions: Data
    var clipPolicy: Data
    var renderColorMaps: [String: Data]
    var description: String
    var parentWorkID: String?
    var derivationKind: String
    var pendingProviderAction: Data?
    var savedWorkID: String?
    var startedAt: Date
}

private actor AsyncGate {
    private var locked = false
    private var waiters: [CheckedContinuation<Void, Never>] = []
    func lock() async {
        if locked { await withCheckedContinuation { waiters.append($0) } }
        else { locked = true }
    }
    func unlock() {
        if waiters.isEmpty { locked = false }
        else { waiters.removeFirst().resume() }
    }
}

private actor ExecutionDriver {
    let database: InkuDatabase
    let transport: any ProviderTransport
    let credentials: any CredentialStore
    let gate = AsyncGate()
    var state: StoredExecution
    var databaseRevision: Int64?
    var snapshot: ExactJSON
    var initialRequest: GenerationRequest?
    var providerTask: Task<Data, Error>?
    var driving = false
    var restored = false
    let maximumEffectSteps = 32

    init(request: GenerationRequest, database: InkuDatabase, transport: any ProviderTransport, credentials: any CredentialStore) throws {
        guard try ExactJSON(data: request.configuration).object != nil,
              try ExactJSON(data: request.renderOptions).object != nil,
              try ExactJSON(data: request.clipPolicy).object != nil else { throw HostError("invalid_pipeline_configuration") }
        self.database = database; self.transport = transport; self.credentials = credentials
        self.state = StoredExecution(snapshot: Data(), models: request.models, providers: request.providers,
                                     renderOptions: request.renderOptions, clipPolicy: request.clipPolicy,
                                     renderColorMaps: request.renderColorMaps,
                                     description: request.description, parentWorkID: request.parentWorkID,
                                     derivationKind: request.derivationKind, startedAt: Date())
        self.snapshot = .null; self.initialRequest = request
    }
    init(record: ExecutionSnapshot, database: InkuDatabase, transport: any ProviderTransport, credentials: any CredentialStore) throws {
        let stored = try JSONDecoder().decode(StoredExecution.self, from: record.snapshot)
        guard stored.schema == "inku.swift-pipeline-execution.v1" else { throw HostError("stored_execution_invalid") }
        let snapshot = try ExactJSON(data: stored.snapshot)
        guard snapshot["execution_id"].string == record.id else { throw HostError("stored_execution_invalid") }
        self.database = database; self.transport = transport; self.credentials = credentials
        self.state = stored; self.snapshot = snapshot; self.databaseRevision = record.revision; self.restored = true
    }

    func start(progress: PipelineProgressHandler) async throws -> PipelineView {
        await gate.lock(); defer { Task { await gate.unlock() } }
        guard let request = initialRequest else { throw HostError("execution_already_started") }
        let payload: ExactJSON = .object(["tag": .string("start"), "variation_id": .string(newID()), "authoring_nonce": .string(newID()),
                                         "config": try ExactJSON(data: request.configuration),
                                         "authority": .object(["protocol_version": .string("inku.variation-authority.v1"), "revision": .string("0"),
                                                                "origin": .string(request.authoring.isDirect ? "user_authored_ddl" : "stage1_generated"),
                                                                "authority": .string(request.authoring.isDirect ? "ddl_authoritative" : "description_authoritative")]),
                                         "authoring": request.authoring.json])
        let next = try coreStep(payload)
        let id = try next.snapshot.requiredString("execution_id")
        let saved = try await database.compareAndSwapExecution(id: id, expectedRevision: nil, snapshot: encoded(next.state))
        adopt(next, revision: saved.revision)
        initialRequest = nil
        let result = try makeView(); progress(.changed(result)); return result
    }

    func view() async throws -> PipelineView {
        await gate.lock(); defer { Task { await gate.unlock() } }
        return try makeView()
    }

    func perform(_ command: PipelineCommand, progress: @escaping PipelineProgressHandler) async throws -> PipelineView {
        if case .cancel = command { return try await cancel(progress: progress) }
        await gate.lock()
        do {
            guard !(restored && snapshot["action"].object != nil) else { throw HostError("interrupted_execution_requires_cancel") }
            guard providerTask == nil else { throw HostError("provider_effect_in_flight") }
            restored = false
            let oldDescription = state.description
            if case .generateFromDescription(_, let text, _, _) = command { state.description = text }
            do { try await advance(command.payload()) }
            catch { state.description = oldDescription; throw error }
            progress(.changed(try makeView()))
            await gate.unlock()
        } catch { await gate.unlock(); throw error }
        return try await drive(progress: progress)
    }

    func cancel(progress: PipelineProgressHandler) async throws -> PipelineView {
        await gate.lock(); defer { Task { await gate.unlock() } }
        providerTask?.cancel()
        if !["completed", "needs_user_edit", "failed", "cancelled"].contains(snapshot["phase"]["tag"].string ?? "") {
            try await advance(.object(["tag": .string("cancel")]), clearProvider: true)
        }
        let result = try makeView(); progress(.changed(result)); return result
    }

    func resume(progress: @escaping PipelineProgressHandler) async throws -> PipelineView {
        await gate.lock()
        guard providerTask == nil, state.pendingProviderAction == nil else {
            await gate.unlock(); throw HostError("interrupted_execution_requires_cancel")
        }
        restored = false
        await gate.unlock()
        return try await drive(progress: progress, allowProvider: false)
    }

    func drive(progress: @escaping PipelineProgressHandler, allowProvider: Bool = true) async throws -> PipelineView {
        await gate.lock()
        if driving || restored {
            let result = try makeView(); await gate.unlock(); return result
        }
        driving = true; await gate.unlock()
        do {
            for _ in 0..<maximumEffectSteps {
                try Task.checkCancellation()
                await gate.lock()
                let action = snapshot["action"]
                if action.object == nil {
                    do {
                        if snapshot["phase"]["tag"].string == "score_ready" {
                            try await advance(.object(["tag": .string("render"), "options": try renderOptionsForDelivery(), "clip": try ExactJSON(data: state.clipPolicy)]))
                            progress(.changed(try makeView()))
                        }
                        if state.rendered != nil && state.savedWorkID == nil { try await saveRendered(progress: progress) }
                        let result = try makeView(); driving = false
                        await gate.unlock(); return result
                    } catch { await gate.unlock(); throw error }
                }
                guard let tag = action["tag"].string else { await gate.unlock(); throw HostError("pipeline_schema_violation") }
                if tag == "commit_visible_normalized_ddl" {
                    do { try await commitVisibleDDL(action); progress(.changed(try makeView())); await gate.unlock() }
                    catch { await gate.unlock(); throw error }
                } else if ["generate_sketch", "select_description_catalog", "generate_normalized_ddl", "complete_visible_ddl_holes"].contains(tag) {
                    if !allowProvider {
                        restored = true; driving = false
                        do {
                            let result = try makeView(); progress(.changed(result)); await gate.unlock(); return result
                        } catch { await gate.unlock(); throw error }
                    }
                    let task: Task<Data, Error>
                    do {
                        guard providerTask == nil, state.pendingProviderAction == nil else { throw HostError("provider_effect_in_flight") }
                        // Persist the send claim before starting transport; restore can never infer a safe resend.
                        var claimed = state; claimed.pendingProviderAction = action.data
                        let record = try await database.compareAndSwapExecution(id: executionID(), expectedRevision: databaseRevision, snapshot: encoded(claimed))
                        state = claimed; databaseRevision = record.revision
                        let began = Date()
                        let delayMS = try canonicalUnsigned(action, key: "delay_ms")
                        let timeoutMS = try canonicalUnsigned(action, key: "timeout_ms")
                        progress(.providerAttempt(executionID: try executionID(), report: InkuCore.providerAttempt(snapshot: state.snapshot), beganAt: began,
                                                  deadline: began.addingTimeInterval(Double(delayMS) / 1000 + Double(timeoutMS) / 1000)))
                        let bytes = action.data; let models = state.models; let providers = state.providers
                        let id = try executionID(); let transport = self.transport; let credentials = self.credentials
                        task = Task {
                            if delayMS > 0 {
                                guard delayMS <= UInt64.max / 1_000_000 else { throw HostError("pipeline_schema_violation") }
                                try await Task.sleep(nanoseconds: delayMS * 1_000_000)
                            }
                            try Task.checkCancellation()
                            return try await transport.perform(action: bytes, models: models, providers: providers, credentials: credentials,
                                                               onBytes: { count in progress(.transportBytes(executionID: id, count: count)) })
                        }
                        providerTask = task; await gate.unlock()
                    } catch { await gate.unlock(); throw error }
                    let response: Data
                    do { response = try await task.value }
                    catch {
                        await gate.lock(); providerTask = nil
                        // A cancel invalidates the old action, including a late or failed provider response.
                        if snapshot["action"] != action {
                            do {
                                let result = try makeView(); driving = false; await gate.unlock(); return result
                            } catch { await gate.unlock(); throw error }
                        }
                        await gate.unlock(); throw error
                    }
                    await gate.lock(); providerTask = nil
                    do {
                        if snapshot["action"] == action {
                            try await advance(.object(["tag": .string("effect_result"), "result": try ExactJSON(data: response)]), clearProvider: true)
                            progress(.changed(try makeView()))
                        }
                        await gate.unlock()
                    } catch { await gate.unlock(); throw error }
                } else { await gate.unlock(); throw HostError("unsupported_pipeline_effect") }
            }
            throw HostError("pipeline_effect_limit")
        } catch {
            await gate.lock(); driving = false; await gate.unlock()
            throw error
        }
    }

    private struct NextState { let state: StoredExecution; let snapshot: ExactJSON }
    private func coreStep(_ payload: ExactJSON, clearProvider: Bool = false) throws -> NextState {
        var payload = payload; payload["version"] = .integer(1)
        let messageID = newID()
        let current = snapshot.object == nil ? nil : snapshot
        let sequence = try current.map { try nextDecimal($0.requiredString("sequence")) } ?? "0"
        let envelope: ExactJSON = .object(["protocol": .string("inku.pipeline"), "version": .string("1.0.0"), "kind": .string("input"),
                                          "execution_id": .string(try current?.requiredString("execution_id") ?? "new"), "sequence": .string(sequence),
                                          "message_id": .string(messageID), "payload": payload])
        let config = current?["config"] ?? payload["config"]
        let limits = try config.requiredObject("envelope_limits")
        try within(state.snapshot.count, limit: limits["max_snapshot_bytes"])
        try within(envelope.data.count, limit: limits["max_input_bytes"])
        let bytes = InkuCore.step(snapshot: state.snapshot, input: envelope.data)
        try within(bytes.count, limit: limits["max_output_bytes"])
        let output = try ExactJSON(data: bytes)
        guard output["protocol"].string == "inku.pipeline", output["version"].string == "1.0.0" else { throw HostError("pipeline_protocol_mismatch") }
        if output["kind"].string == "error" { throw HostError(output["payload"]["code"].string ?? "pipeline_error") }
        guard output["kind"].string == "output", output["message_id"].string == messageID,
              output["payload"]["tag"].string == "step_result", output["payload"]["version"].number == "1" else { throw HostError("pipeline_schema_violation") }
        let result = try output.requiredObject("payload").requiredObject("result")
        let nextSnapshot = try result.requiredObject("snapshot")
        if let current { guard nextSnapshot["execution_id"] == current["execution_id"] else { throw HostError("pipeline_execution_identity_changed") } }
        try within(nextSnapshot.data.count, limit: limits["max_snapshot_bytes"])
        guard result["events"].array != nil else { throw HostError("pipeline_schema_violation") }
        var next = state; next.snapshot = nextSnapshot.data; next.events = result["events"].data
        if result["rendered"].object != nil { next.rendered = result["rendered"].data; next.savedWorkID = nil }
        else if current?["document"] != nextSnapshot["document"] || nextSnapshot["delivery"].object == nil {
            next.rendered = nil; next.savedWorkID = nil
        }
        if clearProvider { next.pendingProviderAction = nil }
        return NextState(state: next, snapshot: nextSnapshot)
    }
    private func advance(_ payload: ExactJSON, clearProvider: Bool = false) async throws {
        let next = try coreStep(payload, clearProvider: clearProvider)
        let record = try await database.compareAndSwapExecution(id: executionID(), expectedRevision: databaseRevision, snapshot: encoded(next.state))
        adopt(next, revision: record.revision)
    }
    private func adopt(_ next: NextState, revision: Int64) { state = next.state; snapshot = next.snapshot; databaseRevision = revision }
    private func encoded(_ value: StoredExecution) throws -> Data { let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]; return try encoder.encode(value) }

    private func commitVisibleDDL(_ action: ExactJSON) async throws {
        let payload = try action.requiredObject("payload")
        let authority = try payload.requiredObject("authority")
        guard authority["expected_revision"] == snapshot["authority"]["revision"],
              payload["variation_id"] == snapshot["variation_id"] else { throw HostError("authority_conflict") }
        let acknowledgement: ExactJSON = .object(["tag": .string("visible_normalized_ddl_committed"), "identity": action["identity"],
                                                  "ddl_digest": payload["ddl_digest"], "revision": authority["next_state"]["revision"], "authority_digest": payload["authority_digest"]])
        let next = try coreStep(.object(["tag": .string("effect_result"), "result": acknowledgement]))
        guard let revision = databaseRevision else { throw HostError("execution_not_started") }
        let committed = try await database.commitEffect(id: executionID(), expectedRevision: revision,
                                                       effectID: action["identity"].requiredString("action_id"), snapshot: encoded(next.state), acknowledgement: acknowledgement.data)
        adopt(next, revision: committed.execution.revision)
    }

    private func renderOptionsForDelivery() throws -> ExactJSON {
        var options = try ExactJSON(data: state.renderOptions)
        let compiler = try snapshot.requiredObject("delivery").requiredObject("compiler_options")
        let host = try compiler.requiredObject("host")
        // Auto catalog selection changes the resolved compiler host. Its palette stays authoritative.
        let catalog = try host.requiredString("resolved_catalog_id")
        if options["catalog_id"].string != catalog {
            guard let bytes = state.renderColorMaps[catalog] else { throw HostError("resolved_catalog_render_map_required") }
            let map = try ExactJSON(data: bytes)
            guard map.object != nil else { throw HostError("resolved_catalog_render_map_required") }
            options["resolved_color_map"] = map
        }
        options["catalog_id"] = .string(catalog)
        options["canvas_aspect_id"] = host["canvas_format_id"]
        options["composition_seed"] = compiler["composition_seed"]
        options["error_policy"] = compiler["error_policy"]
        return options
    }

    private func saveRendered(progress: PipelineProgressHandler) async throws {
        guard let renderedBytes = state.rendered, let revision = databaseRevision else { throw HostError("render_not_ready") }
        let rendered = try ExactJSON(data: renderedBytes)
        let svg = try rendered.requiredString("svg")
        let delivery = try snapshot.requiredObject("delivery")
        let score = try delivery.requiredObject("score")
        let options = try renderOptionsForDelivery()
        let metadata = rendered["metadata"]
        let id = WorkIdentity.savedID(executionID: try executionID(), sequence: try snapshot.requiredString("sequence"))
        let nodeID = newID(); let now = Int64(Date().timeIntervalSince1970 * 1000)
        let renderHash = WorkIdentity.render(score: score, options: options, metadata: metadata)
        let descriptionHash = WorkIdentity.description(state.description)
        let compiler = delivery["compiler_options"]
        let compositionSeed = score["composition_seed"].string ?? score["composition_seed"].number ?? compiler["composition_seed"].string
        let renderSeed = options["render_seed"].string ?? compiler["host"]["palette"]["render_seed"].string
        let work = SavedWork(id: id, at: now, input: state.description, score: score.text, svg: svg,
                             sourceText: state.description, ddl: snapshot["document"]["source"].string,
                             elapsedMS: max(0, Int64(Date().timeIntervalSince(state.startedAt) * 1000)),
                             stage1Model: state.models.stage1Model.isEmpty ? nil : state.models.stage1Model,
                             stage2Model: state.models.stage2Model.isEmpty ? nil : state.models.stage2Model,
                             catalogID: options["catalog_id"].string, renderEngineID: metadata["render_engine_id"].string,
                             renderEngineVersion: metadata["render_engine_version"].string,
                             renderColorCatalogID: options["catalog_id"].string,
                             renderColorProfile: ExactJSON.object(["id": .string("srgb"), "name": .string("sRGB IEC61966-2.1"), "standard": .string("IEC 61966-2-1:1999")]).text,
                             renderColorMap: options["resolved_color_map"].text,
                             renderCanvasAspect: options["canvas_aspect_id"].string,
                             renderCanvasAspectID: options["canvas_aspect_id"].string,
                             renderCanvasAspectRatio: canvasRatio(options),
                             renderSeed: renderSeed, renderWild: options["wild"].bool, compositionSeed: compositionSeed,
                             variationAmplitude: compiler["stage15_variation"]["amplitude"].string,
                             variationSeed: compiler["stage15_variation"]["seed"].string,
                             instructionLangResolved: snapshot["config"]["language"].string,
                             sketchText: snapshot["sketch"]["text"].string, sketchState: snapshot["sketch"]["state"].string,
                             renderLimits: legacyRenderLimits(compiler["operational_resource_budget"]),
                             renderHash: renderHash, descriptionHash: descriptionHash, lineageNodeID: nodeID)
        var edge: LineageEdge?
        var rootNodeID = nodeID
        if let parentID = state.parentWorkID {
            guard let parent = try await database.work(id: parentID), let parentNodeID = parent.lineageNodeID,
                  let parentNode = try await database.node(id: parentNodeID) else { throw HostError("lineage_parent_unavailable") }
            rootNodeID = parentNode.rootNodeID ?? parentNode.id
            edge = LineageEdge(id: newID(), parentNodeID: parentNodeID, childNodeID: nodeID, derivationKind: state.derivationKind, at: now)
        }
        let node = LineageNode(id: nodeID, historyID: id, at: now, descriptionHash: descriptionHash, renderHash: renderHash, rootNodeID: rootNodeID)
        var savedState = state; savedState.savedWorkID = id
        let effectID = "save-render:" + (try snapshot.requiredString("sequence"))
        let performance = SavedPerformance.context(score: score, options: options, compiler: compiler, clip: try ExactJSON(data: state.clipPolicy))
        let acknowledgement = SavedPerformance.acknowledgement(workID: id, context: performance)
        let committed = try await database.commitEffect(id: executionID(), expectedRevision: revision, effectID: effectID,
                                                       snapshot: encoded(savedState), acknowledgement: acknowledgement, work: work, node: node, edge: edge)
        state = savedState; databaseRevision = committed.execution.revision
        progress(.saved(executionID: try executionID(), workID: id)); progress(.changed(try makeView()))
    }

    private func makeView() throws -> PipelineView {
        let rendered = try state.rendered.map { try ExactJSON(data: $0) }
        let phase = try snapshot.requiredObject("phase").requiredString("tag")
        return PipelineView(executionID: try executionID(), variationID: try snapshot.requiredString("variation_id"),
                            sequence: try snapshot.requiredString("sequence"), revision: try snapshot["authority"].requiredString("revision"), phase: phase,
                            authority: try snapshot["authority"].requiredString("authority"), origin: try snapshot["authority"].requiredString("origin"),
                            visibleDDL: snapshot["document"]["source"].string,
                            scoreJSON: snapshot["delivery"]["score"].object == nil ? nil : snapshot["delivery"]["score"].data,
                            renderedJSON: state.rendered, svg: rendered?["svg"].string, savedWorkID: state.savedWorkID,
                            patchProposalJSON: phase == "awaiting_patch_approval" ? snapshot["phase"].data : nil,
                            eventsJSON: state.events, busy: snapshot["action"].object != nil || providerTask != nil,
                            interruptedProvider: restored && snapshot["action"].object != nil,
                            description: state.description)
    }
    private func executionID() throws -> String { try snapshot.requiredString("execution_id") }
    private func canonicalUnsigned(_ value: ExactJSON, key: String) throws -> UInt64 {
        let text = try value.requiredString(key)
        guard let number = UInt64(text), String(number) == text else { throw HostError("pipeline_schema_violation") }
        return number
    }
    private func nextDecimal(_ value: String) throws -> String {
        guard let number = UInt64(value), String(number) == value, number < UInt64.max else { throw HostError("sequence_exhausted") }
        return String(number + 1)
    }
    private func within(_ count: Int, limit: ExactJSON) throws {
        guard let maximum = limit.number.flatMap(Int.init), maximum > 0 else { throw HostError("invalid_pipeline_limits") }
        guard count <= maximum else { throw HostError("transport_size_limit") }
    }
    private func canvasRatio(_ options: ExactJSON) -> Double? {
        guard let width = options["canvas"]["width"].number.flatMap(Double.init),
              let height = options["canvas"]["height"].number.flatMap(Double.init),
              width.isFinite, height.isFinite, width > 0, height > 0 else { return nil }
        return width / height
    }
    private func legacyRenderLimits(_ budget: ExactJSON) -> String? {
        let maximum = budget["maximum"]
        guard maximum.object != nil else { return nil }
        return ExactJSON.object(["max_expanded_primitives": maximum["primitive_marks"],
                                 "max_expanded_per_instruction": maximum["maximum_per_template_primitive_marks"],
                                 "schema_count_max": maximum["maximum_resolved_count"],
                                 "max_instructions": maximum["object_templates"]]).text
    }
    private func newID() -> String { UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased() }
}
