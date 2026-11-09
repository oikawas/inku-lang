import CoreGraphics
import CryptoKit
import Foundation
import ImageIO
import InkuCore
import InkuHost
import InkuPersistence
import InkuExport
import Observation
import UniformTypeIdentifiers

/// Availability of the author-facing prompt journal, independent of whether a provider was called.
public enum PromptAvailability: Sendable, Equatable {
    case loading, recorded, notRecorded, unavailable
}

public struct OutputSnapshot: Sendable {
    public let prompt: String
    public let promptAvailability: PromptAvailability
    public let events: String
    public let score: String
}

/// A complete, immutable adjustment snapshot. Views display model facts but never interpret its operation.
public struct DrawingAdjustmentPlan: Sendable {
    public let stage1Model: String?
    public let stage2Model: String?
    fileprivate let parent: SavedWork
    fileprivate let operation: Operation
    /// The ranges a layout option chose again (Server `recomposition`); nil for other adjustments.
    public var recomposition: Recomposition?
    fileprivate enum Operation: Sendable {
        case replay(SavedScoreReplayPlan)
        case author(GenerationRequest)
    }
}

@MainActor
@Observable
public final class AppModel {
    public let autonomousRefinement = AutonomousRefinementModel()
    public private(set) var canvasFitQuestion: CanvasFitQuestion?
    @ObservationIgnored public var canvasFitChoiceHandler: (@MainActor (CanvasFitQuestion) async -> CanvasFitChoice)?
    @ObservationIgnored private var canvasFitContinuation: CheckedContinuation<CanvasFitChoice, Never>?
    public var inputMode = "description"
    public var imageInput: PreparedImageInput?
    public var activeDrawTab = "describe"
    public private(set) var drawDefaults = DrawOptionsCore.release
    public private(set) var drawSelections = DrawOptionsCore.release {
        didSet {
            let before = Set(oldValue.values.compactMap { $0.models.stage1 })
            let after = Set(drawSelections.values.compactMap { $0.models.stage1 })
            if before != after { refreshDrawingAvailability() }
        }
    }
    private struct DrawingAvailability {
        let drawing: Bool
        let batch: Bool
        let vision: Bool
    }
    private var drawingAvailability: [String: DrawingAvailability] = [:]
    struct RecordedOptionsKey: Hashable { let workID: String; let isImage: Bool }
    private var recordedOptionsByWork: [RecordedOptionsKey: [String: Any]] = [:]

    func cachedRecordedOptions(workID: String, isImage: Bool) -> [String: Any]? {
        recordedOptionsByWork[RecordedOptionsKey(workID: workID, isImage: isImage)]
    }
    @discardableResult func prepareRecordedOptions(_ work: SavedWork, isImage: Bool) throws -> [String: Any] {
        let key = RecordedOptionsKey(workID: work.id, isImage: isImage)
        if let cached = recordedOptionsByWork[key] { return cached }
        let value = try DrawOptionsCore.recorded(work, isImage: isImage)
        recordedOptionsByWork[key] = value
        return value
    }
    private func refreshDrawingAvailability() {
        let references = Set(drawSelections.values.compactMap { $0.models.stage1 })
        drawingAvailability = Dictionary(uniqueKeysWithValues: references.map { reference in
            var visionSettings = settings
            visionSettings.models.stage1Model = reference
            visionSettings.models.stage2Model = reference
            return (reference, DrawingAvailability(
                drawing: SettingsModel.isModelAvailable(reference, settings: settings),
                batch: SettingsModel.isBatchModelAvailable(reference, settings: settings),
                vision: SettingsModel.isRegisteredModelAvailable(reference, purpose: "vision", settings: visionSettings)))
        })
    }
    private var currentDrawOptions: DrawOptions {
        get { drawSelections[activeDrawTab] ?? DrawOptionsCore.release[activeDrawTab] ?? .empty }
        set { drawSelections[activeDrawTab] = newValue }
    }
    public var imageCanvasID: String {
        get { currentDrawOptions.canvasAspect }
        set { currentDrawOptions.canvasAspect = newValue }
    }
    public private(set) var imageProvenance = ""
    public private(set) var imageProvenanceTyped = false
    public var imageFileName = ""
    public var imageWarningAcknowledged = false
    public var savedImageDDL: Data?
    public var savedDescriptionDDL: Data?
    public var descriptionText = ""
    public var ddlText = ""
    /// The Web always requests `auto`; an explicit language remains possible for restored inputs.
    public var language = "auto"
    public var catalogID: String {
        get { currentDrawOptions.catalog.id }
        set { currentDrawOptions.catalog.id = newValue }
    }
    public var canvasID: String {
        get { currentDrawOptions.canvasAspect }
        set { currentDrawOptions.canvasAspect = newValue }
    }
    public var seedText = ""
    public var wild: Bool {
        get { currentDrawOptions.wild == "on" }
        set { currentDrawOptions.wild = newValue ? "on" : "off" }
    }
    public var catalogMode: String {
        get { currentDrawOptions.catalog.mode }
        set { currentDrawOptions.catalog.mode = newValue }
    }
    public var sketchMode: String {
        get { currentDrawOptions.sketch }
        set { currentDrawOptions.sketch = newValue }
    }
    public var drawRoute: String {
        get { currentDrawOptions.route }
        set { currentDrawOptions.route = newValue }
    }
    public var descriptionComposition: Bool {
        get { currentDrawOptions.composition == "on" }
        set { currentDrawOptions.composition = newValue ? "on" : "off" }
    }
    public func selectDrawRoute(_ route: String) {
        guard ["read_and_draw", "stages"].contains(route) else { return }
        if route == "read_and_draw", drawRoute != route { sketchMode = "on" }
        drawRoute = route
    }
    public var descriptionCanReview: Bool {
        drawingAvailability[nextDrawingModelReference]?.vision ?? false
    }
    private func applyDescriptionRoute(_ request: inout GenerationRequest, settings: HostSettings) {
        guard case .description = request.authoring, drawRoute == "read_and_draw" else { return }
        request.drawRoute = "read_and_draw"
        request.descriptionComposition = descriptionComposition
        request.descriptionReview = SettingsModel.isRegisteredModelAvailable(request.models.stage1Model, purpose: "vision", settings: settings)
    }
    public var sketchText = ""
    public var selectedHoleIDs: Set<String> = []
    public private(set) var works: [SavedWork] = []
    public private(set) var restorationRevision: UInt64 = 0
    public private(set) var selectedWorkID: String?
    public private(set) var selectedWork: SavedWork?
    public private(set) var previewWork: SavedWork?
    public private(set) var currentSVG = ""
    public private(set) var visibleDDL = ""
    public private(set) var status = "準備中"
    public private(set) var providerProgress: ProviderProgressSnapshot?
    private var progressJournals: [String: RunProgressJournal] = [:]
    private var journalExecutionID: String?
    var runJournal: RunProgressJournal? { journalExecutionID.flatMap { progressJournals[$0] } }
    var runJournalExecutionID: String? { journalExecutionID }
    var runModelReference: String? { journalExecutionID.flatMap { providerModelsByExecution[$0]?.stage1Model } }
    /// Metrics of the displayed saved work, frozen to that work's save identity.
    public private(set) var providerMetrics: [ProviderAttemptMetric] = []
    public private(set) var isBusy = false
    public private(set) var activeSingleInputMode: String?
    public func singleRunStatusVisible(in tab: String) -> Bool {
        guard isBusy else { return false }
        if tab == "image" { return activeSingleInputMode == "image" }
        return tab == "description" && (activeSingleInputMode == "description" || activeSingleInputMode == "ddl")
    }
    /// Failure of this automation request, independent of errors from concurrent browsing.
    public private(set) var automationFailureMessage: String?
    /// Retained between batch rows so browsing does not clear the last row's progress or failure.
    private var backgroundDrawing = false
    private var demoBrowsingLocked = false
    private var operationBrowsingLocked = false
    private var runFollowed = true
    /// Only the demo holds browsing, including the pauses between its operations.
    public var isBrowsingLocked: Bool { demoBrowsingLocked || operationBrowsingLocked }
    /// Preserve the pre-existing gate for settings and other non-browsing actions.
    var isSettingsInteractionLocked: Bool { isBusy && !backgroundDrawing }
    func setDemoBrowsingLocked(_ locked: Bool) { demoBrowsingLocked = locked }
    func stopFollowingRun() { if isBusy { runFollowed = false } }
    public var errorText: String?
    /// The ChatGPT plan diagnostic each execution reported last, for its failure text.
    @ObservationIgnored private var chatGPTFailureCodes: [String: String] = [:]
    /// Web CanvasPanel `clipboardMessage`: the copy button names the result, 2.5 s after success and 8 s after a failure.
    public private(set) var clipboardMessageKey: String?
    public private(set) var nextDrawingModelReference: String {
        get { currentDrawOptions.models.stage1 ?? "" }
        set { currentDrawOptions.models.stage1 = newValue; currentDrawOptions.models.stage2 = newValue }
    }
    public private(set) var providerSettingsRevision = 0
    public private(set) var catalogs: [ColorCatalogOption] = []
    public private(set) var canvases: [CanvasOption] = []
    public private(set) var saijiki: [SaijikiCategory] = [] {
        didSet { saijikiRevision &+= 1; ddlHighlighter = DdlHighlighter(saijiki: saijiki); completionCache = nil }
    }
    public private(set) var pluginWords: [PluginWord] = [] { didSet { completionCache = nil } }
    private(set) var saijikiRevision = 0
    @ObservationIgnored private(set) var ddlHighlighter = DdlHighlighter(saijiki: [])
    @ObservationIgnored private var completionCache: (disabled: [String], uiLanguage: String, language: String, value: DdlCompletions)?
    public private(set) var productReference: ProductReference?
    public private(set) var drawingLimitDefinition: DrawingLimitDefinition?
    public private(set) var importedMacroNames: [String] = []
    public private(set) var authoringRevision = "0"
    public private(set) var authoringAuthority = ""
    public private(set) var authoringOrigin = ""
    public private(set) var authoringPhase = ""
    public private(set) var diagnosticsJSON = ""
    public private(set) var holeIDs: [String] = []
    public private(set) var patchProposalJSON = ""
    public private(set) var patchCandidate = ""
    public private(set) var completionIssues: [HoleCompletionIssue] = []
    /// The creation panel and the editor dismissal share this exact pending execution state.
    public var patchReview: PipelinePatchReview? {
        guard authoringPhase == "awaiting_patch_approval", !patchProposalJSON.isEmpty,
              let executionID = currentExecutionID else { return nil }
        return PipelinePatchReview(executionID: executionID, proposal: patchProposalJSON,
                                   committedDDL: visibleDDL, proposedDDL: patchCandidate)
    }
    public var completionNoticeExecutionID: String? {
        (!completionIssues.isEmpty || patchReview != nil) ? currentExecutionID : nil
    }
    public func shouldReturnToCreation(afterSaving saved: Bool, previousReview: PipelinePatchReview?,
                                       previousIssues: [HoleCompletionIssue], previousNoticeExecutionID: String?) -> Bool {
        saved || (patchReview != nil && patchReview != previousReview)
            || (!completionIssues.isEmpty && (completionIssues != previousIssues || completionNoticeExecutionID != previousNoticeExecutionID))
    }
    /// Web DdlViewer: the displayed work's instructions as the author is editing them in the box. Typing never
    /// draws; "Draw from instructions" draws this text once. Another work starts from its own instructions.
    public private(set) var ddlBoxDraftWorkID: String?
    public private(set) var ddlBoxDraft = ""
    /// A word or a discard waiting for the box editor.
    var ddlBoxInsertion: InkuEditorInsertion?
    /// The numeric range an instruction editor's caret or pointer is on, framed over the displayed work.
    public var rangePreview: CompositionRanges.Preview?
    /// The box holds an invalid range or an IME composition, so drawing from it waits.
    public var ddlBoxRangeBlocked = false
    public func ddlBoxText(for work: SavedWork) -> String { ddlBoxDraftWorkID == work.id ? ddlBoxDraft : work.ddl ?? "" }
    public func setDdlBoxText(_ text: String, for work: SavedWork) {
        guard ddlBoxDraftWorkID == work.id || text != (work.ddl ?? "") else { return }
        ddlBoxDraftWorkID = work.id; ddlBoxDraft = text
    }
    private var workActionStates: [String: SavedWorkActionState] = [:]
    public private(set) var imageWorkProvenance: [String: String] = [:]
    public private(set) var savedDisplayLabels: [String: String] = [:]
    @ObservationIgnored private var displayLabelReads: Set<String> = []
    @ObservationIgnored private var workActionReadsInFlight: Set<String> = []
    @ObservationIgnored private var workActionReadWaiters: [CheckedContinuation<Void, Never>] = []
    @ObservationIgnored private var workActionReadToken = UUID()
    @ObservationIgnored private var pluginWorkContexts: [String: SavedAuthoringContext] = [:]
    public let library = LibraryModel(includeListSVG: false)
    public let display = DisplaySettings()
    public let descriptionMeter = DescriptionMeterModel()
    /// The saijiki preview's painter.
    public let renderer = ArtworkRenderer()
    /// The work area's painter (Skia).
    public let displayRenderer = DisplayRenderer()
    /// Owners of runs with their own stop button, for stopping them all when iOS may not keep the app running.
    public let runStops = RunStopRegistry()
    /// Thumbnails baked to PNG beside the database (I-718).
    public let thumbnails = ArtworkThumbnails()
    @ObservationIgnored public var onSavedWork: (@MainActor (SavedWork) async -> Void)?
    @ObservationIgnored public var onDrawingLog: (@MainActor (DrawingLogRecord) async -> Void)?

    @ObservationIgnored private let databaseURL: URL?
    @ObservationIgnored private let openDatabase: @Sendable (URL) throws -> InkuDatabase
    @ObservationIgnored private let transport: (any ProviderTransport)?
    @ObservationIgnored private var managedTransport: (any ProviderTransport)?
    @ObservationIgnored private var personalRuntime: ChatGPTPlanRuntime?
    @ObservationIgnored private var personalRuntimeOverride: ChatGPTPlanRuntime?
    @ObservationIgnored private let credentials = KeychainCredentialStore()
    @ObservationIgnored private var database: InkuDatabase?
    @ObservationIgnored private var host: PipelineHost?
    @ObservationIgnored private var settingsStore: ProviderSettingsStore?
    @ObservationIgnored private var settings = HostSettings()
    @ObservationIgnored private var cachedStageDefaultProviderID = ProviderModelReference.stageDefaultProviderID
    @ObservationIgnored private var bootstrap: Bootstrap?
    /// Cancellation targets the active task, independently of the saved work being viewed.
    @ObservationIgnored private var activeExecutionID: String? {
        didSet { journalExecutionID = activeExecutionID }
    }
    @ObservationIgnored private(set) var currentExecutionID: String?
    @ObservationIgnored private var displayToken = UUID()
    @ObservationIgnored private var generationToken: UUID?
    @ObservationIgnored private var activeOperation: Task<Void, Never>?
    @ObservationIgnored private var stopping = false
    @ObservationIgnored private var initialized = false
    @ObservationIgnored private var selectedContext: SavedAuthoringContext? { didSet { refreshCompletionRecordKey() } }
    @ObservationIgnored private var currentView: PipelineView? { didSet { refreshCompletionRecordKey() } }
    /// Changes whenever the record `completionRangeStates` reads may have changed, so views ask again.
    public private(set) var completionRecordKey = ""
    private func refreshCompletionRecordKey() {
        let key = [currentView?.executionID ?? "", String(currentView?.completionRangesJSON?.hashValue ?? 0),
                   selectedWorkID ?? "", String(selectedContext?.completionRanges?.hashValue ?? 0)].joined(separator: "|")
        if key != completionRecordKey { completionRecordKey = key }
    }
    @ObservationIgnored private var importedDDL: DDLPackageImport?
    @ObservationIgnored private var providerModelsByExecution: [String: ModelSelection] = [:]
    /// Set once the saved next-work conditions have been read, so the defaults never overwrite them.
    @ObservationIgnored private var colorArrangementCursors: [String: ColorArrangementCursor] = [:]

    public init(databaseURL: URL? = nil, transport: (any ProviderTransport)? = nil) {
        self.databaseURL = databaseURL
        self.transport = transport
        self.openDatabase = { try InkuDatabase(url: $0) }
    }

    // Allows isolated runtime fixtures without reading the user's Keychain or vault.
    init(databaseURL: URL, transport: (any ProviderTransport)? = nil, personalRuntime: ChatGPTPlanRuntime) {
        self.databaseURL = databaseURL
        self.transport = transport
        self.openDatabase = { try InkuDatabase(url: $0) }
        self.personalRuntimeOverride = personalRuntime
    }

    init(databaseURL: URL, openDatabase: @escaping @Sendable (URL) throws -> InkuDatabase) {
        self.databaseURL = databaseURL
        self.transport = nil
        self.openDatabase = openDatabase
    }

    public var sourceLocked: Bool { authoringAuthority == "ddl_authoritative" }
    public var developerModeEnabled: Bool { ProviderObservationPolicy.developerModeEnabled }

    func pluginCalls(source: String, workID: String? = nil) async -> [PluginCall] {
        guard let bootstrap else { return [] }
        let language = instructionLanguage(for: source)
        let disabledPackages = settings.plugins?.disabledPackageIDs ?? []
        let disabledWords = bootstrap.pluginWords.filter { $0.packageID.map(disabledPackages.contains) ?? false }
        let disabledIDs = disabledWords.map(\.id) + Array(disabledPackages)
        let names: [ExactJSON] = bootstrap.pluginWords.flatMap { word in
            (word.japanese + word.english).map { name in
                .object(["name": .string(name), "qualified_name": .string(word.id),
                         "enabled": .bool(!(word.packageID.map(disabledPackages.contains) ?? false))])
            }
        }
        let config: ExactJSON
        let locks: ExactJSON
        let workContext: SavedAuthoringContext?
        if let workID, let host {
            if let cached = pluginWorkContexts[workID] {
                workContext = cached
            } else {
                let token = workActionReadToken
                let loaded = try? await host.savedAuthoringContext(workID: workID)
                guard token == workActionReadToken, !Task.isCancelled else { return [] }
                if let loaded { pluginWorkContexts[workID] = loaded }
                workContext = loaded
            }
        } else { workContext = selectedContext }
        let current = workID == nil ? currentView : nil
        if let configData = current?.configurationJSON ?? workContext?.configuration,
           let documentData = current?.documentJSON ?? workContext?.document,
           let savedConfig = try? ExactJSON(data: configData), let document = try? ExactJSON(data: documentData) {
            config = savedConfig
            locks = document["macro_locks"].array == nil ? .array([]) : document["macro_locks"]
        } else {
            guard let catalog = try? bootstrap.macroCatalogValue(language: language, settings: settings, importedPlugins: importedDDL?.plugins ?? []) else { return [] }
            let entries = catalog["entries"].array ?? []
            config = .object(["definitions": .array(entries.map { $0["definition"] }), "macro_summaries": .array(entries.map { $0["summary"] })])
            locks = catalog["locks"]
        }
        let normalizedLocks = (locks.array ?? []).map { value -> ExactJSON in
            var value = value
            if let digest = value["digest"].string, !digest.hasPrefix("sha256:") { value["digest"] = .string("sha256:" + digest) }
            return value
        }
        let enabled = normalizedLocks.compactMap { $0["qualified_name"].string }
        let request: ExactJSON = .object(["source": .string(source), "language": .string(language),
            "definitions": config["definitions"].array == nil ? .array([]) : config["definitions"],
            "summaries": config["macro_summaries"].array == nil ? .array([]) : config["macro_summaries"],
            "locks": .array(normalizedLocks), "compiler": config["compiler"], "enabled": .array(enabled.map { .string($0) }),
            "disabled": .array(disabledIDs.map { .string($0) }), "plugin_names": .array(names)])
        let bytes = request.data
        let answer = await Task.detached { InkuCore.pluginCalls(bytes) }.value
        guard !Task.isCancelled, let result = try? ExactJSON(data: answer), result["schema"].string == "inku.plugin-calls.v1" else { return [] }
        let entries = result["entries"].array ?? []
        return (result["calls"].array ?? []).compactMap { PluginCall($0, source: source, entries: entries) }
    }
    public var displayedWork: SavedWork? { previewWork ?? selectedWork }
    public var isPreview: Bool { previewWork != nil }
    public var hasNextDrawingModel: Bool {
        settings.providers.contains { nextDrawingModelReference.hasPrefix($0.id + ":") && nextDrawingModelReference.count > $0.id.count + 1 }
    }
    public var canCommitDDL: Bool { !isBusy && !isPreview && !ddlText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && (currentExecutionID != nil || selectedContext != nil) }
    public var canEditCurrentDDL: Bool { !isBusy && !isPreview && (currentExecutionID != nil || selectedContext != nil) }
    public var canCompleteHoles: Bool { !isBusy && currentExecutionID != nil && !holeIDs.isEmpty && !settings.providers.isEmpty && ddlText == visibleDDL }
    var hasDrawingConnection: Bool { !settings.providers.isEmpty }
    public var hasAvailableNextDrawingModel: Bool {
        hasNextDrawingModel && (drawingAvailability[nextDrawingModelReference]?.drawing ?? false)
    }
    public var hasAvailableBatchDrawingModel: Bool {
        drawingAvailability[nextDrawingModelReference]?.batch ?? false
    }
    public var nextBatchDrawingModelReference: String {
        hasAvailableBatchDrawingModel ? nextDrawingModelReference : ""
    }
    /// A description is drawable only when something is left once the author's numbers and comments are cut
    /// (Web `canSubmit`, state.svelte.ts:363-364).
    public var canGenerate: Bool {
        if inputMode == "image" {
            return database != nil && !isBusy && !isPreview && imageInput != nil && !imageVisionModel.isEmpty
        }
        return database != nil && !isBusy && !isPreview
            && (inputMode == "ddl" ? !ddlText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                   : DescriptionLabels.hasDrawableText(descriptionText))
            && (inputMode == "ddl" || (hasAvailableNextDrawingModel
                && !(selectedWorkID != nil && sourceLocked)))
    }
    public var imageVisionModel: String {
        let tab = activeDrawTab == "batch_image" ? "batch_image" : "image"
        return drawSelections[tab]?.models.vision ?? ""
    }
    public func selectImageVisionModel(_ reference: String) {
        let tab = activeDrawTab == "batch_image" ? "batch_image" : "image"
        drawSelections[tab]?.models.vision = reference
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

    /// Web `forkPipelineDescription` → Server `fork_linked_history`: the held work's own description, unchanged, starts
    /// a child of it (`description_fork`, edge `description_edit`) from its saved configuration and the next conditions.
    /// The edited DDL is not carried over, and the held work itself is untouched.
    public func forkDescription() async {
        guard canForkDescription, let parent = selectedWorkID else { return }
        inputMode = "description"
        await generate(parentWorkID: parent, fork: true)
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
            let url = try databaseURL ?? InkuDatabase.applicationSupportURL(hostIdentifier: InkuPlatform.hostIdentifier)
            // Opening validates the existing database before allowing writes and can
            // take significant time. Keep that blocking work off the UI executor.
            let openDatabase = self.openDatabase
            let database = try await Task.detached(priority: .userInitiated) {
                try openDatabase(url)
            }.value
            let store = ProviderSettingsStore(url: url.deletingLastPathComponent().appendingPathComponent("providers.json"))
            let bootstrap = try Bootstrap(pluginDataDirectory: url.deletingLastPathComponent())
            let settings = try await store.loadNormalized()
            self.database = database
            await autonomousRefinement.restore(database: database)
            // A derived store: without it thumbnails are drawn and kept in memory, and nothing else stops.
            await thumbnails.connect(store: try? ThumbnailStore(url: ThumbnailStore.url(besideDatabase: url)), database: database)
            await thumbnails.synchronize()
            library.thumbnails = thumbnails
            library.prefetchesThumbnails = true
            library.pageCompanions = { [weak self] ids in await self?.loadWorkActionStates(workIDs: ids) }
            displayRenderer.connectFailureLog(directory: url.deletingLastPathComponent())
            let personalRuntime = personalRuntimeOverride ?? ChatGPTPlanRuntime(directory: url.deletingLastPathComponent().appendingPathComponent("personal-chatgpt", isDirectory: true))
            let ordinary: any ProviderTransport
            if let native = transport as? URLSessionProviderTransport { ordinary = native.withRateDatabase(database) }
            else { ordinary = transport ?? URLSessionProviderTransport(database: database) }
            let routed = PersonalPlanRoutingTransport(ordinary: ordinary, runtime: personalRuntime)
            self.personalRuntime = personalRuntime
            self.managedTransport = routed
            self.host = PipelineHost(database: database, transport: routed, credentials: credentials,
                                     svgLimitBytes: { try await store.svgLimitBytes() })
            self.settingsStore = store
            self.settings = settings
            updateStageDefaultProviderID()
            synchronizeNextDrawingModel(previousSettings: nil)
            pruneComparisonModels()
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
            var startupCatalogError: Error?
            do { _ = try bootstrap.macroCatalog(language: instructionLanguage(for: currentInputText), settings: settings) }
            catch { startupCatalogError = error }
            library.onMutation = { [weak self] in await self?.refreshWorks() }
            // Web `inku-history-display-mode` and the thumbnail/list tab come back with the library.
            if let layout = display.libraryLayout.flatMap(LibraryLayout.init(rawValue:)) {
                library.layout = layout
            }
            if let grouped = display.libraryGrouped { library.grouped = grouped }
            await library.connect(database: database)
            try await reloadWorks()
            // Web completeAuthentication opens the first normal history item once at startup.
            if let latest = try await database.libraryPage(limit: 1).items.first?.work, selectedWorkID == nil {
                await selectWork(latest)
            }
            status = startupCatalogError.map { "プラグインのカタログを検証できませんでした: \($0.localizedDescription)" } ?? "準備完了"
            if database.vacuumDeferred {
                status = display.message(status) + " " + display.label("空き容量が足りないためデータベースの整理を次回に延期しました。", "Database compaction was postponed until the next launch because there is not enough free space.")
            }
        } catch {
            initialized = false
            report(error)
        }
    }

    public func generate() async { await generate(parentWorkID: selectedWorkID) }

    private func generate(parentWorkID: String?, fork: Bool = false) async {
        guard fork ? canForkDescription : canGenerate, let host, let bootstrap else { return }
        if inputMode == "ddl" {
            if let work = selectedWork, work.id == parentWorkID {
                _ = await drawEditedDDL(work: work, source: ddlText, paperID: canvasID)
            } else { _ = await drawNewDDL(ddlText, presentation: .workspace) }
            return
        }
        let runningMode = inputMode
        let runningImage = runningMode == "image" ? imageInput : nil
        let freshRequest: GenerationRequest
        do {
            if runningMode == "image", let image = runningImage {
                freshRequest = try requestForImage(image, provenance: imageProvenance)
            } else {
                freshRequest = try requestForCurrentInput(inputMode: runningMode, parentWorkID: parentWorkID,
                    derivationKind: parentWorkID == nil ? "new" : "description_edit")
            }
        } catch { report(error); return }
        let initialStatus = runningMode == "description" && drawRoute == "read_and_draw" ? display.webCopy(sketchMode == "on" ? "readDrawReading" : "readDrawWriting", sketchMode == "on" ? "記述を読んでいます…" : "指示書を書いています…") : "生成中"
        _ = await performSerialized(status: initialStatus, singleInputMode: runningMode, clearProgressJournals: true) { [weak self] token in
            guard let self else { return }
            await self.runGeneration(host: host, bootstrap: bootstrap, token: token, parentWorkID: parentWorkID,
                                     runningMode: runningMode, image: runningImage, freshRequest: freshRequest)
        }
    }

    private func runGeneration(host: PipelineHost, bootstrap: Bootstrap, token: UUID, parentWorkID: String?,
                               runningMode: String, image: PreparedImageInput?, freshRequest: GenerationRequest) async {
        do {
            let request = try await pinPersonalPlanRequests([freshRequest])[0]
            let view = try await host.generate(request, image: image) { [weak self] progress in
                Task { @MainActor in self?.receive(progress, token: token, models: request.models) }
            }
            await recordDescriptionFeedback(request: request, view: view)
            await notifyCommittedWork(view)
            guard generationToken == token, !Task.isCancelled else { return }
            let saved: SavedWork?
            if let id = view.savedWorkID { saved = try await database?.work(id: id) }
            else { saved = nil }
            let context: SavedAuthoringContext?
            if let saved { context = try await host.savedAuthoringContext(workID: saved.id) }
            else { context = nil }
            guard generationToken == token, !Task.isCancelled else { return }
            if runFollowed { apply(view) }
            else { finishProviderStage(view); status = statusText(for: view) }
            if runFollowed, let work = saved {
                displayWork(work)
                selectedContext = context
                savedImageDDL = selectedContext?.imageDDL
                savedDescriptionDDL = selectedContext?.descriptionDDL
                if savedImageDDL != nil { imageInput = nil; imageFileName = ""; imageProvenanceTyped = false }
            }
            try await reloadWorks()
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

    public func selectWork(_ work: SavedWork, adoptDrawOptions: Bool = true) async {
        guard !isBrowsingLocked else { return }
        stopFollowingRun()
        if !isBusy && !backgroundDrawing {
            providerProgress = nil
            errorText = nil
        }
        displayWork(work, loadSelectedAnnotation: false)
        let selectionToken = displayToken
        currentExecutionID = nil
        currentView = nil
        selectedContext = nil
        savedImageDDL = nil
        holeIDs = []
        selectedHoleIDs = []
        patchProposalJSON = ""
        patchCandidate = ""
        completionIssues = []
        diagnosticsJSON = ""
        await library.loadSelectedAnnotation(workID: work.id)
        guard displayToken == selectionToken, selectedWorkID == work.id, !isBrowsingLocked else { return }
        guard let host else { return }
        let recordedMetrics = (try? await host.savedProviderMetrics(workID: work.id)) ?? []
        guard displayToken == selectionToken, selectedWorkID == work.id, !isBrowsingLocked else { return }
        providerMetrics = recordedMetrics
        do {
            let context = try await host.savedAuthoringContext(workID: work.id)
            guard displayToken == selectionToken, selectedWorkID == work.id, !isBrowsingLocked else { return }
            if let document = context.document,
               (try ExactJSON(data: document))["saijiki"].string != SaijikiEdition.current {
                throw HostError("saijiki_migration_required")
            }
            selectedContext = context
            savedImageDDL = context.imageDDL
            savedDescriptionDDL = context.descriptionDDL
            imageProvenanceTyped = false
            let recordedTab = context.imageDDL == nil ? "describe" : "image"
            let recordedOptions = try prepareRecordedOptions(work, isImage: context.imageDDL != nil)
            if adoptDrawOptions { drawSelections[recordedTab] = try DrawOptionsCore.forRecorded(recordedOptions, tab: recordedTab, defaults: drawDefaults) }
            if context.imageDDL != nil {
                imageInput = nil; imageFileName = ""; imageProvenance = context.imageProvenance ?? ""
                inputMode = "image"
            } else if inputMode == "image" {
                imageInput = nil; imageFileName = ""; imageProvenance = ""
                inputMode = "description"
            }
            authoringAuthority = context.authority
            authoringOrigin = context.origin
            authoringRevision = context.revision
            authoringPhase = "completed"
            let presentation = try await host.savedWorkPresentation(workID: work.id)
            guard displayToken == selectionToken, selectedWorkID == work.id, !isBrowsingLocked else { return }
            diagnosticsJSON = try presentation.diagnosticsJSON.map(Self.pretty) ?? ""
        } catch {
            guard displayToken == selectionToken, selectedWorkID == work.id, !isBrowsingLocked else { return }
            if adoptDrawOptions, let recorded = try? prepareRecordedOptions(work, isImage: false),
               let options = try? DrawOptionsCore.forRecorded(recorded, tab: "describe", defaults: drawDefaults) {
                drawSelections["describe"] = options
            }
            if (error as? HostError)?.code == "saijiki_migration_required" { errorText = failureMessage(error) }
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
        // The box draft belongs to the work it was typed for.
        if ddlBoxDraftWorkID != work.id { ddlBoxDraftWorkID = nil; ddlBoxDraft = "" }
        selectedWorkID = work.id
        selectedWork = work
        // Web `adoptSketch`: another work on screen brings its own prose; an edit belongs to the work it was made on.
        if loadSelectedAnnotation {
            Task { @MainActor [weak self] in
                guard let self, self.displayToken == selectionToken,
                      self.selectedWorkID == work.id, self.previewWork == nil else { return }
                await self.library.loadSelectedAnnotation(workID: work.id)
            }
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
        ddlText = work.ddl ?? ""
        descriptionText = work.effectiveSourceText
    }

    public func replay(_ work: SavedWork) async {
        guard !isBusy, let host else { return }
        _ = await performSerialized(status: "再演奏中") { [weak self] token in
            guard let self else { return }
            await self.runReplay(work: work, host: host, token: token)
        }
    }

    private func runReplay(work: SavedWork, host: PipelineHost, token: UUID) async {
        do {
            let result = try await host.replay(workID: work.id)
            await notifySavedWork(result)
            guard generationToken == token, !Task.isCancelled else { return }
            try await reloadWorks()
            if runFollowed {
                let context = try? await host.savedAuthoringContext(workID: result.id)
                if runFollowed {
                    displayWork(result)
                    selectedContext = context
                    currentExecutionID = nil
                    currentView = nil
                }
            }
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
        progressJournals.removeAll()
        providerModelsByExecution.removeAll()
        chatGPTFailureCodes.removeAll()
        journalExecutionID = nil
        activeSingleInputMode = nil
        operationBrowsingLocked = false
        stopping = false
        isBusy = false
    }

    public func localDataDirectory() -> URL? { database?.url.deletingLastPathComponent() }
    public var stageDefaultProviderID: String { cachedStageDefaultProviderID }
    private func updateStageDefaultProviderID() {
        cachedStageDefaultProviderID = ProviderModelReference.split(settings.models.stage1Model, providers: settings.providers)?.providerID
            ?? ProviderModelReference.stageDefaultProviderID
    }
    func reloadPluginPackages() throws {
        guard let directory = localDataDirectory() else { throw HostError("database_unavailable") }
        let updated = try Bootstrap(pluginDataDirectory: directory)
        _ = try updated.macroCatalogValue(language: instructionLanguage(for: currentInputText), settings: settings,
                                           importedPlugins: importedDDL?.plugins ?? [])
        bootstrap = updated
        pluginWords = updated.pluginWords.filter { settings.plugins?.isEnabled($0.packageID ?? "") ?? true }
    }

    public func checkPluginPackage(data: Data, isArchive: Bool) async throws -> PluginPackageCheck {
        guard !isBusy, let directory = localDataDirectory(), let bootstrap else { throw HostError("plugin_package_busy") }
        return try await PluginPackageRepository(dataDirectory: directory).check(data: data, isArchive: isArchive, bootstrap: bootstrap)
    }

    @discardableResult
    public func installPluginPackage(data: Data, isArchive: Bool, replace: Bool) async throws -> PluginPackageCheck {
        guard !isBusy, let directory = localDataDirectory(), let bootstrap else { throw HostError("plugin_package_busy") }
        let repository = PluginPackageRepository(dataDirectory: directory)
        let checked = try await repository.check(data: data, isArchive: isArchive, bootstrap: bootstrap)
        guard checked.ok else { return checked }
        guard !isBusy else { throw HostError("plugin_package_busy") }
        try repository.install(checked, replace: replace)
        try reloadPluginPackages()
        return checked
    }

    public func deletePluginPackage(_ id: String) async throws {
        guard !isBusy, let directory = localDataDirectory() else { throw HostError("plugin_package_busy") }
        let repository = PluginPackageRepository(dataDirectory: directory)
        guard try repository.load().contains(where: { $0.id == id }) else { throw HostError("plugin_package_not_found") }
        try repository.delete(id)
        var updated = await hostSettings()
        var preferences = updated.plugins ?? .init()
        preferences.disabledPackageIDs.remove(id)
        updated.plugins = preferences
        try await updateHostSettings(updated)
        try reloadPluginPackages()
    }
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
        nextDrawingModelReference = reference
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

    /// Web model-inspection `$effect`: a saved comparison model that is no longer offered leaves the saved choice at once,
    /// not at the next tick of a checkbox.
    func pruneComparisonModels() {
        guard let saved = display.preferences.comparisonModels else { return }
        let kept = Array(saved.filter { SettingsModel.isBatchModelAvailable($0, settings: settings) }.prefix(4))
        if kept != saved { display.preferences.comparisonModels = kept }
    }

    private func synchronizeNextDrawingModel(previousSettings: HostSettings?) {
        refreshDrawingAvailability()
        providerSettingsRevision += 1
    }

    public func updateHostSettings(_ settings: HostSettings) async throws {
        guard !isSettingsInteractionLocked, let settingsStore,
              !isBusy || settings.plugins == self.settings.plugins else { throw HostError("settings_busy_or_unavailable") }
        var settings = settings
        if self.settings.providerDefaultsInstalled == true { settings.providerDefaultsInstalled = true }
        if settings.inactiveBuiltinProviderIDs == nil { settings.inactiveBuiltinProviderIDs = self.settings.inactiveBuiltinProviderIDs }
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
        _ = try bootstrap?.macroCatalogValue(language: instructionLanguage(for: currentInputText), settings: settings, importedPlugins: importedDDL?.plugins ?? [])
        settings = try await settingsStore.save(settings)
        let previousSettings = self.settings
        self.settings = settings
        updateStageDefaultProviderID()
        synchronizeNextDrawingModel(previousSettings: previousSettings)
        pruneComparisonModels()
        if let bootstrap {
            pluginWords = bootstrap.pluginWords.filter { settings.plugins?.isEnabled($0.packageID ?? "") ?? true }
        }
    }

    public func operationalLimitDefaults() throws -> [String: UInt32] {
        guard let bootstrap else { throw HostError("installation_unavailable") }
        return try bootstrap.operationalLimitDefaults()
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

    public var svgLimitMiB: Int { settings.svgLimitMiB ?? SVGGenerationLimit.recommendedMiB }

    public func updateDrawingLimits(_ limits: [String: UInt32], svgLimitMiB: Int? = nil) async throws {
        var changed = settings
        changed.drawingLimits = limits
        if let svgLimitMiB { changed.svgLimitMiB = svgLimitMiB }
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

    /// Copies the active ChatGPT profile's published models into the settings the model pickers read. It reads the
    /// saved publication only (no catalog or token refresh); a profile that cannot be pinned leaves no ChatGPT model.
    public func synchronizePersonalPlanModels() async {
        guard let personalRuntime else { return }
        await synchronizePersonalPlanModels(try? await personalRuntime.publication())
    }
    public func synchronizePersonalPlanModels(_ publication: ChatGPTPlanPublication?) async {
        let next = SettingsModel.mirroringPersonalPlan(settings, publication: publication)
        guard next != settings else { return }
        try? await updateHostSettings(next)
    }

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
            else if !request.authoring.isDirect {
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
        else if !request.authoring.isDirect { throw HostError("chatgpt_session_pin_required") }
    }

    public func clearPreview() async {
        guard !isBusy else { return }
        if let selectedWork { await selectWork(selectedWork, adoptDrawOptions: false) }
        else { clearWorkOutput() }
    }

    public func savePreview() async {
        guard !isBusy, let previewWork, let executionID = currentExecutionID, let host else { return }
        _ = await performSerialized(status: "候補を保存中") { [weak self] _ in
            guard let self else { return }
            let saved = try await host.saveCandidate(executionID: executionID)
            await self.notifySavedWork(saved)
            guard saved.id == previewWork.id else { throw HostError("candidate_identity_changed") }
            try await self.reloadWorks()
            let context = try await host.savedAuthoringContext(workID: saved.id)
            if self.runFollowed {
                self.displayWork(saved)
                self.selectedContext = context
                self.currentExecutionID = nil
            }
            self.status = "選択した候補を保存しました"
        }
    }

    public func savedConfiguration(workID: String) async throws -> SavedAuthoringContext {
        guard let host else { throw HostError("pipeline_unavailable") }
        let context = try await host.savedAuthoringContext(workID: workID)
        workActionStates[workID] = SavedWorkActionState(context)
        if context.imageDDL != nil { imageWorkProvenance[workID] = context.imageProvenance ?? "" }
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

    public func workPresentationTitle(_ work: SavedWork) -> String {
        if let provenance = imageWorkProvenance[work.id] {
            return display.label("画像", "Image") + (provenance.isEmpty ? "" : " · " + provenance)
        }
        return LibraryWorkPresentation.title(work, untitled: display.localized("無題"))
    }

    public func loadWorkActionState(_ work: SavedWork) async {
        await loadWorkActionStates(workIDs: [work.id])
    }

    /// Export feedback must not replace a drawing operation's live progress.
    public func reportExportStatus(_ message: String) {
        guard !isBusy else { return }
        status = message
    }

    public func loadWorkActionStates(workIDs: [String]) async {
        if !Set(workIDs).isDisjoint(with: workActionReadsInFlight) {
            await withCheckedContinuation { workActionReadWaiters.append($0) }
            guard !Task.isCancelled else { return }
            await loadWorkActionStates(workIDs: workIDs)
            return
        }
        let eligible = Set(workIDs).subtracting(workActionReadsInFlight)
        let missing = eligible.filter { workActionStates[$0] == nil }
        let labelIDs = eligible.subtracting(displayLabelReads)
        guard !missing.isEmpty || !labelIDs.isEmpty, let host else { return }
        let token = workActionReadToken
        let reading = Set(missing).union(labelIDs)
        workActionReadsInFlight.formUnion(reading)
        defer {
            if token == workActionReadToken { workActionReadsInFlight.subtract(reading) }
            let waiters = workActionReadWaiters
            workActionReadWaiters.removeAll()
            for waiter in waiters { waiter.resume() }
        }
        do {
            LibraryPerformanceProbe.actionSummaryRead()
            let summaries = try await host.savedAuthoringSummaries(workIDs: Array(missing))
            let labels = try await host.savedDisplayLabels(workIDs: Array(labelIDs))
            guard token == workActionReadToken, !Task.isCancelled else { return }
            let states = Dictionary(uniqueKeysWithValues: missing.map { id in
                (id, summaries[id].map { $0.isImage ? .image : SavedWorkActionState(origin: $0.origin, authority: $0.authority) } ?? .unavailable)
            })
            // Every menu observes this dictionary. Publish the page once, not once per card, and not at all when
            // nothing new came back: an unchanged write still redraws every reader.
            if !states.isEmpty { workActionStates.merge(states) { _, new in new } }
            let imageLabels = summaries.reduce(into: [String: String]()) { values, item in
                if item.value.isImage { values[item.key] = item.value.imageProvenance ?? "" }
            }
            if !imageLabels.isEmpty { imageWorkProvenance.merge(imageLabels) { _, new in new } }
            if !labels.isEmpty { savedDisplayLabels.merge(labels) { _, new in new } }
            displayLabelReads.formUnion(labelIDs)
        } catch {
            guard token == workActionReadToken, !Task.isCancelled else { return }
            errorText = error.localizedDescription
        }
    }

    public func applyDDLImport(_ value: DDLPackageImport) throws {
        guard !isBusy, let bootstrap else { throw HostError("ddl_import_busy_or_unavailable") }
        let language = value.language ?? instructionLanguage(for: value.source)
        _ = try bootstrap.macroCatalogValue(language: language, settings: settings, importedPlugins: value.plugins)
        clearWorkOutput()
        importedDDL = value; importedMacroNames = value.names
        inputMode = "ddl"; ddlText = value.source
        status = "DDLを読み込みました。生成して保存できます。"
        if let count = value.migratedEdits {
            status += " " + display.webCopyFormat("ddlImportMigrated", "旧い歳時記から %@ 箇所を書き換えました。", count)
        }
    }

    /// Web `CompletionRangeStatesQuery`: the displayed work's own execution when it is current, else its saved record.
    public func completionRangeStates(source: String) -> [CompletionRangeState] {
        guard let work = displayedWork else { return [] }
        if let view = currentView, view.savedWorkID == work.id {
            return CompletionRangeState.states(configuration: view.configurationJSON, source: source, record: view.completionRangesJSON)
        }
        guard let context = selectedContext, selectedWorkID == work.id else { return [] }
        return CompletionRangeState.states(configuration: context.configuration, source: source, record: context.completionRanges)
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
        // Server `_refuse_if_locked` after `_rewords`: a held parent takes only its own description back (the fork).
        if parentWorkID != nil && mode == "description" && (selectedContext?.authority == "ddl_authoritative" || sourceLocked),
           try (parentWorkID != selectedWorkID
            || DescriptionLabels.rewords(description ?? descriptionText, selectedWork?.effectiveSourceText ?? "")) {
            throw HostError("description_source_locked")
        }
        let sketch: SketchRequest = sketchOverride
            ?? (sketchMode == "on" ? .on : sketchMode == "supplied" ? .supplied(sketchText) : .off)
        let savedConfig = parentWorkID == selectedWorkID && parentWorkID != nil ? selectedContext?.configuration : nil
        var request = try bootstrap.request(inputMode: mode, source: source ?? ddlText,
            description: description ?? descriptionText,
            language: instructionLanguage(for: mode == "ddl" ? source ?? ddlText : description ?? descriptionText), catalogID: catalogID,
            canvasID: canvasID, seed: seedText, wild: wildOverride ?? wild, settings: nextGenerationHostSettings,
            parentWorkID: parentWorkID, derivationKind: derivationKind, catalogMode: catalogModeOverride ?? catalogMode,
            sketch: sketch, savedConfiguration: savedConfig,
            importedPlugins: mode == "ddl" && parentWorkID == nil ? importedDDL?.plugins ?? [] : [])
        if mode == "description" { applyDescriptionRoute(&request, settings: nextGenerationHostSettings) }
        request.recordsDrawOptions = mode == "description" && parentWorkID == nil && derivationKind == "new" ? true : nil
        request.captureProviderIO = developerModeEnabled && display.preferences.captureProviderIO == true
        // Server `start`: a direct DDL drawn from the selected saved work carries its completion range record.
        if mode == "ddl", parentWorkID != nil, parentWorkID == selectedWorkID {
            request.completionRanges = selectedContext?.completionRanges
            request.lawsRecords = selectedContext?.lawsRecords
        }
        return request
    }

    public func setImageProvenanceFromUser(_ text: String) {
        imageProvenance = text
        imageProvenanceTyped = true
    }

    public func setImageInput(_ image: PreparedImageInput, fileName: String, automaticProvenance: String = "") {
        let typed = imageProvenanceTyped && !imageProvenance.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? imageProvenance : nil
        if selectedWork != nil { clearWorkOutput(); inputMode = "image" }
        imageProvenance = typed ?? automaticProvenance
        imageProvenanceTyped = typed != nil
        imageInput = image; imageFileName = fileName
    }

    public func requestForImage(_ image: PreparedImageInput, provenance: String, canvasID: String? = nil, options: DrawOptions? = nil) throws -> GenerationRequest {
        guard let bootstrap else { throw HostError("installation_unavailable") }
        let options = options ?? currentDrawOptions
        let vision = options.models.vision ?? ""
        guard SettingsModel.isRegisteredModelAvailable(vision, purpose: "vision", settings: settings) else { throw HostError("vision_model_not_available") }
        let selectedCanvasID = canvasID ?? options.canvasAspect
        let resolvedCanvasID = selectedCanvasID == "image" ? image.nearestFormatID : selectedCanvasID
        var request = try bootstrap.request(inputMode: "description", source: "", description: "", language: instructionLanguage(for: ""),
            catalogID: options.catalog.id, canvasID: resolvedCanvasID, seed: seedText, wild: false,
            settings: nextGenerationHostSettings, parentWorkID: nil, derivationKind: "new",
            catalogMode: options.catalog.mode, sketch: .off)
        request.authoring = .image(input: image.authoringJSON, autoCatalog: options.catalog.mode == "auto")
        request.imageProvenance = provenance
        request.models.stage1Model = vision; request.models.stage2Model = vision
        var config = try ExactJSON(data: request.configuration)
        if var fields = config.object { fields.removeValue(forKey: "catalog_seed"); config = .object(fields) }
        config["compiler"]["host"]["canvas_fit"] = .string("contain")
        request.configuration = config.data
        return request
    }

    public func requestForBatchDescription(_ description: String, sketchMode: String) throws -> GenerationRequest {
        guard hasAvailableBatchDrawingModel else { throw HostError("drawing_model_not_available") }
        guard ["off", "on"].contains(sketchMode) else { throw HostError("invalid_batch_sketch_mode") }
        return try requestForCurrentInput(inputMode: "description", source: "", description: description,
            parentWorkID: nil, derivationKind: "new", catalogModeOverride: catalogMode,
            sketchOverride: sketchMode == "on" ? .on : .off)
    }

    func makeBatchRows(_ entries: [(Int, String)], sketchMode: String, batchRunID: String) async throws -> [BatchRow] {
        guard ["off", "on"].contains(sketchMode) else { throw HostError("invalid_batch_sketch_mode") }
        guard let bootstrap else { throw HostError("installation_unavailable") }
        guard SettingsModel.isModelAvailable(nextDrawingModelReference, settings: settings) else {
            throw HostError("drawing_model_not_available")
        }
        let capturedSettings = nextGenerationHostSettings
        let requestedLanguage = language, uiLanguage = display.preferences.language
        let chosenCatalog = catalogID, selectedCanvas = canvasID, mode = catalogMode, seed = seedText
        let useWild = wild, route = drawRoute, composition = descriptionComposition
        let review = SettingsModel.isRegisteredModelAvailable(capturedSettings.models.stage1Model, purpose: "vision", settings: capturedSettings)
        let captureIO = developerModeEnabled && display.preferences.captureProviderIO == true
        let catalogChoices = bootstrap.catalogs.map(\.id).filter { $0 != chosenCatalog }
        let task = Task.detached {
            struct Key: Hashable { let language: String; let catalog: String }
            let languages = entries.map { InkuCore.resolveInstructionLanguage(text: $0.1, requested: requestedLanguage, fallback: uiLanguage) ?? "ja" }
            let invariant = try bootstrap.batchInvariant(languages: Set(languages), settings: capturedSettings)
            var templates: [Key: (GenerationRequest, String)] = [:]
            var rows: [BatchRow] = []
            for (index, entry) in entries.enumerated() {
                try Task.checkCancellation()
                let selected: String
                if mode == "random" {
                    guard let choice = catalogChoices.randomElement() else { throw HostError("catalog_selection_unavailable") }
                    selected = choice
                } else { selected = chosenCatalog }
                let actualSeed = seed.isEmpty ? String(UInt64.random(in: 0...((UInt64(1) << 53) - 1))) : seed
                let key = Key(language: languages[index], catalog: selected)
                var request: GenerationRequest
                if let cached = templates[key] {
                    request = cached.1 == actualSeed ? cached.0 : try bootstrap.reseedBatchRequest(cached.0, seed: actualSeed,
                        language: key.language, invariant: invariant)
                }
                else {
                    request = try bootstrap.request(inputMode: "description", source: "", description: entry.1,
                        language: key.language, catalogID: chosenCatalog, canvasID: selectedCanvas, seed: actualSeed,
                        wild: useWild, settings: capturedSettings, catalogMode: mode,
                        sketch: sketchMode == "on" ? .on : .off, batchInvariant: invariant,
                        batchSelectedCatalog: mode == "random" ? selected : nil)
                    if route == "read_and_draw" {
                        request.drawRoute = route; request.descriptionComposition = composition; request.descriptionReview = review
                    }
                    request.recordsDrawOptions = true; request.captureProviderIO = captureIO
                    templates[key] = (request, actualSeed)
                }
                request.authoring = .description(entry.1, autoCatalog: mode == "auto", sketch: sketchMode == "on" ? .on : .off)
                request.description = entry.1
                var provenance = request.provenance ?? GenerationProvenance()
                provenance.batchRunID = batchRunID; provenance.batchLineNumber = entry.0
                provenance.displayLabel = "#\(entry.0)"; request.provenance = provenance
                rows.append(BatchRow(line: entry.0, input: entry.1, request: request))
            }
            return rows
        }
        return try await withTaskCancellationHandler { try await task.value } onCancel: { task.cancel() }
    }

    public func requestForDemoDescription(_ description: String, sketchMode: String) throws -> GenerationRequest {
        guard let bootstrap, ["off", "on"].contains(sketchMode),
              SettingsModel.isBatchModelAvailable(settings.models.stage1Model, settings: settings) else {
            throw HostError("drawing_model_not_available")
        }
        // Web work/state.svelte.ts:636-641: the demo follows the catalog choice but has no wild setting (`wildOverride(false)`).
        var request = try bootstrap.request(inputMode: "description", source: "", description: description,
            language: instructionLanguage(for: description), catalogID: catalogID, canvasID: canvasID, seed: seedText, wild: false,
            settings: settings, parentWorkID: nil, derivationKind: "new",
            catalogMode: catalogMode == "auto" ? "auto" : "fixed", sketch: sketchMode == "on" ? .on : .off)
        applyDescriptionRoute(&request, settings: settings)
        return request
    }

    public func drawNewDDL(_ source: String, imported: DDLPackageImport? = nil,
                           presentation: CanvasFitPresentation = .editor) async -> Bool {
        guard !isBusy, canvasFitQuestion == nil, let bootstrap,
              !source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        do {
            let paperID = canvasID
            let fit = await chooseCanvasFit(source: source, paperID: paperID, presentation: presentation)
            guard fit != .cancel, !isBusy, canvasID == paperID else { return false }
            var request = try bootstrap.request(inputMode: "ddl", source: source, description: "",
                language: imported?.language ?? instructionLanguage(for: source), catalogID: catalogID, canvasID: paperID,
                seed: seedText, wild: wild, settings: nextGenerationHostSettings, parentWorkID: nil, derivationKind: "new",
                importedPlugins: imported?.plugins ?? [])
            request.configuration = try configuration(request.configuration, canvasFit: fit, paperID: paperID)
            request = try await pinPersonalPlanRequests([request])[0]
            return await runAutomation(request: request, singleInputMode: "ddl") != nil
        } catch { report(error); return false }
    }

    public func drawEditedDDL(work: SavedWork, source: String,
                              paperID: String? = nil, presentation: CanvasFitPresentation = .workspace,
                              forceEdit: Bool = false) async -> Bool {
        guard !isBusy, canvasFitQuestion == nil, !work.trashed,
              !source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        do {
            _ = try await checkedSavedAdjustmentParent(work)
            let saved = try await savedConfiguration(workID: work.id)
            var options = try ExactJSON(data: saved.renderOptions)
            let target = paperID ?? options["canvas_aspect_id"].string ?? work.renderCanvasAspectID ?? canvasID
            let unchanged = !forceEdit && source == work.ddl && options["wild"].bool == wild
                && work.stage1Model == nextDrawingModelReference && work.stage2Model == nextDrawingModelReference
            let fit = await chooseCanvasFit(source: source, recordedWork: unchanged ? work : nil,
                                             paperID: target, presentation: presentation)
            guard fit != .cancel, !isBusy else { return false }
            if fit == .contain, unchanged { return await drawFittedSavedWork(work, paperID: target) }
            if let paperID, let bootstrap {
                let paper = try bootstrap.replayOptions(catalogID: catalogID, canvasID: paperID)
                options["canvas_aspect_id"] = .string(paper.canvasID)
                options["canvas"] = .object(["width": .number(String(Int(paper.canvasWidth))), "height": .number(String(Int(paper.canvasHeight)))])
            }
            options["wild"] = .bool(wild)
            guard let catalog = options["catalog_id"].string, options["resolved_color_map"].object != nil else {
                throw HostError("saved_refinement_options_unavailable")
            }
            let models = nextGenerationHostSettings.models
            var request = GenerationRequest(authoring: .directDDL(source),
                configuration: try configuration(saved.configuration, canvasFit: fit, paperID: target),
                renderOptions: options.data, clipPolicy: saved.clipPolicy, models: models, providers: settings.providers,
                renderColorMaps: [catalog: options["resolved_color_map"].data], description: work.effectiveSourceText,
                parentWorkID: work.id, derivationKind: "ddl_edit")
            request.completionRanges = saved.completionRanges
            request.lawsRecords = saved.lawsRecords
            request.inheritedImageDDL = saved.imageDDL
            request.imageProvenance = saved.imageProvenance
            request = try await pinPersonalPlanRequests([request])[0]
            return await runAutomation(request: request, singleInputMode: "ddl") != nil
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
            result = saved
            let context = try await host.savedAuthoringContext(workID: saved.id)
            if self.runFollowed { self.displayWork(saved); self.selectedContext = context }
        }
        return result
    }

    /// Allocate the entire round before any drawing, keeping saved colors, locks, policies and source authority.
    public func makeDrawingAdjustmentPlans(work: SavedWork, kind: String, count: Int,
                                           wildOverride: Bool? = nil,
                                           modelReference: String? = nil,
                                           recomposeMode: Recomposition.Mode = .principled) async throws -> [DrawingAdjustmentPlan] {
        guard !isPreview, !stopping, let host else { throw HostError("authoring_busy_or_unavailable") }
        guard kind == "layout_change" else { throw HostError("unknown_refinement_kind") }
        guard [1, 4].contains(count) else { throw HostError("invalid_adjustment_count") }
        let drawing = nextGenerationHostSettings
        let selected = currentDrawOptions
        let source = try await checkedSavedAdjustmentParent(work)
        let saved = try await host.savedAuthoringContext(workID: source.id)
        try Task.checkCancellation()
        guard ["description_authoritative", "ddl_authoritative"].contains(saved.authority) else { throw HostError("saved_authoring_context_unavailable") }
        let baseConfiguration = try ExactJSON(data: saved.configuration)
        let baseOptions = try ExactJSON(data: saved.renderOptions)
        guard baseOptions["catalog_id"].string != nil, baseOptions["resolved_color_map"].object != nil else {
            throw HostError("saved_refinement_options_unavailable")
        }
        guard let document = saved.document, let ddl = source.ddl, !ddl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw HostError("saved_document_unavailable")
        }
        let description = source.effectiveSourceText.trimmingCharacters(in: .whitespacesAndNewlines)
        var models = drawing.models
        models.stage2Model = modelReference ?? drawing.models.stage2Model
        if let modelReference { try validateAdjustmentModel(modelReference, providers: drawing.providers) }
        var usedSeeds = Set([source.compositionSeed].compactMap { $0 }.compactMap(UInt64.init))
        guard let bootstrap, let canvas = baseOptions["canvas_aspect_id"].string,
              let renderSeed = baseOptions["render_seed"].string ?? baseOptions["render_seed"].number else {
            throw HostError("saved_refinement_options_unavailable")
        }
        let chosenCatalog = try bootstrap.request(inputMode: "ddl", source: ddl, description: description,
            language: source.instructionLangResolved ?? "ja", catalogID: selected.catalog.id, canvasID: canvas,
            seed: renderSeed, wild: wildOverride ?? source.renderWild ?? false, settings: drawing,
            parentWorkID: source.id, derivationKind: kind, catalogMode: "fixed", savedConfiguration: saved.configuration)
        let chosenConfiguration = try ExactJSON(data: chosenCatalog.configuration)
        let chosenOptions = try ExactJSON(data: chosenCatalog.renderOptions)
        var requests: [GenerationRequest] = []
        var recompositions: [Recomposition?] = []
        for _ in 0..<count {
            var configuration = baseConfiguration
            var options = baseOptions
            configuration["compiler"]["host"] = chosenConfiguration["compiler"]["host"]
            options["catalog_id"] = chosenOptions["catalog_id"]
            options["resolved_color_map"] = chosenOptions["resolved_color_map"]
            configuration["catalogs"] = .array([])
            configuration["compiler"]["stage15_variation"] = .null
            options["wild"] = .bool(wildOverride ?? source.renderWild ?? baseOptions["wild"].bool ?? false)
            options["svg_profile"] = .string("display")
            var metadata: ExactJSON = .object([:])
            var recomposition: Recomposition?
            if kind == "layout_change" {
                var seed: UInt64
                repeat { seed = UInt64.random(in: 0...((UInt64(1) << 53) - 1)) } while usedSeeds.contains(seed)
                usedSeeds.insert(seed)
                configuration["compiler"]["composition_seed"] = .string(String(seed))
                options["composition_seed"] = .string(String(seed))
                // Server compose: the numeric ranges are chosen again with this option's exact configuration.
                recomposition = Recomposition.choose(configuration: configuration, source: ddl, mode: recomposeMode, seed: String(seed),
                                                     lawsRecords: saved.lawsRecords)
                metadata = .object(["composition_seed": .number(String(seed)), "recompose_mode": .string(recomposeMode.rawValue)])
            }
            // A recomposed option is a new direct DDL from the saved work; unchanged ranges keep its document.
            let chosen = recomposition?.source
            let authoring: GenerationAuthoring = .directDDL(chosen ?? ddl)
            let retains = chosen == nil
            requests.append(GenerationRequest(authoring: authoring, configuration: configuration.data, renderOptions: options.data,
                clipPolicy: saved.clipPolicy, models: models, providers: drawing.providers,
                renderColorMaps: chosenCatalog.renderColorMaps, description: description,
                parentWorkID: source.id, derivationKind: kind, saveHistory: false,
                retainedDocument: retains ? document : nil, retainedAuthority: retains ? saved.authorityJSON : nil,
                derivationMetadata: metadata.data))
            recompositions.append(recomposition)
            // A redraw of the saved DDL keeps the parent's completion range and laws records (Server fork).
            requests[requests.count - 1].completionRanges = saved.completionRanges
            requests[requests.count - 1].lawsRecords = saved.lawsRecords
        }
        requests = try await pinPersonalPlanRequests(requests)
        try Task.checkCancellation()
        return zip(requests, recompositions).map { request, recomposition in
            DrawingAdjustmentPlan(stage1Model: request.models.stage1Model,
                stage2Model: request.models.stage2Model.isEmpty ? nil : request.models.stage2Model, parent: source, operation: .author(request),
                recomposition: recomposition)
        }
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
        recordDrawingLog(executionID: candidate.executionID)
        await notifySavedWork(saved)
        do { try await reloadWorks() } catch { report(error) }
        guard generationToken == token, !stopping, !Task.isCancelled, runFollowed else { return saved }
        do {
            let context = try await host.savedAuthoringContext(workID: saved.id)
            let view = try? await host.restore(executionID: candidate.executionID)
            guard generationToken == token, !stopping, !Task.isCancelled, runFollowed else { return saved }
            if let view, view.savedWorkID == saved.id { apply(view) }
            else {
                diagnosticsJSON = ""
            }
            displayWork(saved)
            selectedContext = context
            authoringAuthority = context.authority; authoringOrigin = context.origin; authoringRevision = context.revision
            authoringPhase = "completed"
            currentExecutionID = nil; currentView = nil
            holeIDs = []; selectedHoleIDs = []; patchProposalJSON = ""; patchCandidate = ""; completionIssues = []
            status = "選択した候補を保存しました"
        } catch { report(error) }
        return saved
    }

    /// Validate the pinned parent before an option page saves or replaces any candidates.
    public func validateSavedAdjustmentParent(_ work: SavedWork) async throws {
        try Task.checkCancellation()
        _ = try await checkedSavedAdjustmentParent(work)
        try Task.checkCancellation()
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

    public func makeRefinementRequest(work: SavedWork, kind: String,
                                      modelReference: String? = nil, catalogIDOverride: String? = nil,
                                      wildOverride: Bool? = nil, compositionForm: String? = nil) async throws -> GenerationRequest {
        guard let bootstrap else { throw HostError("installation_unavailable") }
        guard ["layout_change", "catalog_change", "model_comparison", CompositionForm.derivationKind].contains(kind) else {
            throw HostError("unknown_refinement_kind")
        }
        let formChange = kind == CompositionForm.derivationKind
        if formChange { guard let compositionForm, CompositionForm.all.contains(compositionForm) else { throw HostError("invalid_authoring_options") } }
        let saved = try await savedConfiguration(workID: work.id)
        let config = try ExactJSON(data: saved.configuration)
        let options = try ExactJSON(data: saved.renderOptions)
        let held = saved.authority == "ddl_authoritative"
        let reading = kind == "model_comparison" || formChange
        if held && reading { throw HostError("description_source_locked") }
        let language = work.instructionLangResolved ?? config["language"].string ?? instructionLanguage(for: work.effectiveSourceText)
        guard let renderSeed = work.renderSeed ?? options["render_seed"].string ?? options["render_seed"].number,
              let canvasID = work.renderCanvasAspectID ?? options["canvas_aspect_id"].string,
              let catalogID = work.renderColorCatalogID ?? work.catalogID ?? options["catalog_id"].string else {
            throw HostError("saved_refinement_options_unavailable")
        }
        let fresh = String(UInt64.random(in: 0...((UInt64(1) << 53) - 1)))
        // Web generateCompositionFormCandidates: the work's own catalog, fixed, and a sketch (its saved one, else a new one).
        let chosenCatalog = catalogIDOverride ?? (kind == "catalog_change" || formChange ? catalogID : self.catalogID)
        let description = work.effectiveSourceText
        let sketch: SketchRequest = work.sketchText.map(SketchRequest.supplied) ?? (formChange ? .on : .off)
        var request = try bootstrap.request(inputMode: reading ? "description" : "ddl", source: work.ddl ?? "", description: description,
            language: language, catalogID: chosenCatalog, canvasID: canvasID, seed: renderSeed, wild: wildOverride ?? work.renderWild ?? false,
            settings: nextGenerationHostSettings, parentWorkID: work.id, derivationKind: kind,
            catalogMode: reading && !formChange ? self.catalogMode : "fixed", sketch: sketch,
            savedConfiguration: saved.configuration)
        if formChange, let compositionForm {
            request.drawRoute = "read_and_draw"; request.descriptionComposition = true
            request.descriptionCompositionForm = compositionForm
            if let stage1 = work.stage1Model ?? work.stage2Model { request.models.stage1Model = stage1 }
            if let stage2 = work.stage2Model ?? work.stage1Model { request.models.stage2Model = stage2 }
            let from = saved.descriptionDDL.flatMap { try? ExactJSON(data: $0) }?["composition"]["answer"]["form"].string
            request.derivationMetadata = ExactJSON.object(["form_from": from.map(ExactJSON.string) ?? .null,
                                                           "form_to": .string(compositionForm)]).data
        }
        var nextConfig = try ExactJSON(data: request.configuration)
        var nextOptions = try ExactJSON(data: request.renderOptions)
        let composition: ExactJSON = kind == "layout_change" ? .string(fresh) : config["compiler"]["composition_seed"]
        nextConfig["compiler"]["composition_seed"] = composition
        nextOptions["composition_seed"] = composition
        request.configuration = nextConfig.data; request.renderOptions = nextOptions.data
        // Web composeLayoutGeneration: the AI process chooses the ranges again by principle.
        var recomposed: String?
        if kind == "layout_change", !reading, let ddl = work.ddl {
            let recomposition = Recomposition.choose(configuration: nextConfig, source: ddl, mode: .principled, seed: fresh,
                                                     lawsRecords: saved.lawsRecords)
            recomposed = recomposition.source
            if let chosen = recomposed { request.authoring = .directDDL(chosen) }
            var metadata = (try? request.derivationMetadata.map { try ExactJSON(data: $0) } ?? nil) ?? .object([:])
            if metadata.object == nil { metadata = .object([:]) }
            metadata["composition_seed"] = .number(fresh); metadata["recompose_mode"] = .string("principled")
            request.derivationMetadata = metadata.data
        }
        if let modelReference {
            guard !modelReference.isEmpty else { throw HostError("model_reference_missing") }
            request.models.stage1Model = modelReference; request.models.stage2Model = modelReference
        }
        if !reading {
            guard let document = saved.document else { throw HostError("saved_document_unavailable") }
            if recomposed == nil { request.retainedDocument = document; request.retainedAuthority = saved.authorityJSON }
            request.completionRanges = saved.completionRanges
            request.lawsRecords = saved.lawsRecords
        }
        return request
    }

    /// A saved-work edit starts a child from its pinned configuration, independently of editor restoration.
    /// `metadata` adds fields to a description edit's record (a juxtaposition's `juxtaposition`).
    public func makeSavedWorkEditRequest(work: SavedWork, mode: WorkEditMode, description: String,
                                        sketchMode: String = "off", wildOverride: Bool? = nil,
                                        metadata: [String: ExactJSON] = [:], drawingSettings: HostSettings? = nil) async throws -> GenerationRequest {
        guard !isBusy, !isPreview, database != nil else { throw HostError("authoring_busy_or_unavailable") }
        let drawing = drawingSettings ?? nextGenerationHostSettings
        let chosen = currentDrawOptions
        guard drawingSettings != nil || hasNextDrawingModel else { throw HostError("model_reference_missing") }
        let saved = try await savedWorkEditContext(work)
        let text = (mode == .description ? description : work.effectiveSourceText).trimmingCharacters(in: .whitespacesAndNewlines)
        let selectedLanguage = instructionLanguage(for: text)
        guard ["ja", "en"].contains(selectedLanguage) else { throw HostError("invalid_instruction_language") }
        guard !text.isEmpty else { throw HostError("description_required") }
        var configuration = try ExactJSON(data: saved.configuration)
        guard let bootstrap else { throw HostError("installation_unavailable") }
        try bootstrap.updatePluginDefinitions(in: &configuration, language: selectedLanguage, settings: drawing)
        var options = try ExactJSON(data: saved.renderOptions)
        guard let canvas = options["canvas_aspect_id"].string,
              let seed = options["render_seed"].string ?? options["render_seed"].number else { throw HostError("saved_refinement_options_unavailable") }
        let current = try bootstrap.request(inputMode: "description", source: "", description: text,
            language: selectedLanguage, catalogID: chosen.catalog.id, canvasID: canvas, seed: seed,
            wild: wildOverride ?? work.renderWild ?? false, settings: drawing, parentWorkID: work.id,
            derivationKind: "description_edit", catalogMode: chosen.catalog.mode, sketch: .off,
            savedConfiguration: saved.configuration)
        let currentConfiguration = try ExactJSON(data: current.configuration)
        let currentOptions = try ExactJSON(data: current.renderOptions)
        configuration["compiler"]["host"] = currentConfiguration["compiler"]["host"]
        configuration["catalogs"] = currentConfiguration["catalogs"]
        configuration["catalog_seed"] = currentConfiguration["catalog_seed"]
        options["catalog_id"] = currentOptions["catalog_id"]
        options["resolved_color_map"] = currentOptions["resolved_color_map"]
        configuration["language"] = .string(selectedLanguage)
        // The Server applies Stage 1.5 only when this operation explicitly asks for it.
        configuration["compiler"]["stage15_variation"] = .null
        options["wild"] = .bool(wildOverride ?? work.renderWild ?? options["wild"].bool ?? false)
        options["svg_profile"] = .string("display")
        let sketch: SketchRequest
        if mode == .sketch {
            guard ["off", "on"].contains(sketchMode) else { throw HostError("invalid_sketch_mode") }
            // Explicitly asking for the layer runs it anew; it never replays saved prose.
            sketch = sketchMode == "on" ? .on : .off
        } else if let prose = work.sketchText, !prose.isEmpty {
            sketch = text == work.effectiveSourceText.trimmingCharacters(in: .whitespacesAndNewlines) ? .supplied(prose) : .on
        } else { sketch = .off }
        var request = GenerationRequest(authoring: .description(text, autoCatalog: chosen.catalog.mode == "auto", sketch: sketch),
            configuration: configuration.data, renderOptions: options.data, clipPolicy: saved.clipPolicy,
            models: drawing.models, providers: drawing.providers,
            renderColorMaps: current.renderColorMaps, description: text,
            parentWorkID: work.id, derivationKind: mode == .description ? "description_edit" : "sketch_grain_change",
            derivationMetadata: ExactJSON.object(mode == .description
                ? metadata.merging(["edited_from_history_id": .string(work.id)]) { _, edited in edited }
                : ["edited_from_history_id": .string(work.id), "from_sketch_state": work.sketchState.map(ExactJSON.string) ?? .null,
                   "to_sketch_mode": .string(sketchMode)]).data)
        try Task.checkCancellation()
        if chosen.route == "read_and_draw" {
            request.drawRoute = "read_and_draw"; request.descriptionComposition = chosen.composition == "on"
            request.descriptionReview = SettingsModel.isRegisteredModelAvailable(request.models.stage1Model, purpose: "vision", settings: drawing)
        }
        let pinned = try await pinPersonalPlanRequests([request])[0]
        try Task.checkCancellation()
        return pinned
    }

    /// Only the start payload differs from a saved DDL child. The shared pipeline decides whether its laws can run.
    public func makeSavedLawsRequest(work: SavedWork, direction: ExactJSON, settings: HostSettings,
                                     wild: Bool?) async throws -> GenerationRequest {
        let chosen = currentDrawOptions
        let saved = try await savedConfiguration(workID: work.id)
        var configuration = try ExactJSON(data: saved.configuration)
        var options = try ExactJSON(data: saved.renderOptions)
        if let wild { options["wild"] = .bool(wild) }
        guard let bootstrap, let canvas = options["canvas_aspect_id"].string,
              let seed = options["render_seed"].string ?? options["render_seed"].number else {
            throw HostError("saved_refinement_options_unavailable")
        }
        let selected = try bootstrap.request(inputMode: "ddl", source: work.ddl ?? "", description: work.effectiveSourceText,
            language: work.instructionLangResolved ?? "ja", catalogID: chosen.catalog.id, canvasID: canvas, seed: seed,
            wild: wild ?? work.renderWild ?? false, settings: settings, parentWorkID: work.id,
            derivationKind: "laws_change", catalogMode: "fixed", savedConfiguration: saved.configuration)
        let selectedConfiguration = try ExactJSON(data: selected.configuration)
        let selectedOptions = try ExactJSON(data: selected.renderOptions)
        configuration["compiler"]["host"] = selectedConfiguration["compiler"]["host"]
        options["catalog_id"] = selectedOptions["catalog_id"]
        options["resolved_color_map"] = selectedOptions["resolved_color_map"]
        configuration["catalogs"] = .array([])
        var request = GenerationRequest(authoring: .directDDL(work.ddl ?? ""), configuration: configuration.data,
            renderOptions: options.data, clipPolicy: saved.clipPolicy, models: settings.models, providers: settings.providers,
            renderColorMaps: selected.renderColorMaps, description: work.effectiveSourceText,
            parentWorkID: work.id, derivationKind: "laws_change", historyVisibility: "normal")
        request.savedLawsDirection = direction.data
        request.completionRanges = saved.completionRanges
        request.lawsRecords = saved.lawsRecords
        return try await pinPersonalPlanRequests([request])[0]
    }

    /// A run owns this serialized operation, but does not replace the canvas with each lineage-only attempt.
    public func runAutonomousMove(request: GenerationRequest) async throws -> SavedWork {
        guard let host, let database else { throw HostError("pipeline_unavailable") }
        var child: SavedWork?
        var failure: Error?
        let ran = await performSerialized(status: "生成中", background: true) { [self] token in
            do {
                try await validatePinnedRequest(request)
                let view = try await host.generate(request) { [weak self] progress in
                    Task { @MainActor in self?.receive(progress, token: token, models: request.models) }
                }
                if let id = view.savedWorkID { child = try await database.work(id: id) }
                if child == nil {
                    let events = try ExactJSON(data: view.eventsJSON).array ?? []
                    let reason = events.last { $0["tag"].string == "failed" }?["payload"]["reason"].string
                    throw HostError(reason ?? "autonomous_generation_failed")
                }
                await notifyCommittedWork(view)
                try await reloadWorks()
            } catch { failure = error; throw error }
        }
        if let child { return child }
        try Task.checkCancellation()
        if let failure { throw failure }
        throw HostError(ran ? "autonomous_generation_failed" : "authoring_busy_or_unavailable")
    }

    func sendChunkPrompt(_ asked: ExactJSON, png: Data?, request: GenerationRequest) async throws -> String {
        guard let transport = managedTransport ?? transport else { throw HostError("pipeline_unavailable") }
        var prompt: ExactJSON = .object(["system": asked["system"], "message": asked["text"],
            "response_schema": asked["response_schema"], "action_name": .string("generate_normalized_ddl")])
        var images: [ExactJSON] = []
        if let png {
            let hash = SHA256.hash(data: png).map { String(format: "%02x", $0) }.joined()
            prompt["images"] = .array([.object(["media_type": .string("image/png"), "byte_len": .integer(png.count), "sha256": .string(hash)])])
            images = [.string("data:image/png;base64," + png.base64EncodedString())]
        }
        let digest = SHA256.hash(data: prompt.data).map { String(format: "%02x", $0) }.joined()
        prompt["prompt_id"] = .string("inku.chunk-moves-\(asked["purpose"].string ?? "choose").v1")
        prompt["prompt_digest"] = .string("sha256:" + digest)
        let config = try ExactJSON(data: request.configuration)
        prompt["instruction_language"] = config["language"]
        var action: ExactJSON = .object(["tag": .string("generate_normalized_ddl"), "timeout_ms": .string("300000"), "delay_ms": .string("0"),
            "payload": .object(["prompt": prompt]), "_transient_images": .array(images),
            "identity": .object(["action_id": .string(UUID().uuidString), "attempt": .integer(1), "request_digest": .string(digest)])])
        for attempt in 1...2 {
            action["identity"]["attempt"] = .integer(attempt)
            let result: Data
            if let personal = transport as? any ChatGPTPlanEffectTransport {
                let limit = (config["prompt_limits"]["max_response_bytes"].number ?? config["prompt_limits"]["max_response_bytes"].string).flatMap(Int.init) ?? 1_048_576
                result = try await personal.performPersonalPlan(action: action.data, models: request.models, providers: request.providers,
                    session: request.chatGPTSession, argumentLimit: limit, credentials: credentials, onBytes: { _ in }, onDiagnostic: { _ in })
            } else {
                result = try await transport.perform(action: action.data, models: request.models, providers: request.providers, credentials: credentials, onBytes: { _ in })
            }
            let response = try ExactJSON(data: result)
            if response["tag"].string == "provider_failed" {
                let failure = response["failure"].string ?? "provider_failed"
                if attempt == 1 && ["rate_limited", "transport_timeout", "transport_unavailable"].contains(failure) {
                    try await Task.sleep(for: .seconds(2)); continue
                }
                throw HostError(failure)
            }
            guard let text = response["response"].string else { throw HostError("unusable_answer") }
            return text
        }
        throw HostError("provider_failed")
    }

    /// SPEC §7.8 juxtaposition: what the shared core reads for this work (Server `api_juxtaposition`). `written` is the
    /// description as the work keeps it, labels and all; the others are read without labels. The sources are the
    /// author's other works that may lend a sentence: not in the trash or kept only in a lineage, not labelled DDL or
    /// demo, no `test data` comment, a description, and not held by their DDL (the menu's own judgement).
    public func juxtapositionInputs(work: SavedWork) async throws -> JuxtapositionInputs {
        guard let database, let host else { throw HostError("pipeline_unavailable") }
        _ = try await savedWorkEditContext(work)
        let written = work.effectiveSourceText
        let description = try Self.unlabelled(written)
        guard !description.isEmpty else { throw HostError("juxtaposition_source_has_no_description") }
        guard !work.svg.isEmpty else { throw HostError("juxtaposition_source_has_no_image") }
        var lineage: [String] = []
        var added: [String] = []
        if let nodeID = work.lineageNodeID, let branch = try await database.lineage(focusNodeID: nodeID, pathOnly: true) {
            for node in branch.nodes {
                let text = try Self.unlabelled(node.work?.effectiveSourceText ?? "")
                if !text.isEmpty, lineage.last != text { lineage.append(text) }
            }
            for edge in branch.edges {
                let recorded = (try? ExactJSON(data: Data(edge.metadataJSON.utf8)))?["juxtaposition"]["sentence"].string
                let sentence = recorded?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                if !sentence.isEmpty { added.append(sentence) }
            }
        }
        try Task.checkCancellation()
        let rows = try await database.juxtapositionSources()
        let ids = rows.map(\.id)
        let summaries = try await host.savedAuthoringSummaries(workIDs: ids)
        let labels = try await host.savedDisplayLabels(workIDs: ids)
        let sources = Self.juxtapositionSources(rows: rows, labels: labels, summaries: summaries, excluding: work.id)
        return JuxtapositionInputs(description: description, written: written, lineage: lineage, added: added, sources: sources)
    }

    /// The stored works that may lend a sentence, labels removed (Server `owned_description_sources` and the
    /// current work left out). A work counts as held by its DDL by the menu's own judgement of its saved authority.
    nonisolated public static func juxtapositionSources(rows: [(id: String, text: String, note: String?)], labels: [String: String],
                                            summaries: [String: SavedAuthoringSummary],
                                            excluding workID: String) -> [(id: String, text: String)] {
        rows.compactMap { row in
            let label = labels[row.id]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            guard row.id != workID, !["DDL", "[demo]"].contains(label), !(row.note ?? "").lowercased().contains("test data"),
                  !row.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, let summary = summaries[row.id],
                  SavedWorkActionState(origin: summary.origin, authority: summary.authority) == .description else { return nil }
            guard let text = try? InkuCore.descriptionWithoutLabels(row.text) else { return nil }
            return (row.id, text)
        }
    }

    private static func unlabelled(_ text: String) throws -> String {
        try InkuCore.descriptionWithoutLabels(text).trimmingCharacters(in: .whitespacesAndNewlines)
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
                if !adopted && self.runFollowed { self.currentExecutionID = previousExecution; self.currentView = previousView }
            }
            let candidate = try await self.generateCandidate(request: request, token: token, comparison: false)
            try Task.checkCancellation()
            let saved = try await self.saveComparisonCandidate(executionID: candidate.executionID, token: token)
            self.recordDrawingLog(executionID: candidate.executionID)
            result = saved
            guard self.generationToken == token, !self.stopping, !Task.isCancelled else { return }
            guard self.runFollowed else { try await self.reloadWorks(); return }
            let view = try await host.restore(executionID: candidate.executionID)
            let context = try await host.savedAuthoringContext(workID: saved.id)
            guard self.generationToken == token, !self.stopping, !Task.isCancelled else { return }
            guard self.runFollowed else { try await self.reloadWorks(); return }
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
        if config.object?["catalog_seed"] != nil { config["catalog_seed"] = .string(seed) }
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
            defer {
                if let self, self.runFollowed {
                    self.currentExecutionID = self.selectedWorkID == originalWorkID ? execution : nil
                }
            }
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
        if view.phase == "failed", let events = try ExactJSON(data: view.eventsJSON).array,
           let failure = events.last(where: { $0["tag"].string == "failed" })?["payload"],
           failure["reason"].string == "svg_too_large" {
            throw HostError("svg_too_large", svgLimitMiB: failure["svg_limit_mib"].number.flatMap(Int.init))
        }
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

    public func makeToolVariantPlans(work: SavedWork, mode: ToolChangeMode) async throws -> [ToolVariantPlan] {
        guard !isPreview, !stopping, let host else { throw HostError("authoring_busy_or_unavailable") }
        _ = try await checkedSavedAdjustmentParent(work)
        return try await host.makeToolVariantPlans(workID: work.id, mode: mode)
    }

    public func nextColorArrangementPage(work: SavedWork) async throws -> ColorArrangementPage? {
        guard !isPreview, !stopping, let host else { throw HostError("authoring_busy_or_unavailable") }
        _ = try await checkedSavedAdjustmentParent(work)
        let cursor: SavedVariantOrdinal
        switch colorArrangementCursors[work.id] ?? .next(0) {
        case .exhausted: return nil
        case .next(let value): cursor = value
        }
        let page = try await host.makeColorArrangementPage(workID: work.id, cursor: cursor)
        // Reserve before drawing, including failed/stopped options, as the Web coordinator does.
        colorArrangementCursors[work.id] = page.nextCursor.map(ColorArrangementCursor.next) ?? .exhausted
        return page
    }

    public func makeGroundVariantPlans(work: SavedWork) async throws -> [SavedScoreVariantPlan] {
        guard !isPreview, !stopping, let host else { throw HostError("authoring_busy_or_unavailable") }
        _ = try await checkedSavedAdjustmentParent(work)
        return try await host.makeGroundVariantPlans(workID: work.id)
    }

    public func prepareSavedScoreVariant(_ plan: SavedScoreVariantPlan, token: UUID) async throws -> PreparedCandidate {
        guard generationToken == token, !stopping, let host else { throw CancellationError() }
        let candidate = try await host.previewSavedScoreVariant(plan)
        try Task.checkCancellation()
        guard generationToken == token, !stopping else { throw CancellationError() }
        return candidate
    }

    public func prepareToolVariant(_ plan: ToolVariantPlan, token: UUID) async throws -> PreparedCandidate {
        guard generationToken == token, !stopping, let host else { throw CancellationError() }
        let candidate = try await host.previewToolVariant(plan)
        try Task.checkCancellation()
        guard generationToken == token, !stopping else { throw CancellationError() }
        return candidate
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
        // As adoptDrawingAdjustmentCandidate: the "saving the chosen options" line does not outlive the save.
        status = "選択した候補を保存しました"
        await notifySavedWork(saved)
        // The explicit transaction result remains authoritative if a later refresh is interrupted.
        do { try await reloadWorks() } catch { report(error) }
        return saved
    }

    /// A committed option becomes the displayed child; the author's next description remains a draft.
    public func showSavedRefinement(_ work: SavedWork) async {
        let descriptionDraft = descriptionText
        await selectWork(work)
        descriptionText = descriptionDraft
        await library.loadLineage(work: work)
    }

    /// The busy flag remains held until cancellation has drained the active task.
    @discardableResult
    public func performSerialized(status: String, background: Bool = false, locksBrowsing: Bool = false, singleInputMode: String? = nil,
                                  clearProgressJournals: Bool = false,
                                  operation: @escaping @MainActor (UUID) async throws -> Void) async -> Bool {
        guard !isBusy, activeOperation == nil, database != nil else { return false }
        let token = UUID()
        generationToken = token
        activeSingleInputMode = singleInputMode
        providerProgress = nil
        activeExecutionID = nil
        if clearProgressJournals { progressJournals.removeAll() }
        if !background { currentExecutionID = nil }
        backgroundDrawing = background
        operationBrowsingLocked = locksBrowsing
        runFollowed = true
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
                if self.generationToken == token && !Task.isCancelled {
                    if background {
                        self.automationFailureMessage = self.failureMessage(error)
                        if !self.stopping { self.providerProgress?.finish(.failed, at: Date()) }
                        self.status = "処理を完了できませんでした"
                    } else {
                        self.report(error)
                    }
                }
            }
        }
        activeOperation = task
        await task.value
        finishOperation(token: token)
        return succeeded
    }

    public func runAutomation(request: GenerationRequest, image: PreparedImageInput? = nil, background: Bool = false, locksBrowsing: Bool = false,
                              singleInputMode: String? = nil,
                              onExecutionStarted: (@MainActor @Sendable (String) async throws -> Void)? = nil) async -> SavedWork? {
        guard let host else { return nil }
        var result: SavedWork?
        _ = await performSerialized(status: "生成中", background: background, locksBrowsing: locksBrowsing, singleInputMode: singleInputMode) { [weak self] token in
            guard let self else { return }
            self.automationFailureMessage = nil
            try await self.validatePinnedRequest(request)
            let view = try await host.generate(request, image: image, onStarted: onExecutionStarted) { [weak self] progress in
                Task { @MainActor in self?.receive(progress, token: token, models: request.models) }
            }
            if self.generationToken == token, !self.stopping {
                self.activeExecutionID = view.executionID
                if let message = self.drawingFailureText(view) {
                    self.automationFailureMessage = message
                    // Background batch failures belong to their original row, not the single-drawing notice.
                    if !background, self.errorText == nil { self.errorText = message }
                }
                if background {
                    self.finishProviderStage(view)
                    self.status = self.statusText(for: view)
                }
            }
            await self.recordDescriptionFeedback(request: request, view: view)
            await self.notifyCommittedWork(view)
            try Task.checkCancellation()
            if !background && self.runFollowed { self.apply(view) }
            else if !background { self.finishProviderStage(view); self.status = self.statusText(for: view) }
            try await self.reloadWorks()
            if let id = view.savedWorkID, let work = try await self.database?.work(id: id) {
                if !background && self.runFollowed {
                    let context = try await host.savedAuthoringContext(workID: id)
                    if self.runFollowed {
                        self.displayWork(work)
                        self.selectedContext = context
                        if request.retainedDocument != nil {
                            // Retained compilation stores a completed candidate, not an editable core execution.
                            self.currentExecutionID = nil
                            self.currentView = nil
                        }
                    }
                }
                result = work
            } else if !request.saveHistory, let work = view.candidateWork {
                if !background && self.runFollowed {
                    self.previewWork = work
                    self.providerMetrics = view.providerMetrics
                    self.status = "未保存の候補を表示しています"
                }
                result = work
            }
        }
        return result
    }

    func savedAutomationWork(executionID: String) async throws -> SavedWork? {
        guard let host else { throw HostError("database_unavailable") }
        return try await host.savedWorkForExecution(executionID)
    }

    /// Detach the next drawing without erasing the author's current text or sketch.
    public func detachLineage() {
        guard !isBusy else { return }
        let description = descriptionText, mode = inputMode
        let ddl = selectedWork.map { ddlBoxText(for: $0) } ?? ddlText
        let sketch = sketchText
        clearWorkOutput()
        descriptionText = description; ddlText = ddl; inputMode = mode; sketchText = sketch
    }

    public func newWork(resetTab: String? = nil) {
        guard !isBusy else { return }
        resetDrawOptions(tab: resetTab ?? activeDrawTab)
        clearWorkOutput()
    }

    private func clearWorkOutput() {
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
        savedDescriptionDDL = nil; savedImageDDL = nil; imageInput = nil; imageFileName = ""; imageProvenance = ""; imageProvenanceTyped = false
        currentExecutionID = nil
        currentSVG = ""
        visibleDDL = ""
        authoringAuthority = ""
        authoringOrigin = ""
        authoringRevision = "0"
        authoringPhase = ""
        patchProposalJSON = ""
        patchCandidate = ""
        completionIssues = []
        holeIDs = []
        selectedHoleIDs = []
        diagnosticsJSON = ""
        errorText = nil
        inputMode = activeDrawTab == "image" ? "image" : "description"
        descriptionText = ""
        ddlText = ""
        sketchText = ""
    }

    public func commitDDL(wildOverride: Bool? = nil, presentation: CanvasFitPresentation = .workspace) async {
        guard canCommitDDL else { return }
        if let work = displayedWork, !work.trashed {
            _ = await drawEditedDDL(work: work, source: ddlText, presentation: presentation)
        } else if let id = currentExecutionID, wildOverride == nil {
            await performCommand(executionID: id, command: .commitUserDDL(expectedRevision: authoringRevision, source: ddlText), kind: "ddl_edit")
        } else if selectedContext != nil {
            do {
                let request = try requestForCurrentInput(inputMode: "ddl", parentWorkID: selectedWorkID, derivationKind: "ddl_edit", wildOverride: wildOverride)
                _ = await runAutomation(request: request)
            } catch { report(error) }
        }
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
        let parentID: String?
        switch command {
        case .approvePatch, .declinePatch, .completeHoles:
            // Completion belongs to the execution that proposed it. Its original parent is already
            // pinned by the host; the currently displayed work may be unrelated or absent.
            parentID = nil
        default:
            parentID = selectedWorkID
        }
        _ = await performSerialized(status: "DDLを処理中") { [weak self] token in
            guard let self else { return }
            self.activeExecutionID = executionID
            if self.runFollowed { self.currentExecutionID = executionID }
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
            if self.runFollowed { self.apply(view) }
            else { self.finishProviderStage(view); self.status = self.statusText(for: view) }
            try await self.reloadWorks()
            if self.runFollowed, let id = view.savedWorkID, let work = try await self.database?.work(id: id), self.runFollowed {
                self.displayWork(work)
                let context = try await host.savedAuthoringContext(workID: id)
                if self.runFollowed { self.selectedContext = context }
            }
        }
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
                if self.runFollowed {
                    let context = try await host.savedAuthoringContext(workID: result.id)
                    if self.runFollowed {
                        self.displayWork(result)
                        self.selectedContext = context
                        self.currentView = nil
                        self.currentExecutionID = nil
                    }
                }
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
                "source": .string(ddlText), "language": .string(language), "macro_locks": locksJSON, "saijiki": .string(SaijikiEdition.current),
            ])
            document["source"] = .string(ddlText)
            let input = ExactJSON.object(["document": document, "definitions": config["definitions"], "compiler": config["compiler"]]).data
            let result = await Task.detached { InkuCore.compile(input) }.value
            diagnosticsJSON = try Self.pretty(result)
            status = "DDLを検査しました（未確定）"
        } catch { report(error) }
    }


    public func prepareExportSources(works: [SavedWork], profile: String = "display", requiresPluginDefinitions: Bool = false, lineAnimation: Bool = false) async throws -> [ExportSource] {
        guard !isBusy, let host, let database else { throw HostError("export_busy_or_unavailable") }
        let exportRevision = restorationRevision
        var sources: [ExportSource] = []
        for candidate in works {
            try Task.checkCancellation()
            let work: SavedWork
            if candidate.svg.isEmpty {
                guard let full = try await database.work(id: candidate.id),
                      !isBusy, restorationRevision == exportRevision,
                      full.renderHash == candidate.renderHash, full.at == candidate.at,
                      full.trashed == candidate.trashed else {
                    throw HostError("saved_export_work_changed")
                }
                work = full
            } else { work = candidate }
            var value: ExactJSON = .object([:])
            var locks: [ExactJSON] = []
            var lineRequest: ExactJSON?
            do {
                let context = try await host.savedAuthoringContext(workID: work.id)
                value = try ExactJSON(data: context.configuration)
                if let document = context.document { locks = try ExactJSON(data: document)["macro_locks"].array ?? [] }
                if lineAnimation { lineRequest = try PipelineHost.lineAnimationRequest(work: work, context: context, locks: locks) }
            }
            catch {
                if profile != "display" || requiresPluginDefinitions || lineAnimation { throw HostError("saved_export_plugin_context_unavailable") }
            }
            var profiles: [String: String] = [:]
            if profile != "display" { profiles[profile] = try await host.exportSVG(workID: work.id, profile: profile) }
            guard !isBusy, restorationRevision == exportRevision else { throw HostError("saved_export_work_changed") }
            sources.append(ExportSource(work: work, profiles: profiles,
                pluginDefinitions: value["definitions"].array ?? [], pluginSummaries: value["macro_summaries"].array?.compactMap(\.string) ?? [], pluginLocks: locks,
                language: value["language"].string, lineAnimationRequest: lineRequest))
        }
        return sources
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
            progressJournals.removeAll()
            providerModelsByExecution.removeAll()
            chatGPTFailureCodes.removeAll()
            journalExecutionID = nil
            try await database.restore(from: url)
            displayToken = UUID()
            activeExecutionID = nil
            currentExecutionID = nil
            generationToken = nil
            currentSVG = ""
            visibleDDL = ""
            selectedWorkID = nil
            selectedWork = nil
            previewWork = nil
            importedDDL = nil; importedMacroNames = []
            selectedContext = nil
            currentView = nil
            workActionStates = [:]
            imageWorkProvenance = [:]
            savedDisplayLabels = [:]
            displayLabelReads = []
            workActionReadsInFlight = []
            workActionReadToken = UUID()
            pluginWorkContexts.removeAll()
            await library.resetAfterRestore()
            await thumbnails.synchronize()
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

    public func copyImage(work target: SavedWork? = nil) async {
        guard InkuPasteboard.supportsImages else { return }
        guard !isBusy, let work = target ?? displayedWork, !work.svg.isEmpty else { return }
        let executionID = currentExecutionID
        let height = min(4096, max(256, display.preferences.clipboardHeight))
        clipboardMessageKey = nil
        let copied = await performSerialized(status: "コピー画像を準備中") { [weak self] _ in
            guard let self else { return }
            defer { if self.runFollowed { self.currentExecutionID = executionID } }
            let options = self.display.preferences.clipboardExportOptions(height: height)
            let artifacts = try await ExportService.prepare(sources: [ExportSource(work: work)], options: options)
            try Task.checkCancellation()
            guard let data = artifacts.first?.data else {
                throw HostError("clipboard_image_unavailable")
            }
            try InkuPasteboard.copy(image: data)
            self.status = "画像をコピーしました（Y軸 \(height)px）"
        }
        let key = copied ? "canvasCopiedToClipboard" : "clipboardCopyFailed"
        clipboardMessageKey = key
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(copied ? 2500 : 8000))
            if self?.clipboardMessageKey == key { self?.clipboardMessageKey = nil }
        }
    }

    private func reloadWorks() async throws {
        guard let database else { return }
        works = try await database.recentMetadata(limit: 100)
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
        await thumbnails.bakeSaved(work)
        guard let callback = onSavedWork else { return }
        // A separate task makes the committed snapshot independent of later caller cancellation.
        await Task { @MainActor in await callback(work) }.value
    }
    /// Web `runningStageLabel`: the laws stage and the color stage name themselves while they wait and receive.
    private func choosingStatus(comparison: Bool) -> String? {
        switch providerProgress?.stage {
        case .some(.laws): comparison ? "比較候補の法則の選択中…" : "法則の選択中…"
        case .some(.colors): comparison ? "比較候補の配色の選択中…" : "配色の選択中…"
        default: nil
        }
    }
    private func receive(_ progress: PipelineProgress, token: UUID, models: ModelSelection? = nil) {
        recordDrawingProgress(progress)
        guard generationToken == token, !stopping else { return }
        receiveProviderProgress(progress, models: models, comparison: false)
        switch progress {
        case .changed(let view):
            if backgroundDrawing || !runFollowed { status = statusText(for: view) }
            else { apply(view) }
        case .providerAttempt(_, _, _, let deadline):
            if let stage = providerProgress?.stage, [.descriptionReading, .descriptionComposition, .descriptionWriting, .descriptionReview].contains(stage) {
                status = providerProgress?.displayTitle(display) ?? ""
            }
            else if let choosing = choosingStatus(comparison: false) { status = choosing }
            else { status = providerProgress?.stage == .composition ? "構図を読んでいます" : "モデルの応答待ち（期限 \(deadline.formatted(date: .omitted, time: .standard))）" }
        case .transportBytes(_, let count):
            if let stage = providerProgress?.stage, [.descriptionReading, .descriptionComposition, .descriptionWriting, .descriptionReview].contains(stage) {
                status = providerProgress?.displayTitle(display) ?? ""
            }
            else if let choosing = choosingStatus(comparison: false) { status = choosing }
            else { status = providerProgress?.stage == .composition ? "構図の応答を受信中" : "応答を受信中（\(count) bytes）" }
        case .providerDiagnostic(let id, let diagnostic): receive(diagnostic, executionID: id)
        case .providerMetric, .runProgress: break
        case .saved(_, _): status = "作品を保存しました"
        }
    }
    private func receiveCandidate(_ progress: PipelineProgress, token: UUID, comparison: Bool = true, models: ModelSelection? = nil) {
        recordDrawingProgress(progress)
        guard generationToken == token, !stopping else { return }
        receiveProviderProgress(progress, models: models, comparison: comparison)
        switch progress {
        case .changed(let view): if runFollowed { currentExecutionID = view.executionID }
        case .providerAttempt(_, _, _, let deadline):
            if let choosing = choosingStatus(comparison: comparison) { status = choosing }
            else if providerProgress?.stage == .composition { status = comparison ? "比較候補の構図を読んでいます" : "構図を読んでいます" }
            else { status = comparison ? "比較候補のモデル応答待ち（期限 \(deadline.formatted(date: .omitted, time: .standard))）" : "モデルの応答待ち（期限 \(deadline.formatted(date: .omitted, time: .standard))）" }
        case .transportBytes(_, let count):
            if let choosing = choosingStatus(comparison: comparison) { status = choosing }
            else if providerProgress?.stage == .composition { status = comparison ? "比較候補の構図の応答を受信中" : "構図の応答を受信中" }
            else { status = comparison ? "比較候補を受信中（\(count) bytes）" : "応答を受信中（\(count) bytes）" }
        case .providerDiagnostic(let id, let diagnostic): receive(diagnostic, executionID: id)
        case .providerMetric, .runProgress: break
        case .saved: break
        }
    }
    /// Web words a ChatGPT plan failure with `chatgptStatus(code)`.
    private func receive(_ diagnostic: ChatGPTPlanDiagnostic, executionID: String) {
        chatGPTFailureCodes[executionID] = diagnostic.code
        errorText = ChatGPTStatusCopy.text(diagnostic.code, language: display.preferences.language)
    }
    func receiveProviderProgress(_ progress: PipelineProgress, models: ModelSelection?, comparison: Bool) {
        switch progress {
        case .runProgress(let id, let data):
            guard let value = try? ExactJSON(data: data), value["run_progress"].object != nil else { break }
            if progressJournals[id] == nil { progressJournals[id] = RunProgressJournal(report: value["run_progress"]) }
            else { progressJournals[id]?.report = value["run_progress"] }
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
            if progressJournals[id] == nil { progressJournals[id] = RunProgressJournal(report: .object([:])) }
            progressJournals[id]?.receive(metric)
        case .providerDiagnostic, .saved: break
        }
    }

    public func drawingLogs() async throws -> [DrawingLogRecord] {
        guard let host else { throw HostError("database_unavailable") }
        return try await host.drawingLogs()
    }

    /// Checks and inspectors request these durable outputs only when they need them.
    public func outputSnapshot() async -> OutputSnapshot {
        let score = displayedWork?.score ?? currentView?.scoreJSON.map { String(decoding: $0, as: UTF8.self) } ?? ""
        if let view = currentView {
            let restored: PipelineView
            if let host, let value = try? await host.restore(executionID: view.executionID) { restored = value }
            else { restored = view }
            let prompt = restored.promptJSON.flatMap { try? Self.pretty($0) } ?? ""
            let events = (try? Self.pretty(restored.eventsJSON)) ?? String(decoding: restored.eventsJSON, as: UTF8.self)
            return OutputSnapshot(prompt: prompt, promptAvailability: prompt.isEmpty ? .notRecorded : .recorded,
                                  events: events, score: score)
        }
        guard let host, let work = selectedWork else {
            return OutputSnapshot(prompt: "", promptAvailability: .unavailable, events: "", score: score)
        }
        do {
            let presentation = try await host.savedWorkPresentation(workID: work.id)
            let prompt = try presentation.promptJSON.map(Self.pretty) ?? ""
            let events = try presentation.eventsJSON.map(Self.pretty) ?? ""
            return OutputSnapshot(prompt: prompt, promptAvailability: presentation.promptJSON == nil ? .notRecorded : .recorded,
                                  events: events, score: score)
        } catch {
            return OutputSnapshot(prompt: "", promptAvailability: .unavailable, events: "", score: score)
        }
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
        guard display.preferences.saveResultLog, let host, let callback = onDrawingLog else { return }
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
        currentView = view
        currentExecutionID = view.executionID
        if isBusy, view.savedWorkID == displayedWork?.id { providerMetrics = view.providerMetrics }
        if let ddl = view.visibleDDL, ddl != visibleDDL {
            visibleDDL = ddl
            ddlText = ddl
        }
        if let svg = view.svg { currentSVG = svg }
        else if view.phase == "failed" { currentSVG = "" }
        authoringRevision = view.revision
        authoringAuthority = view.authority
        authoringOrigin = view.origin
        authoringPhase = view.phase
        holeIDs = view.holeIDs
        completionIssues = view.completionIssues
        selectedHoleIDs.formIntersection(Set(holeIDs))
        patchProposalJSON = view.patchProposalJSON.map { (try? Self.pretty($0)) ?? String(decoding: $0, as: UTF8.self) } ?? ""
        if let bytes = view.patchProposalJSON, let proposal = try? ExactJSON(data: bytes) {
            patchCandidate = proposal["candidate"]["source"].string ?? ""
        } else { patchCandidate = "" }
        if let bytes = view.deliveryJSON {
            let newDiagnostics = (try? Self.pretty(bytes)) ?? String(decoding: bytes, as: UTF8.self)
            if newDiagnostics != diagnosticsJSON { diagnosticsJSON = newDiagnostics }
        }
        status = statusText(for: view)
    }
    /// Web PipelineStatus prints `pipelineAttentionText` for a failed run, not a bare "failed".
    private func statusText(for view: PipelineView) -> String {
        if let failure = drawingFailureText(view) { return failure }
        if view.phase == "score_ready", drawRoute == "read_and_draw", activeSingleInputMode == "description" { return display.webCopy("readDrawSaving", "作品を保存しています…") }
        switch view.actionTag {
        case "read_description": return display.webCopy("readDrawReading", "記述を読んでいます…")
        case "compose_description": return display.webCopy("readDrawComposing", "構図と法則を決めています…")
        case "write_description_ddl": return display.webCopy("readDrawWriting", "指示書を書いています…")
        case "review_description_ddl": return display.webCopy("readDrawReviewing", "描いた画を見て直しています…")
        case "select_image_catalog": return display.webCopy("imageSelectingCatalog", "画像から色カタログを選んでいます…")
        case "write_image_ddl": return display.webCopy("imageWritingDdl", "画像から指示書を書いています…")
        case "draw_image_review": return display.localized("見比べる画を描いています…")
        case "review_image_ddl": return display.webCopy("imageReviewingDdl", "画像と描いた画を見比べています…")
        default:
            if view.phase == "score_ready", drawRoute == "read_and_draw" { return display.webCopy("readDrawSaving", "作品を保存しています…") }
            return Self.phaseStatus(view.phase)
        }
    }
    func drawingFailureText(_ view: PipelineView) -> String? {
        guard let text = DrawingFailureMessage.text(for: view, language: display.preferences.language,
                                   chatGPTCode: chatGPTFailureCodes[view.executionID], copy: { key, fallback in self.display.webCopy(key, fallback) }) else { return nil }
        if let delivery = view.deliveryJSON, let document = try? ExactJSON(data: delivery),
           ["upstream_diagnostics", "downstream_diagnostics", "resource_omissions", "relation_omissions", "render_warnings", "catalog_diagnostics"].contains(where: { !(document[$0].array ?? []).isEmpty }) {
            return text + "\n" + PipelineDiagnosticText.formatDocument(String(decoding: delivery, as: UTF8.self), display: display, pluginWords: pluginWords)
        }
        return text
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
        do {
            drawDefaults = try DrawOptionsCore.normalized(settings: settings, preferences: display.preferences,
                                                           colorIDs: catalogs.map(\.id))
            drawSelections = drawDefaults
        } catch { report(error) }
    }

    public func saveDrawDefaults(_ defaults: [String: DrawOptions]) throws {
        let updated = try DrawOptionsCore.update(defaults, settings: settings, preferences: display.preferences,
                                                 colorIDs: catalogs.map(\.id))
        drawDefaults = updated
        display.preferences.drawDefaults = updated
    }

    public func resetDrawOptions(tab: String) {
        if let defaults = drawDefaults[tab] { drawSelections[tab] = defaults }
    }

    private func report(_ error: Error) {
        if generationToken != nil, !stopping { providerProgress?.finish(.failed, at: Date()) }
        errorText = failureMessage(error)
        status = "処理を完了できませんでした"
    }

    public func failureMessage(_ error: Error) -> String {
        switch (error as? HostError)?.code {
        case "saijiki_migration_required": return display.label("この作品は旧い歳時記の語で保存されていて、移行が済むまで開けません。", "This work was saved in the words of an older Saijiki and cannot be opened until it is migrated.")
        case "image_missing", "image_expired": return display.webCopy("imageMissing", "画像を読み直してください。画像ファイルを選び直してから描いてください。")
        case "image_invalid": return display.webCopy("imageInvalid", "画像を読めません。JPEG・PNG・GIF・TIFF のファイルを選んでください。")
        case "image_too_large": return display.webCopy("imageTooLarge", "画像が大きすぎます。小さくしてから選んでください。")
        case "vision_model_not_available", "image_model_not_vision": return display.webCopy("imageVisionRequired", "画像を見る Vision のモデルを選んでください。")
        case "description_ddl_failed": return display.webCopy("descriptionDdlFailed", "記述から指示書を書けませんでした。モデルを変えて、もう一度描いてください")
        case "description_ddl_undrawable": return display.webCopy("descriptionDdlUndrawable", "書いた指示書から何も描けませんでした。記述かモデルを変えて、もう一度描いてください")
        case "image_ddl_failed", "image_ddl_undrawable": return display.webCopy("imageDdlFailed", "画像から指示書を書けませんでした。モデルを変えて、もう一度描いてください。")
        default: break
        }
        if (error as? HostError)?.code == "touch_change_unavailable" {
            return display.localized("この作品のてざわりを替えられません。")
        }
        if (error as? HostError)?.code == "svg_too_large" {
            if let limit = (error as? HostError)?.svgLimitMiB {
                return DrawingFailureMessage.svgLimitText(limit, language: display.preferences.language)
            }
            return display.localized("生成SVGが設定した容量の上限を超えました。設定→制限値で上限を変更できます。")
        }
        return error.localizedDescription
    }
    private static func pretty(_ bytes: Data) throws -> String {
        let value = try ExactJSON(data: bytes)
        // Pretty formatting may round JSON numbers; retain exact wire lexemes in the displayed output.
        return value.text
    }
}

extension AppModel {
    /// The shared core resolves the requested instruction language against the UI fallback.
    public func instructionLanguage(for text: String) -> String {
        InkuCore.resolveInstructionLanguage(text: text, requested: language, fallback: display.preferences.language) ?? "ja"
    }

    var currentInputText: String { inputMode == "ddl" ? ddlText : descriptionText }

    /// Web `ddlCompletions`: the enabled saijiki words and macro names, in the language the instructions read in.
    public var ddlCompletions: DdlCompletions {
        let disabled = (settings.plugins?.disabledPackageIDs ?? []).sorted()
        let uiLanguage = display.preferences.language
        if let cached = completionCache, cached.disabled == disabled, cached.uiLanguage == uiLanguage, cached.language == language { return cached.value }
        let value = DdlCompletions(saijiki: saijiki, plugins: pluginWords.filter { $0.packageID.map { !disabled.contains($0) } ?? true }, uiLanguage: uiLanguage, languageKey: language + "|" + uiLanguage) { [weak self] text in self?.instructionLanguage(for: text) ?? "ja" }
        completionCache = (disabled, uiLanguage, language, value)
        return value
    }

    private func chooseCanvasFit(source: String, recordedWork: SavedWork? = nil, paperID: String,
                                 presentation: CanvasFitPresentation) async -> CanvasFitChoice {
        guard let paper = canvases.first(where: { $0.id == paperID }),
              let target = CanvasRatio(width: Int(paper.widthRatio), height: Int(paper.heightRatio)) else { return .paper }
        let recorded = recordedWork.flatMap { work in
            canvases.first { $0.id == (work.renderCanvasAspectID ?? work.renderCanvasAspect) }
        }.flatMap { CanvasRatio(width: Int($0.widthRatio), height: Int($0.heightRatio)) }
        guard let basis = CanvasRatio.declared(in: source) ?? recorded, basis != target else { return .paper }
        guard canvasFitQuestion == nil else { return .cancel }
        let question = CanvasFitQuestion(ratio: basis, paper: paper, presentation: presentation)
        if let handler = canvasFitChoiceHandler {
            canvasFitQuestion = question
            let choice = await handler(question)
            guard canvasFitQuestion?.id == question.id else { return .cancel }
            canvasFitQuestion = nil
            return choice
        }
        return await withCheckedContinuation { continuation in
            canvasFitContinuation = continuation
            canvasFitQuestion = question
        }
    }

    public func resolveCanvasFit(_ choice: CanvasFitChoice, id: UUID) {
        guard canvasFitQuestion?.id == id else { return }
        let continuation = canvasFitContinuation
        canvasFitContinuation = nil
        canvasFitQuestion = nil
        continuation?.resume(returning: choice)
    }

    private func configuration(_ data: Data, canvasFit: CanvasFitChoice, paperID: String) throws -> Data {
        var config = try ExactJSON(data: data)
        var host = try config["compiler"].requiredObject("host").object ?? [:]
        host.removeValue(forKey: "canvas_fit")
        if canvasFit == .contain { host["canvas_fit"] = .string("contain") }
        host["canvas_format_id"] = .string(paperID)
        config["compiler"]["host"] = .object(host)
        return config.data
    }

    private func drawFittedSavedWork(_ work: SavedWork, paperID: String) async -> Bool {
        guard !isBusy, let host, let bootstrap else { return false }
        do {
            let paper = try bootstrap.replayOptions(catalogID: catalogID, canvasID: paperID)
            return await performSerialized(status: "はめ込み中") { [weak self] _ in
                guard let self else { return }
                let result = try await host.fitSavedWork(workID: work.id, paper: paper)
                await self.notifySavedWork(result)
                try Task.checkCancellation()
                try await self.reloadWorks()
                if self.runFollowed {
                    let context = try await host.savedAuthoringContext(workID: result.id)
                    if self.runFollowed {
                        self.displayWork(result)
                        self.selectedContext = context
                        self.currentView = nil; self.currentExecutionID = nil
                    }
                }
                self.status = "はめ込みを保存しました"
            }
        } catch { report(error); return false }
    }
}
