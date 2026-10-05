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

/// The sketch prose of one saved work as the author is editing it, and the description it was written for.
public struct SketchDraft: Sendable, Equatable {
    public let workID: String
    public let source: String
    public let original: String
    public var text: String
    public var editing = true
    public init(workID: String, source: String, original: String) {
        self.workID = workID; self.source = source; self.original = original; text = original
    }
}

/// Availability of the author-facing prompt journal, independent of whether a provider was called.
public enum PromptAvailability: Sendable, Equatable {
    case loading, recorded, notRecorded, unavailable
}

/// A complete, immutable adjustment snapshot. Views display model facts but never interpret its operation.
public struct DrawingAdjustmentPlan: Sendable {
    public let stage1Model: String?
    public let stage2Model: String?
    fileprivate let parent: SavedWork
    fileprivate let operation: Operation
    fileprivate enum Operation: Sendable {
        case replay(SavedScoreReplayPlan)
        case author(GenerationRequest)
    }
}

@MainActor
@Observable
public final class AppModel {
    public var inputMode = "description"
    public var descriptionText = ""
    public var ddlText = ""
    /// The Web always requests `auto`; an explicit language remains possible for restored inputs.
    public var language = "auto"
    public var catalogID = "default" { didSet { rememberNextConditions() } }
    public var canvasID = "square" { didSet { rememberNextConditions() } }
    public var seedText = ""
    public var wild = false { didSet { rememberNextConditions() } }
    public var catalogMode = "fixed" { didSet { rememberNextConditions() } }
    public var sketchMode = "off"
    public var sketchText = ""
    /// Web `sketchDraft`/`sketchEditing`: the author's edit of the displayed work's sketch prose. Drawing that work's
    /// description again with the sketch on sends the edited prose instead of calling the layer (I8).
    public var sketchDraft: SketchDraft?
    public var variationAmplitude = "small"
    public var variationSeedText = ""
    public var selectedHoleIDs: Set<String> = []
    public private(set) var works: [SavedWork] = []
    public private(set) var restorationRevision: UInt64 = 0
    public private(set) var selectedWorkID: String?
    public private(set) var selectedWork: SavedWork?
    public private(set) var previewWork: SavedWork?
    public private(set) var currentSVG = ""
    public private(set) var visibleDDL = ""
    public private(set) var scoreJSON = ""
    public private(set) var status = "準備中"
    public private(set) var providerProgress: ProviderProgressSnapshot?
    /// Metrics of the displayed saved work, frozen to that work's save identity.
    public private(set) var providerMetrics: [ProviderAttemptMetric] = []
    public private(set) var isBusy = false
    /// Failure of this automation request, independent of errors from concurrent browsing.
    public private(set) var automationFailureMessage: String?
    /// Retained between batch rows so browsing does not clear the last row's progress or failure.
    private var backgroundDrawing = false
    /// Browsing may continue during an explicitly backgrounded batch row; writers still use isBusy.
    public var isBrowsingLocked: Bool { isBusy && !backgroundDrawing }
    public var errorText: String?
    /// Web CanvasPanel `clipboardMessage`: the copy button names the result, 2.5 s after success and 8 s after a failure.
    public private(set) var clipboardMessageKey: String?
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
    public private(set) var productReference: ProductReference?
    public private(set) var drawingLimitDefinition: DrawingLimitDefinition?
    public private(set) var importedMacroNames: [String] = []
    public private(set) var macroDiagnostics = ""
    public private(set) var authoringRevision = "0"
    public private(set) var authoringAuthority = ""
    public private(set) var authoringOrigin = ""
    public private(set) var authoringPhase = ""
    public private(set) var diagnosticsJSON = ""
    public private(set) var promptJSON = ""
    public private(set) var promptAvailability: PromptAvailability = .notRecorded
    public private(set) var eventsJSON = ""
    public private(set) var holeIDs: [String] = []
    public private(set) var patchProposalJSON = ""
    public private(set) var patchCandidate = ""
    public private(set) var unreadOutputs: Set<String> = []
    private var workActionStates: [String: SavedWorkActionState] = [:]
    public let library = LibraryModel()
    public let display = DisplaySettings()
    public let descriptionMeter = DescriptionMeterModel()
    public let renderer = ArtworkRenderer()
    @ObservationIgnored public var onSavedWork: (@MainActor (SavedWork) async -> Void)?
    @ObservationIgnored public var onDrawingLog: (@MainActor (DrawingLogRecord) async -> Void)?
    public let versionSummary: String = {
        let report = try? JSONSerialization.jsonObject(with: Data(InkuCore.versionReport.utf8)) as? [String: String]
        return "共通コア接続 \(report?["binding_version"] ?? "不明") · 描画接続 \(InkuCore.rasterAPIVersion)"
    }()

    @ObservationIgnored private let databaseURL: URL?
    @ObservationIgnored private let transport: (any ProviderTransport)?
    @ObservationIgnored private var managedTransport: (any ProviderTransport)?
    @ObservationIgnored private var personalRuntime: ChatGPTPlanRuntime?
    @ObservationIgnored private let credentials = KeychainCredentialStore()
    @ObservationIgnored private var database: InkuDatabase?
    @ObservationIgnored private var host: PipelineHost?
    @ObservationIgnored private var settingsStore: ProviderSettingsStore?
    @ObservationIgnored private var settings = HostSettings()
    @ObservationIgnored private var bootstrap: Bootstrap?
    /// Cancellation targets the active task, independently of the saved work being viewed.
    @ObservationIgnored private var activeExecutionID: String?
    @ObservationIgnored private var currentExecutionID: String?
    @ObservationIgnored private var displayToken = UUID()
    @ObservationIgnored private var generationToken: UUID?
    @ObservationIgnored private var activeOperation: Task<Void, Never>?
    @ObservationIgnored private var stopping = false
    @ObservationIgnored private var initialized = false
    @ObservationIgnored private var selectedContext: SavedAuthoringContext?
    @ObservationIgnored private var currentView: PipelineView?
    @ObservationIgnored private var importedDDL: DDLPackageImport?
    @ObservationIgnored private var providerModelsByExecution: [String: ModelSelection] = [:]
    /// Set once the saved next-work conditions have been read, so the defaults never overwrite them.
    @ObservationIgnored private var nextConditionsRestored = false

    public init(databaseURL: URL? = nil, transport: (any ProviderTransport)? = nil) {
        self.databaseURL = databaseURL
        self.transport = transport
    }

    public var sourceLocked: Bool { authoringAuthority == "ddl_authoritative" }
    public var developerModeEnabled: Bool { ProviderObservationPolicy.developerModeEnabled }
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
    public var canCommitDDL: Bool { !isBusy && !isPreview && !ddlText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && (currentExecutionID != nil || selectedContext != nil) }
    public var canEditCurrentDDL: Bool { !isBusy && !isPreview && (currentExecutionID != nil || selectedContext != nil) }
    public var canCompleteHoles: Bool { !isBusy && currentExecutionID != nil && !holeIDs.isEmpty && !settings.providers.isEmpty && ddlText == visibleDDL }
    public var canRegenerateDescription: Bool { !isBusy && !sourceLocked && currentExecutionID != nil && !settings.providers.isEmpty && !descriptionText.isEmpty }
    public var hasAvailableNextDrawingModel: Bool {
        hasNextDrawingModel && SettingsModel.isModelAvailable(nextDrawingModelReference, settings: settings)
    }
    public var hasAvailableBatchDrawingModel: Bool {
        SettingsModel.isBatchModelAvailable(nextDrawingModelReference, settings: settings)
    }
    public var nextBatchDrawingModelReference: String {
        hasAvailableBatchDrawingModel ? nextDrawingModelReference : ""
    }
    /// A description is drawable only when something is left once the author's numbers and comments are cut
    /// (Web `canSubmit`, state.svelte.ts:363-364).
    public var canGenerate: Bool {
        database != nil && !isBusy && !isPreview
            && (inputMode == "ddl" ? !ddlText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                   : DescriptionLabels.hasDrawableText(descriptionText))
            && (inputMode == "ddl" || (hasAvailableNextDrawingModel
                && !(selectedWorkID != nil && sourceLocked)))
    }
    public var canGenerateDescription: Bool {
        database != nil && !isBusy && !isPreview && hasAvailableNextDrawingModel
            && DescriptionLabels.hasDrawableText(descriptionText)
            && !(selectedWorkID != nil && sourceLocked)
    }
    /// Web `forkPipelineDescription`: a work its edited DDL holds is drawn from its description only as a new work.
    public var canForkDescription: Bool {
        database != nil && !isBusy && !isPreview && hasAvailableNextDrawingModel
            && DescriptionLabels.hasDrawableText(descriptionText) && selectedWorkID != nil && sourceLocked
    }

    /// The Server forks the held variation (`fork-description`) as a `description_fork` child; this host refuses a
    /// description request under a held parent, so the description starts an independent new work instead.
    public func forkDescription() async {
        guard canForkDescription else { return }
        inputMode = "description"
        await generate(parentWorkID: nil)
    }

    /// R6: the next drawing model's service needs an API key and none is stored. Read only when a screen asks,
    /// so checks that build an AppModel never query the Keychain.
    public func drawingModelKeyMissing() async -> Bool {
        guard initialized, hasNextDrawingModel,
              let provider = settings.providers.first(where: { nextDrawingModelReference.hasPrefix($0.id + ":") }),
              provider.requiresAPIKey else { return false }
        return (try? await credentials.isConfigured(for: provider.credentialID)) == false
    }

    public func generateDescription() async {
        guard canGenerateDescription else { return }
        inputMode = "description"
        await generate()
    }

    public func initialize() async {
        guard !initialized else { return }
        initialized = true
        do {
            let url = try databaseURL ?? InkuDatabase.applicationSupportURL(hostIdentifier: "app.inku.macos")
            let database = try InkuDatabase(url: url)
            let store = ProviderSettingsStore(url: url.deletingLastPathComponent().appendingPathComponent("providers.json"))
            let bootstrap = try Bootstrap()
            let settings = try await store.load(installingDefaults: BundledProviderDefaults.loadBundled())
            self.database = database
            let personalRuntime = ChatGPTPlanRuntime(directory: url.deletingLastPathComponent().appendingPathComponent("personal-chatgpt", isDirectory: true))
            let ordinary: any ProviderTransport
            if let native = transport as? URLSessionProviderTransport { ordinary = native.withRateDatabase(database) }
            else { ordinary = transport ?? URLSessionProviderTransport(database: database) }
            let routed = PersonalPlanRoutingTransport(ordinary: ordinary, runtime: personalRuntime)
            self.personalRuntime = personalRuntime
            self.managedTransport = routed
            self.host = PipelineHost(database: database, transport: routed, credentials: credentials)
            self.settingsStore = store
            self.settings = settings
            synchronizeNextDrawingModel(previousSettings: nil)
            self.bootstrap = bootstrap
            self.productReference = bootstrap.productReference
            self.drawingLimitDefinition = bootstrap.drawingLimitDefinition
            display.connect(directory: url.deletingLastPathComponent())
            descriptionMeter.connect(directory: url.deletingLastPathComponent())
            self.catalogs = bootstrap.catalogs
            self.canvases = bootstrap.canvases
            restoreNextConditions()
            self.saijiki = bootstrap.saijiki
            self.pluginWords = bootstrap.pluginWords.filter { settings.plugins?.isEnabled($0.packageID ?? "") ?? true }
            let macro = try bootstrap.macroCatalog(language: instructionLanguage(for: currentInputText), settings: settings)
            self.macroDiagnostics = try Self.pretty(try Bootstrap.bytes(macro))
            library.onMutation = { [weak self] in await self?.refreshWorks() }
            // Web `inku-history-display-mode` and the thumbnail/list tab come back with the library.
            if let layout = display.preferences.libraryLayout.flatMap(LibraryLayout.init(rawValue:)), layout != .lineage {
                library.layout = layout
            }
            if let grouped = display.preferences.libraryGrouped { library.grouped = grouped }
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

    public func generate() async { await generate(parentWorkID: selectedWorkID) }

    private func generate(parentWorkID: String?) async {
        guard canGenerate || (parentWorkID == nil && canForkDescription), let host, let bootstrap else { return }
        let token = UUID()
        generationToken = token
        providerProgress = nil
        activeExecutionID = nil
        currentExecutionID = nil
        backgroundDrawing = false
        stopping = false
        isBusy = true
        errorText = nil
        status = "生成中"
        let operation = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.runGeneration(host: host, bootstrap: bootstrap, token: token, parentWorkID: parentWorkID)
        }
        activeOperation = operation
        await operation.value
        finishOperation(token: token)
    }

    private func runGeneration(host: PipelineHost, bootstrap: Bootstrap, token: UUID, parentWorkID: String?) async {
        do {
            let freshRequest = try requestForCurrentInput(parentWorkID: parentWorkID,
                derivationKind: parentWorkID == nil ? "new" : inputMode == "ddl" ? "ddl_edit" : "description_edit")
            let request = try await pinPersonalPlanRequests([freshRequest])[0]
            let view = try await host.generate(request) { [weak self] progress in
                Task { @MainActor in self?.receive(progress, token: token, models: request.models) }
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
        providerProgress?.finish(.cancelled, at: Date())
        status = "停止中"
        let executionID = activeExecutionID
        operation.cancel()
        if let id = executionID, let host {
            do { _ = try await host.cancel(executionID: id) }
            catch { report(error) }
        }
        await operation.value
        if let id = executionID { recordDrawingLog(executionID: id) }
    }

    public func selectWork(_ work: SavedWork) async {
        guard !isBrowsingLocked else { return }
        if !backgroundDrawing {
            providerProgress = nil
            errorText = nil
        }
        displayWork(work, loadSelectedAnnotation: false)
        let selectionToken = displayToken
        currentExecutionID = nil
        currentView = nil
        selectedContext = nil
        holeIDs = []
        selectedHoleIDs = []
        patchProposalJSON = ""
        patchCandidate = ""
        diagnosticsJSON = ""
        promptJSON = ""
        promptAvailability = .loading
        unreadOutputs.remove("prompt")
        eventsJSON = ""
        await library.loadSelectedAnnotation(workID: work.id)
        guard displayToken == selectionToken, selectedWorkID == work.id, !isBrowsingLocked else { return }
        guard let host else { promptAvailability = .unavailable; return }
        let recordedMetrics = (try? await host.savedProviderMetrics(workID: work.id)) ?? []
        guard displayToken == selectionToken, selectedWorkID == work.id, !isBrowsingLocked else { return }
        providerMetrics = recordedMetrics
        do {
            let context = try await host.savedAuthoringContext(workID: work.id)
            guard displayToken == selectionToken, selectedWorkID == work.id, !isBrowsingLocked else { return }
            selectedContext = context
            authoringAuthority = context.authority
            authoringOrigin = context.origin
            authoringRevision = context.revision
            authoringPhase = "completed"
            let presentation = try await host.savedWorkPresentation(workID: work.id)
            guard displayToken == selectionToken, selectedWorkID == work.id, !isBrowsingLocked else { return }
            promptJSON = try presentation.promptJSON.map(Self.pretty) ?? ""
            promptAvailability = presentation.promptJSON == nil ? .notRecorded : .recorded
            diagnosticsJSON = try presentation.diagnosticsJSON.map(Self.pretty) ?? ""
            eventsJSON = try presentation.eventsJSON.map(Self.pretty) ?? ""
        } catch {
            guard displayToken == selectionToken, selectedWorkID == work.id, !isBrowsingLocked else { return }
            promptAvailability = .unavailable
            authoringAuthority = "legacy_unknown"
            authoringOrigin = work.ddlSourceOrigin ?? "legacy_unknown"
            authoringRevision = "0"
            authoringPhase = "saved"
            diagnosticsJSON = "この保存作品には編集用の共通コア設定がありません。保存された画像とScoreを表示しています。"
        }
    }

    private func displayWork(_ work: SavedWork, loadSelectedAnnotation: Bool = true) {
        displayToken = UUID()
        let selectionToken = displayToken
        importedDDL = nil; importedMacroNames = []
        previewWork = nil
        selectedWorkID = work.id
        selectedWork = work
        // Web `adoptSketch`: another work on screen brings its own prose; an edit belongs to the work it was made on.
        if sketchDraft?.workID != work.id { sketchDraft = nil }
        if loadSelectedAnnotation {
            Task { @MainActor [weak self] in
                guard let self, self.displayToken == selectionToken,
                      self.selectedWorkID == work.id, self.previewWork == nil else { return }
                await self.library.loadSelectedAnnotation(workID: work.id)
            }
        }
        if currentView?.savedWorkID != work.id {
            promptJSON = ""
            promptAvailability = .unavailable
            unreadOutputs.remove("prompt")
        }
        providerMetrics = currentView?.savedWorkID == work.id ? currentView?.providerMetrics ?? [] : []
        if currentView?.savedWorkID != work.id, let host {
            Task { @MainActor [weak self] in
                let metrics = (try? await host.savedProviderMetrics(workID: work.id)) ?? []
                guard let self, self.displayToken == selectionToken, self.selectedWorkID == work.id,
                      self.previewWork == nil, !self.isBrowsingLocked else { return }
                self.providerMetrics = metrics
            }
        }
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
        providerProgress = nil
        activeExecutionID = nil
        currentExecutionID = nil
        backgroundDrawing = false
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
        if stopping || activeOperation?.isCancelled == true { providerProgress?.finish(.cancelled, at: Date()) }
        else if providerProgress?.outcome == .running { providerProgress?.finish(.succeeded, at: Date()) }
        if stopping { status = "停止しました" }
        activeOperation = nil
        activeExecutionID = nil
        generationToken = nil
        stopping = false
        isBusy = false
    }

    public func localDataDirectory() -> URL? { database?.url.deletingLastPathComponent() }
    /// The database file in use, once opened.
    public var databaseFileURL: URL? { database?.url }

    public func hostSettings() async -> HostSettings { settings }

    public func nextGenerationSettings() async -> HostSettings { nextGenerationHostSettings }

    public func selectNextDrawingModel(_ reference: String) {
        guard !isBusy, SettingsModel.isModelAvailable(reference, settings: settings) else { return }
        nextDrawingModelReference = reference
    }

    public func selectSharedDrawingModel(_ reference: String) async throws {
        guard !isBusy, SettingsModel.isModelAvailable(reference, settings: settings) else { throw HostError("drawing_model_not_available") }
        var changed = settings
        changed.models.stage1Model = reference
        changed.models.stage2Model = reference
        try await updateHostSettings(changed)
        nextDrawingModelReference = reference
    }

    /// The DDL and adjustment pickers save Stage 2 immediately; the shared next-work picker is a draft.
    public func selectDdlDrawingModel(_ reference: String) async throws {
        guard !isBusy, SettingsModel.isModelAvailable(reference, settings: settings) else { throw HostError("drawing_model_not_available") }
        let next = nextDrawingModelReference
        var changed = settings
        changed.models.stage2Model = reference
        try await updateHostSettings(changed)
        nextDrawingModelReference = next
    }

    public func selectDemoDrawingModel(stage: Int, reference: String) async throws {
        guard !isBusy, [1, 2].contains(stage), SettingsModel.isBatchModelAvailable(reference, settings: settings) else {
            throw HostError("drawing_model_not_available")
        }
        let next = nextDrawingModelReference
        var changed = settings
        if stage == 1 { changed.models.stage1Model = reference }
        else { changed.models.stage2Model = reference }
        try await updateHostSettings(changed)
        nextDrawingModelReference = next
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
        guard !isBrowsingLocked, let settingsStore,
              !isBusy || settings.plugins == self.settings.plugins else { throw HostError("settings_busy_or_unavailable") }
        var settings = settings
        if self.settings.providerDefaultsInstalled == true { settings.providerDefaultsInstalled = true }
        if let limits = settings.drawingLimits {
            guard let drawingLimitDefinition else { throw HostError("installation_unavailable") }
            settings.drawingLimits = drawingLimitDefinition.normalized(limits)
        }
        if let limits = settings.operationalLimits {
            let maximum = try operationalLimitDefaults()
            guard limits.allSatisfy({ key, value in maximum[key].map { value <= $0 } ?? false }) else {
                throw HostError("invalid_operational_limits")
            }
        }
        let diagnostics = try bootstrap.map { try Self.pretty($0.macroCatalogValue(language: instructionLanguage(for: currentInputText), settings: settings, importedPlugins: importedDDL?.plugins ?? []).data) }
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

    public func drawingLimits() throws -> [String: UInt32] {
        guard let drawingLimitDefinition else { throw HostError("installation_unavailable") }
        return drawingLimitDefinition.normalized(settings.drawingLimits)
    }

    public func updateDrawingLimits(_ limits: [String: UInt32]) async throws {
        var changed = settings
        changed.drawingLimits = limits
        try await updateHostSettings(changed)
    }

    public func setCredential(_ key: String?, credentialID: String) async throws {
        guard !isBusy else { throw HostError("settings_busy_or_unavailable") }
        try await credentials.setKey(key, for: credentialID)
    }

    public func auxiliaryProvider() throws -> AuxiliaryProvider {
        guard let selectedTransport = managedTransport ?? transport,
              let auxiliaryTransport = selectedTransport as? any AuxiliaryTransport else { throw HostError("auxiliary_transport_unavailable") }
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
            if request.provenance?.uiLanguage == nil {
                request.provenance?.uiLanguage = display.preferences.language
            }
            if request.captureProviderIO == nil {
                request.captureProviderIO = developerModeEnabled && display.preferences.captureProviderIO == true
            }
            if request.models.includeThinking == nil { request.models.includeThinking = display.preferences.includeThinking }
            if request.captureProviderIO == true, !developerModeEnabled {
                throw HostError("developer_provider_observations_not_available")
            }
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
        if request.captureProviderIO == true, !developerModeEnabled {
            throw HostError("developer_provider_observations_not_available")
        }
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
        let context = try await host.savedAuthoringContext(workID: workID)
        workActionStates[workID] = SavedWorkActionState(context)
        return context
    }

    func savedGenerationInformation(work: SavedWork) async throws -> SavedGenerationInformation {
        guard let host, let database else { throw HostError("pipeline_unavailable") }
        var presentation: SavedWorkPresentation?
        var context: SavedAuthoringContext?
        var metrics: [ProviderAttemptMetric] = []
        do {
            presentation = try await host.savedWorkPresentation(workID: work.id)
            metrics = try await host.savedProviderMetrics(workID: work.id)
            context = try await host.savedAuthoringContext(workID: work.id)
        } catch let error as HostError where ["saved_performance_context_unavailable", "saved_authoring_context_unavailable"].contains(error.code) {
            // Old work can retain its own Score/SVG without a compiler/prompt journal.
        }
        let nodeID = work.lineageNodeID ?? work.id
        let generations = try await database.lineageGenerations(nodeIDs: [nodeID])
        let edge = try await database.edge(childNodeID: nodeID)
        let annotation = try await database.libraryAnnotation(id: work.id)
        return SavedGenerationInformation(presentation: presentation, context: context, metrics: metrics,
            generation: generations[nodeID], edge: edge, annotation: annotation)
    }

    public func workActionState(for work: SavedWork) -> SavedWorkActionState? {
        if let state = workActionStates[work.id] { return state }
        if selectedWorkID == work.id, let selectedContext { return SavedWorkActionState(selectedContext) }
        return nil
    }

    public func loadWorkActionState(_ work: SavedWork) async {
        guard workActionStates[work.id] == nil else { return }
        do { _ = try await savedConfiguration(workID: work.id) }
        catch { workActionStates[work.id] = .unavailable }
    }

    public func applyDDLImport(_ value: DDLPackageImport) throws {
        guard !isBusy, let bootstrap else { throw HostError("ddl_import_busy_or_unavailable") }
        let language = value.language ?? instructionLanguage(for: value.source)
        let catalog = try bootstrap.macroCatalogValue(language: language, settings: settings, importedPlugins: value.plugins)
        newWork()
        importedDDL = value; importedMacroNames = value.names
        importedMacroNames += value.plugins.flatMap { plugin in
            guard let namespace = plugin.definition["namespace"].string else { return [String]() }
            return (plugin.definition["aliases"].array ?? []).compactMap(\.string).map { namespace + "." + $0 }
        }
        inputMode = "ddl"; ddlText = value.source
        macroDiagnostics = try Self.pretty(catalog.data)
        status = "DDLを読み込みました。生成して保存できます。"
    }

    public func requestForCurrentInput(inputMode: String? = nil, source: String? = nil, description: String? = nil,
                                      parentWorkID: String? = nil, derivationKind: String = "new",
                                      catalogModeOverride: String? = nil, sketchOverride: SketchRequest? = nil,
                                      wildOverride: Bool? = nil) throws -> GenerationRequest {
        guard let bootstrap else { throw HostError("installation_unavailable") }
        let mode = inputMode ?? self.inputMode
        if mode == "description", !SettingsModel.isModelAvailable(nextDrawingModelReference, settings: settings) {
            throw HostError("drawing_model_not_available")
        }
        if parentWorkID != nil && mode == "description" && (selectedContext?.authority == "ddl_authoritative" || sourceLocked) { throw HostError("description_source_locked") }
        let sketch: SketchRequest = sketchOverride
            ?? editedSketch(parentWorkID: parentWorkID, mode: mode, description: description ?? descriptionText)
            ?? (sketchMode == "on" ? .on : sketchMode == "supplied" ? .supplied(sketchText) : .off)
        let savedConfig = parentWorkID == selectedWorkID && parentWorkID != nil ? selectedContext?.configuration : nil
        var request = try bootstrap.request(inputMode: mode, source: source ?? ddlText,
            description: description ?? descriptionText,
            language: instructionLanguage(for: mode == "ddl" ? source ?? ddlText : description ?? descriptionText), catalogID: catalogID,
            canvasID: canvasID, seed: seedText, wild: wildOverride ?? wild, settings: mode == "ddl" ? settings : nextGenerationHostSettings,
            parentWorkID: parentWorkID, derivationKind: derivationKind, catalogMode: catalogModeOverride ?? catalogMode,
            sketch: sketch, savedConfiguration: savedConfig,
            importedPlugins: mode == "ddl" && parentWorkID == nil ? importedDDL?.plugins ?? [] : [])
        request.captureProviderIO = developerModeEnabled && display.preferences.captureProviderIO == true
        return request
    }

    /// Web `sketchTextFor`: prose written for this very description, as the author left it. Unedited prose is not
    /// sent, so an ordinary redraw still asks the layer as before.
    private func editedSketch(parentWorkID: String?, mode: String, description: String) -> SketchRequest? {
        guard mode == "description", sketchMode == "on", let draft = sketchDraft, draft.workID == parentWorkID,
              draft.text != draft.original, !draft.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              draft.source.trimmingCharacters(in: .whitespacesAndNewlines) == description.trimmingCharacters(in: .whitespacesAndNewlines)
        else { return nil }
        return .supplied(draft.text)
    }

    public func requestForBatchDescription(_ description: String, sketchMode: String) throws -> GenerationRequest {
        guard hasAvailableBatchDrawingModel else { throw HostError("drawing_model_not_available") }
        guard ["off", "on"].contains(sketchMode) else { throw HostError("invalid_batch_sketch_mode") }
        return try requestForCurrentInput(inputMode: "description", source: "", description: description,
            parentWorkID: nil, derivationKind: "new", catalogModeOverride: catalogMode == "auto" ? "auto" : "fixed",
            sketchOverride: sketchMode == "on" ? .on : .off)
    }

    public func requestForDemoDescription(_ description: String, sketchMode: String) throws -> GenerationRequest {
        guard let bootstrap, ["off", "on"].contains(sketchMode),
              SettingsModel.isBatchModelAvailable(settings.models.stage1Model, settings: settings) else {
            throw HostError("drawing_model_not_available")
        }
        return try bootstrap.request(inputMode: "description", source: "", description: description,
            language: instructionLanguage(for: description), catalogID: catalogID, canvasID: canvasID, seed: seedText, wild: wild,
            settings: settings, parentWorkID: nil, derivationKind: "new",
            catalogMode: catalogMode == "auto" ? "auto" : "fixed", sketch: sketchMode == "on" ? .on : .off)
    }

    public func drawNewDDL(_ source: String, imported: DDLPackageImport? = nil) async -> Bool {
        guard !isBusy, let bootstrap, !source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        do {
            var request = try bootstrap.request(inputMode: "ddl", source: source, description: "",
                language: imported?.language ?? instructionLanguage(for: source), catalogID: catalogID, canvasID: canvasID,
                seed: seedText, wild: wild, settings: settings, parentWorkID: nil, derivationKind: "new",
                importedPlugins: imported?.plugins ?? [])
            request = try await pinPersonalPlanRequests([request])[0]
            return await runAutomation(request: request) != nil
        } catch { report(error); return false }
    }

    public func drawEditedDDL(work: SavedWork, source: String, wildOverride: Bool? = nil) async -> Bool {
        guard !isBusy, !work.trashed, !source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        do {
            _ = try await checkedSavedAdjustmentParent(work)
            let saved = try await savedConfiguration(workID: work.id)
            var options = try ExactJSON(data: saved.renderOptions)
            if let wildOverride { options["wild"] = .bool(wildOverride) }
            guard let catalog = options["catalog_id"].string, options["resolved_color_map"].object != nil else {
                throw HostError("saved_refinement_options_unavailable")
            }
            var models = settings.models
            models.stage1Model = work.stage1Model ?? ""
            if models.stage2Model.isEmpty { models.stage2Model = work.stage2Model ?? "" }
            var request = GenerationRequest(authoring: .directDDL(source), configuration: saved.configuration,
                renderOptions: options.data, clipPolicy: saved.clipPolicy, models: models, providers: settings.providers,
                renderColorMaps: [catalog: options["resolved_color_map"].data], description: work.effectiveSourceText,
                parentWorkID: work.id, derivationKind: "ddl_edit")
            request = try await pinPersonalPlanRequests([request])[0]
            return await runAutomation(request: request) != nil
        } catch { report(error); return false }
    }

    /// Demo files are independent of the history checkbox and never open a save panel per iteration.
    public func saveDemoFiles(_ work: SavedWork) async -> Bool {
        guard let directory = localDataDirectory()?.appendingPathComponent("demo-output", isDirectory: true) else { return false }
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            var options = display.preferences.exportDefaults.options
            options.format = .png
            options.pixelHeight = display.preferences.exportDefaults.resolution == 0
                ? display.preferences.exportDefaults.customHeight : display.preferences.exportDefaults.resolution
            let artifacts = try await ExportService.prepare(sources: [ExportSource(work: work)], options: options)
            for artifact in artifacts { try artifact.data.write(to: directory.appendingPathComponent(artifact.name), options: .atomic) }
            let name = "inku-" + work.id
            try Data(work.svg.utf8).write(to: directory.appendingPathComponent(name + ".svg"), options: .atomic)
            status = "デモの画像を保存しました: " + directory.path
            return true
        } catch { report(error); return false }
    }

    public func saveDemoCandidate(_ work: SavedWork) async -> SavedWork? {
        guard !isBusy, previewWork?.id == work.id, let executionID = currentExecutionID, let host else { return nil }
        var result: SavedWork?
        _ = await performSerialized(status: "候補を保存中") { [weak self] _ in
            guard let self else { return }
            let saved = try await host.saveCandidate(executionID: executionID)
            guard saved.id == work.id else { throw HostError("candidate_identity_changed") }
            await self.notifySavedWork(saved)
            try await self.reloadWorks()
            self.displayWork(saved)
            self.selectedContext = try await host.savedAuthoringContext(workID: saved.id)
            result = saved
        }
        return result
    }

    /// Allocate the entire round before any drawing, keeping saved colors, locks, policies and source authority.
    public func makeDrawingAdjustmentPlans(work: SavedWork, kind: String, count: Int, words: String = "",
                                           amplitude: String = "medium", wildOverride: Bool? = nil,
                                           modelReference: String? = nil) async throws -> [DrawingAdjustmentPlan] {
        guard !isPreview, !stopping, let host else { throw HostError("authoring_busy_or_unavailable") }
        guard ["layout_change", "reinterpretation", "variation", "touch_change"].contains(kind) else { throw HostError("unknown_refinement_kind") }
        guard [1, 4].contains(count), kind != "touch_change" || count == 1 else { throw HostError("invalid_adjustment_count") }
        let drawing = settings
        let source = try await checkedSavedAdjustmentParent(work)
        let saved = try await host.savedAuthoringContext(workID: source.id)
        try Task.checkCancellation()
        guard ["description_authoritative", "ddl_authoritative"].contains(saved.authority) else { throw HostError("saved_authoring_context_unavailable") }
        let baseConfiguration = try ExactJSON(data: saved.configuration)
        let baseOptions = try ExactJSON(data: saved.renderOptions)
        guard let catalog = baseOptions["catalog_id"].string, baseOptions["resolved_color_map"].object != nil else {
            throw HostError("saved_refinement_options_unavailable")
        }
        if kind == "touch_change" {
            let resolved = try InkuCore.renderSeedWords(fromText: words)
            guard let placement = source.compositionSeed ?? baseOptions["composition_seed"].string ?? baseOptions["composition_seed"].number
                    ?? source.renderSeed ?? baseOptions["render_seed"].string ?? baseOptions["render_seed"].number else {
                throw HostError("saved_refinement_options_unavailable")
            }
            let from = source.renderSeed ?? baseOptions["render_seed"].string ?? baseOptions["render_seed"].number
            let metadata: ExactJSON = .object(["render_seed_from": from.map(ExactJSON.number) ?? .null,
                "render_seed_to": .number(resolved.seed), "seed_text": .string(resolved.text)])
            let replay = try await host.makeSavedScoreReplayPlan(workID: source.id, renderSeed: resolved.seed,
                compositionSeed: placement, derivationKind: kind, derivationMetadata: metadata.data, seedText: resolved.text)
            try Task.checkCancellation()
            return [DrawingAdjustmentPlan(stage1Model: source.stage1Model, stage2Model: source.stage2Model,
                parent: source, operation: .replay(replay))]
        }
        if kind == "variation" {
            guard ["small", "medium", "large"].contains(amplitude) else { throw HostError("invalid_variation") }
            var seeds: Set<UInt64> = []
            var plans: [DrawingAdjustmentPlan] = []
            for _ in 0..<count {
                var seed: UInt64
                repeat { seed = UInt64.random(in: 1...((UInt64(1) << 31) - 1)) } while seeds.contains(seed)
                seeds.insert(seed)
                let metadata: ExactJSON = .object(["variation_amplitude": .string(amplitude), "variation_seed": .number(String(seed))])
                // The current shared core's Stage 1.5 variation is a no-op; preserve the Score and actual model facts.
                let replay = try await host.makeSavedScoreReplayPlan(workID: source.id, wild: wildOverride,
                    derivationKind: kind, derivationMetadata: metadata.data, variationAmplitude: amplitude, variationSeed: String(seed))
                try Task.checkCancellation()
                plans.append(DrawingAdjustmentPlan(stage1Model: source.stage1Model, stage2Model: source.stage2Model,
                    parent: source, operation: .replay(replay)))
            }
            return plans
        }
        guard let document = saved.document, let ddl = source.ddl, !ddl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw HostError("saved_document_unavailable")
        }
        let reading = kind == "reinterpretation"
        if reading && saved.authority != "description_authoritative" { throw HostError("description_source_locked") }
        let description = source.effectiveSourceText.trimmingCharacters(in: .whitespacesAndNewlines)
        if reading && description.isEmpty { throw HostError("description_required") }
        var models = drawing.models
        if reading {
            // The Web's Stage 2 picker leaves Stage 1 alone. Server preparation chooses Stage 1 for a rereading.
            try validateAdjustmentModel(models.stage1Model, providers: drawing.providers)
            models.stage2Model = models.stage1Model
        } else {
            models.stage1Model = source.stage1Model ?? ""
            models.stage2Model = modelReference ?? (drawing.models.stage2Model.isEmpty ? source.stage2Model ?? "" : drawing.models.stage2Model)
            if let modelReference { try validateAdjustmentModel(modelReference, providers: drawing.providers) }
        }
        var usedSeeds = Set([source.compositionSeed].compactMap { $0 }.compactMap(UInt64.init))
        var requests: [GenerationRequest] = []
        for _ in 0..<count {
            var configuration = baseConfiguration
            var options = baseOptions
            configuration["catalogs"] = .array([])
            configuration["compiler"]["stage15_variation"] = .null
            options["wild"] = .bool(wildOverride ?? source.renderWild ?? baseOptions["wild"].bool ?? false)
            options["svg_profile"] = .string("display")
            var metadata: ExactJSON = .object([:])
            var interpretation: String?
            if kind == "layout_change" {
                var seed: UInt64
                repeat { seed = UInt64.random(in: 0...((UInt64(1) << 53) - 1)) } while usedSeeds.contains(seed)
                usedSeeds.insert(seed)
                configuration["compiler"]["composition_seed"] = .string(String(seed))
                options["composition_seed"] = .string(String(seed))
                metadata = .object(["composition_seed": .number(String(seed))])
            } else {
                interpretation = UUID().uuidString.lowercased()
                metadata = .object(["interpretation_seed": .string(interpretation!)])
            }
            let authoring: GenerationAuthoring = reading
                ? .description(description, autoCatalog: false, sketch: source.sketchText.map(SketchRequest.supplied) ?? .off)
                : .directDDL(ddl)
            requests.append(GenerationRequest(authoring: authoring, configuration: configuration.data, renderOptions: options.data,
                clipPolicy: saved.clipPolicy, models: models, providers: drawing.providers,
                renderColorMaps: [catalog: baseOptions["resolved_color_map"].data], description: description,
                parentWorkID: source.id, derivationKind: kind, saveHistory: false,
                retainedDocument: reading ? nil : document, retainedAuthority: reading ? nil : saved.authorityJSON,
                derivationMetadata: metadata.data, interpretationSeed: interpretation))
        }
        requests = try await pinPersonalPlanRequests(requests)
        try Task.checkCancellation()
        return requests.map { request in DrawingAdjustmentPlan(stage1Model: reading ? request.models.stage1Model : source.stage1Model,
            stage2Model: request.models.stage2Model.isEmpty ? nil : request.models.stage2Model, parent: source, operation: .author(request)) }
    }

    public func prepareDrawingAdjustmentCandidate(plan: DrawingAdjustmentPlan, token: UUID) async throws -> PreparedCandidate {
        guard generationToken == token, !stopping, let host else { throw CancellationError() }
        _ = try await checkedSavedAdjustmentParent(plan.parent)
        try Task.checkCancellation()
        let candidate: PreparedCandidate
        switch plan.operation {
        case .replay(let replay): candidate = try await host.previewSavedScoreReplay(replay)
        case .author(let request): candidate = try await generateCandidate(request: request, token: token, comparison: false)
        }
        try Task.checkCancellation()
        guard generationToken == token, !stopping else { throw CancellationError() }
        return candidate
    }

    /// The committed transaction remains authoritative if cancellation or display refresh follows it.
    public func adoptDrawingAdjustmentCandidate(candidate: PreparedCandidate, token: UUID) async throws -> SavedWork {
        guard generationToken == token, !stopping, let host else { throw CancellationError() }
        let saved = try await host.saveCandidate(executionID: candidate.executionID, expectedWorkID: candidate.work.id)
        await notifySavedWork(saved)
        do { try await reloadWorks() } catch { report(error) }
        guard generationToken == token, !stopping, !Task.isCancelled else { return saved }
        do {
            let context = try await host.savedAuthoringContext(workID: saved.id)
            let view = try? await host.restore(executionID: candidate.executionID)
            guard generationToken == token, !stopping, !Task.isCancelled else { return saved }
            if let view, view.savedWorkID == saved.id { apply(view) }
            else {
                diagnosticsJSON = ""; promptJSON = ""; eventsJSON = ""; unreadOutputs = []
                promptAvailability = .unavailable
            }
            displayWork(saved)
            selectedContext = context
            authoringAuthority = context.authority; authoringOrigin = context.origin; authoringRevision = context.revision
            authoringPhase = "completed"
            currentExecutionID = nil; currentView = nil
            holeIDs = []; selectedHoleIDs = []; patchProposalJSON = ""; patchCandidate = ""
            status = "選択した候補を保存しました"
        } catch { report(error) }
        return saved
    }

    private func checkedSavedAdjustmentParent(_ work: SavedWork) async throws -> SavedWork {
        guard let database, let stored = try await database.work(id: work.id), !stored.trashed,
              stored.lineageNodeID != nil else { throw HostError("saved_work_changed_or_unavailable") }
        var expected = work
        expected.starred = stored.starred; expected.trashed = stored.trashed
        guard stored == expected else { throw HostError("saved_work_changed_or_unavailable") }
        return work
    }

    private func validateAdjustmentModel(_ reference: String, providers: [ProviderSettings]) throws {
        if try PersonalPlanRoutingTransport.personalModel(reference, providers: providers) != nil { return }
        if let colon = reference.firstIndex(of: ":"), let provider = providers.first(where: { $0.id == String(reference[..<colon]) }),
           !reference[reference.index(after: colon)...].isEmpty { try provider.validate(); return }
        if !reference.contains(":"), !reference.isEmpty, providers.count == 1 { try providers[0].validate(); return }
        throw HostError("provider_selection_required")
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
        let language = work.instructionLangResolved ?? config["language"].string ?? instructionLanguage(for: work.effectiveSourceText)
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

    /// A saved-work edit starts a child from its pinned configuration, independently of editor restoration.
    public func makeSavedWorkEditRequest(work: SavedWork, mode: WorkEditMode, description: String,
                                        sketchMode: String = "off", wildOverride: Bool? = nil) async throws -> GenerationRequest {
        guard !isBusy, !isPreview, database != nil else { throw HostError("authoring_busy_or_unavailable") }
        let drawing = nextGenerationHostSettings
        guard hasNextDrawingModel else { throw HostError("model_reference_missing") }
        let saved = try await savedWorkEditContext(work)
        let text = (mode == .description ? description : work.effectiveSourceText).trimmingCharacters(in: .whitespacesAndNewlines)
        let selectedLanguage = instructionLanguage(for: text)
        guard ["ja", "en"].contains(selectedLanguage) else { throw HostError("invalid_instruction_language") }
        guard !text.isEmpty else { throw HostError("description_required") }
        var configuration = try ExactJSON(data: saved.configuration)
        var options = try ExactJSON(data: saved.renderOptions)
        guard let catalog = options["catalog_id"].string,
              options["resolved_color_map"].object != nil,
              options["canvas_aspect_id"].string != nil else { throw HostError("saved_refinement_options_unavailable") }
        configuration["language"] = .string(selectedLanguage)
        // The Server applies Stage 1.5 only when this operation explicitly asks for it.
        configuration["compiler"]["stage15_variation"] = .null
        configuration["catalogs"] = .array([])
        options["wild"] = .bool(mode == .description ? wildOverride ?? work.renderWild ?? options["wild"].bool ?? false
                                                    : work.renderWild ?? options["wild"].bool ?? false)
        options["svg_profile"] = .string("display")
        let sketch: SketchRequest
        if mode == .sketch {
            guard ["off", "on"].contains(sketchMode) else { throw HostError("invalid_sketch_mode") }
            // Explicitly asking for the layer runs it anew; it never replays saved prose.
            sketch = sketchMode == "on" ? .on : .off
        } else if let prose = work.sketchText, !prose.isEmpty {
            sketch = text == work.effectiveSourceText.trimmingCharacters(in: .whitespacesAndNewlines) ? .supplied(prose) : .on
        } else { sketch = .off }
        let request = GenerationRequest(authoring: .description(text, autoCatalog: false, sketch: sketch),
            configuration: configuration.data, renderOptions: options.data, clipPolicy: saved.clipPolicy,
            models: drawing.models, providers: drawing.providers,
            renderColorMaps: [catalog: options["resolved_color_map"].data], description: text,
            parentWorkID: work.id, derivationKind: mode == .description ? "description_edit" : "sketch_grain_change",
            derivationMetadata: ExactJSON.object(mode == .description
                ? ["edited_from_history_id": .string(work.id)]
                : ["edited_from_history_id": .string(work.id), "from_sketch_state": work.sketchState.map(ExactJSON.string) ?? .null,
                   "to_sketch_mode": .string(sketchMode)]).data)
        try Task.checkCancellation()
        let pinned = try await pinPersonalPlanRequests([request])[0]
        try Task.checkCancellation()
        return pinned
    }

    /// Menu availability is read from saved authority, never inferred from a model label or DDL contents.
    public func canEditSavedWork(_ work: SavedWork) async -> Bool {
        guard !isBusy, !isPreview, hasNextDrawingModel else { return false }
        let available = (try? await savedWorkEditContext(work)) != nil
        return available && !isBusy && !isPreview && hasNextDrawingModel
    }

    private func savedWorkEditContext(_ work: SavedWork) async throws -> SavedAuthoringContext {
        guard let database, let stored = try await database.work(id: work.id), !stored.trashed,
              stored.lineageNodeID != nil else { throw HostError("saved_work_changed_or_unavailable") }
        var expected = work
        // Stars are mutable annotations, while the saved source and performance remain immutable.
        expected.starred = stored.starred
        expected.trashed = stored.trashed
        guard stored == expected else { throw HostError("saved_work_changed_or_unavailable") }
        try Task.checkCancellation()
        let context = try await savedConfiguration(workID: work.id)
        try Task.checkCancellation()
        guard ["description_authoritative", "ddl_authoritative"].contains(context.authority) else { throw HostError("saved_authoring_context_unavailable") }
        guard context.authority == "description_authoritative" else { throw HostError("description_source_locked") }
        guard !work.effectiveSourceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw HostError("description_required") }
        return context
    }

    /// Keep the displayed workspace intact until this dialog's child is actually committed.
    public func runSavedWorkEdit(request: GenerationRequest) async -> SavedWork? {
        guard let host, request.parentWorkID != nil,
              ["description_edit", "sketch_grain_change"].contains(request.derivationKind),
              request.retainedDocument == nil, case .description = request.authoring else { return nil }
        let previousExecution = currentExecutionID
        let previousView = currentView
        var result: SavedWork?
        var adopted = false
        _ = await performSerialized(status: "生成中") { [weak self] token in
            guard let self else { return }
            defer {
                if !adopted { self.currentExecutionID = previousExecution; self.currentView = previousView }
            }
            let candidate = try await self.generateCandidate(request: request, token: token, comparison: false)
            try Task.checkCancellation()
            let saved = try await self.saveComparisonCandidate(executionID: candidate.executionID, token: token)
            result = saved
            guard self.generationToken == token, !self.stopping, !Task.isCancelled else { return }
            let view = try await host.restore(executionID: candidate.executionID)
            let context = try await host.savedAuthoringContext(workID: saved.id)
            guard self.generationToken == token, !self.stopping, !Task.isCancelled else { return }
            self.apply(view)
            self.displayWork(saved)
            self.selectedContext = context
            // This execution remains a preview writer. Future edits must fork the committed saved context.
            self.currentExecutionID = nil
            self.currentView = nil
            adopted = true
            self.status = "作品を保存しました"
        }
        return result
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
    public func performComparison(status: String, restoreDisplayStatus: Bool = false,
                                  operation: @escaping @MainActor (UUID) async throws -> Void) async -> Bool {
        let execution = currentExecutionID
        let originalWorkID = selectedWorkID
        let originalStatus = self.status
        return await performSerialized(status: status) { [weak self] token in
            defer { self?.currentExecutionID = self?.selectedWorkID == originalWorkID ? execution : nil }
            try await operation(token)
            if restoreDisplayStatus { self?.status = originalStatus }
        }
    }

    public func generateCandidate(request: GenerationRequest, token: UUID, comparison: Bool = true) async throws -> PreparedCandidate {
        guard generationToken == token, !stopping, let host else { throw CancellationError() }
        var request = request; request.saveHistory = false; request.historyVisibility = "normal"
        try await validatePinnedRequest(request)
        let models = request.models
        let view = try await host.generate(request) { [weak self] progress in
            Task { @MainActor in self?.receiveCandidate(progress, token: token, comparison: comparison, models: models) }
        }
        recordDrawingLog(executionID: view.executionID)
        if generationToken == token, !stopping, !Task.isCancelled { finishProviderStage(view) }
        await recordDescriptionFeedback(request: request, view: view)
        try Task.checkCancellation()
        guard generationToken == token, let work = view.candidateWork else { throw HostError("comparison_candidate_requires_edit") }
        return PreparedCandidate(executionID: view.executionID, work: work, authority: view.authority, providerMetrics: view.providerMetrics)
    }

    public func prepareReplayComparison(work: SavedWork, token: UUID) async throws -> ReplayComparisonSnapshot {
        guard generationToken == token, !stopping, let host else { throw CancellationError() }
        try Task.checkCancellation()
        _ = try await checkedSavedAdjustmentParent(work)
        try Task.checkCancellation()
        guard generationToken == token, !stopping else { throw CancellationError() }
        let snapshot = try await host.prepareReplayComparison(work: work)
        try Task.checkCancellation()
        guard generationToken == token, !stopping, snapshot.workID == work.id else { throw CancellationError() }
        _ = try await checkedSavedAdjustmentParent(work)
        try Task.checkCancellation()
        guard generationToken == token, !stopping else { throw CancellationError() }
        return snapshot
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
    public func performSerialized(status: String, allowsBrowsing: Bool = false,
                                  operation: @escaping @MainActor (UUID) async throws -> Void) async -> Bool {
        guard !isBusy, activeOperation == nil, database != nil else { return false }
        let token = UUID()
        generationToken = token
        providerProgress = nil
        activeExecutionID = nil
        if !allowsBrowsing { currentExecutionID = nil }
        backgroundDrawing = allowsBrowsing
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

    public func runAutomation(request: GenerationRequest, allowsBrowsing: Bool = false) async -> SavedWork? {
        guard let host else { return nil }
        var result: SavedWork?
        _ = await performSerialized(status: "生成中", allowsBrowsing: allowsBrowsing) { [weak self] token in
            guard let self else { return }
            self.automationFailureMessage = nil
            try await self.validatePinnedRequest(request)
            let view = try await host.generate(request) { [weak self] progress in
                Task { @MainActor in self?.receive(progress, token: token, models: request.models) }
            }
            if self.generationToken == token, !self.stopping {
                self.activeExecutionID = view.executionID
                if let message = DrawingFailureMessage.text(for: view, language: self.display.preferences.language) {
                    self.automationFailureMessage = message
                    if self.errorText == nil { self.errorText = message }
                }
                if allowsBrowsing {
                    self.finishProviderStage(view)
                    self.status = Self.phaseStatus(view.phase)
                }
            }
            await self.recordDescriptionFeedback(request: request, view: view)
            await self.notifyCommittedWork(view)
            try Task.checkCancellation()
            if !allowsBrowsing { self.apply(view) }
            try await self.reloadWorks()
            if let id = view.savedWorkID, let work = try await self.database?.work(id: id) {
                if !allowsBrowsing {
                    self.displayWork(work)
                    self.selectedContext = try await host.savedAuthoringContext(workID: id)
                    if request.retainedDocument != nil {
                        // Retained compilation stores a completed candidate, not an editable core execution.
                        self.currentExecutionID = nil
                        self.currentView = nil
                    }
                }
                result = work
            } else if !request.saveHistory, let work = view.candidateWork {
                if !allowsBrowsing {
                    self.previewWork = work
                    self.providerMetrics = view.providerMetrics
                    self.status = "未保存の候補を表示しています"
                }
                result = work
            }
        }
        return result
    }

    public func newWork() {
        guard !isBusy else { return }
        backgroundDrawing = false
        displayToken = UUID()
        library.clearSelectedAnnotation()
        providerProgress = nil
        providerMetrics = []
        status = "準備完了"
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
        promptAvailability = .notRecorded
        eventsJSON = ""
        errorText = nil
        unreadOutputs = []
        inputMode = "description"
        descriptionText = ""
        ddlText = ""
        sketchDraft = nil
    }

    public func commitDDL(wildOverride: Bool? = nil) async {
        guard canCommitDDL else { return }
        if let work = displayedWork, ddlText == visibleDDL || wildOverride != nil {
            _ = await drawEditedDDL(work: work, source: ddlText, wildOverride: wildOverride)
        } else if let id = currentExecutionID, wildOverride == nil {
            await performCommand(executionID: id, command: .commitUserDDL(expectedRevision: authoringRevision, source: ddlText), kind: "ddl_edit")
        } else if selectedContext != nil {
            do {
                let request = try requestForCurrentInput(inputMode: "ddl", parentWorkID: selectedWorkID, derivationKind: "ddl_edit", wildOverride: wildOverride)
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
            self.activeExecutionID = executionID
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
            let catalog = try bootstrap.macroCatalog(language: instructionLanguage(for: ddlText), settings: settings, importedPlugins: importedDDL?.plugins ?? [])
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
        backgroundDrawing = false
        isBusy = true
        defer { isBusy = false }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            try await host.cancelAll()
            try await database.restore(from: url)
            displayToken = UUID()
            activeExecutionID = nil
            currentExecutionID = nil
            generationToken = nil
            currentSVG = ""
            visibleDDL = ""
            scoreJSON = ""
            selectedWorkID = nil
            selectedWork = nil
            previewWork = nil
            importedDDL = nil; importedMacroNames = []
            selectedContext = nil
            currentView = nil
            workActionStates = [:]
            await library.resetAfterRestore()
            restorationRevision &+= 1
            try await reloadWorks()
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

    public func copyImage(work target: SavedWork? = nil) async {
        #if os(macOS)
        guard !isBusy, let work = target ?? displayedWork, !work.svg.isEmpty else { return }
        let executionID = currentExecutionID
        let height = min(4096, max(256, display.preferences.clipboardHeight))
        clipboardMessageKey = nil
        let copied = await performSerialized(status: "コピー画像を準備中") { [weak self] _ in
            guard let self else { return }
            defer { self.currentExecutionID = executionID }
            var options = self.display.preferences.exportDefaults.options
            options.format = self.display.preferences.clipboardFormat == "card" ? .shareCard : .png
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
        let key = copied ? "canvasCopiedToClipboard" : "clipboardCopyFailed"
        clipboardMessageKey = key
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(copied ? 2500 : 8000))
            if self?.clipboardMessageKey == key { self?.clipboardMessageKey = nil }
        }
        #endif
    }

    private func reloadWorks() async throws {
        guard let database else { return }
        works = try await database.list(limit: 100)
        if let id = selectedWorkID {
            let selectionToken = displayToken
            let saved = try await database.work(id: id)
            if displayToken == selectionToken, selectedWorkID == id {
                if let saved { selectedWork = saved }
                else {
                    displayToken = UUID()
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
    private func receive(_ progress: PipelineProgress, token: UUID, models: ModelSelection? = nil) {
        recordDrawingProgress(progress)
        guard generationToken == token, !stopping else { return }
        receiveProviderProgress(progress, models: models, comparison: false)
        switch progress {
        case .changed(let view):
            if backgroundDrawing { status = Self.phaseStatus(view.phase) }
            else { apply(view) }
        case .providerAttempt(_, _, _, let deadline):
            status = providerProgress?.stage == .composition ? "構図を読んでいます" : "モデルの応答待ち（期限 \(deadline.formatted(date: .omitted, time: .standard))）"
        case .transportBytes(_, let count):
            status = providerProgress?.stage == .composition ? "構図の応答を受信中" : "応答を受信中（\(count) bytes）"
        case .providerDiagnostic(_, let diagnostic): errorText = "ChatGPTプラン: \(diagnostic.code)（\(diagnostic.action)）"
        case .providerMetric: break
        case .saved(_, _): status = "作品を保存しました"
        }
    }
    private func receiveCandidate(_ progress: PipelineProgress, token: UUID, comparison: Bool = true, models: ModelSelection? = nil) {
        recordDrawingProgress(progress)
        guard generationToken == token, !stopping else { return }
        receiveProviderProgress(progress, models: models, comparison: comparison)
        switch progress {
        case .changed(let view): currentExecutionID = view.executionID
        case .providerAttempt(_, _, _, let deadline):
            if providerProgress?.stage == .composition { status = comparison ? "比較候補の構図を読んでいます" : "構図を読んでいます" }
            else { status = comparison ? "比較候補のモデル応答待ち（期限 \(deadline.formatted(date: .omitted, time: .standard))）" : "モデルの応答待ち（期限 \(deadline.formatted(date: .omitted, time: .standard))）" }
        case .transportBytes(_, let count):
            if providerProgress?.stage == .composition { status = comparison ? "比較候補の構図の応答を受信中" : "構図の応答を受信中" }
            else { status = comparison ? "比較候補を受信中（\(count) bytes）" : "応答を受信中（\(count) bytes）" }
        case .providerDiagnostic(_, let diagnostic): errorText = "ChatGPTプラン: \(diagnostic.code)（\(diagnostic.action)）"
        case .providerMetric: break
        case .saved: break
        }
    }
    private func receiveProviderProgress(_ progress: PipelineProgress, models: ModelSelection?, comparison: Bool) {
        switch progress {
        case .providerAttempt(let id, let report, let beganAt, let deadline):
            activeExecutionID = id
            if let models { providerModelsByExecution[id] = models }
            if let next = ProviderProgressSnapshot.start(executionID: id, report: report, beganAt: beganAt,
                deadline: deadline, models: models ?? providerModelsByExecution[id], comparison: comparison, previous: providerProgress) {
                providerProgress = next
            }
        case .changed(let view):
            activeExecutionID = view.executionID
            if let models { providerModelsByExecution[view.executionID] = models }
            finishProviderStage(view)
        case .transportBytes(let id, let bytes):
            if providerProgress?.executionID == id { providerProgress?.receive(bytes: bytes) }
        case .providerMetric(let id, let metric):
            if providerProgress?.executionID == id { providerProgress?.receive(metric: metric) }
        case .providerDiagnostic, .saved: break
        }
    }

    public func drawingLogs() async throws -> [DrawingLogRecord] {
        guard let host else { throw HostError("database_unavailable") }
        return try await host.drawingLogs()
    }

    private func recordDrawingProgress(_ progress: PipelineProgress) {
        // Durable logs outlive the UI token, including delayed terminal callbacks after Stop.
        switch progress {
        case .changed(let view): recordDrawingLog(executionID: view.executionID)
        case .providerMetric(let id, _): recordDrawingLog(executionID: id)
        default: break
        }
    }

    private func recordDrawingLog(executionID: String) {
        guard let host, let callback = onDrawingLog else { return }
        // Read durable public facts, independent of UI selection and the caller's cancellation.
        Task { @MainActor in
            do {
                if let record = try await host.drawingLog(executionID: executionID) { await callback(record) }
            } catch { self.errorText = "描画ログを読み込めませんでした。" }
        }
    }
    private func finishProviderStage(_ view: PipelineView) {
        if providerProgress?.executionID == view.executionID {
            if let metric = view.providerMetrics.last(where: { $0.action == providerProgress?.action && Int($0.identity.attempt) == providerProgress?.attempt }) {
                providerProgress?.receive(metric: metric)
            }
            providerProgress?.changed(phase: view.phase, at: Date())
        }
    }

    /// Raw IO is fetched only by an explicit developer inspector action, never by the normal metric path.
    public func savedProviderObservations(workID: String) async throws -> [ProviderAttemptObservation] {
        guard developerModeEnabled, let host else { throw HostError("developer_provider_observations_not_available") }
        return try await host.savedProviderObservations(workID: workID)
    }
    public func providerObservations(executionID: String) async throws -> [ProviderAttemptObservation] {
        guard developerModeEnabled, let host else { throw HostError("developer_provider_observations_not_available") }
        return try await host.providerObservations(executionID: executionID)
    }
    private func apply(_ view: PipelineView) {
        finishProviderStage(view)
        recordDrawingLog(executionID: view.executionID)
        currentView = view
        currentExecutionID = view.executionID
        if isBusy, view.savedWorkID == displayedWork?.id { providerMetrics = view.providerMetrics }
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
            promptAvailability = prompt.isEmpty ? .notRecorded : .recorded
            if prompt != promptJSON { promptJSON = prompt; unreadOutputs.insert("prompt") }
        } else {
            promptJSON = ""
            promptAvailability = .notRecorded
            unreadOutputs.remove("prompt")
        }
        eventsJSON = (try? Self.pretty(view.eventsJSON)) ?? String(decoding: view.eventsJSON, as: UTF8.self)
        status = Self.phaseStatus(view.phase)
    }
    private static func phaseStatus(_ phase: String) -> String {
        [
            "authoring_started": "生成を開始しました", "awaiting_llm": "モデルの応答待ち",
            "awaiting_visible_ddl_commit": "DDLを確認しています", "awaiting_patch_approval": "補完案の承認待ち",
            "score_ready": "描画中", "completed": "生成を完了しました",
            "needs_user_edit": "DDLを編集してください", "failed": "生成できませんでした",
            "cancelled": "停止しました",
        ][phase] ?? "処理中"
    }
    /// Web restores the catalog, paper and wild choice at start-up; a saved catalog or paper that is gone is the default.
    private func restoreNextConditions() {
        let saved = display.preferences
        if let id = saved.nextCatalogID, catalogs.contains(where: { $0.id == id }) { catalogID = id }
        if let mode = saved.nextCatalogMode, ["fixed", "auto"].contains(mode) { catalogMode = mode }
        if let id = saved.nextCanvasID, canvases.contains(where: { $0.id == id }) { canvasID = id }
        if let saved = saved.nextWild { wild = saved }
        nextConditionsRestored = true
    }

    private func rememberNextConditions() {
        guard nextConditionsRestored else { return }
        var next = display.preferences
        next.nextCatalogID = catalogID
        // Batch-only modes are not a next-work choice of the creation screen.
        if ["fixed", "auto"].contains(catalogMode) { next.nextCatalogMode = catalogMode }
        next.nextCanvasID = canvasID
        next.nextWild = wild
        if next != display.preferences { display.preferences = next }
    }

    private func report(_ error: Error) {
        if generationToken != nil, !stopping { providerProgress?.finish(.failed, at: Date()) }
        errorText = error.localizedDescription
        status = "処理を完了できませんでした"
    }
    private static func pretty(_ bytes: Data) throws -> String {
        let value = try ExactJSON(data: bytes)
        // Pretty formatting may round JSON numbers; retain exact wire lexemes in the displayed output.
        return value.text
    }
}

extension AppModel {
    /// Server `_resolve_instruction_lang`: an explicit language wins; `auto` reads Japanese, then Latin
    /// letters, and otherwise falls back to the UI language.
    public func instructionLanguage(for text: String) -> String {
        if ["ja", "en"].contains(language) { return language }
        let scalars = text.unicodeScalars
        if scalars.contains(where: { (0x3040...0x30ff).contains($0.value) || (0x3400...0x9fff).contains($0.value) }) { return "ja" }
        if scalars.contains(where: { (0x41...0x5a).contains($0.value) || (0x61...0x7a).contains($0.value) }) { return "en" }
        return display.preferences.language == "en" ? "en" : "ja"
    }

    var currentInputText: String { inputMode == "ddl" ? ddlText : descriptionText }
}
