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
    public init(database: InkuDatabase, transport: (any ProviderTransport)? = nil,
                credentials: any CredentialStore = KeychainCredentialStore()) {
        self.database = database
        if let native = transport as? URLSessionProviderTransport { self.transport = native.withRateDatabase(database) }
        else { self.transport = transport ?? URLSessionProviderTransport(database: database) }
        self.credentials = credentials
    }

    public func generate(_ request: GenerationRequest, progress: @escaping PipelineProgressHandler = { _ in }) async throws -> PipelineView {
        let request = try request.normalizedForNewWork()
        if request.captureProviderIO == true, !ProviderObservationPolicy.developerModeEnabled {
            throw HostError("developer_provider_observations_not_available")
        }
        guard ["normal", "lineage_only"].contains(request.historyVisibility) else { throw HostError("invalid_history_visibility") }
        // Server `fork_linked_history`/`fork_description`: a work its edited DDL holds refuses a description that
        // rewords it (`_refuse_if_locked`), while its own description starts a new child (the description fork).
        if !request.authoring.isDirect, let parentID = request.parentWorkID,
           try await savedAuthoringContext(workID: parentID).authority == "ddl_authoritative" {
            guard let parent = try await database.work(id: parentID),
                  !DescriptionLabels.rewords(request.description, parent.effectiveSourceText) else {
                throw HostError("description_source_locked")
            }
        }
        if request.retainedDocument != nil || request.retainedAuthority != nil {
            return try await generateRetained(request, progress: progress)
        }
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

    public func perform(executionID: String, command: PipelineCommand, parentWorkID: String? = nil, derivationKind: String? = nil,
                        derivationMetadata: Data? = nil,
                        progress: @escaping PipelineProgressHandler = { _ in }) async throws -> PipelineView {
        guard derivationKind != "variation" else { throw HostError("variation_retired") }
        let driver = try await execution(executionID)
        return try await withTaskCancellationHandler {
            try await driver.perform(command, parentWorkID: parentWorkID, derivationKind: derivationKind,
                                     derivationMetadata: derivationMetadata, progress: progress)
        } onCancel: {
            Task { _ = try? await driver.cancel(progress: progress) }
        }
    }
    public func cancel(executionID: String) async throws -> PipelineView {
        if let record = try await database.loadExecution(id: executionID),
           let stored = try? JSONDecoder().decode(StandaloneCandidate.self, from: record.snapshot), stored.schema == "inku.swift-candidate.v1" {
            // Pure replay/compilation has already completed; it has no live provider effect to cancel.
            let context = try ExactJSON(data: stored.candidate.context)
            let authority = try context.requiredObject("authority")
            return PipelineView(executionID: executionID, variationID: executionID, sequence: "0",
                revision: try authority.requiredString("revision"), phase: "completed",
                authority: try authority.requiredString("authority"), origin: try authority.requiredString("origin"),
                visibleDDL: stored.candidate.work.ddl, scoreJSON: Data(stored.candidate.work.score.utf8), renderedJSON: nil,
                svg: stored.candidate.work.svg, savedWorkID: stored.saved ? stored.candidate.work.id : nil,
                patchProposalJSON: nil, eventsJSON: Data("[]".utf8), busy: false, interruptedProvider: false,
                description: stored.candidate.work.effectiveSourceText, configurationJSON: context["configuration"].data,
                documentJSON: context["document"].data, deliveryJSON: nil, promptJSON: nil, holeIDs: [], candidateWork: stored.candidate.work,
                providerMetrics: try metrics(in: context))
        }
        return try await execution(executionID).cancel(progress: { _ in })
    }

    /// An explicit editor action can bind a previously unbound execution; an old pin is never replaced.
    public func bindPersonalPlanSession(executionID: String, session: ChatGPTPlanSession) async throws {
        try await execution(executionID).bindPersonalPlanSession(session)
    }
    public func personalPlanContext(executionID: String, stage2: Bool) async throws -> (required: Bool, session: ChatGPTPlanSession?) {
        try await execution(executionID).personalPlanContext(stage2: stage2)
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

    /// Metrics are safe for ordinary presentation. Raw records have a separate developer-only boundary.
    public func providerMetrics(executionID: String) async throws -> [ProviderAttemptMetric] {
        guard let record = try await database.loadExecution(id: executionID) else { throw HostError("execution_not_found") }
        if let stored = try? JSONDecoder().decode(StandaloneCandidate.self, from: record.snapshot) {
            return try metrics(in: ExactJSON(data: stored.candidate.context))
        }
        return try JSONDecoder().decode(StoredMetricRead.self, from: record.snapshot).providerObservations?.map(\.metric) ?? []
    }

    public func savedProviderMetrics(workID: String) async throws -> [ProviderAttemptMetric] {
        try metrics(in: await savedPerformanceContext(workID: workID))
    }

    public func savedWorkPresentation(workID: String) async throws -> SavedWorkPresentation {
        try SavedWorkPresentation(context: await savedPerformanceContext(workID: workID))
    }

    public func providerObservations(executionID: String) async throws -> [ProviderAttemptObservation] {
        guard ProviderObservationPolicy.developerModeEnabled else { throw HostError("developer_provider_observations_not_available") }
        guard let record = try await database.loadExecution(id: executionID) else { throw HostError("execution_not_found") }
        if let stored = try? JSONDecoder().decode(StandaloneCandidate.self, from: record.snapshot) {
            return try await observations(in: ExactJSON(data: stored.candidate.context))
        }
        return try JSONDecoder().decode(StoredExecution.self, from: record.snapshot).providerObservations?.filter { $0.raw != nil } ?? []
    }

    public func savedProviderObservations(workID: String) async throws -> [ProviderAttemptObservation] {
        guard ProviderObservationPolicy.developerModeEnabled else { throw HostError("developer_provider_observations_not_available") }
        return try await observations(in: savedPerformanceContext(workID: workID))
    }

    private func metrics(in context: ExactJSON) throws -> [ProviderAttemptMetric] {
        guard context["provider_metrics"].array != nil else { return [] }
        return try JSONDecoder().decode([ProviderAttemptMetric].self, from: context["provider_metrics"].data)
    }

    private func observations(in context: ExactJSON) async throws -> [ProviderAttemptObservation] {
        guard let executionID = context["provider_observation_execution_id"].string else { return [] }
        let fixed = try metrics(in: context)
        let records = try await providerObservations(executionID: executionID)
        return records.filter { observation in fixed.contains { $0.identity == observation.metric.identity } }
    }

    public func savedAuthoringContext(workID: String) async throws -> SavedAuthoringContext {
        let context = try await savedPerformanceContext(workID: workID)
        guard context["configuration"].object != nil, context["options"].object != nil,
              context["clip"].object != nil, context["authority"].object != nil else {
            throw HostError("saved_authoring_context_unavailable")
        }
        return SavedAuthoringContext(configuration: context["configuration"].data,
            renderOptions: context["options"].data, clipPolicy: context["clip"].data,
            document: context["document"].object == nil ? nil : context["document"].data,
            authority: try context["authority"].requiredString("authority"),
            origin: try context["authority"].requiredString("origin"), revision: try context["authority"].requiredString("revision"), authorityJSON: context["authority"].data)
    }

    public func exportSVG(workID: String, profile: String) async throws -> String {
        guard ["display", "editable", "compat", "live"].contains(profile) else { throw HostError("invalid_svg_profile") }
        let work = try await restoreSavedWork(workID: workID)
        let context = try await savedPerformanceContext(workID: workID)
        var request = try SavedPerformance.renderRequest(work: work, context: context, renderSeed: nil, wild: nil)
        request["request"]["options"]["svg_profile"] = .string(profile)
        try Task.checkCancellation()
        let rendered = try ExactJSON(data: InkuCore.renderSaved(request.data))
        if let code = rendered["error"].string { throw HostError(code) }
        return try rendered.requiredString("svg")
    }

    private func savedPerformanceContext(workID: String) async throws -> ExactJSON {
        let location = try WorkIdentity.location(workID)
        guard let bytes = try await database.acknowledgement(executionID: location.executionID, effectID: location.effectID) else {
            throw HostError("saved_performance_context_unavailable")
        }
        let ack = try ExactJSON(data: bytes)
        guard ack["work_id"].string == workID else { throw HostError("saved_performance_context_invalid") }
        return try ack.requiredObject("performance")
    }

    /// Ordinary replay compares SVGs without creating an execution, history row or lineage child.
    public func prepareReplayComparison(work: SavedWork) async throws -> ReplayComparisonSnapshot {
        try Task.checkCancellation()
        try await checkReplayComparisonParent(work)
        let context = try await savedPerformanceContext(workID: work.id)
        let comparison = try SavedPerformance.replayComparisonRequest(work: work, context: context)
        try Task.checkCancellation()
        let rendered = try ExactJSON(data: InkuCore.renderSaved(comparison.request.data))
        if let code = rendered["error"].string { throw HostError(code) }
        let snapshot = ReplayComparisonSnapshot(workID: work.id, originalSVG: work.svg,
            replayedSVG: try rendered.requiredString("svg"), recordedVersion: work.renderEngineVersion,
            currentVersion: try rendered["metadata"].requiredString("render_engine_version"),
            provisionalSeed: comparison.provisionalSeed, providerMetrics: try metrics(in: context))
        try Task.checkCancellation()
        try await checkReplayComparisonParent(work)
        try Task.checkCancellation()
        return snapshot
    }

    private func checkReplayComparisonParent(_ work: SavedWork) async throws {
        guard let stored = try await database.work(id: work.id), !stored.trashed,
              let nodeID = work.lineageNodeID,
              try await database.node(id: nodeID)?.historyID == work.id else {
            throw HostError("saved_work_changed_or_unavailable")
        }
        var expected = work
        expected.starred = stored.starred; expected.trashed = stored.trashed
        guard stored == expected else { throw HostError("saved_work_changed_or_unavailable") }
    }

    /// Draws the saved Score with its attested policies and saves one new lineage child.
    public func replay(workID: String, renderSeed: String? = nil, wild: Bool? = nil, options replayOptions: ReplayOptions? = nil) async throws -> SavedWork {
        let candidate = try await previewReplay(workID: workID, renderSeed: renderSeed, wild: wild, options: replayOptions, derivationKind: "replay")
        return try await saveCandidate(executionID: candidate.executionID)
    }

    public func previewReplay(workID: String, renderSeed: String? = nil, wild: Bool? = nil,
                              options replayOptions: ReplayOptions? = nil, derivationKind: String = "catalog_change") async throws -> PreparedCandidate {
        let plan = try await makeSavedScoreReplayPlan(workID: workID, renderSeed: renderSeed, wild: wild,
                                                     options: replayOptions, derivationKind: derivationKind)
        return try await previewSavedScoreReplay(plan)
    }

    /// Freeze all saved rendering facts before any candidate starts, without resolving today's colors.
    public func makeSavedScoreReplayPlan(workID: String, renderSeed: String? = nil, wild: Bool? = nil,
                                        options replayOptions: ReplayOptions? = nil, compositionSeed: String? = nil,
                                        derivationKind: String = "touch_change", derivationMetadata: Data? = nil,
                                        seedText: String? = nil, variationAmplitude: String? = nil,
                                        variationSeed: String? = nil) async throws -> SavedScoreReplayPlan {
        guard derivationKind != "variation", variationAmplitude == nil, variationSeed == nil else {
            throw HostError("variation_retired")
        }
        let source = try await restoreSavedWork(workID: workID)
        let location = try WorkIdentity.location(workID)
        guard let acknowledgement = try await database.acknowledgement(executionID: location.executionID, effectID: location.effectID) else { throw HostError("saved_performance_context_unavailable") }
        let ack = try ExactJSON(data: acknowledgement)
        guard ack["work_id"].string == workID, let parentNodeID = source.lineageNodeID,
              let parentNode = try await database.node(id: parentNodeID) else { throw HostError("saved_performance_context_invalid") }
        let context = try ack.requiredObject("performance")
        let request = try SavedPerformance.renderRequest(work: source, context: context, renderSeed: renderSeed, wild: wild,
                                                        replayOptions: replayOptions, compositionSeed: compositionSeed)
        _ = try metadataText(derivationMetadata)
        try Task.checkCancellation()
        return SavedScoreReplayPlan(work: source, parentNode: parentNode, context: context.data, renderRequest: request.data,
            derivationKind: derivationKind, derivationMetadata: derivationMetadata, seedText: seedText,
            variationAmplitude: variationAmplitude, variationSeed: variationSeed)
    }

    public func previewSavedScoreReplay(_ plan: SavedScoreReplayPlan) async throws -> PreparedCandidate {
        guard plan.derivationKind != "variation", plan.variationAmplitude == nil, plan.variationSeed == nil else {
            throw HostError("variation_retired")
        }
        let began = Date()
        let source = plan.work
        guard let stored = try await database.work(id: source.id), !stored.trashed,
              try await database.node(id: plan.parentNode.id)?.historyID == source.id else { throw HostError("lineage_parent_unavailable") }
        var expected = source
        expected.starred = stored.starred; expected.trashed = stored.trashed
        guard stored == expected else { throw HostError("saved_work_changed_or_unavailable") }
        let context = try ExactJSON(data: plan.context)
        let request = try ExactJSON(data: plan.renderRequest)
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
        work.compositionSeed = options["composition_seed"].number ?? options["composition_seed"].string
        if let seedText = plan.seedText { work.seedText = seedText }
        work.variationAmplitude = nil; work.variationSeed = nil
        work.renderWild = options["wild"].bool
        work.catalogID = options["catalog_id"].string
        work.renderColorCatalogID = options["catalog_id"].string
        work.renderColorMap = options["resolved_color_map"].text
        work.renderCanvasAspectID = options["canvas_aspect_id"].string
        work.renderCanvasAspect = options["canvas_aspect_id"].string
        if let width = options["canvas"]["width"].number.flatMap(Double.init),
           let height = options["canvas"]["height"].number.flatMap(Double.init), height > 0 {
            work.renderCanvasAspectRatio = width / height
        }
        work.renderEngineID = rendered["metadata"]["render_engine_id"].string
        work.renderEngineVersion = rendered["metadata"]["render_engine_version"].string
        work.renderHash = WorkIdentity.render(score: request["request"]["score"], options: options, metadata: rendered["metadata"])
        let node = LineageNode(id: nodeID, historyID: id, at: now, descriptionHash: work.descriptionHash,
                               renderHash: work.renderHash, rootNodeID: plan.parentNode.rootNodeID ?? plan.parentNode.id)
        let edge = LineageEdge(id: UUID().uuidString, parentNodeID: plan.parentNode.id, childNodeID: nodeID,
                               derivationKind: plan.derivationKind, metadataJSON: try metadataText(plan.derivationMetadata), at: now)
        var nextContext = context
        var stringOptions = options
        for key in ["render_seed", "composition_seed"] { if let number = options[key].number { stringOptions[key] = .string(number) } }
        nextContext["options"] = stringOptions
        if var compiler = nextContext["configuration"]["compiler"].object {
            compiler.removeValue(forKey: "stage15_variation")
            nextContext["configuration"]["compiler"] = .object(compiler)
        }
        nextContext["presentation"] = try SavedPresentation.replay(context: context, rendered: rendered)
        let candidate = StoredCandidate(work: work, node: node, edge: edge, context: nextContext.data)
        return try await prepareCandidate(executionID: executionID, candidate: candidate)
    }

    private func metadataText(_ data: Data?) throws -> String {
        guard let data else { return "{}" }
        let value = try ExactJSON(data: data)
        guard value.object != nil else { throw HostError("invalid_derivation_metadata") }
        return value.text
    }

    /// Explicit adoption is idempotent; previews never enter the history table.
    public func saveCandidate(executionID: String, expectedWorkID: String? = nil) async throws -> SavedWork {
        guard let record = try await database.loadExecution(id: executionID) else { throw HostError("candidate_not_found") }
        if var stored = try? JSONDecoder().decode(StandaloneCandidate.self, from: record.snapshot), stored.schema == "inku.swift-candidate.v1" {
            guard expectedWorkID == nil || expectedWorkID == stored.candidate.work.id else { throw HostError("candidate_identity_changed") }
            if stored.saved, let work = try await database.work(id: stored.candidate.work.id) { return work }
            try Task.checkCancellation()
            stored.saved = true
            let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
            _ = try await database.commitEffect(id: executionID, expectedRevision: record.revision, effectID: "save-render:0",
                snapshot: encoder.encode(stored), acknowledgement: SavedPerformance.acknowledgement(workID: stored.candidate.work.id,
                    context: try ExactJSON(data: stored.candidate.context)), work: stored.candidate.work,
                node: stored.candidate.node, edge: stored.candidate.edge)
            return stored.candidate.work
        }
        return try await execution(executionID).saveCandidate(expectedWorkID: expectedWorkID)
    }

    private func prepareCandidate(executionID: String, candidate: StoredCandidate) async throws -> PreparedCandidate {
        try Task.checkCancellation()
        let stored = StandaloneCandidate(candidate: candidate)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        let bytes = try encoder.encode(stored)
        let execution = try await database.compareAndSwapExecution(id: executionID, expectedRevision: nil, snapshot: bytes)
        let ack: ExactJSON = .object(["tag": .string("rendered_candidate_prepared"), "candidate_id": .string(executionID)])
        _ = try await database.commitEffect(id: executionID, expectedRevision: execution.revision, effectID: "prepare-candidate:0",
            snapshot: bytes, acknowledgement: ack.data)
        let context = try ExactJSON(data: candidate.context)
        return PreparedCandidate(executionID: executionID, work: candidate.work, authority: context["authority"]["authority"].string ?? "legacy_unknown",
            providerMetrics: try metrics(in: context))
    }

    private func generateRetained(_ request: GenerationRequest, progress: PipelineProgressHandler) async throws -> PipelineView {
        let began = Date()
        guard let documentBytes = request.retainedDocument, let authorityBytes = request.retainedAuthority,
              let parentID = request.parentWorkID, let parent = try await database.work(id: parentID),
              let parentNodeID = parent.lineageNodeID, let parentNode = try await database.node(id: parentNodeID) else {
            throw HostError("retained_source_context_unavailable")
        }
        let document = try ExactJSON(data: documentBytes)
        let authority = try ExactJSON(data: authorityBytes)
        let saved = try await savedAuthoringContext(workID: parentID)
        guard let savedDocument = saved.document, document == (try ExactJSON(data: savedDocument)),
              authority == (try ExactJSON(data: saved.authorityJSON)), document["source"].string == parent.ddl,
              ["description_authoritative", "ddl_authoritative"].contains(authority["authority"].string ?? "") else {
            throw HostError("retained_source_changed")
        }
        let config = try ExactJSON(data: request.configuration)
        let compiler = try config.requiredObject("compiler")
        let compileInput: ExactJSON = .object(["document": document, "definitions": config["definitions"], "compiler": compiler])
        try Task.checkCancellation()
        let delivery = try ExactJSON(data: InkuCore.compile(compileInput.data))
        if let code = delivery["error"].string { throw HostError(code) }
        guard delivery["score"].object != nil else { throw HostError("retained_source_requires_edit") }
        let options = try ExactJSON(data: request.renderOptions)
        let clip = try ExactJSON(data: request.clipPolicy)
        let renderInput: ExactJSON = .object(["delivery": delivery, "options": options, "compiler": compiler, "clip": clip])
        try Task.checkCancellation()
        let rendered = try ExactJSON(data: InkuCore.renderCompiled(renderInput.data))
        if let code = rendered["error"].string { throw HostError(code) }
        let executionID = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        let nodeID = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        let id = WorkIdentity.savedID(executionID: executionID, sequence: "0")
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        let score = delivery["score"]
        var work = parent
        work.id = id; work.at = now; work.svg = try rendered.requiredString("svg"); work.score = score.text
        work.elapsedMS = max(0, Int64(Date().timeIntervalSince(began) * 1000)); work.lineageNodeID = nodeID
        work.starred = false; work.trashed = false; work.historyVisibility = request.historyVisibility
        work.renderSeed = options["render_seed"].string ?? options["render_seed"].number
        work.compositionSeed = score["composition_seed"].string ?? score["composition_seed"].number ?? compiler["composition_seed"].string
        work.renderWild = options["wild"].bool
        work.catalogID = options["catalog_id"].string; work.renderColorCatalogID = options["catalog_id"].string
        work.renderColorMap = options["resolved_color_map"].text
        work.renderCanvasAspectID = options["canvas_aspect_id"].string; work.renderCanvasAspect = options["canvas_aspect_id"].string
        if let width = options["canvas"]["width"].number.flatMap(Double.init),
           let height = options["canvas"]["height"].number.flatMap(Double.init), height > 0 { work.renderCanvasAspectRatio = width / height }
        work.renderEngineID = rendered["metadata"]["render_engine_id"].string; work.renderEngineVersion = rendered["metadata"]["render_engine_version"].string
        if !request.models.stage2Model.isEmpty { work.stage2Model = request.models.stage2Model }
        work.variationAmplitude = compiler["stage15_variation"]["amplitude"].string
        work.variationSeed = compiler["stage15_variation"]["seed"].string
        work.renderHash = WorkIdentity.render(score: score, options: options, metadata: rendered["metadata"])
        let node = LineageNode(id: nodeID, historyID: id, state: request.historyVisibility == "lineage_only" ? "lineage_only" : "active",
            at: now, descriptionHash: work.descriptionHash, renderHash: work.renderHash, rootNodeID: parentNode.rootNodeID ?? parentNode.id)
        let edge = LineageEdge(id: UUID().uuidString, parentNodeID: parentNodeID, childNodeID: nodeID,
            derivationKind: request.derivationKind, metadataJSON: try metadataText(request.derivationMetadata), at: now)
        var context = SavedPerformance.context(score: score, options: options, compiler: compiler, clip: clip)
        context["configuration"] = config; context["document"] = document; context["authority"] = authority
        context["presentation"] = try SavedPresentation.capture(delivery: delivery, rendered: rendered,
            prompts: nil, events: Data("[]".utf8), configuration: config, document: document,
            disabledPluginNames: request.disabledPluginNames ?? [], provenance: request.provenance)
        let candidate = try await prepareCandidate(executionID: executionID,
            candidate: StoredCandidate(work: work, node: node, edge: edge, context: context.data))
        let savedID: String?
        if request.saveHistory { savedID = try await saveCandidate(executionID: executionID).id }
        else { savedID = nil }
        let view = PipelineView(executionID: executionID, variationID: executionID, sequence: "0",
            revision: try authority.requiredString("revision"), phase: "completed", authority: try authority.requiredString("authority"),
            origin: try authority.requiredString("origin"), visibleDDL: document["source"].string,
            scoreJSON: score.data, renderedJSON: rendered.data, svg: work.svg, savedWorkID: savedID,
            patchProposalJSON: nil, eventsJSON: Data("[]".utf8), busy: false, interruptedProvider: false,
            description: work.effectiveSourceText, configurationJSON: config.data, documentJSON: document.data,
            deliveryJSON: delivery.data, promptJSON: nil, holeIDs: [], candidateWork: candidate.work,
            providerMetrics: try metrics(in: context))
        progress(.changed(view))
        return view
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
    var derivationMetadata: Data? = nil
    var interpretationSeed: String? = nil
    var pendingProviderAction: Data?
    var savedWorkID: String?
    var prompts: Data? = nil
    var saveHistory: Bool? = nil
    var historyVisibility: String? = nil
    var candidate: StoredCandidate? = nil
    var chatGPTSession: ChatGPTPlanSession? = nil
    var captureProviderIO: Bool? = nil
    var disabledPluginNames: [String]? = nil
    var provenance: GenerationProvenance? = nil
    var providerObservations: [ProviderAttemptObservation]? = nil
    var startedAt: Date
}

/// Normal metric reads skip private bodies during decoding as well as in their returned type.
private struct StoredMetricRead: Decodable {
    struct Record: Decodable { let metric: ProviderAttemptMetric }
    let providerObservations: [Record]?
}

private struct StoredCandidate: Codable, Sendable {
    var work: SavedWork
    var node: LineageNode
    var edge: LineageEdge?
    var context: Data
}

private struct StandaloneCandidate: Codable, Sendable {
    var schema = "inku.swift-candidate.v1"
    var candidate: StoredCandidate
    var saved = false
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
    // A native private-capture lifetime budget; normal metrics do not consume this budget.
    let maximumExecutionRawBodyBytes = 64 * 1_024 * 1_024

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
        self.state.saveHistory = request.saveHistory
        self.state.historyVisibility = request.historyVisibility
        self.state.chatGPTSession = request.chatGPTSession
        self.state.captureProviderIO = request.captureProviderIO
        self.state.disabledPluginNames = request.disabledPluginNames
        self.state.provenance = request.provenance
        self.state.providerObservations = []
        if let metadata = request.derivationMetadata {
            guard try ExactJSON(data: metadata).object != nil else { throw HostError("invalid_derivation_metadata") }
        }
        self.state.derivationMetadata = request.derivationMetadata
        self.state.interpretationSeed = request.interpretationSeed
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
    func bindPersonalPlanSession(_ session: ChatGPTPlanSession) async throws {
        await gate.lock(); defer { Task { await gate.unlock() } }
        guard providerTask == nil, state.pendingProviderAction == nil else { throw HostError("provider_effect_in_flight") }
        guard state.chatGPTSession == nil || state.chatGPTSession == session else { throw HostError("chatgpt_session_changed") }
        var changed = state; changed.chatGPTSession = session
        let record = try await database.compareAndSwapExecution(id: executionID(), expectedRevision: databaseRevision, snapshot: encoded(changed))
        state = changed; databaseRevision = record.revision
    }
    func personalPlanContext(stage2: Bool) async throws -> (required: Bool, session: ChatGPTPlanSession?) {
        (PersonalPlanRoutingTransport.isPersonal(stage2 ? state.models.stage2Model : state.models.stage1Model, providers: state.providers), state.chatGPTSession)
    }

    func perform(_ command: PipelineCommand, parentWorkID: String?, derivationKind: String?, derivationMetadata: Data?,
                 progress: @escaping PipelineProgressHandler) async throws -> PipelineView {
        if case .cancel = command { return try await cancel(progress: progress) }
        await gate.lock()
        do {
            guard !(restored && snapshot["action"].object != nil) else { throw HostError("interrupted_execution_requires_cancel") }
            guard providerTask == nil else { throw HostError("provider_effect_in_flight") }
            restored = false
            let oldState = state
            if let parentWorkID { state.parentWorkID = parentWorkID }
            if let derivationKind {
                if let metadata = derivationMetadata {
                    guard try ExactJSON(data: metadata).object != nil else { throw HostError("invalid_derivation_metadata") }
                }
                state.derivationKind = derivationKind; state.derivationMetadata = derivationMetadata
            }
            if case .generateFromDescription(_, let text, _, _) = command { state.description = text }
            do { try await advance(command.payload()) }
            catch { state = oldState; throw error }
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
                } else if ["generate_sketch", "select_description_catalog", "generate_normalized_ddl", "read_composition", "complete_visible_ddl_holes"].contains(tag) {
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
                        // The composition reading belongs to its private effect
                        // snapshot, never to the author-facing prompt tabs.
                        if tag != "read_composition" {
                            var prompts = (try claimed.prompts.map { try ExactJSON(data: $0).array } ?? nil) ?? []
                            prompts.append(.object(["action": action["tag"], "identity": action["identity"], "prompt": action["payload"]["prompt"]]))
                            claimed.prompts = ExactJSON.array(prompts).data
                        }
                        let record = try await database.compareAndSwapExecution(id: executionID(), expectedRevision: databaseRevision, snapshot: encoded(claimed))
                        state = claimed; databaseRevision = record.revision
                        let began = Date()
                        let delayMS = try canonicalUnsigned(action, key: "delay_ms")
                        let timeoutMS = try canonicalUnsigned(action, key: "timeout_ms")
                        progress(.providerAttempt(executionID: try executionID(), report: InkuCore.providerAttempt(snapshot: state.snapshot), beganAt: began,
                                                  deadline: began.addingTimeInterval(Double(delayMS) / 1000 + Double(timeoutMS) / 1000)))
                        let bytes = action.data; let models = state.models; let providers = state.providers
                        let personalSession = state.chatGPTSession
                        let limitValue = snapshot["config"]["prompt_limits"]["max_response_bytes"]
                        guard let argumentLimit = (limitValue.number ?? limitValue.string).flatMap(Int.init), argumentLimit > 0 else {
                            throw HostError("pipeline_schema_violation")
                        }
                        let id = try executionID(); let transport = self.transport; let credentials = self.credentials
                        let observation = ProviderObservationOptions(captureRaw: state.captureProviderIO == true)
                        task = Task {
                            if delayMS > 0 {
                                guard delayMS <= UInt64.max / 1_000_000 else { throw HostError("pipeline_schema_violation") }
                                try await Task.sleep(nanoseconds: delayMS * 1_000_000)
                            }
                            try Task.checkCancellation()
                            let willSend: ProviderObservationHandler = { value in
                                try await self.persistObservation(value, action: action, final: false, progress: progress)
                            }
                            let didFinish: ProviderObservationHandler = { value in
                                try await self.persistObservation(value, action: action, final: true, progress: progress)
                            }
                            if let personal = transport as? any ObservedChatGPTPlanEffectTransport {
                                return try await personal.performPersonalPlanObserved(action: bytes, models: models, providers: providers,
                                    session: personalSession, argumentLimit: argumentLimit, credentials: credentials,
                                    observation: observation, willSend: willSend, didFinish: didFinish,
                                    onBytes: { count in progress(.transportBytes(executionID: id, count: count)) },
                                    onDiagnostic: { diagnostic in progress(.providerDiagnostic(executionID: id, diagnostic: diagnostic)) })
                            }
                            if let observed = transport as? any ObservedProviderTransport {
                                return try await observed.performObserved(action: bytes, models: models, providers: providers, credentials: credentials,
                                    observation: observation, willSend: willSend, didFinish: didFinish,
                                    onBytes: { count in progress(.transportBytes(executionID: id, count: count)) })
                            }
                            guard !observation.captureRaw else { throw ProviderObservationFailure.unsupportedTransport }
                            if let personal = transport as? any ChatGPTPlanEffectTransport {
                                return try await personal.performPersonalPlan(action: bytes, models: models, providers: providers,
                                    session: personalSession, argumentLimit: argumentLimit, credentials: credentials,
                                    onBytes: { count in progress(.transportBytes(executionID: id, count: count)) },
                                    onDiagnostic: { diagnostic in progress(.providerDiagnostic(executionID: id, diagnostic: diagnostic)) })
                            }
                            let reference = tag == "complete_visible_ddl_holes" ? models.stage2Model : models.stage1Model
                            if PersonalPlanRoutingTransport.isPersonal(reference, providers: providers) { throw HostError("chatgpt_transport_unavailable") }
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

    private func persistObservation(_ observation: ProviderAttemptObservation, action: ExactJSON, final: Bool,
                                    progress: PipelineProgressHandler) async throws {
        await gate.lock()
        do {
            let identity = try ProviderActionIdentity(action: action.data)
            let cancelledFinal = final && observation.metric.outcome == .cancelled
                && snapshot["phase"]["tag"].string == "cancelled"
                && state.providerObservations?.contains(where: { $0.metric.identity == identity && $0.metric.outcome == .requestSaved }) == true
            if !cancelledFinal { try Task.checkCancellation() }
            guard cancelledFinal || (snapshot["action"] == action && state.pendingProviderAction == action.data) else { throw CancellationError() }
            let reference = action["tag"].string == "complete_visible_ddl_holes" ? state.models.stage2Model : state.models.stage1Model
            guard observation.metric.identity == identity, observation.metric.action == action["tag"].string,
                  ProviderObservationStage(action: observation.metric.action) == observation.metric.stage,
                  observation.metric.requestedModelReference == reference,
                  observation.metric.timeoutMS == (try canonicalUnsigned(action, key: "timeout_ms")),
                  (final ? observation.metric.outcome != .requestSaved : observation.metric.outcome == .requestSaved) else {
                throw HostError("provider_observation_identity_mismatch")
            }
            if !final, state.captureProviderIO == true, !ProviderObservationPolicy.developerModeEnabled {
                throw HostError("developer_provider_observations_not_available")
            }
            var stored = observation
            if state.captureProviderIO != true { stored.raw = nil }
            if state.captureProviderIO == true, !final, stored.raw?.requestBody == nil {
                throw HostError("provider_observation_request_missing")
            }
            if let raw = stored.raw {
                guard (raw.requestBody?.utf8.count ?? 0) <= ProviderObservationPolicy.maximumRawBytes,
                      (raw.responseBody?.utf8.count ?? 0) <= ProviderObservationPolicy.maximumRawBytes else {
                    throw HostError("provider_observation_body_too_large")
                }
            }
            var changed = state
            var records = changed.providerObservations ?? []
            if state.captureProviderIO == true, !final {
                guard stored.raw?.responseBody == nil else { throw HostError("provider_observation_response_before_send") }
                let prior = try rawBodyBytes(in: records)
                let requestBytes = stored.raw?.requestBody?.utf8.count ?? 0
                // Reserve a full bounded response before HTTP, preserving every earlier capture.
                guard requestBytes <= maximumExecutionRawBodyBytes - prior,
                      ProviderObservationPolicy.maximumRawBytes <= maximumExecutionRawBodyBytes - prior - requestBytes else {
                    throw HostError("provider_observation_capture_budget_exhausted")
                }
            }
            if let index = records.firstIndex(where: { $0.metric.identity == identity }) {
                guard final, records[index].metric.outcome == .requestSaved else { throw HostError("provider_observation_already_finished") }
                records[index] = stored
            } else {
                // A classified rejection before HTTP can finish without a request body.
                guard !final || !stored.metric.sent else { throw HostError("provider_observation_request_missing") }
                records.append(stored)
            }
            if state.captureProviderIO == true { _ = try rawBodyBytes(in: records) }
            changed.providerObservations = records
            let saved = try await database.compareAndSwapExecution(id: executionID(), expectedRevision: databaseRevision,
                                                                  snapshot: encoded(changed))
            state = changed; databaseRevision = saved.revision
            progress(.providerMetric(executionID: try executionID(), metric: stored.metric))
            await gate.unlock()
        } catch is CancellationError {
            await gate.unlock(); throw CancellationError()
        } catch {
            await gate.unlock()
            throw final ? ProviderObservationFailure.outcomeSaveFailed : ProviderObservationFailure.requestSaveFailed
        }
    }

    private func rawBodyBytes(in observations: [ProviderAttemptObservation]) throws -> Int {
        var total = 0
        for observation in observations {
            for bytes in [observation.raw?.requestBody?.utf8.count ?? 0, observation.raw?.responseBody?.utf8.count ?? 0] {
                guard bytes <= maximumExecutionRawBodyBytes - total else { throw HostError("provider_observation_capture_budget_exhausted") }
                total += bytes
            }
        }
        return total
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
        var next = state; next.snapshot = nextSnapshot.data
        let priorEvents = try ExactJSON(data: state.events).array ?? []
        next.events = ExactJSON.array(priorEvents + (result["events"].array ?? [])).data
        if result["rendered"].object != nil { next.rendered = result["rendered"].data; next.savedWorkID = nil; next.candidate = nil }
        else if current?["document"] != nextSnapshot["document"] || nextSnapshot["delivery"].object == nil {
            next.rendered = nil; next.savedWorkID = nil; next.candidate = nil
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
        if state.saveHistory == false && state.candidate != nil { return }
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
        let sketch = savedSketchResult()
        let work = SavedWork(id: id, at: now, input: state.description, score: score.text, svg: svg,
                             sourceText: state.description, ddl: snapshot["document"]["source"].string,
                             // This portable field records legacy body migration, not pipeline authority.
                             ddlSourceOrigin: nil,
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
                             interpretationSeed: state.interpretationSeed,
                             variationAmplitude: compiler["stage15_variation"]["amplitude"].string,
                             variationSeed: compiler["stage15_variation"]["seed"].string,
                             instructionLangResolved: snapshot["config"]["language"].string,
                             sketchText: sketch.text, sketchState: sketch.state,
                             renderLimits: legacyRenderLimits(compiler["operational_resource_budget"]),
                             renderHash: renderHash, descriptionHash: descriptionHash,
                             historyVisibility: state.historyVisibility ?? "normal", lineageNodeID: nodeID)
        var edge: LineageEdge?
        var rootNodeID = nodeID
        if let parentID = state.parentWorkID {
            guard let parent = try await database.work(id: parentID), let parentNodeID = parent.lineageNodeID,
                  let parentNode = try await database.node(id: parentNodeID) else { throw HostError("lineage_parent_unavailable") }
            rootNodeID = parentNode.rootNodeID ?? parentNode.id
            let metadata = try state.derivationMetadata.map { try ExactJSON(data: $0).text } ?? "{}"
            edge = LineageEdge(id: newID(), parentNodeID: parentNodeID, childNodeID: nodeID,
                               derivationKind: state.derivationKind, metadataJSON: metadata, at: now)
        }
        let node = LineageNode(id: nodeID, historyID: id, state: state.historyVisibility == "lineage_only" ? "lineage_only" : "active",
            at: now, descriptionHash: descriptionHash, renderHash: renderHash, rootNodeID: rootNodeID)
        var savedState = state; savedState.savedWorkID = id
        let effectID = "save-render:" + (try snapshot.requiredString("sequence"))
        var performance = SavedPerformance.context(score: score, options: options, compiler: compiler, clip: try ExactJSON(data: state.clipPolicy))
        performance["configuration"] = snapshot["config"]
        performance["document"] = snapshot["document"]
        performance["authority"] = snapshot["authority"]
        performance["presentation"] = try SavedPresentation.capture(delivery: delivery, rendered: rendered,
            prompts: state.prompts, events: state.events, configuration: snapshot["config"], document: snapshot["document"],
            disabledPluginNames: state.disabledPluginNames ?? [], provenance: state.provenance)
        // Freeze only public metrics at this save identity. Raw stays in the private execution snapshot.
        performance["provider_metrics"] = try ExactJSON(data: JSONEncoder().encode(state.providerObservations?.map(\.metric) ?? []))
        performance["provider_observation_execution_id"] = .string(try executionID())
        if let session = state.chatGPTSession {
            performance["personal_provider_context"] = .object(["provider": .string("chatgpt"),
                "profile_id": .string(session.profileID), "generation": .string(String(session.generation))])
        }
        savedState.candidate = StoredCandidate(work: work, node: node, edge: edge, context: performance.data)
        try Task.checkCancellation()
        if state.saveHistory == false {
            savedState.savedWorkID = nil
            let acknowledgement: ExactJSON = .object(["tag": .string("rendered_candidate_prepared"), "candidate_id": .string(try executionID())])
            let committed = try await database.commitEffect(id: executionID(), expectedRevision: revision,
                effectID: "prepare-candidate:" + (try snapshot.requiredString("sequence")), snapshot: encoded(savedState), acknowledgement: acknowledgement.data)
            state = savedState; databaseRevision = committed.execution.revision
            progress(.changed(try makeView()))
            return
        }
        let acknowledgement = SavedPerformance.acknowledgement(workID: id, context: performance)
        let committed = try await database.commitEffect(id: executionID(), expectedRevision: revision, effectID: effectID,
                                                       snapshot: encoded(savedState), acknowledgement: acknowledgement, work: work, node: node, edge: edge)
        state = savedState; databaseRevision = committed.execution.revision
        progress(.saved(executionID: try executionID(), workID: id)); progress(.changed(try makeView()))
    }

    /// Current Server pipeline_product.sketch_result maps only this run's new result.
    /// Historical NULL/not_applicable metadata remains untouched in saved-work replay.
    private func savedSketchResult() -> (text: String?, state: String) {
        let record = snapshot["sketch"]
        guard record.object != nil else { return (nil, "off") }
        let state = record["state"].string
        if ["supplemented", "supplied"].contains(state ?? ""), let text = record["text"].string, !text.isEmpty {
            return (text, "supplemented")
        }
        if state == "not_needed" { return (nil, "not_needed") }
        return (nil, "fallback")
    }

    func saveCandidate(expectedWorkID: String? = nil) async throws -> SavedWork {
        await gate.lock(); defer { Task { await gate.unlock() } }
        if let id = state.savedWorkID, let work = try await database.work(id: id) {
            guard expectedWorkID == nil || expectedWorkID == work.id else { throw HostError("candidate_identity_changed") }
            return work
        }
        guard let candidate = state.candidate, let revision = databaseRevision else { throw HostError("candidate_not_ready") }
        guard expectedWorkID == nil || expectedWorkID == candidate.work.id else { throw HostError("candidate_identity_changed") }
        try Task.checkCancellation()
        var savedState = state; savedState.savedWorkID = candidate.work.id
        // Explicit promotion makes later editor commands ordinary committed child mutations.
        savedState.saveHistory = true
        let context = try ExactJSON(data: candidate.context)
        let committed = try await database.commitEffect(id: executionID(), expectedRevision: revision,
            effectID: "save-render:" + (try snapshot.requiredString("sequence")), snapshot: encoded(savedState),
            acknowledgement: SavedPerformance.acknowledgement(workID: candidate.work.id, context: context),
            work: candidate.work, node: candidate.node, edge: candidate.edge)
        state = savedState; databaseRevision = committed.execution.revision
        return candidate.work
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
                            description: state.description, configurationJSON: snapshot["config"].data,
                            documentJSON: snapshot["document"].object == nil ? nil : snapshot["document"].data,
                            deliveryJSON: snapshot["delivery"].object == nil ? nil : snapshot["delivery"].data,
                            promptJSON: state.prompts,
                            holeIDs: snapshot["delivery"]["compiler_lock"]["hole_identities"].array?.compactMap(\.string) ?? [], candidateWork: state.candidate?.work,
                            providerMetrics: state.providerObservations?.map(\.metric) ?? [])
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
