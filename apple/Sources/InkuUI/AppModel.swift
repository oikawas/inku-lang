import CoreGraphics
import Foundation
import ImageIO
import InkuCore
import InkuHost
import InkuPersistence
import InkuExport
import Observation
import UniformTypeIdentifiers
#if os(macOS)
import AppKit
#endif

@MainActor
@Observable
public final class AppModel {
    public var inputMode = "ddl"
    public var descriptionText = ""
    public var ddlText = "place one red circle at center."
    public var language = "en"
    public var catalogID = "default"
    public var canvasID = "square"
    public var seedText = ""
    public var wild = false
    public var catalogMode = "fixed"
    public var sketchMode = "off"
    public var sketchText = ""
    public var variationAmplitude = "small"
    public var variationSeedText = ""
    public var selectedHoleIDs: Set<String> = []
    public private(set) var works: [SavedWork] = []
    public private(set) var selectedWorkID: String?
    public private(set) var selectedWork: SavedWork?
    public private(set) var previewWork: SavedWork?
    public private(set) var currentSVG = ""
    public private(set) var visibleDDL = ""
    public private(set) var scoreJSON = ""
    public private(set) var status = "準備中"
    public private(set) var isBusy = false
    public var errorText: String?
    public var providerURL = "http://localhost:8080/v1"
    public var providerModel = ""
    public var providerKind = "openai_compatible"
    public var providerKey = ""
    public private(set) var nextDrawingModelReference = ""
    public private(set) var providerSettingsRevision = 0
    public private(set) var catalogs: [ColorCatalogOption] = []
    public private(set) var canvases: [CanvasOption] = []
    public private(set) var saijiki: [SaijikiCategory] = []
    public private(set) var pluginWords: [PluginWord] = []
    public private(set) var importedMacroNames: [String] = []
    public private(set) var macroDiagnostics = ""
    public private(set) var authoringRevision = "0"
    public private(set) var authoringAuthority = ""
    public private(set) var authoringOrigin = ""
    public private(set) var authoringPhase = ""
    public private(set) var diagnosticsJSON = ""
    public private(set) var promptJSON = ""
    public private(set) var eventsJSON = ""
    public private(set) var holeIDs: [String] = []
    public private(set) var patchProposalJSON = ""
    public private(set) var patchCandidate = ""
    public private(set) var unreadOutputs: Set<String> = []
    public let library = LibraryModel()
    public let display = DisplaySettings()
    public let descriptionMeter = DescriptionMeterModel()
    public let renderer = ArtworkRenderer()
    @ObservationIgnored public var onSavedWork: (@MainActor (SavedWork) async -> Void)?
    public let versionSummary: String = {
        let report = try? JSONSerialization.jsonObject(with: Data(InkuCore.versionReport.utf8)) as? [String: String]
        return "共通コア接続 \(report?["binding_version"] ?? "不明") · 描画接続 \(InkuCore.rasterAPIVersion)"
    }()

    @ObservationIgnored private let databaseURL: URL?
    @ObservationIgnored private let transport: any ProviderTransport
    @ObservationIgnored private var managedTransport: (any ProviderTransport)?
    @ObservationIgnored private var personalRuntime: ChatGPTPlanRuntime?
    @ObservationIgnored private let credentials = KeychainCredentialStore()
    @ObservationIgnored private var database: InkuDatabase?
    @ObservationIgnored private var host: PipelineHost?
    @ObservationIgnored private var settingsStore: ProviderSettingsStore?
    @ObservationIgnored private var settings = HostSettings()
    @ObservationIgnored private var bootstrap: Bootstrap?
    @ObservationIgnored private var currentExecutionID: String?
    @ObservationIgnored private var generationToken: UUID?
    @ObservationIgnored private var activeOperation: Task<Void, Never>?
    @ObservationIgnored private var stopping = false
    @ObservationIgnored private var initialized = false
    @ObservationIgnored private var selectedContext: SavedAuthoringContext?
    @ObservationIgnored private var currentView: PipelineView?
    @ObservationIgnored private var importedDDL: DDLPackageImport?

    public init(databaseURL: URL? = nil, transport: any ProviderTransport = URLSessionProviderTransport()) {
        self.databaseURL = databaseURL
        self.transport = transport
    }

    public var sourceLocked: Bool { authoringAuthority == "ddl_authoritative" }
    /// Names actually pinned to the visible authoring document, independent of next-work plugin preferences.
    public var authoringMacroNames: [String] {
        guard let data = currentView?.configurationJSON ?? selectedContext?.configuration,
              let configuration = try? ExactJSON(data: data) else { return importedMacroNames }
        let names = (configuration["definitions"].array ?? []).flatMap { definition -> [String] in
            guard let namespace = definition["namespace"].string, let heading = definition["heading"].string else { return [] }
            return ([heading] + (definition["aliases"].array ?? []).compactMap(\.string)).map { namespace + "." + $0 }
        }
        return Array(Set(names + importedMacroNames)).sorted()
    }
    public var displayedWork: SavedWork? { previewWork ?? selectedWork }
    public var isPreview: Bool { previewWork != nil }
    public var hasConfiguredProviders: Bool { !settings.providers.isEmpty }
    public var hasNextDrawingModel: Bool {
        settings.providers.contains { nextDrawingModelReference.hasPrefix($0.id + ":") && nextDrawingModelReference.count > $0.id.count + 1 }
    }
    public var canCommitDDL: Bool { !isBusy && !isPreview && !ddlText.isEmpty && ddlText != visibleDDL && (currentExecutionID != nil || selectedContext != nil) }
    public var canCompleteHoles: Bool { !isBusy && currentExecutionID != nil && !holeIDs.isEmpty && !settings.providers.isEmpty && ddlText == visibleDDL }
    public var canRegenerateDescription: Bool { !isBusy && !sourceLocked && currentExecutionID != nil && !settings.providers.isEmpty && !descriptionText.isEmpty }
    public var canGenerate: Bool {
        database != nil && !isBusy && !isPreview && !(inputMode == "ddl" ? ddlText : descriptionText).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && (inputMode == "ddl" || (hasNextDrawingModel && !(selectedWorkID != nil && sourceLocked)))
    }

    public func initialize() async {
        guard !initialized else { return }
        initialized = true
        do {
            let url = try databaseURL ?? InkuDatabase.applicationSupportURL(hostIdentifier: "app.inku.macos")
            let database = try InkuDatabase(url: url)
            let store = ProviderSettingsStore(url: url.deletingLastPathComponent().appendingPathComponent("providers.json"))
            let settings = try await store.load()
            let bootstrap = try Bootstrap()
            self.database = database
            let personalRuntime = ChatGPTPlanRuntime(directory: url.deletingLastPathComponent().appendingPathComponent("personal-chatgpt", isDirectory: true))
            let routed = PersonalPlanRoutingTransport(ordinary: transport, runtime: personalRuntime)
            self.personalRuntime = personalRuntime
            self.managedTransport = routed
            self.host = PipelineHost(database: database, transport: routed, credentials: credentials)
            self.settingsStore = store
            self.settings = settings
            synchronizeNextDrawingModel(previousSettings: nil)
            self.bootstrap = bootstrap
            display.connect(directory: url.deletingLastPathComponent())
            descriptionMeter.connect(directory: url.deletingLastPathComponent())
            self.catalogs = bootstrap.catalogs
            self.canvases = bootstrap.canvases
            self.saijiki = bootstrap.saijiki
            self.pluginWords = bootstrap.pluginWords.filter { settings.plugins?.isEnabled($0.packageID ?? "") ?? true }
            let macro = try bootstrap.macroCatalog(language: language, settings: settings)
            self.macroDiagnostics = try Self.pretty(try Bootstrap.bytes(macro))
            library.onMutation = { [weak self] in await self?.refreshWorks() }
            await library.connect(database: database)
            if let provider = settings.providers.first {
                providerURL = provider.baseURL.absoluteString
                providerKind = provider.apiProfile == "mlx" ? "mlx" : provider.kind.rawValue
                providerModel = settings.models.stage1Model.hasPrefix("\(provider.id):")
                    ? String(settings.models.stage1Model.dropFirst(provider.id.count + 1)) : settings.models.stage1Model
            }
            try await reloadWorks()
            status = "準備完了"
        } catch {
            initialized = false
            report(error)
        }
    }

    public func generate() async {
        guard canGenerate, let host, let bootstrap else { return }
        let token = UUID()
        generationToken = token
        currentExecutionID = nil
        stopping = false
        isBusy = true
        errorText = nil
        status = "生成中"
        let operation = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.runGeneration(host: host, bootstrap: bootstrap, token: token)
        }
        activeOperation = operation
        await operation.value
        finishOperation(token: token)
    }

    private func runGeneration(host: PipelineHost, bootstrap: Bootstrap, token: UUID) async {
        do {
            let freshRequest = try requestForCurrentInput(parentWorkID: selectedWorkID,
                derivationKind: selectedWorkID == nil ? "new" : inputMode == "ddl" ? "ddl_edit" : "description_edit")
            let request = try await pinPersonalPlanRequests([freshRequest])[0]
            let view = try await host.generate(request) { [weak self] progress in
                Task { @MainActor in self?.receive(progress, token: token) }
            }
            await recordDescriptionFeedback(request: request, view: view)
            await notifyCommittedWork(view)
            guard generationToken == token, !Task.isCancelled else { return }
            apply(view)
            try await reloadWorks()
            if let id = view.savedWorkID, let work = works.first(where: { $0.id == id }) {
                displayWork(work)
                selectedContext = try await host.savedAuthoringContext(workID: id)
            }
        } catch {
            guard generationToken == token, !Task.isCancelled else { return }
            report(error)
        }
    }

    public func cancel() async {
        guard let operation = activeOperation, !stopping else { return }
        stopping = true
        status = "停止中"
        operation.cancel()
        if let id = currentExecutionID, let host {
            do { _ = try await host.cancel(executionID: id) }
            catch { report(error) }
        }
        await operation.value
    }

    public func selectWork(_ work: SavedWork) async {
        guard !isBusy else { return }
        errorText = nil
        displayWork(work)
        currentExecutionID = nil
        currentView = nil
        selectedContext = nil
        holeIDs = []
        selectedHoleIDs = []
        patchProposalJSON = ""
        patchCandidate = ""
        diagnosticsJSON = ""
        promptJSON = ""
        eventsJSON = ""
        guard let host else { return }
        do {
            let context = try await host.savedAuthoringContext(workID: work.id)
            selectedContext = context
            authoringAuthority = context.authority
            authoringOrigin = context.origin
            authoringRevision = context.revision
            authoringPhase = "completed"
            let location = work.id.split(separator: "_").dropLast().joined(separator: "_")
            if let view = try? await host.restore(executionID: location), view.savedWorkID == work.id {
                apply(view)
            }
        } catch {
            authoringAuthority = "legacy_unknown"
            authoringOrigin = work.ddlSourceOrigin ?? "legacy_unknown"
            authoringRevision = "0"
            authoringPhase = "saved"
            diagnosticsJSON = "この保存作品には編集用の共通コア設定がありません。保存された画像とScoreを表示しています。"
        }
    }

    private func displayWork(_ work: SavedWork) {
        importedDDL = nil; importedMacroNames = []
        previewWork = nil
        selectedWorkID = work.id
        selectedWork = work
        currentSVG = work.svg
        visibleDDL = work.ddl ?? ""
        scoreJSON = work.score
        ddlText = work.ddl ?? ""
        descriptionText = work.effectiveSourceText
    }

    public func replay(_ work: SavedWork) async {
        guard !isBusy, let host else { return }
        let token = UUID()
        generationToken = token
        currentExecutionID = nil
        stopping = false
        isBusy = true
        errorText = nil
        status = "再演奏中"
        let operation = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.runReplay(work: work, host: host, token: token)
        }
        activeOperation = operation
        await operation.value
        finishOperation(token: token)
    }

    private func runReplay(work: SavedWork, host: PipelineHost, token: UUID) async {
        do {
            let result = try await host.replay(workID: work.id)
            await notifySavedWork(result)
            guard generationToken == token, !Task.isCancelled else { return }
            try await reloadWorks()
            displayWork(result)
            selectedContext = try? await host.savedAuthoringContext(workID: result.id)
            currentExecutionID = nil
            currentView = nil
            status = "再演奏を保存しました"
        } catch {
            guard generationToken == token, !Task.isCancelled else { return }
            report(error)
        }
    }

    private func finishOperation(token: UUID) {
        guard generationToken == token else { return }
        if stopping { status = "停止しました" }
        activeOperation = nil
        generationToken = nil
        stopping = false
        isBusy = false
    }

    public func localDataDirectory() -> URL? { database?.url.deletingLastPathComponent() }

    public func hostSettings() async -> HostSettings { settings }

    public func nextGenerationSettings() async -> HostSettings { nextGenerationHostSettings }

    public func selectNextDrawingModel(_ reference: String) {
        guard !isBusy, settings.providers.contains(where: { reference.hasPrefix($0.id + ":") && reference.count > $0.id.count + 1 }) else { return }
        nextDrawingModelReference = reference
    }

    private var nextGenerationHostSettings: HostSettings {
        var next = settings
        next.models.stage1Model = nextDrawingModelReference
        next.models.stage2Model = nextDrawingModelReference
        return next
    }

    private func synchronizeNextDrawingModel(previousSettings: HostSettings?) {
        if previousSettings == nil || previousSettings?.models != settings.models || !hasNextDrawingModel {
            nextDrawingModelReference = settings.models.stage1Model
            if !hasNextDrawingModel { nextDrawingModelReference = "" }
        }
        providerSettingsRevision += 1
    }

    public func updateHostSettings(_ settings: HostSettings) async throws {
        guard !isBusy, let settingsStore else { throw HostError("settings_busy_or_unavailable") }
        if let limits = settings.operationalLimits {
            let maximum = try operationalLimitDefaults()
            guard limits.allSatisfy({ key, value in maximum[key].map { value <= $0 } ?? false }) else {
                throw HostError("invalid_operational_limits")
            }
        }
        let diagnostics = try bootstrap.map { try Self.pretty($0.macroCatalogValue(language: language, settings: settings, importedPlugins: importedDDL?.plugins ?? []).data) }
        try await settingsStore.save(settings)
        let previousSettings = self.settings
        self.settings = settings
        synchronizeNextDrawingModel(previousSettings: previousSettings)
        if let bootstrap {
            pluginWords = bootstrap.pluginWords.filter { settings.plugins?.isEnabled($0.packageID ?? "") ?? true }
            macroDiagnostics = diagnostics ?? ""
        }
    }

    public func operationalLimitDefaults() throws -> [String: UInt32] {
        guard let bootstrap else { throw HostError("installation_unavailable") }
        return try bootstrap.operationalLimitDefaults()
    }

    public func operationalLimits() throws -> [String: UInt32] {
        try operationalLimitDefaults().merging(settings.operationalLimits ?? [:]) { _, selected in selected }
    }

    public func updateOperationalLimits(_ limits: [String: UInt32]?) async throws {
        var changed = settings
        changed.operationalLimits = limits
        try await updateHostSettings(changed)
    }

    public func setCredential(_ key: String?, credentialID: String) async throws {
        try await credentials.setKey(key, for: credentialID)
    }

    public func auxiliaryProvider() throws -> AuxiliaryProvider {
        guard let auxiliaryTransport = (managedTransport ?? transport) as? any AuxiliaryTransport else { throw HostError("auxiliary_transport_unavailable") }
        return AuxiliaryProvider(transport: auxiliaryTransport, credentials: credentials)
    }

    public func auxiliaryDatabase() throws -> InkuDatabase {
        guard let database else { throw HostError("pipeline_unavailable") }
        return database
    }

    public func personalPlanRuntime() throws -> ChatGPTPlanRuntime {
        guard let personalRuntime else { throw HostError("pipeline_unavailable") }; return personalRuntime
    }
    public func shutdownPersonalPlan() async { await personalRuntime?.shutdown() }

    /// New runs pin once before journaling. A supplied pin is checked and is never replaced.
    public func pinPersonalPlanRequests(_ requests: [GenerationRequest]) async throws -> [GenerationRequest] {
        guard let personalRuntime else { throw HostError("pipeline_unavailable") }
        var freshPin: ChatGPTPlanSession?
        var pinned: [GenerationRequest] = []
        for var request in requests {
            let stage1 = try PersonalPlanRoutingTransport.personalModel(request.models.stage1Model, providers: request.providers)
            let stage2 = try PersonalPlanRoutingTransport.personalModel(request.models.stage2Model, providers: request.providers)
            let usesPersonal = stage1 != nil || stage2 != nil
            guard usesPersonal, request.retainedDocument == nil else { pinned.append(request); continue }
            if let session = request.chatGPTSession {
                try await personalRuntime.validate(session)
                guard freshPin == nil || freshPin == session else { throw HostError("chatgpt_session_pin_conflict") }
                freshPin = session
            }
            else if case .description = request.authoring {
                if freshPin == nil { freshPin = try await personalRuntime.pin() }
                request.chatGPTSession = freshPin
            } else {
                // Local DDL compilation does not require an account. An explicit later hole action can bind one.
                if freshPin == nil { freshPin = try? await personalRuntime.pin() }
                request.chatGPTSession = freshPin
            }
            pinned.append(request)
        }
        return pinned
    }
    private func validatePinnedRequest(_ request: GenerationRequest) async throws {
        guard request.retainedDocument == nil else { return }
        let stage1 = try PersonalPlanRoutingTransport.personalModel(request.models.stage1Model, providers: request.providers)
        let stage2 = try PersonalPlanRoutingTransport.personalModel(request.models.stage2Model, providers: request.providers)
        let usesPersonal = stage1 != nil || stage2 != nil
        guard usesPersonal else { return }
        if let session = request.chatGPTSession { try await personalPlanRuntime().validate(session) }
        else if case .description = request.authoring { throw HostError("chatgpt_session_pin_required") }
    }

    public func clearPreview() async {
        guard !isBusy else { return }
        if let selectedWork { await selectWork(selectedWork) }
        else { newWork() }
    }

    public func savePreview() async {
        guard !isBusy, let previewWork, let executionID = currentExecutionID, let host else { return }
        _ = await performSerialized(status: "候補を保存中") { [weak self] _ in
            guard let self else { return }
            let saved = try await host.saveCandidate(executionID: executionID)
            await self.notifySavedWork(saved)
            guard saved.id == previewWork.id else { throw HostError("candidate_identity_changed") }
            try await self.reloadWorks()
            self.displayWork(saved)
            self.selectedContext = try await host.savedAuthoringContext(workID: saved.id)
            self.currentExecutionID = nil
            self.status = "選択した候補を保存しました"
        }
    }

    public func savedConfiguration(workID: String) async throws -> SavedAuthoringContext {
        guard let host else { throw HostError("pipeline_unavailable") }
        return try await host.savedAuthoringContext(workID: workID)
    }

    public func applyDDLImport(_ value: DDLPackageImport) throws {
        guard !isBusy, let bootstrap else { throw HostError("ddl_import_busy_or_unavailable") }
        let language = value.language ?? self.language
        let catalog = try bootstrap.macroCatalogValue(language: language, settings: settings, importedPlugins: value.plugins)
        newWork()
        importedDDL = value; importedMacroNames = value.names
        importedMacroNames += value.plugins.flatMap { plugin in
            guard let namespace = plugin.definition["namespace"].string else { return [String]() }
            return (plugin.definition["aliases"].array ?? []).compactMap(\.string).map { namespace + "." + $0 }
        }
        inputMode = "ddl"; ddlText = value.source; self.language = language
        macroDiagnostics = try Self.pretty(catalog.data)
        status = "DDLを読み込みました。生成して保存できます。"
    }

    public func requestForCurrentInput(inputMode: String? = nil, source: String? = nil, description: String? = nil,
                                      parentWorkID: String? = nil, derivationKind: String = "new") throws -> GenerationRequest {
        guard let bootstrap else { throw HostError("installation_unavailable") }
        let mode = inputMode ?? self.inputMode
        if parentWorkID != nil && mode == "description" && (selectedContext?.authority == "ddl_authoritative" || sourceLocked) { throw HostError("description_source_locked") }
        let sketch: SketchRequest = sketchMode == "on" ? .on : sketchMode == "supplied" ? .supplied(sketchText) : .off
        let savedConfig = parentWorkID == selectedWorkID && parentWorkID != nil ? selectedContext?.configuration : nil
        return try bootstrap.request(inputMode: mode, source: source ?? ddlText,
            description: description ?? descriptionText, language: language, catalogID: catalogID,
            canvasID: canvasID, seed: seedText, wild: wild, settings: nextGenerationHostSettings,
            parentWorkID: parentWorkID, derivationKind: derivationKind, catalogMode: catalogMode,
            sketch: sketch, savedConfiguration: savedConfig,
            importedPlugins: mode == "ddl" && parentWorkID == nil ? importedDDL?.plugins ?? [] : [])
    }

    public func makeRefinementRequest(work: SavedWork, kind: String, direction: String = "", amplitude: String = "medium",
                                      modelReference: String? = nil, catalogIDOverride: String? = nil,
                                      readDescription: Bool? = nil, wildOverride: Bool? = nil) async throws -> GenerationRequest {
        guard let bootstrap else { throw HostError("installation_unavailable") }
        guard ["touch_change", "layout_change", "catalog_change", "variation", "reinterpretation", "model_comparison"].contains(kind) else {
            throw HostError("unknown_refinement_kind")
        }
        let saved = try await savedConfiguration(workID: work.id)
        let config = try ExactJSON(data: saved.configuration)
        let options = try ExactJSON(data: saved.renderOptions)
        let held = saved.authority == "ddl_authoritative"
        let reading = readDescription ?? (kind == "reinterpretation" || kind == "model_comparison" || !direction.isEmpty && kind != "catalog_change")
        if held && (reading || kind == "model_comparison" || kind == "reinterpretation") { throw HostError("description_source_locked") }
        let language = work.instructionLangResolved ?? config["language"].string ?? self.language
        guard let renderSeed = work.renderSeed ?? options["render_seed"].string ?? options["render_seed"].number,
              let canvasID = work.renderCanvasAspectID ?? options["canvas_aspect_id"].string,
              let catalogID = work.renderColorCatalogID ?? work.catalogID ?? options["catalog_id"].string else {
            throw HostError("saved_refinement_options_unavailable")
        }
        let fresh = String(UInt64.random(in: 0...((UInt64(1) << 53) - 1)))
        let chosenRenderSeed = kind == "touch_change" ? fresh : renderSeed
        let chosenCatalog = catalogIDOverride ?? (kind == "catalog_change" ? direction : catalogID)
        let description = work.effectiveSourceText + (reading && !direction.isEmpty ? "\n" + direction : "")
        let sketch: SketchRequest = work.sketchText.map(SketchRequest.supplied) ?? .off
        var request = try bootstrap.request(inputMode: reading ? "description" : "ddl", source: work.ddl ?? "", description: description,
            language: language, catalogID: chosenCatalog, canvasID: canvasID, seed: chosenRenderSeed, wild: wildOverride ?? work.renderWild ?? false,
            settings: nextGenerationHostSettings, parentWorkID: work.id, derivationKind: kind, sketch: sketch,
            variationAmplitude: kind == "variation" ? amplitude : nil, variationSeed: kind == "variation" ? fresh : nil,
            savedConfiguration: saved.configuration)
        var nextConfig = try ExactJSON(data: request.configuration)
        var nextOptions = try ExactJSON(data: request.renderOptions)
        let composition: ExactJSON = kind == "layout_change" ? .string(fresh)
            : kind == "touch_change" ? config["compiler"]["composition_seed"] == .null ? .string(renderSeed) : config["compiler"]["composition_seed"]
            : config["compiler"]["composition_seed"]
        nextConfig["compiler"]["composition_seed"] = composition
        nextOptions["composition_seed"] = composition
        request.configuration = nextConfig.data; request.renderOptions = nextOptions.data
        if let modelReference {
            guard !modelReference.isEmpty else { throw HostError("model_reference_missing") }
            request.models.stage1Model = modelReference; request.models.stage2Model = modelReference
        }
        if !reading {
            guard let document = saved.document else { throw HostError("saved_document_unavailable") }
            request.retainedDocument = document; request.retainedAuthority = saved.authorityJSON
        }
        return request
    }

    public func makeDemoRequest(template: GenerationRequest, description: String, randomizeSeed: Bool) throws -> GenerationRequest {
        guard case .description(_, let auto, let sketch) = template.authoring,
              template.retainedDocument == nil else { throw HostError("demo_requires_description_template") }
        var request = template
        request.authoring = .description(description, autoCatalog: auto, sketch: sketch)
        request.description = description
        guard randomizeSeed else { return request }
        let seed = String(UInt64.random(in: 0...((UInt64(1) << 53) - 1)))
        var config = try ExactJSON(data: request.configuration)
        var options = try ExactJSON(data: request.renderOptions)
        func reseed(_ host: ExactJSON) throws -> ExactJSON {
            guard let id = host["resolved_catalog_id"].string, let map = request.renderColorMaps[id] else {
                throw HostError("resolved_catalog_render_map_required")
            }
            var next = host
            next["palette"] = try ExactJSON(data: InkuCore.resolvePalette(ExactJSON.object([
                "color_map": try ExactJSON(data: map), "catalog_id": .string(id), "render_seed": .string(seed), "background": host["background"],
            ]).data))
            if let error = next["palette"]["error"].string { throw HostError(error) }
            return next
        }
        config["compiler"]["host"] = try reseed(config["compiler"]["host"])
        config["compiler"]["composition_seed"] = .string(seed)
        if let catalogs = config["catalogs"].array {
            config["catalogs"] = .array(try catalogs.map { entry in
                var next = entry; next["resolved"] = try reseed(entry["resolved"]); return next
            })
        }
        options["render_seed"] = .string(seed); options["composition_seed"] = .string(seed)
        request.configuration = config.data; request.renderOptions = options.data
        return request
    }

    @discardableResult
    public func performComparison(status: String, operation: @escaping @MainActor (UUID) async throws -> Void) async -> Bool {
        let execution = currentExecutionID
        return await performSerialized(status: status) { [weak self] token in
            defer { self?.currentExecutionID = execution }
            try await operation(token)
        }
    }

    public func generateCandidate(request: GenerationRequest, token: UUID) async throws -> PreparedCandidate {
        guard generationToken == token, !stopping, let host else { throw CancellationError() }
        var request = request; request.saveHistory = false; request.historyVisibility = "normal"
        try await validatePinnedRequest(request)
        let view = try await host.generate(request) { [weak self] progress in
            Task { @MainActor in self?.receiveCandidate(progress, token: token) }
        }
        await recordDescriptionFeedback(request: request, view: view)
        try Task.checkCancellation()
        guard generationToken == token, let work = view.candidateWork else { throw HostError("comparison_candidate_requires_edit") }
        return PreparedCandidate(executionID: view.executionID, work: work, authority: view.authority)
    }

    public func previewCatalogCandidate(work: SavedWork, catalogID: String, token: UUID) async throws -> PreparedCandidate {
        guard generationToken == token, !stopping, let host, let bootstrap else { throw CancellationError() }
        let context = try await savedConfiguration(workID: work.id)
        let savedOptions = try ExactJSON(data: context.renderOptions)
        guard let canvasID = work.renderCanvasAspectID ?? savedOptions["canvas_aspect_id"].string else { throw HostError("saved_canvas_unavailable") }
        let options = try bootstrap.replayOptions(catalogID: catalogID, canvasID: canvasID)
        let candidate = try await host.previewReplay(workID: work.id, options: options, derivationKind: "catalog_change")
        try Task.checkCancellation()
        guard generationToken == token else { throw CancellationError() }
        return candidate
    }

    public func saveComparisonCandidate(executionID: String, token: UUID) async throws -> SavedWork {
        guard generationToken == token, !stopping, let host else { throw CancellationError() }
        let saved = try await host.saveCandidate(executionID: executionID)
        await notifySavedWork(saved)
        // The explicit transaction result remains authoritative if a later refresh is interrupted.
        do { try await reloadWorks() } catch { report(error) }
        return saved
    }

    /// The busy flag remains held until cancellation has drained the active task.
    @discardableResult
    public func performSerialized(status: String, operation: @escaping @MainActor (UUID) async throws -> Void) async -> Bool {
        guard !isBusy, activeOperation == nil, database != nil else { return false }
        let token = UUID()
        generationToken = token
        currentExecutionID = nil
        stopping = false
        isBusy = true
        errorText = nil
        self.status = status
        var succeeded = false
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                try await operation(token)
                if !Task.isCancelled { succeeded = true }
            } catch {
                if self.generationToken == token && !Task.isCancelled { self.report(error) }
            }
        }
        activeOperation = task
        await task.value
        finishOperation(token: token)
        return succeeded
    }

    public func runAutomation(request: GenerationRequest) async -> SavedWork? {
        guard let host else { return nil }
        var result: SavedWork?
        _ = await performSerialized(status: "生成中") { [weak self] token in
            guard let self else { return }
            try await self.validatePinnedRequest(request)
            let view = try await host.generate(request) { [weak self] progress in
                Task { @MainActor in self?.receive(progress, token: token) }
            }
            await self.recordDescriptionFeedback(request: request, view: view)
            await self.notifyCommittedWork(view)
            try Task.checkCancellation()
            self.apply(view)
            try await self.reloadWorks()
            if let id = view.savedWorkID, let work = try await self.database?.work(id: id) {
                self.displayWork(work)
                self.selectedContext = try await host.savedAuthoringContext(workID: id)
                if request.retainedDocument != nil {
                    // Retained compilation stores a completed candidate, not an editable core execution.
                    self.currentExecutionID = nil
                    self.currentView = nil
                }
                result = work
            } else if !request.saveHistory, let work = view.candidateWork {
                self.previewWork = work
                self.status = "未保存の候補を表示しています"
                result = work
            }
        }
        return result
    }

    public func newWork() {
        guard !isBusy else { return }
        selectedWork = nil
        selectedWorkID = nil
        previewWork = nil
        importedDDL = nil; importedMacroNames = []
        selectedContext = nil
        currentView = nil
        currentExecutionID = nil
        currentSVG = ""
        visibleDDL = ""
        scoreJSON = ""
        authoringAuthority = ""
        authoringOrigin = ""
        authoringRevision = "0"
        authoringPhase = ""
        patchProposalJSON = ""
        patchCandidate = ""
        holeIDs = []
        selectedHoleIDs = []
        diagnosticsJSON = ""
        promptJSON = ""
        eventsJSON = ""
        errorText = nil
        unreadOutputs = []
    }

    public func commitDDL() async {
        guard !isBusy, ddlText != visibleDDL else { return }
        if let id = currentExecutionID {
            await performCommand(executionID: id, command: .commitUserDDL(expectedRevision: authoringRevision, source: ddlText), kind: "ddl_edit")
        } else if selectedContext != nil {
            do {
                let request = try requestForCurrentInput(inputMode: "ddl", parentWorkID: selectedWorkID, derivationKind: "ddl_edit")
                _ = await runAutomation(request: request)
            } catch { report(error) }
        }
    }

    public func regenerateDescription() async {
        guard canRegenerateDescription, let id = currentExecutionID else { return }
        let sketch: SketchRequest = sketchMode == "on" ? .on : sketchMode == "supplied" ? .supplied(sketchText) : .off
        await performCommand(executionID: id, command: .generateFromDescription(expectedRevision: authoringRevision,
            description: descriptionText, autoCatalog: catalogMode == "auto", sketch: sketch), kind: "description_edit")
    }

    public func completeHoles() async {
        guard canCompleteHoles, let id = currentExecutionID else { return }
        let selected = selectedHoleIDs.isEmpty ? holeIDs : holeIDs.filter { selectedHoleIDs.contains($0) }
        await performCommand(executionID: id, command: .completeHoles(expectedRevision: authoringRevision, holeIDs: selected), kind: "ddl_edit")
    }

    public func approvePatch() async {
        guard !isBusy, let id = currentExecutionID,
              let bytes = patchProposalJSON.data(using: .utf8), let proposal = try? ExactJSON(data: bytes),
              let digest = proposal["proposal_digest"].string else { return }
        await performCommand(executionID: id, command: .approvePatch(expectedRevision: authoringRevision, proposalDigest: digest), kind: "ddl_edit")
    }

    public func declinePatch() async {
        guard !isBusy, let id = currentExecutionID,
              let bytes = patchProposalJSON.data(using: .utf8), let proposal = try? ExactJSON(data: bytes),
              let digest = proposal["proposal_digest"].string else { return }
        await performCommand(executionID: id, command: .declinePatch(proposalDigest: digest), kind: "ddl_edit")
    }

    private func performCommand(executionID: String, command: PipelineCommand, kind: String) async {
        guard let host else { return }
        let parentID = selectedWorkID
        _ = await performSerialized(status: "DDLを処理中") { [weak self] token in
            guard let self else { return }
            self.currentExecutionID = executionID
            let stage2: Bool?
            switch command {
            case .completeHoles: stage2 = true
            case .generateFromDescription: stage2 = false
            default: stage2 = nil
            }
            if let stage2 {
                let context = try await host.personalPlanContext(executionID: executionID, stage2: stage2)
                if context.required {
                    let runtime = try self.personalPlanRuntime()
                    let session: ChatGPTPlanSession
                    if let existing = context.session { try await runtime.validate(existing); session = existing }
                    else { session = try await runtime.pin() }
                    try await host.bindPersonalPlanSession(executionID: executionID, session: session)
                }
            }
            let view = try await host.perform(executionID: executionID, command: command, parentWorkID: parentID, derivationKind: kind) { [weak self] progress in
                Task { @MainActor in self?.receive(progress, token: token) }
            }
            if case .generateFromDescription(_, let description, _, _) = command {
                await self.recordDescriptionFeedback(description: description, view: view)
            }
            await self.notifyCommittedWork(view)
            try Task.checkCancellation()
            self.apply(view)
            try await self.reloadWorks()
            if let id = view.savedWorkID, let work = try await self.database?.work(id: id) {
                self.displayWork(work)
                self.selectedContext = try await host.savedAuthoringContext(workID: id)
            }
        }
    }

    public func varySelectedWork() async {
        guard !isBusy, !isPreview, let selectedWork else { return }
        do {
            var request = try await makeRefinementRequest(work: selectedWork, kind: "variation", amplitude: variationAmplitude)
            if !variationSeedText.isEmpty {
                guard let seed = UInt64(variationSeedText), String(seed) == variationSeedText else { throw HostError("invalid_variation") }
                var configuration = try ExactJSON(data: request.configuration)
                configuration["compiler"]["stage15_variation"]["seed"] = .string(variationSeedText)
                request.configuration = configuration.data
            }
            _ = await runAutomation(request: try await pinPersonalPlanRequests([request])[0])
        } catch { report(error) }
    }

    public func replayWithCurrentOptions() async {
        guard !isBusy, let work = selectedWork, let host, let bootstrap else { return }
        do {
            let seed = seedText.isEmpty ? String(UInt64.random(in: 0...((UInt64(1) << 53) - 1))) : seedText
            let options = try bootstrap.replayOptions(catalogID: catalogID, canvasID: canvasID)
            _ = await performSerialized(status: "再演奏中") { [weak self] _ in
                guard let self else { return }
                let result = try await host.replay(workID: work.id, renderSeed: seed, wild: self.wild, options: options)
                await self.notifySavedWork(result)
                try Task.checkCancellation()
                try await self.reloadWorks()
                self.displayWork(result)
                self.selectedContext = try await host.savedAuthoringContext(workID: result.id)
                self.currentView = nil
                self.currentExecutionID = nil
                self.status = "再演奏を保存しました"
            }
        } catch { report(error) }
    }

    public func checkDDL() async {
        guard !isBusy, let bootstrap else { return }
        do {
            let request = try requestForCurrentInput(inputMode: "ddl", parentWorkID: selectedWorkID, derivationKind: "ddl_edit")
            let config = try ExactJSON(data: request.configuration)
            let catalog = try bootstrap.macroCatalog(language: language, settings: settings, importedPlugins: importedDDL?.plugins ?? [])
            let entries = catalog["entries"] as? [[String: Any]] ?? []
            let locks = try Bootstrap.bytes(entries.map { item in
                ["qualified_name": item["qualified_name"]!, "version": item["version"]!, "digest": item["digest"]!, "aliases": item["aliases"] ?? []]
            })
            let locksJSON = try ExactJSON(data: locks)
            var document = selectedContext?.document.flatMap { try? ExactJSON(data: $0) } ?? .object([
                "source": .string(ddlText), "language": .string(language), "macro_locks": locksJSON, "saijiki": .string("inku.saijiki.v2"),
            ])
            document["source"] = .string(ddlText)
            let input = ExactJSON.object(["document": document, "definitions": config["definitions"], "compiler": config["compiler"]]).data
            let result = await Task.detached { InkuCore.compile(input) }.value
            diagnosticsJSON = try Self.pretty(result)
            unreadOutputs.insert("diagnostics")
            status = "DDLを検査しました（未確定）"
        } catch { report(error) }
    }

    public func markOutputRead(_ output: String) { unreadOutputs.remove(output) }

    public func prepareExportSources(works: [SavedWork], profile: String = "display", requiresPluginDefinitions: Bool = false) async throws -> [ExportSource] {
        guard !isBusy, let host else { throw HostError("export_busy_or_unavailable") }
        var sources: [ExportSource] = []
        for work in works {
            try Task.checkCancellation()
            var value: ExactJSON = .object([:])
            do { value = try ExactJSON(data: await host.savedAuthoringContext(workID: work.id).configuration) }
            catch {
                if profile != "display" || requiresPluginDefinitions { throw HostError("saved_export_plugin_context_unavailable") }
            }
            var profiles: [String: String] = [:]
            if profile != "display" { profiles[profile] = try await host.exportSVG(workID: work.id, profile: profile) }
            sources.append(ExportSource(work: work, profiles: profiles,
                pluginDefinitions: value["definitions"].array ?? [], pluginSummaries: value["macro_summaries"].array?.compactMap(\.string) ?? [],
                language: value["language"].string))
        }
        return sources
    }

    public func saveProvider() async {
        guard settingsStore != nil, let url = URL(string: providerURL),
              !providerModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            report(HostError("provider_settings_incomplete"))
            return
        }
        do {
            let kind: ProviderKind = providerKind == "mlx" ? .openAICompatible
                : ProviderKind(rawValue: providerKind) ?? .openAICompatible
            let provider = ProviderSettings(id: "local", kind: kind, baseURL: url,
                apiProfile: providerKind == "mlx" ? "mlx" : nil,
                requiresAPIKey: url.scheme == "https")
            try provider.validate()
            if !providerKey.isEmpty { try await credentials.setKey(providerKey, for: provider.credentialID) }
            let modelID = "local:\(providerModel)"
            var changed = settings
            if let index = changed.providers.firstIndex(where: { $0.id == provider.id }) { changed.providers[index] = provider }
            else { changed.providers.append(provider) }
            changed.models.stage1Model = modelID
            changed.models.stage2Model = modelID
            try await updateHostSettings(changed)
            providerKey = ""
            errorText = nil
            status = "接続設定を保存しました"
        } catch { report(error) }
    }

    @discardableResult
    public func backup(to url: URL) async -> Bool {
        guard let database else { return false }
        return await performComparison(status: "バックアップ中") { [weak self] _ in
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            try Task.checkCancellation()
            try await database.backup(to: url)
            try Task.checkCancellation()
            self?.status = "バックアップを保存しました"
        }
    }

    public func restore(from url: URL) async {
        guard !isBusy, activeOperation == nil, let database, let host else { return }
        isBusy = true
        defer { isBusy = false }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            try await host.cancelAll()
            try await database.restore(from: url)
            currentExecutionID = nil
            generationToken = nil
            try await reloadWorks()
            currentSVG = ""
            visibleDDL = ""
            scoreJSON = ""
            selectedWorkID = nil
            selectedWork = nil
            previewWork = nil
            importedDDL = nil; importedMacroNames = []
            selectedContext = nil
            currentView = nil
            status = "復元しました"
        } catch { report(error) }
    }

    public func exportSVG(to url: URL) async {
        guard let work = selectedWork else { return }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do { try Data(work.svg.utf8).write(to: url, options: .atomic); status = "SVGを書き出しました" }
        catch { report(error) }
    }

    public func exportPNG(to url: URL, height: UInt32) async {
        guard let work = selectedWork else { return }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            let raster = try await Task.detached {
                try InkuCore.rasterize(svg: work.svg, targetHeight: height)
            }.value
            guard let image = raster.makeCGImage() else { throw ArtworkError.imageUnavailable }
            guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
                throw HostError("png_destination_unavailable")
            }
            CGImageDestinationAddImage(destination, image, nil)
            guard CGImageDestinationFinalize(destination) else { throw HostError("png_encode_failed") }
            status = "PNGを書き出しました"
        } catch { report(error) }
    }

    public func copyImage() async {
        #if os(macOS)
        guard !isBusy, let work = selectedWork, !work.svg.isEmpty else { return }
        let executionID = currentExecutionID
        let height = display.preferences.clipboardHeight
        _ = await performSerialized(status: "コピー画像を準備中") { [weak self] _ in
            guard let self else { return }
            defer { self.currentExecutionID = executionID }
            var options = ExportOptions()
            options.format = .png
            options.pixelHeight = height
            let artifacts = try await ExportService.prepare(sources: [ExportSource(work: work)], options: options)
            try Task.checkCancellation()
            guard let data = artifacts.first?.data, let nativeImage = NSImage(data: data) else {
                throw HostError("clipboard_image_unavailable")
            }
            NSPasteboard.general.clearContents()
            guard NSPasteboard.general.writeObjects([nativeImage]) else { throw HostError("clipboard_write_failed") }
            self.status = "画像をコピーしました（Y軸 \(height)px）"
        }
        #endif
    }

    private func reloadWorks() async throws {
        guard let database else { return }
        works = try await database.list(limit: 100)
        if let id = selectedWorkID {
            if let saved = try await database.work(id: id) { selectedWork = saved }
            else {
                selectedWork = nil
                selectedWorkID = nil
                selectedContext = nil
                currentView = nil
                currentExecutionID = nil
                currentSVG = ""
                visibleDDL = ""
                scoreJSON = ""
            }
        }
        await library.refresh()
    }
    public func refreshWorks() async {
        do { try await reloadWorks() } catch { report(error) }
    }
    private func recordDescriptionFeedback(request: GenerationRequest, view: PipelineView) async {
        guard request.retainedDocument == nil, case .description(let description, _, _) = request.authoring else { return }
        await recordDescriptionFeedback(description: description, view: view)
    }
    private func recordDescriptionFeedback(description: String, view: PipelineView) async {
        guard let database, let ddl = view.visibleDDL, view.candidateWork != nil || view.savedWorkID != nil else { return }
        do {
            try await Task { @MainActor in try await DescriptionFeedback.record(description: description, ddl: ddl, database: database) }.value
        } catch { errorText = "作品は生成されましたが、未読語の記録に失敗しました: \(error.localizedDescription)" }
    }
    private func notifyCommittedWork(_ view: PipelineView) async {
        guard let id = view.savedWorkID else { return }
        if let work = view.candidateWork, work.id == id { await notifySavedWork(work) }
        else if let work = try? await database?.work(id: id) { await notifySavedWork(work) }
    }
    private func notifySavedWork(_ work: SavedWork) async {
        guard let callback = onSavedWork else { return }
        // A separate task makes the committed snapshot independent of later caller cancellation.
        await Task { @MainActor in await callback(work) }.value
    }
    private func receive(_ progress: PipelineProgress, token: UUID) {
        guard generationToken == token, !stopping else { return }
        switch progress {
        case .changed(let view): apply(view)
        case .providerAttempt(_, _, _, let deadline):
            status = "モデルの応答待ち（期限 \(deadline.formatted(date: .omitted, time: .standard))）"
        case .transportBytes(_, let count): status = "応答を受信中（\(count) bytes）"
        case .providerDiagnostic(_, let diagnostic): errorText = "ChatGPTプラン: \(diagnostic.code)（\(diagnostic.action)）"
        case .saved(_, _): status = "作品を保存しました"
        }
    }
    private func receiveCandidate(_ progress: PipelineProgress, token: UUID) {
        guard generationToken == token, !stopping else { return }
        switch progress {
        case .changed(let view): currentExecutionID = view.executionID
        case .providerAttempt(_, _, _, let deadline): status = "比較候補のモデル応答待ち（期限 \(deadline.formatted(date: .omitted, time: .standard))）"
        case .transportBytes(_, let count): status = "比較候補を受信中（\(count) bytes）"
        case .providerDiagnostic(_, let diagnostic): errorText = "ChatGPTプラン: \(diagnostic.code)（\(diagnostic.action)）"
        case .saved: break
        }
    }
    private func apply(_ view: PipelineView) {
        currentView = view
        currentExecutionID = view.executionID
        if let ddl = view.visibleDDL, ddl != visibleDDL {
            visibleDDL = ddl
            ddlText = ddl
            unreadOutputs.insert("ddl")
        }
        if let svg = view.svg { currentSVG = svg }
        if let score = view.scoreJSON {
            let value = String(decoding: score, as: UTF8.self)
            if value != scoreJSON { scoreJSON = value; unreadOutputs.insert("score") }
        }
        authoringRevision = view.revision
        authoringAuthority = view.authority
        authoringOrigin = view.origin
        authoringPhase = view.phase
        holeIDs = view.holeIDs
        selectedHoleIDs.formIntersection(Set(holeIDs))
        patchProposalJSON = view.patchProposalJSON.map { (try? Self.pretty($0)) ?? String(decoding: $0, as: UTF8.self) } ?? ""
        if let bytes = view.patchProposalJSON, let proposal = try? ExactJSON(data: bytes) {
            patchCandidate = proposal["candidate"]["source"].string ?? ""
        } else { patchCandidate = "" }
        if let bytes = view.deliveryJSON {
            let newDiagnostics = (try? Self.pretty(bytes)) ?? String(decoding: bytes, as: UTF8.self)
            if newDiagnostics != diagnosticsJSON { diagnosticsJSON = newDiagnostics; unreadOutputs.insert("diagnostics") }
        }
        if let bytes = view.promptJSON {
            let prompt = (try? Self.pretty(bytes)) ?? String(decoding: bytes, as: UTF8.self)
            if prompt != promptJSON { promptJSON = prompt; unreadOutputs.insert("prompt") }
        }
        eventsJSON = (try? Self.pretty(view.eventsJSON)) ?? String(decoding: view.eventsJSON, as: UTF8.self)
        status = [
            "authoring_started": "生成を開始しました", "awaiting_llm": "モデルの応答待ち",
            "awaiting_visible_ddl_commit": "DDLを確認しています", "awaiting_patch_approval": "補完案の承認待ち",
            "score_ready": "描画中", "completed": "生成を完了しました",
            "needs_user_edit": "DDLを編集してください", "failed": "生成できませんでした",
            "cancelled": "停止しました",
        ][view.phase] ?? "処理中"
    }
    private func report(_ error: Error) {
        errorText = error.localizedDescription
        status = "処理を完了できませんでした"
    }
    private static func pretty(_ bytes: Data) throws -> String {
        let value = try ExactJSON(data: bytes)
        // Pretty formatting may round JSON numbers; retain exact wire lexemes in the displayed output.
        return value.text
    }
}
