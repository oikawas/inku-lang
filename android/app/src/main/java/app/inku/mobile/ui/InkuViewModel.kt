package app.inku.mobile.ui

import android.app.Application
import android.os.SystemClock
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import app.inku.mobile.InkuApplication
import app.inku.mobile.ui.i18n.InkuFailure
import app.inku.mobile.ui.i18n.InkuStrings
import app.inku.mobile.ui.i18n.UiLanguage
import app.inku.mobile.ui.i18n.inkuError
import app.inku.mobile.ui.i18n.messageFor
import app.inku.mobile.ui.i18n.stringsFor
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.drawnWild
import app.inku.mobile.data.db.HistoryListItem
import app.inku.mobile.data.db.ExportTemplateEntity
import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.CatalogSelection
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.data.DdlExport
import app.inku.mobile.data.DdlSource
import app.inku.mobile.data.model.CameraInputProvenance
import app.inku.mobile.data.model.CameraInputOrigin
import app.inku.mobile.data.lineage.LineageDeclaration
import app.inku.mobile.data.lineage.LineageGraphNode
import app.inku.mobile.data.lineage.LineageGraphResult
import app.inku.mobile.data.lineage.SubmitDerivationKind
import app.inku.mobile.data.refinement.ComparisonPlanner
import app.inku.mobile.data.refinement.MODEL_COMPARISON_MODE
import app.inku.mobile.data.refinement.RefinementElement
import app.inku.mobile.data.refinement.RefinementParent
import app.inku.mobile.data.refinement.RefinementPlan
import app.inku.mobile.data.refinement.RefinementPlanner
import app.inku.mobile.llm.DefaultModelDownloads
import app.inku.mobile.llm.ModelProviderHttpException
import app.inku.mobile.llm.CameraDescriptionRequest
import app.inku.mobile.llm.CameraDescriptionPrompts
import app.inku.mobile.llm.isLocalVisionModel
import app.inku.mobile.llm.VisionAnalysisRequest
import app.inku.mobile.llm.VisionImagePreparer
import app.inku.mobile.pipeline.ImportedPluginDefinition
import app.inku.mobile.pipeline.drawingModelOf
import app.inku.mobile.pipeline.InstructionLanguages
import app.inku.mobile.pipeline.ComposeFromDdlProgress
import app.inku.mobile.pipeline.InterpretResult
import app.inku.mobile.pipeline.PaintResult
import app.inku.mobile.pipeline.RecomposeMode
import app.inku.mobile.pipeline.AndroidWorkPipeline
import app.inku.mobile.pipeline.PipelineInteractionRequired
import app.inku.mobile.pipeline.PipelineView
import app.inku.mobile.pipeline.SketchInput
import app.inku.mobile.pipeline.SketchMode
import app.inku.mobile.pipeline.Sketches
import app.inku.mobile.pipeline.ProviderAttempt
import app.inku.mobile.ui.camera.CameraCaptureFileStore
import app.inku.mobile.ui.camera.CameraOriginalPhotoStore
import app.inku.mobile.ui.camera.CameraCaptureRequest
import app.inku.mobile.ui.camera.CameraCaptureState
import app.inku.mobile.ui.camera.CameraFailure
import app.inku.mobile.ui.camera.CameraDrawRoute
import app.inku.mobile.ui.camera.CameraDrawRouting
import app.inku.mobile.ui.camera.CameraDrawSettings
import app.inku.mobile.ui.camera.ModelReadinessIssue
import app.inku.mobile.ui.camera.CameraInstantPrintCoordinator
import app.inku.mobile.ui.camera.CameraInstantPrintPhase
import app.inku.mobile.ui.camera.cameraDevelopmentPresentation
import app.inku.mobile.ui.camera.modelReadinessIssue
import app.inku.mobile.ui.camera.clearCameraOrigin
import app.inku.mobile.ui.camera.locksCameraInteraction
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlin.math.abs
import org.json.JSONArray
import org.json.JSONObject

const val DefaultDemoSeedPhrase = "世界の人と動物、自然と都市を主題として96文字の短文を作って。感情豊かに、季節や、人生と人のつながり、人生、世代、神。色々な観点から。"
const val DemoCanvasAspectId = CanvasAspects.DEFAULT_ID
/** Bookkeeping the demo loop puts in front of the prose it saves. */
const val DemoHistoryInputPrefix = "[demo] "

/** The prose that determines a history row's parent description. */
internal fun sourceTextOf(item: HistoryItemEntity): String =
    (item.sourceText ?: item.originalInput).trim()

const val SETTING_KEY_MASCOT_KIND = "mascot_kind"
const val SETTING_KEY_UI_LANGUAGE = "ui_lang"
const val SETTING_KEY_UI_TEXT_SCALE = "ui_text_scale"
val UI_TEXT_SCALE_CHOICES: List<Float> = listOf(1f, 1.15f, 1.3f, 1.5f)

private fun normalizeUiTextScale(scale: Float): Float =
    if (scale.isFinite()) UI_TEXT_SCALE_CHOICES.minBy { abs(it - scale) } else 1f

/** 「推敲要素の選択は前回値をブラウザに記憶する」-- here, the device remembers it. */
const val SETTING_KEY_REFINEMENT_ELEMENT = "refinement_element"
const val SETTING_KEY_DISPLAY_SAFE_MARGINS = "display_safe_margins"
/**
 * Wild (engine 12), one switch for every new drawing. web keeps it as
 * `inku-wild` and states it on every fresh paint (`features/wild/render.ts`).
 */
const val SETTING_KEY_RENDER_WILD = "render_wild"
/** Said by every generating entry point that refuses while candidates are drawn. */
val REFINEMENT_IN_PROGRESS: (InkuStrings) -> String = { it.refinementInProgress }
/** Up to four explicitly chosen models, each used for both stages (SPEC §7.8). */
const val MAX_COMPARE_SELECTION = 4
val MODEL_SELECT_PROMPT: (InkuStrings) -> String = { it.comparisonModelSelectPrompt }
val MODEL_CHOICE_BLOCKED: (InkuStrings) -> String = { it.comparisonModelChoiceBlocked }
private const val MaxBatchItems = 100
private const val MaxDemoCycles = 100

// The magnification range web offers in `CanvasPanel.svelte:45-51`. The port
// takes the same numbers rather than a phone-sized guess: the same work has to
// be readable to the same depth on both.
const val CANVAS_ZOOM_MIN = 0.25f
const val CANVAS_ZOOM_MAX = 10.0f

/** The whole work on screen. Only the full screen leaves it. */
const val CANVAS_FIT_ZOOM = 1.0f

/** Float slack for "is it back at fit", which a pinch never lands on exactly. */
const val CANVAS_ZOOM_EPSILON = 0.01f

/**
 * The description field is held by the DDL. web's rule
 * (`features/work/state.svelte.ts`): a saved work answers with its lock mark
 * ([InkuUiState.historyDescriptionLocked]), which also holds a work derived from
 * an edited DDL without reading the description again; before a work is
 * saved, its authoring variation's authority decides.
 */
val InkuUiState.descriptionLocked: Boolean
    get() = historyAuthorityLoading || (!descriptionForkRequested &&
        (historyDescriptionLocked
            ?: (pipelineView?.authority == "ddl_authoritative" || historyAuthority == "ddl_authoritative")))

data class ProviderModelFetchState(
    val message: String,
    val loading: Boolean = false,
    val failed: Boolean = false,
)

data class InkuUiState(
    val prompt: String = "",
    val ddl: String = "",
    val ddlRangePreview: DdlRangePreview? = null,
    val ddlEditedAfterGeneration: Boolean = false,
    val confirmDdlOverwrite: Boolean = false,
    val pipelineView: PipelineView? = null,
    val historyAuthority: String? = null,
    /**
     * The selected saved work's description lock (`DescriptionLock`), or `null`
     * while there is no saved work to answer for or its mark could not be read.
     */
    val historyDescriptionLocked: Boolean? = null,
    val historyAuthorityLoading: Boolean = false,
    val descriptionForkRequested: Boolean = false,
    val batchText: String = "赤い円を5個、横に並べる\n黒い太筆の線を3本、斜めに置く\n緑の四角を12個、散らす",
    val batchPromptHistory: List<String> = emptyList(),
    val batchTotal: Int = 0,
    val batchCurrent: Int = 0,
    val batchSuccess: Int = 0,
    val batchFailures: List<BatchFailure> = emptyList(),
    val batchActiveLine: Int? = null,
    val batchActiveDdl: String? = null,
    val batchActiveElapsedMs: Long? = null,
    val batchElapsedMs: Long = 0L,
    val batchLatestHashShort: String? = null,
    val batchRetryLimit: Int = 0,
    val batchRetryRound: Int = 0,
    val batchCanRetry: Boolean = false,
    val demoSeed: String = DefaultDemoSeedPhrase,
    val demoIntervalSeconds: Int = 30,
    val demoGeneratedPrompt: String = "",
    val demoGeneratedDdl: String? = null,
    val demoCurrentCatalogId: String? = null,
    val demoWaitingSeconds: Int? = null,
    val demoCurrentElapsedMs: Long? = null,
    val demoTotalElapsedMs: Long = 0L,
    val demoRenderCount: Int = 0,
    val modelLicenseAccepted: Boolean = false,
    val modelDownloadState: String = "not downloaded",
    val modelAssets: List<ModelAssetEntity> = emptyList(),
    val providerSettings: List<ProviderSettingEntity> = emptyList(),
    val chatGptPlan: app.inku.mobile.llm.ChatGptPlanView = app.inku.mobile.llm.ChatGptPlanView(),
    val providerModelCandidates: Map<String, List<String>> = emptyMap(),
    val modelCatalog: app.inku.mobile.data.ModelCatalog = app.inku.mobile.data.ModelCatalog.EMPTY,
    val modelCatalogObservations: Map<String, app.inku.mobile.data.ModelCatalogObservation> = emptyMap(),
    val providerModelFetchStates: Map<String, ProviderModelFetchState> = emptyMap(),
    val exportTemplates: List<ExportTemplateEntity> = emptyList(),
    val activeModelDownloadId: String? = null,
    val selectedModelId: String = CompatibilityConstants.defaultStage1Model,
    val selectedStage2ModelId: String = CompatibilityConstants.defaultStage2Model,
    val includeThinking: Boolean = false,
    val modelSelectionOpen: Boolean = false,
    // A model choice confirmed over the preview reaches the capture in progress.
    val modelSelectionForCamera: Boolean = false,
    val catalogSelectionOpen: Boolean = false,
    val canvasSelectionOpen: Boolean = false,
    val selectedCatalogId: String = "default",
    val selectedCanvasAspect: String = "square",
    val selectedHistory: HistoryItemEntity? = null,
    /** Saved parent retained across description stops until the first successful history save. */
    val pendingDescriptionParent: HistoryItemEntity? = null,
    /** Work being shown to someone from the Works gallery, separate from the editing selection. */
    val presentationHistory: HistoryItemEntity? = null,
    /** Gallery order at the moment presentation began (including search and favorite filters). */
    val presentationSequence: List<String> = emptyList(),
    // web's `lineageDetached` (+page.svelte:515). While it is up, the work on
    // screen is shown but not inherited from: the next save becomes a root.
    val lineageDetached: Boolean = false,
    // The graph around the work on screen. Held rather than derived, because it
    // is read from the database and web refetches it on the same occasions
    // (+page.svelte:4556): opening the lineage, and picking a node in it.
    val lineageGraph: LineageGraphResult? = null,
    val lineageLoading: Boolean = false,
    val historySearchQuery: String = "",
    val historyStarredOnly: Boolean = false,
    val canvasSearchOpen: Boolean = false,
    val canvasSearchQuery: String = "",
    val canvasSearchBusy: Boolean = false,
    val canvasSearchFailed: Boolean = false,
    val canvasSearchResultIds: List<String> = emptyList(),
    /** The works screen lists the trash instead of the works. */
    val historyTrashView: Boolean = false,
    /**
     * What a trash, restore or permanent delete just did, said where it was
     * done: 「操作結果を明示する」(SPEC, the lineage card's ゴミ箱).
     */
    val workNotice: String? = null,
    val displaySafeMarginsEnabled: Boolean = false,
    val pngAlphaWhite: Boolean = false,
    val maxSvgMiB: Int = app.inku.mobile.render.SvgOutputLimit.DEFAULT_MIB,
    val saijikiOpen: Boolean = false,
    // Whether the description is being written. The bottom bar reads it: while
    // the keyboard is up, the four destinations give their place to the one
    // action the writing is heading for.
    val descriptionFocused: Boolean = false,
    val descriptionEditing: Boolean = false,
    /** Contextual work operations never replace the new-work draft. */
    val workContextId: String? = null,
    val workActionsTarget: HistoryItemEntity? = null,
    val workSketchTarget: HistoryItemEntity? = null,
    val ddlEditorOpen: Boolean = false,
    val cameraCaptureState: CameraCaptureState = CameraCaptureState.Idle,
    val cameraSourcePhotoPath: String? = null,
    val bundledPluginsEnabled: Boolean = true,
    /** Definitions read with an `inku.ddl-export.v1` file, held for the next new work. */
    val importedPlugins: List<ImportedPluginDefinition> = emptyList(),
    val importedPluginNames: List<String> = emptyList(),
    val bundledPluginWordsJa: List<String> = emptyList(),
    val bundledPluginWordsEn: List<String> = emptyList(),
    val isDrawing: Boolean = false,
    val message: String? = null,
    val tab: AppTab = AppTab.Compose,
    val settingsPane: SettingsPane = SettingsPane.Home,
    val settingsReturnTab: AppTab = AppTab.Compose,
    val composeMode: ComposeMode = ComposeMode.Write,
    val renderTab: RenderTab = RenderTab.Artwork,
    val uiMode: String = "full",
    val uiLanguage: UiLanguage = UiLanguage.DEFAULT,
    val uiTextScale: Float = 1f,
    val mascotKind: String = "incu",
    val canvasZoom: Float = 1.0f,
    val canvasPanX: Float = 0f,
    val canvasPanY: Float = 0f,
    val canvasPresentationMode: Boolean = false,
    val renderWild: Boolean = false,
    // 写生 runs only when the author chooses it; the initial choice is off.
    val sketchMode: SketchMode = Sketches.DEFAULT_MODE,
    // 推敲 (SPEC :614). The element is one value, never a set: the radio is
    // exclusive because a lineage edge has one cause.
    val refinementOpen: Boolean = false,
    val refinementParent: HistoryItemEntity? = null,
    val toolChangeOpen: Boolean = false,
    val toolChangeMode: app.inku.mobile.data.refinement.ToolChangeMode = app.inku.mobile.data.refinement.ToolChangeMode.Uniform,
    val refinementElement: RefinementElement = RefinementElement.Layout,
    val refinementLayoutMode: RecomposeMode = RecomposeMode.Principled,
    val refinementCount: Int = 1,
    /**
     * How many candidates the running round draws. The colour change draws
     * every other catalogue and a comparison every chosen model, so the
     * progress lanes count this rather than [refinementCount].
     */
    val refinementPlannedCount: Int = 0,
    val refinementRoundStartCount: Int = 0,
    val refinementBusy: Boolean = false,
    // 「開始3秒後から共通デザインの停止ボタンでAPI要求を中断できる」.
    val refinementCanAbort: Boolean = false,
    val refinementStatus: String? = null,
    val refinementWildOverride: Boolean? = null,
    val colorArrangementExhausted: Boolean = false,
    val groundCurrentLabel: String? = null,
    val refinementCandidates: List<RefinementCandidate> = emptyList(),
    // The candidate on the canvas that has not been saved. Drawing on from here
    // has to put it in the lineage first (SPEC :2105).
    val refinementPreviewId: String? = null,
    // 検分 (SPEC :616). The model comparison is a sub-view beside 調整 rather
    // than a screen of its own, and it shares every field above: the
    // candidates, the busy flag, the stop and the save are the refinement's.
    val refinementSubview: RefinementSubview = RefinementSubview.Adjust,
    val modelCompareSelectedModels: List<String> = emptyList(),
    val modelCompareFailedModels: Map<String, String> = emptyMap(),
    val replayOpen: Boolean = false,
    val replayBusy: Boolean = false,
    val replaySaving: Boolean = false,
    val replaySavedHistoryId: String? = null,
    val replayError: String? = null,
    val replayComparison: app.inku.mobile.data.refinement.ReplayComparison? = null,
    val autonomousOpen: Boolean = false,
    val autonomousParent: HistoryItemEntity? = null,
    val autonomousSettings: AutonomousRefinementSettings = AutonomousRefinementSettings(),
    val autonomousStatus: AutonomousRefinementStatus = AutonomousRefinementStatus(),
) {
    /**
     * Whether any operation is running.
     *
     * web has no such flag: every running operation renders `RunStatus.svelte`
     * itself, so the condition is spread over the components. The port needs the
     * union in one place, because Android shows one status row for the whole
     * screen. `isDrawing` covers the single draw, the batch, the demo and the
     * DDL editor's draw; `refinementBusy` covers the lineage's refinement and
     * the model and language comparisons.
     */
    val isRunning: Boolean get() = isDrawing || refinementBusy || replayBusy || replaySaving || autonomousStatus.busy || cameraCaptureState.locksCameraInteraction
}

private data class CameraDrawRunInput(
    val description: String,
    val inputProvenance: CameraInputProvenance,
    val canvasAspect: String,
    val uiLanguageCode: String,
    val originalPhoto: java.io.File,
    val drawSettings: CameraDrawSettings,
) {
    val route: CameraDrawRoute
        get() = CameraDrawRoute(inputProvenance, drawSettings)
}

private class CameraStageFailure(val failure: CameraFailure) : RuntimeException()

/**
 * The two sub-views of 推敲 (SPEC `:616`).
 *
 * 調整 varies one of the five elements; the other varies the model. They are
 * one screen with two faces rather than two screens, which is what
 * 「比較のロジックを複製しない」(SPEC `:688`) asks for. The language comparison
 * was a third; the web retired it on 2026-08-29 and SPEC keeps only the saved
 * `language_comparison` works readable, so it is gone here too.
 */
enum class RefinementSubview(val id: String) {
    Adjust("adjust"),
    Model("model"),
    ColorArrangement("color-arrangement"),
    Ground("ground"),
    ;

    companion object {
        fun byId(id: String?): RefinementSubview = entries.firstOrNull { it.id == id } ?: Adjust
    }
}

data class BatchFailure(
    val line: Int,
    val input: String,
    val message: String,
)

/**
 * 「保存操作は未保存・保存中・保存済みの3状態を区別し、保存済み候補は再保存できない」
 * (SPEC `:678`). Three states rather than a boolean, because the middle one is
 * what stops a second tap while the first save is still in the database.
 */
enum class RefinementSaveState {
    Unsaved,
    Saving,
    Saved,
}

/**
 * One drawn alternative, held until the author picks it or leaves.
 *
 * 「調整候補は生成元の作品に属する一時状態」: nothing here is in the database. The
 * plan it was drawn from is kept whole, because the save reads its derivation
 * kind and metadata from the same object the drawing came from -- there is no
 * second place where the edge is decided.
 */
data class RefinementCandidate(
    val id: String,
    val label: String,
    val plan: RefinementPlan,
    val displaySvg: String,
    val scoreJson: String,
    val normalizedDdl: String,
    val renderHash: String,
    val renderHashShort: String,
    val renderMetadataJson: String,
    val elapsedMs: Long,
    // What the drawing actually used, so the save writes what happened rather
    // than what was asked for. The models matter for a model comparison, where
    // the two stages differ from the parent's and from each other.
    val stage1Model: String,
    val stage2Model: String,
    val instructionLangRequested: String? = null,
    val instructionLangResolved: String? = null,
    val saveState: RefinementSaveState = RefinementSaveState.Unsaved,
    val savedHistoryId: String? = null,
    val savedNodeId: String? = null,
    val pipelineResult: PaintResult? = null,
    val selected: Boolean = false,
)

enum class AppTab {
    Compose,
    History,
    // web keeps the lineage beside the canvas, as one of the output tabs
    // (CanvasPanel.svelte:517). A phone has no room next to the canvas for a
    // tree, so it gets a screen of its own; author's ruling, 2026-08-07.
    Lineage,
    // The demo used to be the fifth destination here. M3 reserves the bottom bar
    // for the places one goes back to; the demo is run once in a while, so it
    // lives under `SettingsPane.Demo` beside its own settings (ruling 2026-08-08).
    Settings,
}

enum class SettingsPane {
    Home,
    Models,
    ChatGpt,
    Demo,
    Export,
    Limits,
    Misc,
    Version,
}

enum class ComposeMode {
    Write,
    Batch,
}

enum class RenderTab {
    Artwork,
    Prompt,
    Json,
}

/**
 * `@JvmOverloads` is what makes the app start.
 *
 * `androidx.lifecycle`'s default factory looks the constructor up by
 * reflection, as `<init>(Application)`. Kotlin does not emit that signature for
 * a constructor with a defaulted second parameter -- it emits the two-argument
 * one plus a synthetic bridge -- so from the day [repositoryOverride] was added
 * (`4c5e82f6`, 2026-08-06) `viewModel()` in `InkuApp` threw
 * `NoSuchMethodException` and the app died on launch. Nothing caught it: every
 * test builds the view model from Kotlin, which calls the bridge.
 * `AppStartupTest` composes `InkuApp` instead and walks the same reflective
 * path the running app does.
 */
class InkuViewModel @JvmOverloads constructor(
    application: Application,
    // Injectable so an instrumented test can drive the drawing paths against a
    // repository it built itself, with a throwaway database and no language
    // model. The server stubs `_ask_model` for the same reason: what is under
    // test is which catalogue the run reaches, not what the models write.
    repositoryOverride: InkuRepository? = null,
) : AndroidViewModel(application) {
    private val repository = repositoryOverride
        ?: InkuRepository(application.applicationContext, (application as? InkuApplication)?.database ?: app.inku.mobile.data.db.InkuDatabase.open(application))
    private val localState = MutableStateFlow(InkuUiState())
    private var authoringReturnState: InkuUiState? = null
    private var pausedWorkState: InkuUiState? = null
    private val history = repository.history()
    private val modelAssets = repository.modelAssets()
    private val providerSettings = repository.providerSettings()
    private val providerModelCandidates = repository.providerModelCandidates()
    private val exportTemplates = repository.exportTemplates()
    private var modelDownloadJob: Job? = null
    private var drawingJob: Job? = null
    private var lineageJob: Job? = null
    private var refinementJob: Job? = null
    private var canvasSearchJob: Job? = null
    private var replayJob: Job? = null
    private var autonomousJob: Job? = null
    private var refinementSaving = false
    private var replaySerial = 0L
    private var canvasSearchSerial = 0L
    private var lastBatchSnapshot: BatchSnapshot? = null
    private var lastBatchSavedWork: HistoryItemEntity? = null
    private val colorArrangementCursors = mutableMapOf<String, java.math.BigInteger?>()
    private var toolChangeNextNumber = 1
    private var litertWarmupJob: Job? = null
    private var cameraJob: Job? = null
    private val cameraFiles = CameraCaptureFileStore(application.applicationContext)
    private val originalPhotos = CameraOriginalPhotoStore(application.filesDir).also { it.cleanupStagedOnce() }
    private var stagedCameraPhoto: java.io.File? = null
    private var pendingCameraFile: java.io.File? = null
    private var cameraRunSerial: Long = 0L
    private var cameraComposeSnapshot: InkuUiState? = null
    private var cameraRetryInput: CameraDrawRunInput? = null
    // The run a camera capture stopped in for an answer. Its photo goes with
    // that run's approval or resume and with no other run's.
    private var cameraPipelineExecutionId: String? = null
    private val mutableCameraCaptureRequests = MutableSharedFlow<CameraCaptureRequest>(extraBufferCapacity = 1)
    val cameraCaptureRequests: SharedFlow<CameraCaptureRequest> = mutableCameraCaptureRequests.asSharedFlow()
    private val mutableChatGptAuthorizationRequests = MutableSharedFlow<String>()
    val chatGptAuthorizationRequests: SharedFlow<String> = mutableChatGptAuthorizationRequests.asSharedFlow()
    private var drawingRunSerial: Long = 0L
    private var promptEditedByUser = false
    private var modelSelectionSnapshot: Pair<String, String>? = null
    private var catalogSelectionSnapshot: String? = null
    private var lastHistorySwipeAt = 0L
    private var presentationNavigationSerial = 0L

    private val providerConfig = combine(providerSettings, providerModelCandidates, repository.chatGptPlan.state, repository.modelCatalogObservations()) { providers, candidates, plan, observations ->
        val personalCandidates = candidates - "chatgpt" + (plan.models?.let { mapOf("chatgpt" to it.map { model -> model.id }) } ?: emptyMap())
        Triple(providers, personalCandidates, plan) to observations
    }

    val state: StateFlow<InkuUiState> = combine(localState, history, modelAssets, providerConfig, exportTemplates) { state, items, assets, providerPair, templates ->
        val (providers, candidates, plan) = providerPair.first
        val selectedModel = assets.firstOrNull { it.modelId == state.selectedModelId }
        val modelState = selectedModel?.let { modelStatusText(it) } ?: "model catalog initializing"
        state.copy(
            modelAssets = assets,
            providerSettings = providers,
            providerModelCandidates = candidates,
            modelCatalog = repository.modelCatalog,
            modelCatalogObservations = providerPair.second,
            chatGptPlan = plan,
            exportTemplates = templates,
            modelLicenseAccepted = selectedModel?.licenseAcceptedAt != null,
            modelDownloadState = modelState,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), InkuUiState())

    val historyItems: StateFlow<List<HistoryListItem>> = history.stateIn(
        viewModelScope,
        SharingStarted.Eagerly,
        emptyList(),
    )

    val trashedItems: StateFlow<List<HistoryListItem>> = repository.trashedHistory().stateIn(
        viewModelScope,
        SharingStarted.Eagerly,
        emptyList(),
    )

    /** The model call the running drawing waits on; the running row shows it. */
    val providerAttempt: StateFlow<ProviderAttempt?> = repository.providerAttempt

    init {
        viewModelScope.launch {
            repository.ensureDefaultModelAssets()
            repository.ensureDefaultProviderSettings()
            repository.ensureDefaultExportTemplates()
            restorePersistedSettings()
            runCatching { withContext(Dispatchers.IO) { repository.restoreActivePipeline() } }
                .onSuccess { view ->
                    // The latest execution is read after the settings above,
                    // and by then the reader can have started one of their
                    // own: a refinement run writes its execution too, and
                    // presenting that as the drawing to resume closed the
                    // refinement under the run that was still going.
                    if (view != null && view.phaseTag != "cancelled" &&
                        !promptEditedByUser && !localState.value.isDrawing &&
                        !localState.value.refinementOpen && !localState.value.refinementBusy
                    ) {
                        presentPipelineView(view)
                    }
                }
                .onFailure { error -> localState.value = localState.value.copy(message = messageFor(error, strings(), strings().restoreDrawingFailed)) }
            withContext(Dispatchers.IO) {
                var offset = 0
                var refreshedInPass = 0
                while (true) {
                    val batch = repository.backfillMissingThumbnails(limit = 2, offset = offset)
                    if (batch.scanned == 0) {
                        if (refreshedInPass == 0) {
                            // Every thumbnail is current; the files they replaced can go.
                            runCatching { repository.removeStaleThumbnails() }
                            break
                        }
                        offset = 0
                        refreshedInPass = 0
                    } else {
                        // Refreshed rows leave the query; only failed rows remain before the cursor.
                        offset += batch.scanned - batch.refreshed
                        refreshedInPass += batch.refreshed
                    }
                    delay(750)
                }
            }
        }
    }

    override fun onCleared() {
        repository.chatGptPlan.cancelAuthorization()
        drawingRunSerial += 1
        drawingJob?.cancel()
        lineageJob?.cancel()
        refinementJob?.cancel()
        replayJob?.cancel()
        canvasSearchJob?.cancel()
        autonomousJob?.cancel()
        modelDownloadJob?.cancel()
        litertWarmupJob?.cancel()
        cameraRunSerial += 1
        cameraJob?.cancel()
        cameraFiles.delete(pendingCameraFile)
        discardStagedCameraPhoto()
        pendingCameraFile = null
        (getApplication() as InkuApplication).applicationScope.launch {
            repository.close()
        }
        super.onCleared()
    }

    fun setPrompt(value: String) {
        if (localState.value.descriptionLocked) return
        promptEditedByUser = true
        localState.value = localState.value.copy(prompt = value, message = null)
    }

    fun startDescriptionVariation() {
        if (localState.value.isDrawing || localState.value.historyAuthorityLoading) return
        localState.value = localState.value.copy(
            pipelineView = null,
            descriptionForkRequested = true,
            selectedCanvasAspect = CanvasAspects.newSelectionOrDefault(localState.value.selectedCanvasAspect),
            message = strings().pipelineNewDescriptionNotice,
        )
    }

    private fun presentPipelineView(view: PipelineView) {
        // This closes the refinement; a candidate run left going would keep
        // asking the model and adding candidates to a panel no longer shown,
        // with the busy flag already down. When the run itself failed into
        // this view, cancelling it here only ends what was ending.
        refinementJob?.cancel()
        refinementJob = null
        val context = JSONObject(view.hostContextJson)
        val options = context.optJSONObject("host_options")
        val parentId = context.optJSONObject("result_options")?.optString("parent_history_id")
        // A drawing the run saved before it stopped for the author is the work
        // on screen while the proposal or the stop is answered, as on web.
        val selected = (repository.safePerformance(view.executionId)
            ?: localState.value.selectedHistory?.takeIf { item ->
                item.id == parentId || runCatching {
                    JSONObject(item.renderMetadataJson).optString("pipeline_execution_id") == view.executionId
                }.getOrDefault(false)
            }).takeUnless { view.phaseReason == "svg_output_too_large" }
        localState.value = localState.value.copy(
            tab = AppTab.Compose,
            composeMode = ComposeMode.Write,
            // The answer is asked for on the studio; a full screen opened over
            // it, here or from Works, would hide it (SPEC 2026-10-12).
            canvasPresentationMode = false,
            presentationHistory = null,
            presentationSequence = emptyList(),
            refinementOpen = false,
            refinementBusy = false,
            selectedHistory = selected,
            pendingDescriptionParent = null,
            lineageDetached = selected == null,
            selectedCanvasAspect = options?.optString("canvas_aspect")?.takeIf { it.isNotBlank() } ?: localState.value.selectedCanvasAspect,
            selectedCatalogId = if (options?.optString("catalog_mode") == "auto") CatalogSelection.AUTO_ID else options?.optString("catalog_id")?.takeIf { it.isNotBlank() } ?: localState.value.selectedCatalogId,
            // One model draws both stages (2026-09-30, the author): a run started
            // before then with two resumes on its Stage 1 model.
            selectedModelId = view.models?.let { drawingModelOf(it.stage1ModelId, it.stage2ModelId) } ?: localState.value.selectedModelId,
            selectedStage2ModelId = view.models?.let { drawingModelOf(it.stage1ModelId, it.stage2ModelId) } ?: localState.value.selectedStage2ModelId,
            renderWild = options?.optBoolean("wild") ?: localState.value.renderWild,
            prompt = view.description ?: localState.value.prompt,
            ddl = view.visibleDdl ?: localState.value.ddl,
            pipelineView = view,
            historyAuthority = view.authority,
            historyDescriptionLocked = null,
            historyAuthorityLoading = false,
            descriptionForkRequested = false,
            ddlEditedAfterGeneration = false,
            isDrawing = false,
            cameraCaptureState = CameraCaptureState.Idle,
            message = when {
                view.patchProposal != null -> strings().pipelineProposal
                view.phaseReason != null -> pipelineAttentionText(view.phaseReason, view.providerFailure, strings(), view.svgOutputLimitMiB)
                else -> strings().pipelineCheckDdl
            },
        )
    }

    /**
     * For a run nobody is there to answer -- a batch line, a demo cycle: the
     * stopped run is cancelled and the reason returned, so the caller can go
     * on. Null when the failure was not the pipeline stopping.
     */
    private suspend fun abandonPipelineInteraction(error: Throwable): String? {
        if (error !is PipelineInteractionRequired) return null
        val view = error.view
        runCatching { withContext(Dispatchers.IO) { repository.cancelPipeline(view.executionId) } }
        return when {
            view.patchProposal != null -> strings().pipelineProposalNotAnswered
            view.phaseReason != null -> pipelineAttentionText(view.phaseReason, view.providerFailure, strings(), view.svgOutputLimitMiB)
            else -> strings().pipelineCheckDdl
        }
    }

    private fun presentPipelineInteraction(error: Throwable): Boolean {
        if (error !is PipelineInteractionRequired) return false
        presentPipelineView(error.view)
        return true
    }

    fun approvePipelinePatch() = continuePipeline(approve = true)

    fun resumePipeline() = continuePipeline(approve = false)

    private fun continuePipeline(approve: Boolean) {
        val view = localState.value.pipelineView ?: return
        val originalPhoto = cameraRetryInput?.originalPhoto?.takeIf { view.executionId == cameraPipelineExecutionId }
        val runId = beginDrawingRun()
        localState.value = localState.value.copy(isDrawing = true)
        drawingJob = viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    if (approve) {
                        // The proposal on screen is the one approved; one that
                        // changed since is refused by the core, as on web.
                        val proposal = view.patchProposal ?: throw app.inku.mobile.pipeline.PipelineHostException("patch_proposal_required")
                        repository.approvePipelinePatch(view.executionId, view.revision, proposal.proposalDigest, originalPhoto)
                    } else {
                        repository.resumePipeline(view.executionId, originalPhoto)
                    }
                }
            }.onSuccess { item ->
                if (!isCurrentDrawingRun(runId)) return@onSuccess
                discardStagedCameraPhoto()
                cameraRetryInput = null
                adoptSavedHistory(item, activeExecution = true, isCurrent = { isCurrentDrawingRun(runId) }) { current ->
                    current.copy(
                        prompt = item.originalInput,
                        ddl = item.normalizedDdl.orEmpty(),
                        descriptionForkRequested = false,
                        lineageDetached = false,
                        isDrawing = false,
                        message = strings().statusRendered(item.renderHashShort),
                    )
                }
            }.onFailure { error ->
                if (!isCurrentDrawingRun(runId)) return@onFailure
                if (!presentPipelineInteraction(error)) {
                    localState.value = localState.value.copy(isDrawing = false, message = messageFor(error, strings(), strings().statusDrawFailed))
                }
            }
        }
    }

    fun declinePipelinePatch() {
        val view = localState.value.pipelineView ?: return
        if (localState.value.isDrawing) return
        viewModelScope.launch {
            val proposal = view.patchProposal ?: return@launch
            runCatching { withContext(Dispatchers.IO) { repository.declinePipelinePatch(view.executionId, proposal.proposalDigest) } }
                .onSuccess { if (localState.value.pipelineView?.executionId == view.executionId) presentPipelineView(it) }
                .onFailure { localState.value = localState.value.copy(message = messageFor(it, strings(), strings().pipelineDeclineFailed)) }
        }
    }

    fun requestCameraCaptureDirect() {
        if (!canRequestCameraInput()) return
        beginCameraInput()
    }

    private fun canRequestCameraInput(): Boolean {
        val current = localState.value
        return !current.isRunning && current.cameraCaptureState != CameraCaptureState.Capturing
    }

    private fun beginCameraInput() {
        cameraRunSerial += 1
        cameraJob?.cancel()
        cameraFiles.delete(pendingCameraFile)
        discardStagedCameraPhoto()
        pendingCameraFile = null
        cameraComposeSnapshot = localState.value.copy(
            cameraCaptureState = CameraCaptureState.Idle,
            isDrawing = false,
            message = null,
        )
        cameraRetryInput = null
        startCameraCapture()
    }

    private fun startCameraCapture() {
        cameraRunSerial += 1
        val serial = cameraRunSerial
        cameraJob?.cancel()
        cameraFiles.delete(pendingCameraFile)
        pendingCameraFile = null
        localState.value = localState.value.copy(
            pipelineView = null,
            cameraSourcePhotoPath = null,
            historyAuthority = null,
            historyDescriptionLocked = null,
            historyAuthorityLoading = false,
        )
        cameraJob = viewModelScope.launch {
            try {
                val snapshot = cameraComposeSnapshot ?: localState.value
                val cameraProviders = providerSettings.first()
                val cameraAssets = modelAssets.first()
                val visionModelId = snapshot.selectedModelId
                // The ChatGPT plan does not read the photo (SPEC 2026-10-17: not a
                // camera Vision candidate). The shared model selection can still
                // hold one, and the capture used to fail right after the shutter
                // with no reason given.
                if (visionModelId.startsWith("chatgpt:")) {
                    if (serial == cameraRunSerial) {
                        localState.value = localState.value.copy(
                            cameraCaptureState = CameraCaptureState.Failed(CameraFailure.ModelNotReady),
                            message = strings().cameraChatGptCannotReadPhoto,
                        )
                    }
                    return@launch
                }
                modelReadinessIssue(visionModelId, cameraProviders, cameraAssets)?.let { issue ->
                    if (serial == cameraRunSerial) {
                        localState.value = localState.value.copy(
                            cameraCaptureState = CameraCaptureState.Failed(CameraFailure.ModelNotReady),
                            message = readinessMessage(issue, visionModelId, cameraProviders),
                        )
                    }
                    return@launch
                }
                cameraDrawReadiness(snapshot, cameraProviders, cameraAssets)?.let { message ->
                    if (serial == cameraRunSerial) {
                        localState.value = localState.value.copy(
                            cameraCaptureState = CameraCaptureState.Failed(CameraFailure.DrawModelNotReady),
                            message = message,
                        )
                    }
                    return@launch
                }
                // Load a local Vision model while the author is still framing the shot.
                if (isLocalVisionModel(visionModelId)) {
                    litertWarmupJob?.cancel()
                    litertWarmupJob = viewModelScope.launch(Dispatchers.IO) {
                        runCatching { repository.warmupLocalModelIfReady(visionModelId) }
                    }
                }
                val file = withContext(Dispatchers.IO) { cameraFiles.createPendingCapture() }
                if (serial != cameraRunSerial) {
                    cameraFiles.delete(file)
                    return@launch
                }
                pendingCameraFile = file
                localState.value = localState.value.copy(
                    cameraCaptureState = CameraCaptureState.Capturing,
                    message = null,
                )
                mutableCameraCaptureRequests.emit(CameraCaptureRequest(file, cameraFiles.contentUri(file)))
            } catch (error: CancellationException) {
                throw error
            } catch (_: Throwable) {
                cameraFiles.delete(pendingCameraFile)
                pendingCameraFile = null
                if (serial == cameraRunSerial) {
                    localState.value = localState.value.copy(
                        cameraCaptureState = CameraCaptureState.Failed(CameraFailure.CaptureUnavailable),
                    )
                }
            }
        }
    }

    fun onCameraCaptureResult(success: Boolean) {
        val file = pendingCameraFile
        pendingCameraFile = null
        if (!success) {
            cameraFiles.delete(file)
            restoreCameraComposeSnapshot()
            return
        }
        if (file == null || !file.isFile || file.length() == 0L) {
            cameraFiles.delete(file)
            localState.value = localState.value.copy(
                tab = AppTab.Compose,
                composeMode = ComposeMode.Write,
                cameraCaptureState = CameraCaptureState.Failed(CameraFailure.EmptyImage),
            )
            return
        }

        cameraRunSerial += 1
        val serial = cameraRunSerial
        cameraJob?.cancel()
        cameraJob = viewModelScope.launch {
            // A description model chosen over the preview was not there for the
            // check before the capture; the drawing model is checked again
            // before drawing (`cameraRouteReadiness`).
            val snapshot = cameraComposeSnapshot ?: localState.value
            val providers = providerSettings.first()
            modelReadinessIssue(snapshot.selectedModelId, providers, modelAssets.first())?.let { issue ->
                cameraFiles.delete(file)
                if (serial == cameraRunSerial) {
                    localState.value = localState.value.copy(
                        tab = AppTab.Compose,
                        composeMode = ComposeMode.Write,
                        cameraCaptureState = CameraCaptureState.Failed(CameraFailure.ModelNotReady),
                        message = readinessMessage(issue, snapshot.selectedModelId, providers),
                    )
                }
                return@launch
            }
            runCameraInstantPrint(
                serial = serial,
                file = file,
                origin = CameraInputOrigin.Camera,
                cleanup = { cameraFiles.delete(it) },
            )
        }
    }

    private suspend fun runCameraInstantPrint(
        serial: Long,
        file: java.io.File,
        origin: CameraInputOrigin,
        cleanup: (java.io.File?) -> Unit,
    ) {
        val coordinator = cameraCoordinator(serial)
        var stagedPhoto: java.io.File? = null
        try {
            val outcome = coordinator.run(
                prepare = {
                    try {
                        val prepared = withContext(Dispatchers.IO) {
                            VisionImagePreparer.prepare(file).also {
                                stagedPhoto = originalPhotos.stage(file)
                            }
                        }
                        if (serial != cameraRunSerial) throw CancellationException("Camera input was replaced.")
                        stagedCameraPhoto = stagedPhoto
                        localState.value = localState.value.copy(cameraSourcePhotoPath = stagedPhoto?.absolutePath)
                        prepared
                    } catch (error: CancellationException) {
                        throw error
                    } catch (_: Throwable) {
                        throw CameraStageFailure(CameraFailure.DecodeFailed)
                    }
                },
                load = {
                    val snapshot = cameraComposeSnapshot ?: localState.value
                    if (isLocalVisionModel(snapshot.selectedModelId)) {
                        litertWarmupJob?.join()
                        repository.warmupLocalModelIfReady(snapshot.selectedModelId)
                    }
                },
                analyze = { prepared ->
                    val current = localState.value
                    val snapshot = cameraComposeSnapshot ?: current
                    val uiLanguageCode = snapshot.uiLanguage.code
                    val request = VisionAnalysisRequest(
                        normalizedJpeg = prepared.jpegBytes,
                        width = prepared.width,
                        height = prepared.height,
                        languageCode = uiLanguageCode,
                        modelId = snapshot.selectedModelId,
                    )
                    val result = repository.analyzeVision(request)
                    if (result.text.isBlank()) throw CameraStageFailure(CameraFailure.EmptyResult)
                    CameraDrawRunInput(
                        description = result.text.trim(),
                        inputProvenance = CameraInputProvenance.fromAnalysis(request, result, origin),
                        canvasAspect = snapshot.selectedCanvasAspect,
                        uiLanguageCode = uiLanguageCode,
                        originalPhoto = requireNotNull(stagedPhoto),
                        drawSettings = cameraDrawSettings(snapshot),
                    )
                },
                writeDescription = { observed ->
                    try {
                        val result = repository.writeCameraDescription(
                            CameraDescriptionRequest(
                                observation = observed.description,
                                modelId = observed.drawSettings.stage1ModelId,
                                languageCode = observed.uiLanguageCode,
                            ),
                        )
                        observed.copy(
                            description = result.text,
                            inputProvenance = observed.inputProvenance.copy(
                                descriptionModelId = result.modelId,
                                descriptionPromptVersion = CameraDescriptionPrompts.VERSION,
                            ),
                        )
                    } catch (error: CancellationException) {
                        throw error
                    } catch (_: Throwable) {
                        throw CameraStageFailure(CameraFailure.DescriptionFailed)
                    }
                },
                onLocalReady = { input ->
                    cameraRetryInput = input
                    promptEditedByUser = true
                    localState.value = localState.value.copy(
                        prompt = input.description,
                        ddl = "",
                        ddlEditedAfterGeneration = false,
                        message = null,
                    )
                },
                interpret = ::interpretCameraInput,
                compose = { input, interpreted, progress ->
                    composeCameraInput(serial, input, interpreted, progress)
                },
            )
            finishCameraRun(serial, outcome.result)
        } catch (error: CameraStageFailure) {
            failCameraRun(serial, error.failure, canRetryDraw = false)
        } catch (error: CancellationException) {
            if (serial == cameraRunSerial) {
                localState.value = localState.value.copy(
                    cameraCaptureState = CameraCaptureState.Cancelled,
                    isDrawing = false,
                )
            }
            throw error
        } catch (error: PipelineInteractionRequired) {
            if (serial == cameraRunSerial) presentCameraPipelineStop(serial, error)
        } catch (_: Throwable) {
            failCameraRun(
                serial,
                if (cameraRetryInput != null) CameraFailure.DrawFailed else CameraFailure.AnalysisFailed,
                canRetryDraw = cameraRetryInput != null,
            )
        } finally {
            cleanup(file)
            if (serial != cameraRunSerial || cameraRetryInput?.originalPhoto != stagedPhoto) {
                originalPhotos.deleteStaged(stagedPhoto)
                if (stagedCameraPhoto == stagedPhoto) {
                    stagedCameraPhoto = null
                    if (localState.value.cameraSourcePhotoPath == stagedPhoto?.absolutePath) {
                        localState.value = localState.value.copy(cameraSourcePhotoPath = null)
                    }
                }
            }
        }
    }

    fun retryCameraDevelopment() {
        val failed = localState.value.cameraCaptureState as? CameraCaptureState.Failed ?: return
        val input = cameraRetryInput ?: return
        if (!failed.canRetryDraw) return
        cameraRunSerial += 1
        val serial = cameraRunSerial
        cameraJob?.cancel()
        cameraJob = viewModelScope.launch {
            val cameraProviders = providerSettings.first()
            cameraRouteReadiness(input.route, cameraProviders, modelAssets.first())?.let { message ->
                if (serial == cameraRunSerial) {
                    localState.value = localState.value.copy(
                        cameraCaptureState = CameraCaptureState.Failed(CameraFailure.DrawModelNotReady, canRetryDraw = true),
                        isDrawing = false,
                        message = message,
                    )
                }
                return@launch
            }
            val coordinator = cameraCoordinator(serial)
            try {
                val outcome = coordinator.runFromAnalysis(
                    local = input,
                    interpret = ::interpretCameraInput,
                    compose = { retained, interpreted, progress ->
                        composeCameraInput(serial, retained, interpreted, progress)
                    },
                )
                finishCameraRun(serial, outcome.result)
            } catch (error: CancellationException) {
                if (serial == cameraRunSerial) {
                    localState.value = localState.value.copy(
                        cameraCaptureState = CameraCaptureState.Cancelled,
                        isDrawing = false,
                    )
                }
                throw error
            } catch (error: PipelineInteractionRequired) {
                if (serial == cameraRunSerial) presentCameraPipelineStop(serial, error)
            } catch (_: Throwable) {
                failCameraRun(serial, CameraFailure.DrawFailed, canRetryDraw = true)
            }
        }
    }

    fun cancelCameraDevelopment() {
        val current = localState.value.cameraCaptureState
        if (current == CameraCaptureState.Cancelling) return
        if (!current.locksCameraInteraction && current !is CameraCaptureState.Failed) return
        cameraRunSerial += 1
        val cancelSerial = cameraRunSerial
        val job = cameraJob
        cameraJob = null
        val warmupJob = litertWarmupJob
        litertWarmupJob = null
        job?.cancel()
        warmupJob?.cancel()
        localState.value = localState.value.copy(
            cameraCaptureState = CameraCaptureState.Cancelling,
            isDrawing = false,
            message = null,
        )
        viewModelScope.launch {
            // Native inference and warmup must finish before their engine is closed.
            withContext(NonCancellable) {
                job?.join()
                warmupJob?.join()
                repository.releaseLocalVisionModel(
                    (cameraComposeSnapshot ?: localState.value).selectedModelId,
                )
            }
            cameraFiles.delete(pendingCameraFile)
            pendingCameraFile = null
            if (cancelSerial == cameraRunSerial) restoreCameraComposeSnapshot()
        }
    }

    private fun cameraCoordinator(serial: Long) = CameraInstantPrintCoordinator(
        isCurrent = { serial == cameraRunSerial },
        onPhase = { phase -> updateCameraPhase(serial, phase) },
    )

    private fun updateCameraPhase(serial: Long, phase: CameraInstantPrintPhase) {
        if (serial != cameraRunSerial || phase == CameraInstantPrintPhase.Completed) return
        val captureState = when (phase) {
            CameraInstantPrintPhase.PreparingImage -> CameraCaptureState.PreparingImage
            CameraInstantPrintPhase.LoadingLocalModel -> CameraCaptureState.LoadingLocalModel
            CameraInstantPrintPhase.AnalyzingLocally -> CameraCaptureState.AnalyzingLocally
            CameraInstantPrintPhase.WritingDescription -> CameraCaptureState.WritingDescription
            CameraInstantPrintPhase.InterpretingStage1 -> CameraCaptureState.InterpretingStage1
            CameraInstantPrintPhase.Composing -> CameraCaptureState.Composing
            CameraInstantPrintPhase.Rendering -> CameraCaptureState.Rendering
            CameraInstantPrintPhase.Saving -> CameraCaptureState.Saving
            CameraInstantPrintPhase.Completed -> return
        }
        val current = localState.value
        val presentation = cameraDevelopmentPresentation(
            captureState,
            isJapanese = !current.uiLanguage.isEnglish,
            animationsEnabled = false,
        )
        localState.value = current.copy(
            tab = AppTab.Compose,
            composeMode = ComposeMode.Write,
            cameraCaptureState = captureState,
            isDrawing = phase >= CameraInstantPrintPhase.InterpretingStage1,
            selectedHistory = if (phase >= CameraInstantPrintPhase.InterpretingStage1) null else current.selectedHistory,
            pendingDescriptionParent = if (phase >= CameraInstantPrintPhase.InterpretingStage1) null else current.pendingDescriptionParent,
            pipelineView = if (phase >= CameraInstantPrintPhase.InterpretingStage1) null else current.pipelineView,
            historyAuthority = if (phase >= CameraInstantPrintPhase.InterpretingStage1) null else current.historyAuthority,
            historyDescriptionLocked = if (phase >= CameraInstantPrintPhase.InterpretingStage1) null else current.historyDescriptionLocked,
            historyAuthorityLoading = if (phase >= CameraInstantPrintPhase.InterpretingStage1) false else current.historyAuthorityLoading,
            message = presentation?.message,
        )
    }

    private suspend fun interpretCameraInput(input: CameraDrawRunInput): InterpretResult {
        val route = input.route
        return withContext(Dispatchers.IO) {
            repository.interpret(
                input.description,
                route.catalogId,
                input.canvasAspect,
                route.stage1ModelId,
                route.stage2ModelId,
                route.autoRepair,
                false,
                instructionLang = InstructionLanguages.AUTO,
                uiLang = input.uiLanguageCode,
                sketch = route.sketch,
                inputProvenance = input.inputProvenance,
                renderWild = route.renderWild,
            )
        }
    }

    private suspend fun composeCameraInput(
        serial: Long,
        input: CameraDrawRunInput,
        interpreted: InterpretResult,
        progress: suspend (CameraInstantPrintPhase) -> Unit,
    ): HistoryItemEntity = withContext(Dispatchers.IO) {
        val route = input.route
        repository.composeFromDdl(
            input.description,
            interpreted.normalizedDdl,
            route.catalogId,
            input.canvasAspect,
            route.stage1ModelId,
            route.stage2ModelId,
            route.autoRepair,
            false,
            lineage = LineageDeclaration(),
            instructionLang = InstructionLanguages.AUTO,
            uiLang = input.uiLanguageCode,
            sketch = route.sketch,
            inputProvenance = input.inputProvenance,
            executionId = interpreted.executionId,
            originalPhoto = input.originalPhoto,
            onProgress = { pipelinePhase ->
                progress(
                    when (pipelinePhase) {
                        ComposeFromDdlProgress.Rendering -> CameraInstantPrintPhase.Rendering
                        ComposeFromDdlProgress.Saving -> CameraInstantPrintPhase.Saving
                    },
                )
            },
            beforeSave = {
                if (serial != cameraRunSerial) throw CancellationException("Camera run was cancelled before save.")
            },
        )
    }

    private fun finishCameraRun(serial: Long, item: HistoryItemEntity) {
        if (serial != cameraRunSerial) return
        promptEditedByUser = false
        cameraRetryInput = null
        discardStagedCameraPhoto()
        cameraComposeSnapshot = null
        adoptSavedHistory(item, activeExecution = true, isCurrent = { serial == cameraRunSerial }) { current ->
            current.copy(
                prompt = item.originalInput,
                ddl = item.normalizedDdl.orEmpty(),
                ddlEditedAfterGeneration = false,
                confirmDdlOverwrite = false,
                lineageDetached = false,
                cameraCaptureState = CameraCaptureState.Completed(item.id),
                isDrawing = false,
                message = cameraDevelopmentPresentation(
                    CameraCaptureState.Completed(item.id),
                    isJapanese = !current.uiLanguage.isEnglish,
                    animationsEnabled = false,
                )?.message,
            )
        }
    }

    /**
     * A camera drawing the pipeline stopped. A proposal, or a run that can be
     * resumed, is shown for an answer as any drawing's is, and keeps the photo.
     * A stop with nothing to answer is the drawing failing: the development
     * screen stays with its 再試行 from the poetic description and its 取消
     * back to before the capture (SPEC 2026-09-30), which the studio's stop
     * panel offered neither of.
     */
    private suspend fun presentCameraPipelineStop(serial: Long, error: PipelineInteractionRequired) {
        val view = error.view
        val answerable = view.patchProposal != null || view.phaseReason == null || view.phaseReason == "svg_output_too_large"
        if (answerable) {
            cameraPipelineExecutionId = view.executionId
            presentPipelineInteraction(error)
            return
        }
        runCatching { withContext(Dispatchers.IO) { repository.cancelPipeline(view.executionId) } }
        failCameraRun(serial, CameraFailure.DrawFailed, canRetryDraw = cameraRetryInput != null)
        if (serial == cameraRunSerial) {
            localState.value = localState.value.copy(
                message = pipelineAttentionText(view.phaseReason!!, view.providerFailure, strings(), view.svgOutputLimitMiB),
            )
        }
    }

    private fun failCameraRun(serial: Long, failure: CameraFailure, canRetryDraw: Boolean) {
        if (serial != cameraRunSerial) return
        localState.value = localState.value.copy(
            cameraCaptureState = CameraCaptureState.Failed(failure, canRetryDraw),
            isDrawing = false,
            message = null,
        )
    }

    private fun discardStagedCameraPhoto() {
        val discardedPath = stagedCameraPhoto?.absolutePath
        originalPhotos.deleteStaged(stagedCameraPhoto)
        stagedCameraPhoto = null
        if (discardedPath != null && localState.value.cameraSourcePhotoPath == discardedPath) {
            localState.value = localState.value.copy(cameraSourcePhotoPath = null)
        }
    }

    private fun restoreCameraComposeSnapshot() {
        val snapshot = cameraComposeSnapshot
        cameraComposeSnapshot = null
        cameraRetryInput = null
        discardStagedCameraPhoto()
        localState.value = (snapshot ?: localState.value).copy(
            cameraCaptureState = CameraCaptureState.Idle,
            isDrawing = false,
            message = null,
        )
    }

    /** The drawing settings a camera run keeps from its start. */
    private fun cameraDrawSettings(snapshot: InkuUiState) = CameraDrawSettings(
        stage1ModelId = snapshot.selectedModelId,
        stage2ModelId = snapshot.selectedStage2ModelId,
        catalogId = snapshot.selectedCatalogId,
        sketchRequested = snapshot.sketchMode == SketchMode.On,
        renderWild = snapshot.renderWild,
    )

    /** Checks the drawing models a camera run started from [snapshot] will call. */
    private fun cameraDrawReadiness(
        snapshot: InkuUiState,
        providers: List<ProviderSettingEntity>,
        assets: List<ModelAssetEntity>,
    ): String? {
        val models = listOf(snapshot.selectedModelId, snapshot.selectedStage2ModelId).distinct()
        return models.firstNotNullOfOrNull { modelId ->
            modelReadinessIssue(modelId, providers, assets)?.let { readinessMessage(it, modelId, providers) }
        }
    }

    private fun cameraRouteReadiness(
        route: CameraDrawRoute,
        providers: List<ProviderSettingEntity>,
        assets: List<ModelAssetEntity>,
    ): String? {
        val models = listOf(route.stage1ModelId, route.stage2ModelId).distinct()
        return models.firstNotNullOfOrNull { modelId ->
            modelReadinessIssue(modelId, providers, assets)?.let { readinessMessage(it, modelId, providers) }
        }
    }

    private fun readinessMessage(
        issue: ModelReadinessIssue,
        modelId: String,
        providers: List<ProviderSettingEntity>,
    ): String {
        val providerName = app.inku.mobile.llm.RoutingModelProvider.resolveProviderForRouting(providers, modelId, null)
            ?.takeUnless { it.isDefaultLocal }
            ?.displayName
            ?: modelId.substringBefore(':')
        return when (issue) {
            ModelReadinessIssue.LocalModelNotReady -> strings().cameraModelNotReady
            ModelReadinessIssue.ProviderMissingOrDisabled -> strings().errorProviderNotFoundForModel(modelId)
            ModelReadinessIssue.BaseUrlMissing -> strings().errorProviderBaseUrlMissing(providerName)
            ModelReadinessIssue.ApiKeyMissing -> strings().errorProviderApiKeyMissing(providerName)
        }
    }

    fun onCameraCaptureLaunchFailed() {
        cameraRunSerial += 1
        cameraJob?.cancel()
        cameraFiles.delete(pendingCameraFile)
        pendingCameraFile = null
        localState.value = localState.value.copy(
            cameraCaptureState = CameraCaptureState.Failed(CameraFailure.CaptureUnavailable),
        )
    }

    fun clearPrompt() {
        if (state.value.isDrawing) return
        if (localState.value.workContextId != null) closeWorkContext()
        // Starting a new work leaves a drawing that was waiting on the author --
        // restored at start or presented after a stop -- for good, as the stop
        // itself does; left open, it was restored again at every start.
        localState.value.pipelineView?.takeIf { !it.terminal }?.let { view ->
            viewModelScope.launch { runCatching { repository.cancelPipeline(view.executionId) } }
        }
        discardStagedCameraPhoto()
        cameraRetryInput = null
        promptEditedByUser = true
        localState.value = localState.value.copy(
            prompt = "",
            ddl = "",
            pipelineView = null,
            historyAuthority = null,
            historyDescriptionLocked = null,
            historyAuthorityLoading = false,
            descriptionForkRequested = false,
            selectedHistory = null,
            descriptionEditing = false,
            pendingDescriptionParent = null,
            workContextId = null,
            tab = AppTab.Compose,
            canvasPresentationMode = false,
            presentationHistory = null,
            presentationSequence = emptyList(),
            sketchMode = Sketches.DEFAULT_MODE,
            cameraSourcePhotoPath = null,
            lineageDetached = true,
            ddlEditedAfterGeneration = false,
            cameraCaptureState = localState.value.cameraCaptureState.clearCameraOrigin(),
            selectedCanvasAspect = CanvasAspects.newSelectionOrDefault(localState.value.selectedCanvasAspect),
            message = null,
        )
    }

    fun setDdl(value: String) {
        localState.value = localState.value.copy(ddl = value, ddlEditedAfterGeneration = true, message = null)
    }

    internal suspend fun completionRangeStates(source: String): List<app.inku.mobile.pipeline.CompletionRangeState> {
        val current = localState.value
        return withContext(Dispatchers.IO) {
            repository.completionRangeStates(source, matchingPipelineExecutionId(current),
                current.selectedHistory?.id?.takeUnless { current.lineageDetached })
        }
    }

    internal fun previewDdlRange(preview: DdlRangePreview?) {
        localState.value = localState.value.copy(ddlRangePreview = preview)
    }

    /**
     * Reads a DDL file into the editor. An `inku.ddl-export.v1` file brings its
     * plugin definitions for the next new work only; the work is detached from
     * the current lineage because an import is never an edit of that work.
     */
    fun importDdlFile(text: String) {
        val parsed = runCatching { DdlExport.parse(text) }.getOrElse {
            localState.value = localState.value.copy(message = strings().ddlImportInvalid)
            return
        }
        localState.value = localState.value.copy(
            ddl = parsed.ddl.orEmpty(),
            ddlEditedAfterGeneration = true,
            lineageDetached = true,
            pipelineView = null,
            pendingDescriptionParent = null,
            historyAuthority = null,
            historyDescriptionLocked = null,
            importedPlugins = parsed.plugins,
            importedPluginNames = parsed.names,
            message = if (parsed.names.isEmpty()) null else strings().ddlImportedPlugins(parsed.names.joinToString(", ")),
        )
    }

    fun ddlImportFailed() {
        localState.value = localState.value.copy(message = strings().ddlImportInvalid)
    }

    /** The work's SVG in [profile]; editable and compat are drawn again from its Score. */
    suspend fun exportSvg(item: HistoryItemEntity, profile: String): String =
        withContext(Dispatchers.IO) { repository.exportSvg(item, profile) }

    /** The saved work as `inku.ddl-export.v1` text, for the share sheet. */
    suspend fun ddlExportJson(item: HistoryItemEntity): String =
        withContext(Dispatchers.IO) { repository.ddlExportJson(item) }

    fun setBatchText(value: String) {
        localState.value = localState.value.copy(batchText = value, message = null)
    }

    fun clearBatchText() {
        if (state.value.isDrawing) return
        localState.value = localState.value.copy(batchText = "", message = null)
    }

    fun restoreBatchPrompt(prompt: String) {
        if (state.value.isDrawing) return
        localState.value = localState.value.copy(batchText = prompt, message = null)
    }

    fun setDemoSeed(value: String) {
        localState.value = localState.value.copy(demoSeed = value, message = null)
        persistSetting("demo_seed_phrase", JSONObject().put("value", value).toString())
    }

    fun resetDemoSeed() {
        setDemoSeed(DefaultDemoSeedPhrase)
    }

    fun setDemoIntervalSeconds(value: Int) {
        val normalized = value.coerceIn(1, 999)
        localState.value = localState.value.copy(demoIntervalSeconds = normalized, message = null)
        persistSetting("demo_interval_seconds", JSONObject().put("value", normalized).toString())
    }

    fun setCatalog(id: String) {
        val selectionId = CatalogSelection.normalizedSelectionId(id)
        localState.value = localState.value.copy(selectedCatalogId = selectionId)
        persistSetting("color_catalog", JSONObject().put("value", selectionId).toString())
    }

    fun setCanvasAspect(id: String) {
        val selected = CanvasAspects.newSelectionOrDefault(id)
        localState.value = localState.value.copy(selectedCanvasAspect = selected)
        persistSetting("canvas_aspect", JSONObject().put("value", selected).toString())
    }

    fun setSelectedModel(modelId: String) {
        localState.value = localState.value.copy(
            selectedModelId = modelId,
            selectedStage2ModelId = modelId,
            message = null,
        )
        warmupLiteRtModels(modelId)
    }

    fun setIncludeThinking(enabled: Boolean) {
        localState.value = localState.value.copy(includeThinking = enabled)
        persistSetting("include_thinking", JSONObject().put("enabled", enabled).toString())
    }

    fun setTab(tab: AppTab) {
        if (tab != AppTab.Settings) repository.chatGptPlan.cancelAuthorization()
        val current = localState.value
        if (current.tab == AppTab.History && tab != AppTab.History) presentationNavigationSerial++
        localState.value = current.copy(
            tab = tab,
            canvasPresentationMode = false,
            presentationHistory = null,
            presentationSequence = emptyList(),
            settingsPane = if (tab == AppTab.Settings && current.tab != AppTab.Settings) SettingsPane.Home else current.settingsPane,
            settingsReturnTab = if (tab == AppTab.Settings && current.tab != AppTab.Settings) current.tab else current.settingsReturnTab,
        )
        // web refetches when the lineage tab comes up (+page.svelte:4556).
        if (tab == AppTab.Lineage) refreshLineage()
    }

    /** The global Studio action returns to writing, never to a viewed work. */
    fun openStudio() {
        if (localState.value.cameraCaptureState.locksCameraInteraction) return
        if (localState.value.isDrawing) {
            setTab(AppTab.Compose)
            return
        }
        // A proposal waiting for 承認 or 辞退 stays on screen until it is
        // answered (SPEC 2026-10-12); 「新しい作品」 is what drops it, and says so
        // by cancelling the run. Leaving it here used to hide the answer with
        // no way back to it.
        if (localState.value.pipelineView?.patchProposal != null) {
            setTab(AppTab.Compose)
            localState.value = localState.value.copy(
                composeMode = ComposeMode.Write,
                canvasPresentationMode = false, presentationHistory = null, presentationSequence = emptyList(),
            )
            return
        }
        closeRefinement()
        var current = localState.value
        if (current.workContextId != null) {
            pausedWorkState = current
            authoringReturnState?.let { current = current.restoreAuthoring(it) }
            authoringReturnState = null
        }
        // A completed result is viewed from Works. An unfinished new-work
        // draft survives a trip through another work or Settings.
        if (current.selectedHistory != null) {
            current = current.copy(
                prompt = "", ddl = "", ddlEditedAfterGeneration = false,
                selectedHistory = null, pipelineView = null, historyAuthority = null, historyDescriptionLocked = null,
                historyAuthorityLoading = false, descriptionForkRequested = false,
                cameraSourcePhotoPath = null, cameraCaptureState = CameraCaptureState.Idle,
            )
        }
        lineageJob?.cancel()
        presentationNavigationSerial++
        promptEditedByUser = true
        localState.value = current.copy(
            tab = AppTab.Compose, composeMode = ComposeMode.Write,
            descriptionEditing = false, workContextId = null, descriptionFocused = false,
            lineageDetached = true, lineageGraph = null, lineageLoading = false,
            pendingDescriptionParent = null,
            canvasPresentationMode = false, presentationHistory = null,
            presentationSequence = emptyList(), workActionsTarget = null, workSketchTarget = null,
            ddlEditorOpen = false, confirmDdlOverwrite = false,
            refinementOpen = false, refinementParent = null, refinementCandidates = emptyList(),
            refinementPreviewId = null, refinementStatus = null, message = null,
        )
    }

    fun closeSettings() {
        repository.chatGptPlan.cancelAuthorization()
        localState.value = localState.value.copy(tab = localState.value.settingsReturnTab, settingsPane = SettingsPane.Home)
    }

    fun openWorkActions(item: HistoryItemEntity) {
        if (state.value.isRunning || item.trashed) return
        localState.value = localState.value.copy(workActionsTarget = item)
    }

    fun closeWorkActions() {
        localState.value = localState.value.copy(workActionsTarget = null)
    }

    fun openCanvasSearch() {
        if (state.value.isRunning) return
        localState.value = localState.value.copy(canvasSearchOpen = true)
        setCanvasSearchQuery(localState.value.canvasSearchQuery)
    }

    fun closeCanvasSearch() {
        canvasSearchSerial++
        canvasSearchJob?.cancel()
        localState.value = localState.value.copy(canvasSearchOpen = false, canvasSearchBusy = false)
    }

    fun setCanvasSearchQuery(value: String) {
        val query = value.take(200)
        val serial = ++canvasSearchSerial
        canvasSearchJob?.cancel()
        localState.value = localState.value.copy(canvasSearchQuery = query, canvasSearchBusy = true, canvasSearchFailed = false, canvasSearchResultIds = emptyList())
        canvasSearchJob = viewModelScope.launch {
            delay(250)
            runCatching {
                withContext(Dispatchers.IO) { repository.canvasSearchEntries().filter { it.matches(query) }.map { it.id } }
            }.onSuccess { ids ->
                if (serial == canvasSearchSerial && localState.value.canvasSearchOpen) {
                    localState.value = localState.value.copy(canvasSearchBusy = false, canvasSearchResultIds = ids)
                }
            }.onFailure { error ->
                if (error is CancellationException) throw error
                if (serial == canvasSearchSerial) localState.value = localState.value.copy(canvasSearchBusy = false, canvasSearchFailed = true)
            }
        }
    }

    fun selectCanvasSearchResult(id: String) {
        if (state.value.isRunning || id !in localState.value.canvasSearchResultIds) return
        val serial = canvasSearchSerial
        viewModelScope.launch {
            val item = withContext(Dispatchers.IO) { repository.getHistoryById(id) } ?: return@launch
            if (serial != canvasSearchSerial || !localState.value.canvasSearchOpen || state.value.isRunning || item.trashed) return@launch
            closeCanvasSearch()
            selectHistory(item)
        }
    }

    fun openReplayComparison(item: HistoryItemEntity) {
        if (state.value.isRunning || item.trashed) return
        enterWorkContext(item)
        closeRefinement()
        val serial = ++replaySerial
        localState.value = localState.value.copy(replayOpen = true, replayBusy = true, replayComparison = null, replayError = null, replaySavedHistoryId = null)
        replayJob = viewModelScope.launch {
            try {
                val comparison = withContext(Dispatchers.IO) { repository.replaySavedWork(item.id) }
                if (serial == replaySerial && localState.value.replayOpen) {
                    localState.value = localState.value.copy(replayComparison = comparison)
                }
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                if (serial == replaySerial) localState.value = localState.value.copy(replayError = messageFor(error, strings(), strings().statusDrawFailed))
            } finally {
                if (serial == replaySerial) localState.value = localState.value.copy(replayBusy = false)
            }
        }
    }

    fun closeReplayComparison() {
        if (localState.value.replaySaving) return
        replaySerial++
        replayJob?.cancel()
        localState.value = localState.value.copy(replayOpen = false, replayBusy = false, replayComparison = null, replayError = null)
    }

    fun saveReplayComparison() {
        val current = localState.value
        if (current.replayBusy || current.replaySaving || current.replaySavedHistoryId != null) return
        val comparison = current.replayComparison ?: return
        localState.value = current.copy(replaySaving = true, replayError = null)
        viewModelScope.launch {
            try {
                val saved = withContext(Dispatchers.IO) { repository.saveReplayChild(comparison) }
                localState.value = localState.value.copy(replaySavedHistoryId = saved.id)
                refreshLineage()
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                localState.value = localState.value.copy(replayError = messageFor(error, strings(), strings().statusSaveFailed))
            } finally {
                localState.value = localState.value.copy(replaySaving = false)
            }
        }
    }

    suspend fun sentPrompts(historyId: String) = withContext(Dispatchers.IO) { repository.sentPrompts(historyId) }

    /** Establish the immutable target before any edit changes the shared pipeline input. */
    private fun enterWorkContext(item: HistoryItemEntity) {
        val current = localState.value
        if (current.workContextId == item.id) {
            localState.value = current.copy(workActionsTarget = null, canvasPresentationMode = false, presentationHistory = null, presentationSequence = emptyList())
            return
        }
        val returnTo = authoringReturnState
        authoringReturnState = when {
            returnTo == null -> current.copy(workActionsTarget = null)
            // Entered again from Works -- its list or its full screen -- after
            // the bottom bar left an earlier work's context. Back goes to where
            // this entry was made; the draft kept is still the one from before
            // the first work. Kept whole, back went to the first work's viewer.
            current.tab == AppTab.History || current.presentationHistory != null -> returnTo.copy(
                tab = current.tab,
                canvasPresentationMode = current.canvasPresentationMode,
                presentationHistory = current.presentationHistory,
                presentationSequence = current.presentationSequence,
            )
            else -> returnTo
        }
        val paused = pausedWorkState?.takeIf { it.workContextId == item.id }
        if (paused != null) {
            localState.value = current.restoreAuthoring(paused)
            pausedWorkState = null
        } else {
            applyHistorySelection(item, AppTab.Compose)
        }
        localState.value = localState.value.copy(
            workContextId = item.id,
            canvasPresentationMode = false,
            presentationHistory = null,
            presentationSequence = emptyList(),
            workActionsTarget = null,
        )
    }

    fun editWorkDescription(item: HistoryItemEntity) {
        if (state.value.isRunning) return
        enterWorkContext(item)
        localState.value = localState.value.copy(
            tab = AppTab.Compose, descriptionEditing = true, composeMode = ComposeMode.Write,
            // 「記述を変える」 is the request to draw from a changed description.
            // A work led by its DDL (a 推敲 child, an edited DDL) otherwise
            // opened with the field locked and 描画する doing nothing, until
            // 「記述から新しい作品を作る」 was found and pressed.
            descriptionForkRequested = true,
        )
    }

    fun editWorkInstructions(item: HistoryItemEntity) {
        if (state.value.isRunning) return
        enterWorkContext(item)
        openLineageDdlEditor(item)
    }

    fun refineWork(item: HistoryItemEntity, subview: RefinementSubview) {
        if (state.value.isRunning) return
        enterWorkContext(item)
        openRefinement(item, subview)
    }

    /** Open a remaining refinement on the same immutable saved-work target. */
    fun refineWork(item: HistoryItemEntity, element: RefinementElement) {
        if (state.value.isRunning) return
        enterWorkContext(item)
        localState.value = localState.value.copy(refinementElement = element)
        openRefinement(item, RefinementSubview.Adjust)
    }

    fun openWorkLineage(item: HistoryItemEntity) {
        if (state.value.isRunning) return
        closeRefinement()
        enterWorkContext(item)
        localState.value = localState.value.copy(tab = AppTab.Lineage)
        refreshLineage()
    }

    fun openWorkLineage(item: HistoryListItem) {
        viewModelScope.launch {
            repository.getHistoryById(item.id)?.let { openWorkLineage(it) }
        }
    }

    fun showWorkSketch(item: HistoryItemEntity) {
        if (state.value.isRunning) return
        localState.value = localState.value.copy(workActionsTarget = null, workSketchTarget = item)
    }

    fun closeWorkSketch() {
        localState.value = localState.value.copy(workSketchTarget = null)
    }

    fun redrawWorkSketch(item: HistoryItemEntity, mode: SketchMode) {
        if (state.value.isRunning) return
        enterWorkContext(item)
        closeWorkSketch()
        redrawSketch(item, mode)
    }

    fun redrawWorkSketchText(item: HistoryItemEntity, text: String) {
        if (state.value.isRunning) return
        enterWorkContext(item)
        closeWorkSketch()
        redrawSketchText(item, text)
    }

    fun finishDescriptionEditing() {
        localState.value = localState.value.copy(descriptionEditing = false, descriptionFocused = false)
    }

    fun closeWorkContext() {
        if (state.value.isRunning) return
        val source = authoringReturnState ?: return
        closeRefinement()
        lineageJob?.cancel()
        localState.value = localState.value.restoreAuthoring(source).copy(workActionsTarget = null, workSketchTarget = null)
        authoringReturnState = null
        pausedWorkState = null
        if (source.tab == AppTab.Lineage) refreshLineage()
    }

    /** Restore only the workspace; provider settings and download progress remain current. */
    private fun InkuUiState.restoreAuthoring(source: InkuUiState): InkuUiState = copy(
        prompt = source.prompt, ddl = source.ddl, ddlEditedAfterGeneration = source.ddlEditedAfterGeneration,
        pipelineView = source.pipelineView, historyAuthority = source.historyAuthority,
        historyDescriptionLocked = source.historyDescriptionLocked,
        historyAuthorityLoading = source.historyAuthorityLoading, descriptionForkRequested = source.descriptionForkRequested,
        selectedHistory = source.selectedHistory, selectedCatalogId = source.selectedCatalogId,
        pendingDescriptionParent = source.pendingDescriptionParent,
        selectedCanvasAspect = source.selectedCanvasAspect, sketchMode = source.sketchMode,
        lineageDetached = source.lineageDetached, cameraSourcePhotoPath = source.cameraSourcePhotoPath,
        cameraCaptureState = source.cameraCaptureState, importedPlugins = source.importedPlugins,
        importedPluginNames = source.importedPluginNames, composeMode = source.composeMode,
        tab = source.tab, renderTab = source.renderTab, descriptionEditing = source.descriptionEditing,
        workContextId = source.workContextId, descriptionFocused = false, ddlEditorOpen = false,
        confirmDdlOverwrite = false, canvasPresentationMode = source.canvasPresentationMode,
        presentationHistory = source.presentationHistory, presentationSequence = source.presentationSequence,
        lineageGraph = source.lineageGraph, lineageLoading = false, message = source.message,
        refinementOpen = source.refinementOpen, refinementParent = source.refinementParent,
        refinementCandidates = source.refinementCandidates, refinementPreviewId = source.refinementPreviewId,
        refinementSubview = source.refinementSubview, refinementStatus = source.refinementStatus,
        refinementBusy = false, refinementCanAbort = false,
        refinementWildOverride = source.refinementWildOverride, modelCompareFailedModels = source.modelCompareFailedModels,
        colorArrangementExhausted = source.colorArrangementExhausted, groundCurrentLabel = source.groundCurrentLabel,
        replayOpen = false, replayBusy = false, replaySaving = false, replayComparison = null,
        replaySavedHistoryId = null, replayError = null, canvasSearchOpen = false,
        autonomousOpen = false, autonomousParent = null, autonomousStatus = AutonomousRefinementStatus(),
    )

    fun setSettingsPane(panel: SettingsPane) {
        if (panel != SettingsPane.ChatGpt) repository.chatGptPlan.cancelAuthorization()
        localState.value = localState.value.copy(settingsPane = panel, message = null)
    }

    fun authorizeChatGpt(profileId: String? = null, consent: Boolean = false) {
        viewModelScope.launch {
            try {
                val url = withContext(Dispatchers.IO) { repository.chatGptPlan.authorize(profileId, consent, !state.value.uiLanguage.isEnglish) }
                mutableChatGptAuthorizationRequests.emit(url)
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) { localState.value = localState.value.copy(message = strings().chatGptError((error as? app.inku.mobile.llm.ChatGptException)?.code ?: "chatgpt_auth_unavailable")) }
        }
    }

    fun cancelChatGptAuthorization() = repository.chatGptPlan.cancelAuthorization()
    fun chatGptBrowserUnavailable() = repository.chatGptPlan.browserUnavailable()
    fun acknowledgeChatGptPlan() {
        viewModelScope.launch {
            try { withContext(Dispatchers.IO) { repository.chatGptPlan.acknowledgePlanNotice() } }
            catch (error: app.inku.mobile.llm.ChatGptException) { localState.value = localState.value.copy(message = strings().chatGptError(error.code)) }
        }
    }

    fun selectChatGptProfile(id: String) {
        viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) { repository.chatGptPlan.selectProfile(id) }
                localState.value = localState.value.copy(providerModelFetchStates = localState.value.providerModelFetchStates - "chatgpt", message = null)
            } catch (error: app.inku.mobile.llm.ChatGptException) { localState.value = localState.value.copy(message = strings().chatGptError(error.code)) }
        }
    }

    fun signOutChatGpt(id: String) {
        viewModelScope.launch {
            try { repository.chatGptPlan.signOut(id) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (error: app.inku.mobile.llm.ChatGptException) { localState.value = localState.value.copy(message = strings().chatGptError(error.code)) }
        }
    }

    fun publishChatGptModels(session: app.inku.mobile.llm.ChatGptSessionRef, models: List<String>) {
        viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) { repository.chatGptPlan.publishModels(session, models) }
                localState.value = localState.value.copy(message = strings().modelSettingsSaved)
            } catch (error: app.inku.mobile.llm.ChatGptException) { localState.value = localState.value.copy(message = strings().chatGptError(error.code)) }
        }
    }

    fun openModelSelection() {
        val current = localState.value
        modelSelectionSnapshot = current.selectedModelId to current.selectedStage2ModelId
        localState.value = current.copy(modelSelectionOpen = true, message = null)
    }

    /**
     * The model selection over the camera preview (the author, 2026-09-30):
     * one model reads the photo, writes the description, and draws the work.
     * Only a capture in progress opens it.
     */
    fun openCameraModelSelection() {
        val current = localState.value
        if (current.cameraCaptureState != CameraCaptureState.Capturing) return
        modelSelectionSnapshot = current.selectedModelId to current.selectedStage2ModelId
        localState.value = current.copy(modelSelectionOpen = true, modelSelectionForCamera = true, message = null)
    }

    fun confirmModelSelection() {
        modelSelectionSnapshot = null
        val current = localState.value
        val unifiedModelId = current.selectedModelId
        val selectedProvider = app.inku.mobile.llm.RoutingModelProvider.resolveProviderForRouting(
            state.value.providerSettings, unifiedModelId, null,
        )?.providerId
        persistSetting("model_selection", JSONObject()
            .put("stage1_model", unifiedModelId)
            .put("stage2_model", unifiedModelId)
            .put("stage1_provider", selectedProvider)
            .put("stage2_provider", selectedProvider)
            .put("include_thinking", current.includeThinking)
            .toString())
        val forCamera = current.modelSelectionForCamera
        if (forCamera) {
            // The capture runs on the settings it started with; a choice made
            // over its preview is the one it is meant to use.
            cameraComposeSnapshot = cameraComposeSnapshot?.copy(
                selectedModelId = unifiedModelId,
                selectedStage2ModelId = unifiedModelId,
                includeThinking = current.includeThinking,
            )
        }
        localState.value = current.copy(
            selectedModelId = unifiedModelId,
            selectedStage2ModelId = unifiedModelId,
            modelSelectionOpen = false,
            modelSelectionForCamera = false,
            message = null,
        )
        warmupLiteRtModels(unifiedModelId)
    }

    fun cancelModelSelection() {
        val snapshot = modelSelectionSnapshot
        modelSelectionSnapshot = null
        localState.value = localState.value.copy(
            selectedModelId = snapshot?.first ?: localState.value.selectedModelId,
            selectedStage2ModelId = snapshot?.second ?: localState.value.selectedStage2ModelId,
            modelSelectionOpen = false,
            modelSelectionForCamera = false,
            message = null,
        )
    }

    fun openCatalogSelection() {
        val current = localState.value
        catalogSelectionSnapshot = current.selectedCatalogId
        localState.value = current.copy(catalogSelectionOpen = true, message = null)
    }

    fun confirmCatalogSelection() {
        catalogSelectionSnapshot = null
        localState.value = localState.value.copy(catalogSelectionOpen = false, message = null)
    }

    fun cancelCatalogSelection() {
        val snapshot = catalogSelectionSnapshot
        catalogSelectionSnapshot = null
        // `setCatalog` saves every choice as it is tapped, so a cancel has to
        // save the value it restores too; otherwise the next start brings back
        // the choice that was just cancelled.
        if (snapshot != null && snapshot != localState.value.selectedCatalogId) {
            persistSetting("color_catalog", JSONObject().put("value", snapshot).toString())
        }
        localState.value = localState.value.copy(
            selectedCatalogId = snapshot ?: localState.value.selectedCatalogId,
            catalogSelectionOpen = false,
            message = null,
        )
    }

    fun openCanvasSelection() {
        localState.value = localState.value.copy(canvasSelectionOpen = true, message = null)
    }

    fun closeTransientPanel() {
        localState.value = localState.value.copy(canvasSelectionOpen = false, catalogSelectionOpen = false, modelSelectionOpen = false, message = null)
    }

    fun setComposeMode(mode: ComposeMode) {
        localState.value = localState.value.copy(composeMode = mode)
    }

    fun setDescriptionFocused(focused: Boolean) {
        if (localState.value.descriptionFocused == focused) return
        localState.value = localState.value.copy(descriptionFocused = focused)
    }

    fun setRenderTab(tab: RenderTab) {
        localState.value = localState.value.copy(renderTab = tab)
    }

    fun setCanvasZoom(value: Float) {
        localState.value = localState.value.copy(canvasZoom = value.coerceIn(CANVAS_ZOOM_MIN, CANVAS_ZOOM_MAX))
    }

    fun scaleCanvasZoom(multiplier: Float) {
        val current = localState.value
        localState.value = current.copy(canvasZoom = (current.canvasZoom * multiplier).coerceIn(CANVAS_ZOOM_MIN, CANVAS_ZOOM_MAX))
    }

    /** Back to fit. The pan goes with it: an unzoomed canvas cannot be off-centre. */
    fun resetCanvasZoom() {
        localState.value = localState.value.copy(canvasZoom = CANVAS_FIT_ZOOM, canvasPanX = 0f, canvasPanY = 0f)
    }

    /**
     * The double tap in presentation: fit <-> 1:1, as web's `CanvasPanel` does.
     *
     * The caller measures `oneToOneZoom`, because only the layout knows how many
     * pixels the fitted artwork got. Off fit, the tap always returns to fit --
     * that is the state one wants back after looking closely.
     */
    fun toggleCanvasZoom(oneToOneZoom: Float) {
        val current = localState.value
        val atFit = abs(current.canvasZoom - CANVAS_FIT_ZOOM) < CANVAS_ZOOM_EPSILON
        if (!atFit) {
            resetCanvasZoom()
            return
        }
        localState.value = current.copy(
            canvasZoom = oneToOneZoom.coerceIn(CANVAS_ZOOM_MIN, CANVAS_ZOOM_MAX),
            canvasPanX = 0f,
            canvasPanY = 0f,
        )
    }

    fun enterCanvasPresentationMode() {
        presentationNavigationSerial++
        localState.value = localState.value.copy(
            canvasZoom = CANVAS_FIT_ZOOM,
            canvasPanX = 0f,
            canvasPanY = 0f,
            canvasPresentationMode = true,
            presentationHistory = null,
            presentationSequence = emptyList(),
        )
    }

    /** Present a gallery work without changing the work or description selected for editing. */
    fun openHistoryPresentation(item: HistoryListItem, filteredIds: List<String>) {
        val request = ++presentationNavigationSerial
        val sequence = filteredIds.distinct().takeIf { item.id in it } ?: listOf(item.id)
        viewModelScope.launch {
            val work = repository.getHistoryById(item.id) ?: return@launch
            if (request != presentationNavigationSerial) return@launch
            localState.value = localState.value.copy(
                tab = AppTab.History,
                canvasZoom = CANVAS_FIT_ZOOM,
                canvasPanX = 0f,
                canvasPanY = 0f,
                canvasPresentationMode = true,
                presentationHistory = work,
                presentationSequence = sequence,
            )
        }
    }

    /**
     * Leave the full screen.
     *
     * This used to be `resetCanvasZoom`, which meant the close button and the
     * zoom reset were the same call and neither could be done without the other.
     */
    fun exitCanvasPresentationMode() {
        presentationNavigationSerial++
        val current = localState.value
        localState.value = current.copy(
            canvasZoom = CANVAS_FIT_ZOOM,
            canvasPanX = 0f,
            canvasPanY = 0f,
            canvasPresentationMode = false,
            presentationHistory = null,
            presentationSequence = emptyList(),
            tab = if (current.presentationHistory != null) AppTab.History else current.tab,
        )
    }

    /** Leave the gallery viewer and explicitly load this work into the editor. */
    fun editPresentedHistory() {
        val work = localState.value.presentationHistory ?: localState.value.selectedHistory ?: return
        openWorkActions(work)
    }

    fun panCanvas(dx: Float, dy: Float) {
        val current = localState.value
        if (current.canvasZoom <= CANVAS_FIT_ZOOM) return
        localState.value = current.copy(
            canvasPanX = (current.canvasPanX + dx).coerceIn(-500f, 500f),
            canvasPanY = (current.canvasPanY + dy).coerceIn(-500f, 500f),
        )
    }

    fun setDisplaySafeMarginsEnabled(enabled: Boolean) {
        localState.value = localState.value.copy(displaySafeMarginsEnabled = enabled)
        persistSetting(SETTING_KEY_DISPLAY_SAFE_MARGINS, JSONObject().put("enabled", enabled).toString())
    }

    fun setPngAlphaWhite(enabled: Boolean) {
        localState.value = localState.value.copy(pngAlphaWhite = enabled)
        persistSetting("png_alpha_white", JSONObject().put("enabled", enabled).toString())
    }

    fun setMaxSvgMiB(text: String) {
        val value = app.inku.mobile.render.SvgOutputLimit.parseMiB(text) ?: return
        viewModelScope.launch {
            runCatching {
                repository.saveSetting(app.inku.mobile.render.SvgOutputLimit.SETTING_KEY,
                    JSONObject().put("value", value * app.inku.mobile.render.SvgOutputLimit.BYTES_PER_MIB).toString())
            }.onSuccess { localState.value = localState.value.copy(maxSvgMiB = value) }
                .onFailure { error -> localState.value = localState.value.copy(message = messageFor(error, strings(), strings().statusSaveFailed)) }
        }
    }

    fun setRenderWild(wild: Boolean) {
        localState.value = localState.value.copy(renderWild = wild)
        persistSetting(SETTING_KEY_RENDER_WILD, JSONObject().put("enabled", wild).toString())
    }

    fun setSketchMode(mode: SketchMode) {
        localState.value = localState.value.copy(sketchMode = mode)
    }

    fun addExportTemplate() {
        val templates = state.value.exportTemplates
        val index = templates.size + 1
        viewModelScope.launch {
            repository.saveExportTemplate(
                id = "png-custom-${System.currentTimeMillis()}",
                name = "PNG Custom $index",
                description = "",
                heightPx = 2160,
                sortOrder = templates.size,
            )
        }
    }

    fun updateExportTemplate(template: ExportTemplateEntity, name: String, description: String, heightPx: Int) {
        viewModelScope.launch {
            repository.saveExportTemplate(template.id, name, description, heightPx, template.sortOrder, template.isBuiltin)
        }
    }

    fun removeExportTemplate(id: String) {
        viewModelScope.launch {
            repository.deleteExportTemplate(id)
        }
    }

    fun setHistorySearchQuery(value: String) {
        localState.value = localState.value.copy(historySearchQuery = value)
    }

    fun toggleHistoryStarredFilter() {
        val current = localState.value
        localState.value = current.copy(historyStarredOnly = !current.historyStarredOnly)
    }

    fun setUiMode(mode: String) {
        val normalized = if (mode == "simple") "simple" else "full"
        localState.value = localState.value.copy(uiMode = normalized, message = null)
        persistSetting("ui_mode", JSONObject().put("value", normalized).toString())
    }

    /** Enables or disables the bundled plugin package for new works. */
    fun setBundledPluginsEnabled(enabled: Boolean) {
        localState.value = localState.value.copy(bundledPluginsEnabled = enabled, message = null)
        viewModelScope.launch { repository.setBundledPluginPackageEnabled(enabled) }
    }

    /**
     * The reader picks the language the interface speaks.
     *
     * Three things change together, which is why this is one call and not three:
     * the wording, the saijiki words, and -- through [InkuUiState.uiLanguage]
     * reaching `resolveWithUiLang` -- which language a work asking for `auto`
     * gets drawn in. On the web the third one is the server's answer to the
     * `ui_lang` the page sends; here the same judgement is made on the device.
     */
    fun setUiLanguage(language: UiLanguage) {
        localState.value = localState.value.copy(uiLanguage = language, message = null)
        persistSetting(SETTING_KEY_UI_LANGUAGE, JSONObject().put("value", language.code).toString())
    }

    fun setUiTextScale(scale: Float) {
        val normalized = normalizeUiTextScale(scale)
        localState.value = localState.value.copy(uiTextScale = normalized)
        persistSetting(SETTING_KEY_UI_TEXT_SCALE, JSONObject().put("value", normalized).toString())
    }

    fun setMascotKind(kind: String) {
        val normalized = if (kind == "yuragi") "yuragi" else "incu"
        localState.value = localState.value.copy(mascotKind = normalized, message = null)
        persistSetting(SETTING_KEY_MASCOT_KIND, JSONObject().put("value", normalized).toString())
    }

    fun toggleSaijiki() {
        val current = localState.value
        localState.value = current.copy(saijikiOpen = !current.saijikiOpen, message = null)
    }

    fun insertDdlWord(word: String) {
        val current = localState.value
        val base = current.ddl.ifBlank { current.prompt }
        val separator = if (base.isBlank() || base.endsWith(" ") || base.endsWith("\n")) "" else " "
        localState.value = current.copy(ddl = base + separator + word, ddlEditedAfterGeneration = true, message = null)
        promptEditedByUser = true
    }

    fun openDdlEditor() {
        localState.value = localState.value.copy(ddlEditorOpen = true, message = null)
    }

    fun openLineageDdlEditor(item: HistoryItemEntity) {
        applyHistorySelection(item, AppTab.Lineage)
        localState.value = localState.value.copy(ddlEditorOpen = true, message = null)
        refreshLineage()
    }

    fun closeDdlEditor() {
        localState.value = localState.value.copy(ddlEditorOpen = false)
    }

    fun selectHistory(item: HistoryItemEntity) = applyHistorySelection(item, AppTab.Compose)

    /** Redraw this lineage work with an explicit 写生 choice and a new child edge. */
    fun redrawSketch(item: HistoryItemEntity, mode: SketchMode) {
        startSketchRedraw(item, mode, null)
    }

    /** The author's corrected prose is supplied directly, without another 写生 call. */
    fun redrawSketchText(item: HistoryItemEntity, text: String) {
        val supplied = text.trim().takeIf { it.isNotEmpty() } ?: return
        startSketchRedraw(item, SketchMode.On, supplied)
    }

    private fun startSketchRedraw(item: HistoryItemEntity, mode: SketchMode, suppliedText: String?) {
        val description = sourceTextOf(item)
        if (item.lineageNodeId.isNullOrEmpty() || description.isBlank()) return
        val before = state.value
        if (before.isDrawing || before.refinementBusy) return
        applyHistorySelection(item, AppTab.Lineage)
        val current = localState.value.copy(
            prompt = description,
            sketchMode = mode,
            selectedCatalogId = item.colorCatalogId,
            selectedCanvasAspect = item.canvasAspect,
            descriptionForkRequested = true,
            refinementOpen = false,
            refinementPreviewId = null,
            // This operation starts a new description run from the saved work;
            // it does not need to resume that work's pipeline authority.
            historyAuthorityLoading = false,
        )
        localState.value = current
        validateModelsForRun(current)?.let { message ->
            localState.value = current.copy(message = message)
            return
        }
        runSubmit(current, sketchRedraw = true, suppliedSketchText = suppliedText)
    }

    /**
     * @param tab where the pick leaves the reader. Picking out of history opens
     *   the work to be drawn again; picking a node in the lineage re-centres the
     *   graph and stays on it, which is what web's `openLineageNode` does
     *   (+page.svelte:4225-4230) -- there it is the double click
     *   (`openLineageNodeInCanvas`, :4234) that moves to the canvas.
     */
    private fun applyHistorySelection(item: HistoryItemEntity, tab: AppTab, asParent: Boolean = true) {
        if (localState.value.isDrawing) stopDrawing()
        discardStagedCameraPhoto()
        cameraRetryInput = null
        promptEditedByUser = false
        adoptSavedHistory(item) { current ->
            current.copy(
                descriptionForkRequested = false,
                // The canvas now shows this work, so no refinement candidate is
                // what the next drawing comes from (`withPreviewParent`).
                refinementPreviewId = null,
                // Only an explicit work operation establishes a parent.
                lineageDetached = !asParent,
                prompt = item.originalInput,
                ddl = item.normalizedDdl.orEmpty(),
                ddlEditedAfterGeneration = false,
                confirmDdlOverwrite = false,
                cameraCaptureState = current.cameraCaptureState.clearCameraOrigin(),
                // The catalog the work was asked for, not only the one it
                // resolved to: a work drawn with 自動 keeps 自動 for the next
                // drawing, as a restored pipeline already does
                // (`presentPipelineView`).
                selectedCatalogId = if (item.catalogMode == "auto") CatalogSelection.AUTO_ID else item.colorCatalogId,
                selectedCanvasAspect = item.canvasAspect,
                sketchMode = Sketches.modeOfWork(item.sketchState, item.sketchGrain),
                tab = tab,
                composeMode = ComposeMode.Write,
            )
        }
    }

    private fun adoptSavedHistory(
        item: HistoryItemEntity,
        activeExecution: Boolean = false,
        isCurrent: () -> Boolean = { true },
        update: (InkuUiState) -> InkuUiState,
    ) {
        localState.value = update(localState.value).copy(
            selectedHistory = item,
            pendingDescriptionParent = null,
            cameraSourcePhotoPath = originalPhotos.savedPhoto(item.id)?.absolutePath,
            pipelineView = null,
            historyAuthority = null,
            historyDescriptionLocked = null,
            historyAuthorityLoading = true,
        )
        viewModelScope.launch {
            val managed = runCatching {
                withContext(Dispatchers.IO) { repository.readManagedHistory(AndroidWorkPipeline.OWNER_ID, item.id) }
            }
            val lock = runCatching {
                withContext(Dispatchers.IO) { repository.isDescriptionLocked(item) }
            }
            val pipelineView = if (activeExecution) {
                runCatching {
                    withContext(Dispatchers.IO) { repository.pipelineViewFor(item) }
                }
            } else {
                Result.success(null)
            }
            val current = localState.value
            if (!isCurrent() || current.selectedHistory?.id != item.id || !current.historyAuthorityLoading) return@launch
            val history = managed.getOrNull()
            val view = pipelineView.getOrNull()?.takeIf { candidate ->
                pipelineIdentity(item)?.let { (executionId, revision) ->
                    candidate.executionId == executionId && candidate.revision == revision
                } == true
            }
            localState.value = current.copy(
                pipelineView = view,
                historyAuthority = history?.authority ?: view?.authority,
                historyDescriptionLocked = lock.getOrNull(),
                historyAuthorityLoading = false,
                message = history?.warning
                    ?: pipelineView.exceptionOrNull()?.let { messageFor(it, strings(), strings().drawingContextUnreadable) }
                    ?: managed.exceptionOrNull()?.let { messageFor(it, strings(), strings().drawingContextUnreadable) }
                    ?: current.message,
            )
        }
    }

    private fun matchingPipelineExecutionId(current: InkuUiState): String? {
        val view = current.pipelineView ?: return null
        val selected = current.selectedHistory ?: return view.executionId
        val recorded = pipelineIdentity(selected) ?: return null
        return view.executionId.takeIf {
            it == recorded.first && view.revision == recorded.second
        }
    }

    private fun pipelineIdentity(item: HistoryItemEntity): Pair<String, String>? = runCatching {
        val metadata = JSONObject(item.renderMetadataJson)
        val executionId = metadata.optString("pipeline_execution_id").takeIf { it.isNotBlank() }
            ?: return@runCatching null
        val revision = metadata.optString("pipeline_revision").takeIf { it.isNotBlank() }
            ?: return@runCatching null
        executionId to revision
    }.getOrNull()

    fun selectHistory(item: HistoryListItem) {
        viewModelScope.launch {
            repository.getHistoryById(item.id)?.let { selectHistory(it) }
        }
    }

    /**
     * 「新しい起点にする」-- the next save starts a lineage of its own instead of
     * hanging off the work on screen.
     *
     * A port of web's `detachLineage` (+page.svelte:4539-4548), minus the parts
     * that clear the lineage graph and switch tabs: this client has no lineage
     * panel to clear. Contract 2/5 brings that panel, and the button web puts on
     * it (`LineagePanel.svelte:788`) belongs there rather than somewhere this
     * client invented.
     */
    fun detachLineage() {
        localState.value = localState.value.copy(
            selectedHistory = null,
            pendingDescriptionParent = null,
            sketchMode = Sketches.DEFAULT_MODE,
            pipelineView = null,
            historyAuthority = null,
            historyDescriptionLocked = null,
            historyAuthorityLoading = false,
            descriptionForkRequested = false,
            lineageDetached = true,
            // The two lines contract 1/5 had to leave out, because there was no
            // lineage on this client to clear or to leave: web's `detachLineage`
            // ends with `lineageGraph = null; outputTab = 'canvas'`
            // (+page.svelte:4544-4546). Nothing is left to look at once the work
            // is dropped, so staying would show an empty screen.
            lineageGraph = null,
            tab = AppTab.Compose,
        )
    }

    /**
     * Reads the graph around the work on screen.
     *
     * The focus is the displayed work's node, the way web's `fetchLineage` is
     * always called with `currentLineageNodeId`; there is no second notion of
     * "which node the lineage is looking at" to fall out of step with it.
     */
    fun refreshLineage() {
        val focus = localState.value.selectedHistory?.lineageNodeId
        lineageJob?.cancel()
        if (focus.isNullOrEmpty()) {
            localState.value = localState.value.copy(lineageGraph = null, lineageLoading = false)
            return
        }
        localState.value = localState.value.copy(lineageLoading = true)
        lineageJob = viewModelScope.launch {
            val graph = repository.loadLineage(focus)
            // Re-read after the read suspended: the reader can have picked
            // another work meanwhile, and writing this graph over theirs would
            // leave the screen describing a work it is not showing.
            val current = localState.value
            if (current.selectedHistory?.lineageNodeId != focus) return@launch
            localState.value = current.copy(lineageGraph = graph, lineageLoading = false)
        }
    }

    /**
     * 系譜の node を選ぶ -- web's `openLineageNode` (+page.svelte:4225).
     *
     * A tombstone has no history row to open, and web guards the same way
     * (`if (!node.history) return`).
     */
    fun selectLineageNode(node: LineageGraphNode) {
        val item = (node as? LineageGraphNode.Work)?.history?.item ?: return
        // Picking another work selects it, and selecting stops the drawing; a
        // tap on a card is not how a run is meant to be stopped.
        if (localState.value.isRunning) return
        val inWorkContext = localState.value.workContextId != null
        applyHistorySelection(item, AppTab.Lineage)
        if (inWorkContext) localState.value = localState.value.copy(workContextId = item.id)
        refreshLineage()
    }

    fun selectPreviousHistory() {
        selectAdjacentHistory(-1)
    }

    fun selectNextHistory() {
        selectAdjacentHistory(1)
    }

    fun selectLatestHistory() {
        val viewer = localState.value
        if (viewer.canvasPresentationMode && viewer.presentationHistory != null) {
            viewer.presentationSequence.firstOrNull()?.let(::showPresentationHistory)
            return
        }
        if (viewer.isRunning) return
        viewModelScope.launch {
            val latest = historyItems.value.firstOrNull() ?: history.first().firstOrNull() ?: return@launch
            selectHistory(latest)
        }
    }

    private fun selectAdjacentHistory(offset: Int) {
        val now = SystemClock.elapsedRealtime()
        if (now - lastHistorySwipeAt < 450L) return
        val viewer = localState.value
        if (viewer.canvasPresentationMode && viewer.presentationHistory != null) {
            val index = viewer.presentationSequence.indexOf(viewer.presentationHistory.id)
            if (index < 0) return
            val next = (index + offset).coerceIn(0, viewer.presentationSequence.lastIndex)
            if (next == index) return
            lastHistorySwipeAt = now
            showPresentationHistory(viewer.presentationSequence[next])
            return
        }
        // Moving to another work selects it, and selecting stops the drawing
        // (`applyHistorySelection`). A swipe while a batch, the demo or a DDL
        // drawing is running would end it without a word.
        if (viewer.isRunning) return
        viewModelScope.launch {
            val items = historyItems.value.ifEmpty { history.first() }
            if (items.isEmpty()) return@launch
            val current = localState.value.selectedHistory
            val currentIndex = current
                ?.let { selected -> items.indexOfFirst { it.id == selected.id } }
                ?.takeIf { it >= 0 }
                ?: 0
            val nextIndex = (currentIndex + offset).coerceIn(0, items.lastIndex)
            if (nextIndex == currentIndex) return@launch
            lastHistorySwipeAt = now
            selectHistory(items[nextIndex])
        }
    }

    private fun showPresentationHistory(id: String) {
        val request = ++presentationNavigationSerial
        viewModelScope.launch {
            val work = repository.getHistoryById(id) ?: return@launch
            val current = localState.value
            if (request != presentationNavigationSerial || !current.canvasPresentationMode || id !in current.presentationSequence) return@launch
            localState.value = current.copy(
                presentationHistory = work,
                canvasZoom = CANVAS_FIT_ZOOM,
                canvasPanX = 0f,
                canvasPanY = 0f,
            )
        }
    }

    fun draw() {
        val current = state.value
        val cameraProvenance = CameraDrawRouting.provenanceFor(current.cameraCaptureState)
        // 「候補生成中は他の生成・描画操作を禁止し」. Before the model check, because
        // what stops this drawing has to be the refinement rather than whichever
        // reason happens to be found first.
        if (current.refinementBusy) {
            localState.value = localState.value.copy(message = REFINEMENT_IN_PROGRESS(strings()))
            return
        }
        validateModelsForRun(current)?.let { message ->
            localState.value = localState.value.copy(message = message)
            return
        }
        // Drawing from the description replaces the instructions with what
        // Stage 1 writes. Instructions the author edited by hand are asked
        // about first; the dialog also offers to draw from them. The dialog was
        // there from the start, but nothing ever raised it.
        if (cameraProvenance == null && current.ddlEditedAfterGeneration && DdlSource.hasBody(current.ddl)) {
            localState.value = localState.value.copy(confirmDdlOverwrite = true)
            return
        }
        runSubmit(current, cameraProvenance)
    }

    fun cancelDdlOverwrite() {
        localState.value = localState.value.copy(confirmDdlOverwrite = false)
    }

    fun confirmDdlOverwriteRegenerate() {
        val current = localState.value.copy(confirmDdlOverwrite = false, ddlEditedAfterGeneration = false)
        localState.value = current
        runSubmit(current)
    }

    fun confirmDdlOverwriteRenderEdited() {
        localState.value = localState.value.copy(confirmDdlOverwrite = false)
        drawFromDdl()
    }

    private fun beginDrawingRun(keepDescriptionParent: Boolean = false): Long {
        drawingRunSerial += 1
        drawingJob?.cancel()
        localState.value = localState.value.copy(
            isDrawing = true,
            pendingDescriptionParent = localState.value.pendingDescriptionParent.takeIf { keepDescriptionParent },
        )
        return drawingRunSerial
    }

    private fun isCurrentDrawingRun(runId: Long): Boolean {
        return drawingRunSerial == runId
    }

    /**
     * Builds the declaration a save carries: which work it came from, and by
     * which operation.
     *
     * `kindOf` is handed the parent -- null when there is none -- so that the
     * "no parent, no kind" branch of `SubmitDerivationKind` is the one this
     * client actually walks, rather than a branch only a unit test ever sees.
     *
     * The canvas ratio is compared against the parent's stored one, which is
     * how web reaches the same judgment through `pendingCanvasAspectDerivation`
     * (+page.svelte:3219-3243).
     */
    /** The work the next save descends from, or null when it becomes a root. */
    private fun lineageParent(current: InkuUiState): HistoryItemEntity? =
        (if (current.lineageDetached) null else current.selectedHistory)
            ?.takeIf { !it.lineageNodeId.isNullOrEmpty() }

    private fun lineageFor(
        current: InkuUiState,
        parent: HistoryItemEntity? = lineageParent(current),
        kindOf: (parent: HistoryItemEntity?, canvasAspectChanged: Boolean) -> String?,
    ): LineageDeclaration {
        val canvasAspectChanged = parent != null && current.selectedCanvasAspect != parent.canvasAspect
        val kind = kindOf(parent, canvasAspectChanged)
        if (parent == null || kind == null) return LineageDeclaration()
        return LineageDeclaration(
            parentNodeId = parent.lineageNodeId,
            derivationKind = kind,
            derivationMetadata = if (!canvasAspectChanged) {
                emptyMap<String, Any?>()
            } else {
                mapOf(
                    "from_canvas_aspect" to parent.canvasAspect,
                    "to_canvas_aspect" to current.selectedCanvasAspect,
                )
            },
        )
    }

    private fun describeLineage(current: InkuUiState): LineageDeclaration =
        lineageFor(current, current.descriptionDrawingParent?.takeIf { !it.lineageNodeId.isNullOrEmpty() }) { parent, canvasAspectChanged ->
            SubmitDerivationKind.forDescribeSubmit(
                hasParent = parent != null,
                canvasAspectChanged = canvasAspectChanged,
                textChanged = parent != null && descriptionChanged(current.prompt, parent),
                grainChanged = parent != null && grainChanged(current.sketchMode, parent),
            )
        }

    /** Old fine/coarse works count as on when comparing an ordinary redraw. */
    private fun grainChanged(mode: SketchMode, parent: HistoryItemEntity): Boolean =
        mode != Sketches.modeOfWork(parent.sketchState, parent.sketchGrain)

    /**
     * What the describe screen asks 写生 (Stage 0.5) for.
     *
     * An ordinary replay carries saved prose through the supplied path. The
     * explicit per-work action forces a fresh request, even at the same mode.
     */
    private fun describeSketchInput(current: InkuUiState, forceFresh: Boolean = false): SketchInput {
        val parent = current.descriptionDrawingParent?.takeIf { !it.lineageNodeId.isNullOrEmpty() }
        val replaying = !forceFresh && parent != null &&
            !descriptionChanged(current.prompt, parent) &&
            !grainChanged(current.sketchMode, parent)
        return SketchInput(
            requested = current.sketchMode == SketchMode.On,
            text = if (replaying) parent?.sketchText else null,
        )
    }

    private fun ddlLineage(current: InkuUiState): LineageDeclaration =
        lineageFor(current) { parent, canvasAspectChanged ->
            SubmitDerivationKind.forDdlSubmit(
                hasParent = parent != null,
                canvasAspectChanged = canvasAspectChanged,
                ddlEdited = current.ddlEditedAfterGeneration,
            )
        }

    /**
     * Whether the description differs from the one its parent was painted from.
     *
     * Like the server and web, this is a single choice: `source_text` when it
     * exists, otherwise `original_input`. No second interpretation is applied
     * to either value.
     */
    private fun descriptionChanged(prompt: String, parent: HistoryItemEntity): Boolean {
        val text = prompt.trim()
        return text != sourceTextOf(parent)
    }

    private fun runSubmit(current: InkuUiState, cameraProvenance: CameraInputProvenance? = null, sketchRedraw: Boolean = false, suppliedSketchText: String? = null) {
        if (current.autonomousStatus.busy || current.replayBusy || current.replaySaving) return
        if (current.descriptionLocked && !current.historyAuthorityLoading) {
            // Said rather than ignored: the button looks the same either way.
            localState.value = current.copy(message = strings().pipelineDdlAuthority)
            return
        }
        if (current.prompt.isBlank()) {
            localState.value = current.copy(message = strings().promptEmpty)
            return
        }
        if (current.refinementBusy) {
            localState.value = current.copy(message = REFINEMENT_IN_PROGRESS(strings()))
            return
        }
        val descriptionParent = if (cameraProvenance == null) current.descriptionDrawingParent else null
        // Read before the coroutine starts: the first thing it does is clear
        // `selectedHistory` (below), so a parent read from inside would be gone.
        val declared = when {
            sketchRedraw -> {
                val parent = requireNotNull(lineageParent(current))
                LineageDeclaration(
                    parentNodeId = parent.lineageNodeId,
                    derivationKind = SubmitDerivationKind.SKETCH_GRAIN_CHANGE,
                    derivationMetadata = mapOf(
                        "edited_from_history_id" to parent.id,
                        "from_sketch_state" to parent.sketchState,
                        "to_sketch_mode" to current.sketchMode.wire,
                    ),
                )
            }
            cameraProvenance == null -> describeLineage(current)
            else -> LineageDeclaration()
        }
        val sketchInput = when {
            suppliedSketchText != null -> SketchInput(text = suppliedSketchText)
            cameraProvenance == null -> describeSketchInput(current, forceFresh = sketchRedraw)
            // A camera description is a new root; it follows the 写生 setting.
            else -> SketchInput(requested = current.sketchMode == SketchMode.On)
        }
        // Read here for the same reason: it is decided against the parent, and
        // the coroutine clears the parent before it draws.
        val stage1ModelId = current.selectedModelId
        val stage2ModelId = current.selectedStage2ModelId
        val stage1CatalogId = current.selectedCatalogId
        val autoRepair = true
        val runId = beginDrawingRun(keepDescriptionParent = true)
        drawingJob = viewModelScope.launch {
            // The selected work's authority was still being read. A DDL-led
            // work is not redrawn from its description unless a fork was asked for.
            if (current.historyAuthorityLoading && current.selectedHistory != null) {
                val read = runCatching {
                    withContext(Dispatchers.IO) {
                        repository.readManagedHistory(AndroidWorkPipeline.OWNER_ID, current.selectedHistory.id)
                    }
                }
                val lock = runCatching {
                    withContext(Dispatchers.IO) { repository.isDescriptionLocked(current.selectedHistory) }
                }.getOrNull()
                if (!isCurrentDrawingRun(runId)) return@launch
                val managed = read.getOrNull()
                if (read.isFailure || managed == null || managed.warning != null) {
                    localState.value = localState.value.copy(
                        isDrawing = false,
                        historyAuthorityLoading = false,
                        message = managed?.warning ?: read.exceptionOrNull()?.let { messageFor(it, strings(), strings().drawingContextUnreadable) } ?: strings().drawingContextMissing,
                    )
                    return@launch
                }
                // A saved work answers with its lock mark, as the field does.
                if ((lock ?: (managed.authority == "ddl_authoritative")) && !current.descriptionForkRequested) {
                    localState.value = localState.value.copy(
                        isDrawing = false,
                        historyAuthorityLoading = false,
                        historyAuthority = managed.authority,
                        historyDescriptionLocked = lock,
                        message = strings().pipelineDdlAuthority,
                    )
                    return@launch
                }
            }
            // A candidate that cannot be kept leaves the declared parent: the
            // drawing is still the author's, and an uncaught failure here
            // would take the app down.
            val lineage = runCatching { withPreviewParent(current, declared) }.getOrElse { error ->
                if (error is CancellationException) throw error
                declared
            }
            localState.value = localState.value.beginDescriptionDrawing(parent = descriptionParent, message = strings().statusStage1)
            runCatching {
                withContext(Dispatchers.IO) {
                    repository.paint(
                        current.prompt,
                        stage1CatalogId,
                        current.selectedCanvasAspect,
                        stage1ModelId,
                        stage2ModelId,
                        autoRepair,
                        lineage = lineage,
                        instructionLang = InstructionLanguages.AUTO,
                        uiLang = current.uiLanguage.code,
                        sketch = sketchInput,
                        parentHistoryId = descriptionParent?.id,
                        inputProvenance = cameraProvenance,
                        renderWild = current.renderWild,
                        onPerformanceSaved = {
                            withContext(Dispatchers.Main.immediate) { descriptionPerformanceSaved(runId) }
                        },
                    )
                }
            }.onSuccess { item ->
                if (!isCurrentDrawingRun(runId)) return@onSuccess
                promptEditedByUser = false
                adoptSavedHistory(item, activeExecution = true, isCurrent = { isCurrentDrawingRun(runId) }) { latest ->
                    latest.copy(
                        prompt = item.originalInput,
                        ddl = item.normalizedDdl.orEmpty(),
                        ddlEditedAfterGeneration = false,
                        confirmDdlOverwrite = false,
                        descriptionForkRequested = false,
                        // A saved work is what the next one comes from (web lowers
                        // the same flag on every save, +page.svelte:2883, :3304).
                        lineageDetached = false,
                        cameraCaptureState = if (cameraProvenance != null) CameraCaptureState.Idle else latest.cameraCaptureState,
                        isDrawing = false,
                        message = strings().statusRendered(item.renderHashShort),
                    )
                }
                if (sketchRedraw) refreshLineage()
            }.onFailure { error ->
                if (!isCurrentDrawingRun(runId)) return@onFailure
                if (presentPipelineInteraction(error)) return@onFailure
                val message = if (error is CancellationException) strings().statusStopped else messageFor(error, strings(), strings().statusDrawFailed)
                localState.value = localState.value.copy(isDrawing = false, message = message)
            }
        }
    }

    fun drawFromDdl() {
        val current = state.value
        if (current.autonomousStatus.busy || current.replayBusy || current.replaySaving) return
        val returnToLineage = current.tab == AppTab.Lineage
        if (current.refinementBusy) {
            localState.value = localState.value.copy(message = REFINEMENT_IN_PROGRESS(strings()))
            return
        }
        val ddl = current.ddl
        if (!DdlSource.hasBody(ddl)) return
        val declared = ddlLineage(current)
        val runId = beginDrawingRun()
        drawingJob = viewModelScope.launch {
            // A candidate that cannot be kept leaves the declared parent: the
            // drawing is still the author's, and an uncaught failure here
            // would take the app down.
            val lineage = runCatching { withPreviewParent(current, declared) }.getOrElse { error ->
                if (error is CancellationException) throw error
                declared
            }
            localState.value = localState.value.copy(isDrawing = true, message = strings().statusComposingFromDdl)
            runCatching {
                withContext(Dispatchers.IO) {
                    val parentHistoryId = current.selectedHistory?.id?.takeUnless { current.lineageDetached }
                    repository.composeFromDdl(
                        current.prompt, ddl, current.selectedCatalogId, current.selectedCanvasAspect,
                        current.selectedModelId, current.selectedStage2ModelId, lineage = lineage,
                        instructionLang = InstructionLanguages.AUTO, uiLang = current.uiLanguage.code,
                        parentHistoryId = parentHistoryId, executionId = matchingPipelineExecutionId(current),
                        // Imported definitions reach a new work only, never an edit of a saved one.
                        importedPlugins = if (parentHistoryId == null) current.importedPlugins else emptyList(),
                        // A DDL drawn from a work keeps that work's Wild; a new one takes the
                        // switch (web's `targetWild`, +page.svelte:2300).
                        renderWild = current.selectedHistory?.takeUnless { current.lineageDetached }?.drawnWild ?: current.renderWild,
                    )
                }
            }.onSuccess { item ->
                if (!isCurrentDrawingRun(runId)) return@onSuccess
                promptEditedByUser = false
                adoptSavedHistory(item, activeExecution = true, isCurrent = { isCurrentDrawingRun(runId) }) { latest ->
                    latest.copy(
                        prompt = item.originalInput,
                        ddl = item.normalizedDdl.orEmpty(),
                        ddlEditedAfterGeneration = false,
                        confirmDdlOverwrite = false,
                        descriptionForkRequested = false,
                        lineageDetached = false,
                        importedPlugins = emptyList(),
                        importedPluginNames = emptyList(),
                        isDrawing = false,
                        message = strings().statusComposed(item.renderHashShort),
                    )
                }
                if (returnToLineage) refreshLineage()
            }.onFailure { error ->
                if (!isCurrentDrawingRun(runId)) return@onFailure
                if (presentPipelineInteraction(error)) return@onFailure
                val message = if (error is CancellationException) strings().statusStopped else messageFor(error, strings(), strings().statusComposeFailed)
                localState.value = localState.value.copy(isDrawing = false, message = message)
            }
        }
    }

    fun runBatch() {
        val current = state.value
        if (current.isRunning) return
        validateSelectedModels(current)?.let { message ->
            localState.value = localState.value.copy(message = message)
            return
        }
        val lines = current.batchText.lines()
            .mapIndexed { index, line -> index + 1 to line.trim() }
            .filter { it.second.isNotBlank() }
        if (lines.isEmpty()) {
            localState.value = current.copy(message = strings().batchEmpty)
            return
        }
        if (lines.size > MaxBatchItems) {
            localState.value = current.copy(message = strings().batchTooManyItems(MaxBatchItems, lines.size))
            return
        }
        rememberBatchPrompt(current.batchText)
        val snapshot = BatchSnapshot(current.batchText, lines.map { NumberedBatchLine(it.first, it.second) },
            BatchConditions(current.selectedCatalogId, current.selectedCanvasAspect,
                current.selectedModelId, current.selectedStage2ModelId, current.uiLanguage.code, current.renderWild))
        lastBatchSnapshot = snapshot
        lastBatchSavedWork = null
        runBatchSnapshot(snapshot, snapshot.lines, retry = false)
    }

    fun setBatchRetryLimit(value: Int) {
        if (state.value.isRunning) return
        val limit = value.coerceIn(0, 5)
        localState.value = localState.value.copy(batchRetryLimit = limit)
        persistSetting("batch_retry_limit", JSONObject().put("value", limit).toString())
    }

    fun retryFailedBatch() {
        val current = localState.value
        if (state.value.isRunning || !current.batchCanRetry) return
        val snapshot = lastBatchSnapshot ?: return
        val failed = failedBatchLines(snapshot, current.batchFailures)
        if (failed.isNotEmpty()) runBatchSnapshot(snapshot, failed, retry = true)
    }

    private fun runBatchSnapshot(snapshot: BatchSnapshot, requested: List<NumberedBatchLine>, retry: Boolean) {
        val current = localState.value
        val conditions = snapshot.conditions
        val runId = beginDrawingRun()
        drawingJob = viewModelScope.launch {
            val startedAt = System.currentTimeMillis()
            var last: HistoryItemEntity? = if (retry) lastBatchSavedWork else null
            var success = if (retry) current.batchSuccess else 0
            var failures = emptyList<BatchFailure>()
            var pending = requested
            var round = 0
            localState.value = localState.value.copy(
                isDrawing = true,
                batchTotal = snapshot.lines.size,
                batchCurrent = 0,
                batchSuccess = success,
                batchFailures = emptyList(),
                batchActiveLine = null,
                batchActiveDdl = null,
                batchActiveElapsedMs = null,
                batchElapsedMs = 0L,
                batchLatestHashShort = null,
                batchCanRetry = false,
                batchRetryRound = 0,
                message = strings().batchRunning(0, pending.size),
            )
            do {
                failures = emptyList()
                val lines = pending.map { it.number to it.input }
                localState.value = localState.value.copy(batchRetryRound = round, batchFailures = emptyList())
                lines.forEachIndexed { index, (lineNumber, prompt) ->
                    val itemStartedAt = System.currentTimeMillis()
                    localState.value = localState.value.copy(
                        batchCurrent = index + 1,
                        batchActiveLine = lineNumber,
                        batchActiveDdl = null,
                        batchActiveElapsedMs = null,
                        batchElapsedMs = System.currentTimeMillis() - startedAt,
                        message = strings().batchRunning(index + 1, lines.size),
                    )
                    runCatching {
                        // The setting as it is: `auto` goes to the shared pipeline,
                        // which chooses the catalogue there.
                        val catalogId = conditions.catalogId
                        withContext(Dispatchers.IO) {
                            repository.paint(
                                description = prompt,
                                catalogId = catalogId,
                                canvasAspect = conditions.canvasAspect,
                                stage1ModelId = conditions.modelId,
                                stage2ModelId = conditions.stage2ModelId,
                                historyInput = "#$lineNumber $prompt",
                                instructionLang = InstructionLanguages.AUTO,
                                uiLang = conditions.languageCode,
                                // The prose without the line number: the same split
                                // the server keeps between `input` and `source_text`.
                                sourceText = prompt,
                                renderWild = conditions.renderWild,
                            )
                        }
                    }.onSuccess { item ->
                        if (!isCurrentDrawingRun(runId)) return@onSuccess
                        success += 1
                        last = item
                        lastBatchSavedWork = item
                        adoptSavedHistory(item, activeExecution = true, isCurrent = { isCurrentDrawingRun(runId) }) { latest ->
                            latest.copy(
                                // The line itself declared no parent -- every batch line
                                // is a root of its own, as web's does (+page.svelte:3327-3345)
                                // -- but the work now on screen is one, and web lowers
                                // this flag on every saved paint (:2883).
                                lineageDetached = false,
                                ddl = item.normalizedDdl.orEmpty(),
                                ddlEditedAfterGeneration = false,
                                batchSuccess = success,
                                batchFailures = failures,
                                batchActiveDdl = item.normalizedDdl.orEmpty(),
                                batchActiveElapsedMs = System.currentTimeMillis() - itemStartedAt,
                                batchElapsedMs = System.currentTimeMillis() - startedAt,
                                batchLatestHashShort = item.renderHashShort,
                                message = strings().batchRunning(index + 1, lines.size),
                            )
                        }
                    }.onFailure { error ->
                        if (error is CancellationException) throw error
                        if (!isCurrentDrawingRun(runId)) return@onFailure
                        // A line the pipeline stopped is a failed line like any
                        // other, so the rest are still drawn and this one can be
                        // run again (SPEC 2026-10-17). Turning to its stop used
                        // to end the whole batch with no tally.
                        val reason = abandonPipelineInteraction(error) ?: messageFor(error, strings(), strings().statusDrawFailed)
                        // Every failure is kept (at most MaxBatchItems): the tally
                        // counts this list, as web's report keeps each one.
                        failures = failures + BatchFailure(lineNumber, prompt, reason)
                        localState.value = localState.value.copy(
                            batchSuccess = success,
                            batchFailures = failures,
                            batchActiveElapsedMs = System.currentTimeMillis() - itemStartedAt,
                            batchElapsedMs = System.currentTimeMillis() - startedAt,
                            message = strings().batchRunning(index + 1, lines.size),
                        )
                    }
                }
                pending = failedBatchLines(snapshot, failures)
                val again = batchRetryAllowed(failures, round, current.batchRetryLimit, interrupted = !isActive)
                if (again) round += 1
            } while (again && isCurrentDrawingRun(runId))
            if (!isCurrentDrawingRun(runId)) return@launch
            localState.value = localState.value.copy(
                selectedHistory = last,
                lineageDetached = false,
                ddl = last?.normalizedDdl.orEmpty(),
                ddlEditedAfterGeneration = false,
                // The saved prose, not `originalInput` minus a prefix: the prefix
                // is the last line's number, which is not the last success's
                // when the final line failed.
                prompt = last?.let(::sourceTextOf) ?: current.prompt,
                isDrawing = false,
                batchCurrent = 0,
                batchActiveLine = null,
                batchActiveDdl = null,
                batchActiveElapsedMs = null,
                batchElapsedMs = System.currentTimeMillis() - startedAt,
                batchCanRetry = failures.isNotEmpty(),
                message = strings().batchCompleted(success, failures.size, snapshot.lines.size),
            )
        }
    }

    private fun rememberBatchPrompt(prompt: String) {
        val clean = prompt.trim().replace("\r\n", "\n")
        if (clean.isBlank()) return
        val next = (listOf(clean) + localState.value.batchPromptHistory.filterNot { it == clean }).take(10)
        localState.value = localState.value.copy(batchPromptHistory = next)
        persistSetting("batch_prompt_history", JSONObject().put("items", JSONArray(next)).toString())
    }

    fun startDemo() {
        val current = state.value
        if (current.isRunning) return
        validateSelectedModels(current)?.let { message ->
            localState.value = localState.value.copy(message = message)
            return
        }
        val runId = beginDrawingRun()
        drawingJob = viewModelScope.launch {
            localState.value = localState.value.copy(
                isDrawing = true,
                demoGeneratedPrompt = "",
                demoGeneratedDdl = null,
                demoCurrentCatalogId = null,
                demoWaitingSeconds = null,
                demoCurrentElapsedMs = null,
                demoTotalElapsedMs = 0L,
                demoRenderCount = 0,
                message = strings().demoRunning,
            )
            var demoCycles = 0
            try {
                while (isActive && demoCycles < MaxDemoCycles) {
                    demoCycles += 1
                    val cycle = state.value
                    val startedAt = System.currentTimeMillis()
                    localState.value = localState.value.copy(
                        demoGeneratedPrompt = "",
                        demoGeneratedDdl = null,
                        demoWaitingSeconds = null,
                        demoCurrentElapsedMs = null,
                        message = strings().demoGeneratingPrompt,
                    )
                    val prompt = withContext(Dispatchers.IO) {
                        repository.generateDemoPrompt(cycle.demoSeed, cycle.selectedModelId)
                    }
                    if (!isCurrentDrawingRun(runId)) return@launch
                    val catalogId = cycle.selectedCatalogId
                    localState.value = localState.value.copy(
                        demoGeneratedPrompt = prompt,
                        demoGeneratedDdl = null,
                        demoCurrentCatalogId = catalogId,
                        demoWaitingSeconds = null,
                        demoCurrentElapsedMs = null,
                        message = strings().demoDrawing,
                    )
                    runCatching {
                        withContext(Dispatchers.IO) {
                            repository.paint(
                                description = prompt,
                                catalogId = catalogId,
                                canvasAspect = DemoCanvasAspectId,
                                stage1ModelId = cycle.selectedModelId,
                                stage2ModelId = cycle.selectedStage2ModelId,
                                historyInput = "$DemoHistoryInputPrefix$prompt",
                                instructionLang = InstructionLanguages.AUTO,
                                uiLang = cycle.uiLanguage.code,
                                // The prose without the demo marker, for the
                                // same reason the batch line strips its number.
                                sourceText = prompt,
                                renderWild = cycle.renderWild,
                            )
                        }
                    }.onSuccess { item ->
                        if (!isCurrentDrawingRun(runId)) return@onSuccess
                        val elapsed = System.currentTimeMillis() - startedAt
                        adoptSavedHistory(item, activeExecution = true, isCurrent = { isCurrentDrawingRun(runId) }) { latest ->
                            latest.copy(
                                lineageDetached = false,
                                prompt = item.originalInput.removePrefix(DemoHistoryInputPrefix),
                                ddl = item.normalizedDdl.orEmpty(),
                                ddlEditedAfterGeneration = false,
                                demoGeneratedDdl = item.normalizedDdl.orEmpty(),
                                demoCurrentElapsedMs = elapsed,
                                demoTotalElapsedMs = latest.demoTotalElapsedMs + elapsed,
                                demoRenderCount = latest.demoRenderCount + 1,
                                message = strings().demoDrawn(item.renderHashShort),
                            )
                        }
                    }.onFailure { error ->
                        if (error is CancellationException) throw error
                        if (!isCurrentDrawingRun(runId)) return@onFailure
                        // The demo goes on to its next cycle, as it does after
                        // any other failed drawing.
                        val reason = abandonPipelineInteraction(error) ?: messageFor(error, strings(), strings().demoFailed)
                        localState.value = localState.value.copy(
                            demoCurrentElapsedMs = System.currentTimeMillis() - startedAt,
                            message = reason,
                        )
                        delay(1000)
                    }
                    // The interval runs from the cycle's start, so a slow
                    // drawing shortens the wait before the next one.
                    val elapsed = System.currentTimeMillis() - startedAt
                    val waitMs = (state.value.demoIntervalSeconds * 1000L - elapsed).coerceAtLeast(0L)
                    var left = ((waitMs + 999L) / 1000L).toInt()
                    while (left > 0 && isActive) {
                        localState.value = localState.value.copy(demoWaitingSeconds = left, message = strings().demoNextIn(left))
                        delay(1000)
                        left -= 1
                    }
                }
            } finally {
                if (isCurrentDrawingRun(runId)) {
                    val reachedLimit = demoCycles >= MaxDemoCycles
                    localState.value = localState.value.copy(
                        isDrawing = false,
                        demoWaitingSeconds = null,
                        message = if (reachedLimit) strings().demoStoppedAtLimit(MaxDemoCycles) else strings().statusStopped,
                    )
                }
            }
        }
    }

    fun stopDrawing() {
        drawingRunSerial += 1
        drawingJob?.cancel()
        drawingJob = null
        val cancelled = localState.value.pipelineView?.takeIf { !it.terminal }?.also { view ->
            viewModelScope.launch { runCatching { repository.cancelPipeline(view.executionId) } }
        }
        localState.value = localState.value.copy(
            isDrawing = false, demoWaitingSeconds = null, batchCanRetry = false, message = strings().statusStopped,
            // The run is cancelled, so its proposal and its 承認・辞退 can no
            // longer be answered; left on screen they only failed when pressed.
            pipelineView = if (cancelled != null) null else localState.value.pipelineView,
        )
    }

    /** A successful early performance save ends the pre-save parent retention too. */
    private fun descriptionPerformanceSaved(runId: Long) {
        if (isCurrentDrawingRun(runId)) {
            localState.update { it.copy(pendingDescriptionParent = null) }
        }
    }

    // ── 推敲 (SPEC :614, :678) ──────────────────────────────

    /**
     * Opens the refinement on one work.
     *
     * The parent is the work itself, read from the database, and every fixed
     * value a candidate inherits comes from that row -- never from the describe
     * screen (「次回描画の設定ではなく表示中の親作品の実効カタログとキャンバスを継承
     * する」).
     */
    fun openRefinement(item: HistoryItemEntity, subview: RefinementSubview = RefinementSubview.Adjust) {
        if (refinementSaving || localState.value.refinementCandidates.any { it.saveState == RefinementSaveState.Saving }) return
        // 「対象作品変更時は結果を破棄し、進行中の要求を中断する」(SPEC :616, :686,
        // :2143). The running job is cancelled first: a candidate that lands
        // after the target changed belongs to a work that is no longer here.
        refinementJob?.cancel()
        refinementJob = null
        val previous = localState.value.refinementParent
        localState.value = localState.value.copy(
            refinementOpen = true,
            toolChangeOpen = false,
            refinementParent = item,
            refinementSubview = subview,
            // A new target owns its own candidates; the previous work's are gone.
            refinementCandidates = emptyList(),
            refinementPreviewId = null,
            refinementStatus = null,
            refinementBusy = false,
            refinementCanAbort = false,
            // The selections are read against the target's own pair, so a new
            // target starts from an empty one rather than from choices that were
            // legal for the last work.
            modelCompareSelectedModels = if (previous?.id == item.id) localState.value.modelCompareSelectedModels else emptyList(),
            modelCompareFailedModels = emptyMap(),
            refinementWildOverride = null,
            colorArrangementExhausted = false,
            groundCurrentLabel = null,
            tab = AppTab.Lineage,
        )
        // The tab is set here rather than through `setTab`, which is what reads
        // the lineage; closing the refinement would otherwise show an empty
        // lineage, or the one of a work opened before.
        refreshLineage()
        colorArrangementCursors.remove(item.id)
        if (subview == RefinementSubview.ColorArrangement || subview == RefinementSubview.Ground ||
            (subview == RefinementSubview.Adjust && localState.value.refinementElement == RefinementElement.Color)) {
            generateRefinementCandidates()
        }
    }

    fun setRefinementSubview(subview: RefinementSubview) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(
            refinementSubview = subview,
            refinementStatus = null,
            refinementCandidates = emptyList(),
            refinementPreviewId = null,
            modelCompareFailedModels = emptyMap(),
            colorArrangementExhausted = false,
        )
        localState.value.refinementParent?.id?.let(colorArrangementCursors::remove)
        if (subview == RefinementSubview.ColorArrangement || subview == RefinementSubview.Ground ||
            (subview == RefinementSubview.Adjust && localState.value.refinementElement == RefinementElement.Color)) {
            generateRefinementCandidates()
        }
    }

    /** Up to four models to compare; each draws both stages (2026-09-30, the author). */
    fun toggleModelCompareSelection(modelId: String) {
        val current = localState.value
        if (current.refinementBusy) return
        val parent = current.refinementParent
        if (ComparisonPlanner.isModelChoiceBlocked(
                model = modelId,
                targetStage1Model = parent?.stage1Model.orEmpty(),
                targetStage2Model = parent?.stage2Model.orEmpty(),
            )
        ) {
            localState.value = current.copy(refinementStatus = MODEL_CHOICE_BLOCKED(strings()))
            return
        }
        val selected = current.modelCompareSelectedModels
        val next = when {
            modelId in selected -> selected - modelId
            selected.size >= MAX_COMPARE_SELECTION -> selected
            else -> selected + modelId
        }
        localState.value = current.copy(modelCompareSelectedModels = next, refinementStatus = null)
    }

    fun closeRefinement() {
        if (refinementSaving || localState.value.refinementCandidates.any { it.saveState == RefinementSaveState.Saving }) return
        refinementJob?.cancel()
        refinementJob = null
        localState.value = localState.value.copy(
            refinementOpen = false,
            toolChangeOpen = false,
            refinementParent = null,
            refinementCandidates = emptyList(),
            refinementPreviewId = null,
            refinementBusy = false,
            refinementCanAbort = false,
            refinementStatus = null,
        )
        // A child saved one by one is not in the graph read when the refinement opened.
        if (localState.value.tab == AppTab.Lineage) refreshLineage()
    }

    fun openToolChange(item: HistoryItemEntity) {
        if (state.value.isRunning || item.trashed) return
        enterWorkContext(item)
        closeRefinement()
        toolChangeNextNumber = 1
        localState.value = localState.value.copy(
            toolChangeOpen = true, toolChangeMode = app.inku.mobile.data.refinement.ToolChangeMode.Uniform,
            refinementParent = item, refinementCandidates = emptyList(),
        )
    }

    fun setToolChangeMode(mode: app.inku.mobile.data.refinement.ToolChangeMode) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(toolChangeMode = mode)
    }

    fun closeToolChange(discard: Boolean = false) {
        val current = localState.value
        if (current.refinementBusy || current.refinementCandidates.any { it.saveState == RefinementSaveState.Saving }) return
        if (!discard && current.refinementCandidates.any { it.saveState == RefinementSaveState.Unsaved }) {
            localState.value = current.copy(refinementStatus = strings().toolChangeSaveOrDiscard)
            return
        }
        closeRefinement()
    }

    fun discardToolChangeCandidate(id: String) {
        val current = localState.value
        if (current.refinementBusy) return
        localState.value = current.copy(
            refinementCandidates = current.refinementCandidates.filterNot { it.id == id && it.saveState == RefinementSaveState.Unsaved },
            refinementPreviewId = current.refinementPreviewId?.takeUnless { it == id },
        )
    }

    /** Replace the displayed options with four in the chosen mode, only on request. */
    fun generateToolChangeCandidates() {
        val current = localState.value
        if (!current.toolChangeOpen || current.refinementBusy || current.isDrawing ||
            current.refinementCandidates.any { it.saveState == RefinementSaveState.Saving }) return
        val item = current.refinementParent ?: return
        val parent = RefinementParent.of(item, sourceTextOf(item))
        localState.value = current.copy(
            refinementBusy = true, refinementStatus = null,
            refinementCandidates = emptyList(), refinementPreviewId = null,
            refinementPlannedCount = 4,
        )
        val run = viewModelScope.launch {
            runCatching {
                val options = withContext(Dispatchers.IO) { repository.toolChangeOptions(parent, current.toolChangeMode) }
                for (option in options) {
                    val started = System.currentTimeMillis()
                    val rendered = withContext(Dispatchers.IO) { repository.renderToolChangeCandidate(parent, option) } ?: continue
                    if (!localState.value.toolChangeOpen || localState.value.refinementParent?.id != item.id) return@launch
                    val (plan, result) = rendered
                    val number = toolChangeNextNumber++
                    val label = if (option.mode == app.inku.mobile.data.refinement.ToolChangeMode.Uniform) {
                        option.source.tools.first { it.value == option.tools.values.first() }.label(current.uiLanguage.code == "ja")
                    } else strings().toolChangePerSentenceCandidate(number)
                    val candidate = RefinementCandidate(
                        id = "tool-$number-${result.renderHash.takeLast(8)}", label = label, plan = plan,
                        displaySvg = result.displaySvg, scoreJson = result.scoreJson,
                        normalizedDdl = result.normalizedDdl.orEmpty(), renderHash = result.renderHash,
                        renderHashShort = result.renderHashShort, renderMetadataJson = result.renderMetadataJson,
                        pipelineResult = result, elapsedMs = System.currentTimeMillis() - started,
                        stage1Model = parent.stage1Model, stage2Model = parent.stage2Model,
                        instructionLangRequested = result.instructionLangRequested,
                        instructionLangResolved = result.instructionLangResolved,
                    )
                    localState.value = localState.value.copy(refinementCandidates = localState.value.refinementCandidates + candidate)
                }
                if (localState.value.refinementCandidates.isEmpty()) {
                    localState.value = localState.value.copy(refinementStatus =
                        if (options.isEmpty()) strings().toolChangeNone else strings().refinementFailed)
                }
            }.onFailure { error ->
                if (error is CancellationException) throw error
                localState.value = localState.value.copy(refinementStatus = messageFor(error, strings(), strings().refinementFailed))
            }
            localState.value = localState.value.copy(refinementBusy = false)
        }
        refinementJob = run
    }

    /** The radio. One value replaces the previous one; two are not spellable. */
    fun setRefinementElement(element: RefinementElement) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(refinementElement = element, refinementStatus = null)
        // 「推敲要素の選択は前回値をブラウザに記憶する」.
        persistSetting(SETTING_KEY_REFINEMENT_ELEMENT, JSONObject().put("value", element.id).toString())
        if (element == RefinementElement.Color && localState.value.refinementOpen) generateRefinementCandidates()
    }

    fun setRefinementLayoutMode(mode: RecomposeMode) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(refinementLayoutMode = mode, refinementStatus = null)
    }

    /** 1 案 or 4 案 for layout; colour compares all other catalogues. */
    fun setRefinementCount(count: Int) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(refinementCount = count.coerceIn(1, 4), refinementStatus = null)
    }

    /** One candidate's orders plus the two strings the grid shows it under. */
    private data class CandidateJob(
        val id: String, val label: String, val plan: RefinementPlan,
        val render: (suspend () -> Pair<RefinementPlan, PaintResult>)? = null,
        val colorArrangement: Boolean = false,
        val nextColorCursor: java.math.BigInteger? = null,
    )

    /** A refusal the author has to read, not a failure: it carries the sentence. */
    // A refusal used to be its own exception carrying a finished sentence. It is
    // an InkuFailure now for the same reason every other message became one: the
    // sentence reaches the reader, so the language is chosen where it is shown.

    /**
     * What to draw, for whichever sub-view is showing.
     *
     * Both lists are built here and nowhere else, so the drawing loop below has
     * no idea which sub-view it is running -- that is what stops the model
     * comparison from growing a second copy of it (SPEC `:688`).
     */
    private suspend fun candidateJobs(current: InkuUiState, parent: RefinementParent): List<CandidateJob> {
        return when (current.refinementSubview) {
            RefinementSubview.Adjust -> adjustJobs(current, parent)
            RefinementSubview.Model -> modelJobs(current, parent)
            RefinementSubview.ColorArrangement -> {
                if (colorArrangementCursors.containsKey(parent.historyId) && colorArrangementCursors[parent.historyId] == null) return emptyList()
                val page = withContext(Dispatchers.IO) {
                    repository.colorArrangementPage(parent, colorArrangementCursors[parent.historyId] ?: java.math.BigInteger.ZERO)
                }
                if (page.entries.isEmpty()) {
                    colorArrangementCursors[parent.historyId] = null
                    localState.value = localState.value.copy(colorArrangementExhausted = true)
                }
                page.entries.map { index ->
                    val next = index + java.math.BigInteger.ONE
                    CandidateJob("arrangement-$index", "${strings().colorArrangementEditAction} $next",
                        RefinementPlanner.plan(RefinementElement.Layout, parent),
                        render = { repository.renderColorArrangementCandidate(parent, index, current.refinementWildOverride) },
                        colorArrangement = true, nextColorCursor = next.takeIf { it < page.total })
                }
            }
            RefinementSubview.Ground -> {
                val plan = withContext(Dispatchers.IO) { repository.groundVariantPlan(parent) }
                localState.value = localState.value.copy(groundCurrentLabel =
                    (if (current.uiLanguage == UiLanguage.Ja) plan.currentLabelJa else plan.currentLabelEn) ?: plan.current)
                plan.entries.map { entry ->
                    CandidateJob("ground-${entry.material}", if (current.uiLanguage == UiLanguage.Ja) entry.labelJa else entry.labelEn,
                        RefinementPlanner.plan(RefinementElement.Layout, parent),
                        render = { repository.renderGroundVariantCandidate(parent, entry.material, current.refinementWildOverride) })
                }
            }
        }
    }

    private fun adjustJobs(current: InkuUiState, parent: RefinementParent): List<CandidateJob> {
        val element = current.refinementElement
        RefinementPlanner.requireSource(element, parent)
        val count = current.refinementCount
        // The colour change draws every other catalogue, one candidate each and
        // named after it, whatever the count says (web's `planRefinementCandidates`).
        val catalogIds = if (element == RefinementElement.Color) {
            RefinementPlanner.catalogCandidateIds(parent.catalogId, ColorCatalogs.all.map { it.id })
        } else {
            emptyList()
        }
        val planned = if (element == RefinementElement.Color) catalogIds.size else count
        return (0 until planned).map { index ->
            CandidateJob(
                id = "${element.id}-$index",
                label = catalogIds.getOrNull(index)?.let { id -> ColorCatalogs.currentDisplayCatalog(id)?.name ?: id }
                    ?: "${strings().refinementElementLabel(element.id)} ${index + 1}",
                plan = RefinementPlanner.plan(
                    element = element,
                    parent = parent,
                    newCatalogId = catalogIds.getOrNull(index),
                    recomposeMode = current.refinementLayoutMode,
                ).copy(renderWildOverride = current.refinementWildOverride),
            )
        }
    }

    /**
     * 「比較対象はユーザーが明示的に選び、未選択モデルをfallback実行しない」(SPEC `:616`):
     * an empty selection draws nothing and says so.
     */
    private fun modelJobs(current: InkuUiState, parent: RefinementParent): List<CandidateJob> {
        RefinementPlanner.requireSource(null, parent)
        val chosen = current.modelCompareSelectedModels
            .take(MAX_COMPARE_SELECTION)
            .filterNot {
                ComparisonPlanner.isModelChoiceBlocked(
                    model = it,
                    targetStage1Model = current.refinementParent?.stage1Model.orEmpty(),
                    targetStage2Model = current.refinementParent?.stage2Model.orEmpty(),
                )
            }
            .filterNot { model -> current.refinementCandidates.any { it.plan.stage1Model == model } }
        if (chosen.isEmpty()) {
            if (current.modelCompareSelectedModels.any { model -> current.refinementCandidates.any { it.plan.stage1Model == model } }) return emptyList()
            throw InkuFailure(MODEL_SELECT_PROMPT)
        }
        return chosen.map { model ->
            val plan = ComparisonPlanner.modelPlan(model, parent).copy(renderWildOverride = current.refinementWildOverride)
            CandidateJob(
                id = "$MODEL_COMPARISON_MODE:$model:$model",
                label = model,
                plan = plan,
            )
        }
    }

    /**
     * Draws the candidates.
     *
     * 「候補生成中は他の生成・描画操作を禁止し」: the guard is at the top of this and
     * at the top of every other generating entry point, so neither can start
     * while the other runs. The candidates are drawn one after another -- web
     * fans out to the number of render slots the server reports, and there is no
     * server here to report one.
     */
    fun generateRefinementCandidates() {
        val current = localState.value
        if (current.refinementBusy || current.isDrawing) return
        val parentItem = current.refinementParent ?: return
        val parent = RefinementParent.of(parentItem, sourceTextOf(parentItem))
        if (current.refinementCandidates.any { it.saveState == RefinementSaveState.Saving }) return
        refinementJob?.cancel()
        localState.value = current.copy(
            refinementBusy = true,
            refinementCanAbort = false,
            refinementStatus = null,
        )
        val run = viewModelScope.launch {
            // The stop appears three seconds in, not at once: a candidate that
            // is already done needs no stop button.
            val abortTimer = launch {
                delay(3000)
                if (localState.value.refinementBusy) {
                    localState.value = localState.value.copy(refinementCanAbort = true)
                }
            }
            runCatching {
                // A four-layout round first preserves the chosen options from
                // the preceding round. A failed save leaves that grid intact.
                if (current.refinementSubview == RefinementSubview.Adjust &&
                    current.refinementElement == RefinementElement.Layout && current.refinementCount == 4) {
                    saveSelectedCandidatesNow(parentItem)
                }
                val jobs = candidateJobs(current, parent)
                val append = current.refinementSubview == RefinementSubview.Model ||
                    current.refinementSubview == RefinementSubview.ColorArrangement
                localState.value = localState.value.copy(
                    refinementCandidates = if (append) localState.value.refinementCandidates else emptyList(),
                    refinementPreviewId = if (append) localState.value.refinementPreviewId else null,
                    refinementPlannedCount = jobs.size,
                    refinementRoundStartCount = if (append) localState.value.refinementCandidates.size else 0,
                )
                jobs.forEach { job ->
                    try {
                        val started = System.currentTimeMillis()
                        val (plan, result) = withContext(Dispatchers.IO) {
                            job.render?.invoke() ?: (job.plan to repository.renderRefinementCandidate(parent, job.plan))
                        }
                        if (localState.value.refinementParent?.id != parentItem.id) return@launch
                        val candidate = RefinementCandidate(
                            id = "${job.id}-${result.renderHash.takeLast(8)}",
                            label = job.label,
                            plan = plan,
                            displaySvg = result.displaySvg,
                            scoreJson = result.scoreJson,
                            normalizedDdl = result.normalizedDdl.orEmpty(),
                            renderHash = result.renderHash,
                            renderHashShort = result.renderHashShort,
                            renderMetadataJson = result.renderMetadataJson,
                            pipelineResult = result,
                            elapsedMs = System.currentTimeMillis() - started,
                            stage1Model = plan.stage1Model ?: parent.stage1Model,
                            stage2Model = plan.stage2Model ?: parent.stage2Model,
                            instructionLangRequested = result.instructionLangRequested,
                            instructionLangResolved = result.instructionLangResolved,
                        )
                        localState.value = localState.value.copy(
                            refinementCandidates = localState.value.refinementCandidates + candidate,
                            modelCompareFailedModels = localState.value.modelCompareFailedModels - job.plan.stage1Model.orEmpty(),
                        )
                        if (job.colorArrangement) {
                            colorArrangementCursors[parent.historyId] = job.nextColorCursor
                            localState.value = localState.value.copy(colorArrangementExhausted = job.nextColorCursor == null)
                        }
                    } catch (error: Exception) {
                        if (error is CancellationException) throw error
                        if (current.refinementSubview != RefinementSubview.Model) throw error
                        if (error is PipelineInteractionRequired) withContext(NonCancellable + Dispatchers.IO) {
                            runCatching { repository.cancelPipeline(error.view.executionId) }
                        }
                        localState.value = localState.value.copy(modelCompareFailedModels =
                            localState.value.modelCompareFailedModels +
                                (job.plan.stage1Model.orEmpty() to messageFor(error, strings(), strings().modelFailed)))
                    }
                }
            }.onFailure { error ->
                if (error is CancellationException) throw error
                // A candidate that stops for the author's attention is not a
                // drawing to resume. web keeps the failure in its grid
                // (`failGrid`) and moves nowhere; here the candidate's execution
                // used to be presented as the drawing, closing the refinement,
                // and it came back at every start as the drawing in progress.
                // It is cancelled now, and the failure stays in the panel.
                if (error is PipelineInteractionRequired) {
                    withContext(NonCancellable + Dispatchers.IO) {
                        runCatching { repository.cancelPipeline(error.view.executionId) }
                    }
                    localState.value = localState.value.copy(refinementStatus = strings().refinementFailed)
                } else {
                    localState.value = localState.value.copy(refinementStatus = messageFor(error, strings(), strings().refinementFailed))
                }
            }
            abortTimer.cancel()
            localState.value = localState.value.copy(refinementBusy = false, refinementCanAbort = false)
        }
        refinementJob = run
        run.invokeOnCompletion { cause ->
            // Only the run that still owns the refinement reports a stop. A run
            // cancelled because the target changed or the refinement closed
            // ends later -- a candidate being drawn is not interrupted -- and
            // would otherwise mark the next target's run as stopped and idle
            // while that run is still drawing, reopening every generate button.
            if (cause is CancellationException && refinementJob === run) {
                localState.value = localState.value.copy(
                    refinementBusy = false,
                    refinementCanAbort = false,
                    refinementStatus = strings().statusStopped,
                )
            }
        }
    }

    /** The stop button. Cancels the work in flight, which is what web's abort does. */
    fun abortRefinementCandidates() {
        if (refinementSaving) return
        refinementJob?.cancel()
    }

    /**
     * Saves one candidate into the ordinary history.
     *
     * 保存済みは二度保存できない: a candidate that is not [RefinementSaveState.Unsaved]
     * is refused here rather than in the screen, so a second tap writes no row
     * whichever way it arrives.
     */
    fun saveRefinementCandidate(candidateId: String) {
        val current = localState.value
        val candidate = current.refinementCandidates.firstOrNull { it.id == candidateId } ?: return
        if (candidate.saveState != RefinementSaveState.Unsaved) return
        if (current.refinementBusy) return
        val parentItem = current.refinementParent ?: return
        updateCandidate(candidateId) { it.copy(saveState = RefinementSaveState.Saving) }
        refinementSaving = true
        localState.value = localState.value.copy(refinementBusy = true)
        refinementJob = viewModelScope.launch {
            try {
                val item = withContext(NonCancellable + Dispatchers.IO) {
                    saveCandidateRow(candidate, parentItem, historyVisibility = null)
                }
                updateCandidate(candidateId) {
                    it.copy(
                        saveState = RefinementSaveState.Saved,
                        savedHistoryId = item.id,
                        savedNodeId = item.lineageNodeId,
                    )
                }
                localState.value = localState.value.copy(refinementStatus = strings().statusSaved(item.renderHashShort))
            } catch (error: Exception) {
                updateCandidate(candidateId) { it.copy(saveState = RefinementSaveState.Unsaved) }
                if (error is CancellationException) throw error
                localState.value = localState.value.copy(refinementStatus = messageFor(error, strings(), strings().statusSaveFailed))
            } finally {
                refinementSaving = false
                localState.value = localState.value.copy(refinementBusy = false)
            }
        }
    }

    fun setRefinementWildOverride(value: Boolean?) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(refinementWildOverride = value)
    }

    fun toggleRefinementCandidateSelection(id: String) {
        if (localState.value.refinementBusy) return
        updateCandidate(id) { if (it.saveState == RefinementSaveState.Unsaved) it.copy(selected = !it.selected) else it }
    }

    fun saveSelectedRefinementCandidates() {
        val current = localState.value
        if (current.refinementBusy || current.refinementCandidates.any { it.saveState == RefinementSaveState.Saving }) return
        val parent = current.refinementParent ?: return
        refinementSaving = true
        localState.value = current.copy(refinementBusy = true)
        refinementJob = viewModelScope.launch {
            try {
                saveSelectedCandidatesNow(parent)
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                localState.value = localState.value.copy(refinementStatus = messageFor(error, strings(), strings().statusSaveFailed))
            } finally {
                refinementSaving = false
                localState.value = localState.value.copy(refinementBusy = false)
            }
        }
    }

    private suspend fun saveSelectedCandidatesNow(parent: HistoryItemEntity) {
        val selected = localState.value.refinementCandidates.filter { it.selected && it.saveState == RefinementSaveState.Unsaved }
        refinementSaving = true
        try {
            for (candidate in selected) {
                updateCandidate(candidate.id) { it.copy(saveState = RefinementSaveState.Saving) }
                try {
                    val saved = withContext(NonCancellable + Dispatchers.IO) { saveCandidateRow(candidate, parent, null) }
                    updateCandidate(candidate.id) { it.copy(saveState = RefinementSaveState.Saved, selected = false,
                        savedHistoryId = saved.id, savedNodeId = saved.lineageNodeId) }
                } catch (error: Exception) {
                    updateCandidate(candidate.id) { it.copy(saveState = RefinementSaveState.Unsaved) }
                    throw error
                }
            }
            if (selected.isNotEmpty()) refreshLineage()
        } finally { refinementSaving = false }
    }

    fun openAutonomousRefinement(item: HistoryItemEntity) {
        if (state.value.isRunning || item.trashed) return
        enterWorkContext(item)
        closeRefinement()
        localState.value = localState.value.copy(
            autonomousOpen = true, autonomousParent = item,
            autonomousSettings = localState.value.autonomousSettings.copy(wildOverride = null),
            autonomousStatus = AutonomousRefinementStatus(),
        )
    }

    fun updateAutonomousRefinementSettings(settings: AutonomousRefinementSettings) {
        if (localState.value.autonomousStatus.busy) return
        localState.value = localState.value.copy(autonomousSettings = settings.copy(
            generations = settings.generations.coerceIn(1, 10), direction = settings.direction.take(160)))
    }

    fun closeAutonomousRefinement() {
        if (localState.value.autonomousStatus.busy) return
        localState.value = localState.value.copy(autonomousOpen = false, autonomousParent = null)
    }

    fun stopAutonomousRefinement() {
        autonomousJob?.cancel()
    }

    fun startAutonomousRefinement() {
        val current = localState.value
        if (state.value.isRunning || !current.autonomousOpen) return
        val original = current.autonomousParent ?: return
        val settings = current.autonomousSettings
        if (settings.allowedKinds.isEmpty() || !DdlSource.hasBody(original.normalizedDdl) ||
            (settings.mode == AutonomousRefinementMode.Vision &&
                settings.modelId !in autonomousVisionModelIds(state.value))) {
            localState.value = current.copy(autonomousStatus = AutonomousRefinementStatus(error = strings().refinementNoneToGenerate))
            return
        }
        localState.value = current.copy(autonomousStatus = AutonomousRefinementStatus(busy = true, total = settings.generations))
        autonomousJob = viewModelScope.launch {
            var item = original
            var advice: app.inku.mobile.llm.RefinementVisionAdvice? = null
            suspend fun observe() {
                val png = withContext(Dispatchers.IO) {
                    app.inku.mobile.llm.RefinementVisionImage.fromSvg(item.displaySvg)
                }
                advice = withContext(Dispatchers.IO) { repository.refineVisionAdvice(app.inku.mobile.llm.RefinementVisionRequest(
                    modelId = settings.modelId, instruction = sourceTextOf(item), direction = settings.direction,
                    enabledKinds = settings.allowedKinds, languageCode = current.uiLanguage.code, imagePng = png)) }
                currentCoroutineContext().ensureActive()
                localState.value = localState.value.copy(autonomousStatus = localState.value.autonomousStatus.copy(
                    observation = advice?.observation, nextDirection = advice?.nextDirection))
            }
            try {
                if (settings.mode == AutonomousRefinementMode.Vision) observe()
                repeat(settings.generations) { index ->
                    currentCoroutineContext().ensureActive()
                    val parent = RefinementParent.of(item, sourceTextOf(item))
                    val kind = advice?.suggestedKind?.takeIf { it in settings.allowedKinds } ?: settings.allowedKinds.random()
                    val element = if (kind == "catalog_change") RefinementElement.Color else RefinementElement.Layout
                    val catalog = if (element == RefinementElement.Color)
                        RefinementPlanner.catalogCandidateIds(parent.catalogId, ColorCatalogs.all.map { it.id }).random() else null
                    val base = RefinementPlanner.plan(element, parent, catalog, RecomposeMode.Principled)
                    // Both modes follow the current parent's DDL. Advice selects
                    // an allowed intervention and is metadata, never new prose.
                    val plan = base.copy(
                        route = app.inku.mobile.data.refinement.RefinementRoute.ComposeFromDdl,
                        stage1Model = settings.modelId.takeIf { settings.mode == AutonomousRefinementMode.Vision },
                        stage2Model = settings.modelId.takeIf { settings.mode == AutonomousRefinementMode.Vision },
                        renderWildOverride = settings.wildOverride,
                        derivationMetadata = base.derivationMetadata + mapOf("autonomous_refine_mode" to settings.mode.name.lowercase()) +
                            (advice?.let { mapOf("vision_model" to it.model, "vision_observation" to it.observation,
                                "vision_next_direction" to it.nextDirection) } ?: emptyMap()),
                    )
                    localState.value = localState.value.copy(autonomousStatus = localState.value.autonomousStatus.copy(
                        step = index + 1, message = strings().refinementElementLabel(element.id)))
                    val started = System.currentTimeMillis()
                    val result = withContext(Dispatchers.IO) { repository.renderRefinementCandidate(parent, plan) }
                    currentCoroutineContext().ensureActive()
                    item = withContext(Dispatchers.IO) {
                        repository.saveRefinementCandidate(result, plan, item.lineageNodeId,
                            System.currentTimeMillis() - started,
                            historyVisibility = if (index == settings.generations - 1) "normal" else "lineage_only",
                            stage1ModelId = plan.stage1Model ?: parent.stage1Model,
                            stage2ModelId = plan.stage2Model ?: parent.stage2Model, sourceText = parent.description)
                    }
                    refreshLineage()
                    if (settings.mode == AutonomousRefinementMode.Vision && index < settings.generations - 1) observe()
                }
                localState.value = localState.value.copy(autonomousStatus = localState.value.autonomousStatus.copy(
                    message = strings().statusSaved(item.renderHashShort)))
            } catch (error: Exception) {
                if (error is PipelineInteractionRequired) withContext(NonCancellable + Dispatchers.IO) {
                    runCatching { repository.cancelPipeline(error.view.executionId) }
                }
                localState.value = localState.value.copy(autonomousStatus = localState.value.autonomousStatus.copy(
                    error = if (error is CancellationException) strings().statusStopped else messageFor(error, strings(), strings().refinementFailed)))
            } finally {
                localState.value = localState.value.copy(autonomousStatus = localState.value.autonomousStatus.copy(busy = false))
                refreshLineage()
            }
        }
    }

    /** Puts a candidate on the canvas without saving it. */
    fun previewRefinementCandidate(candidateId: String) {
        val current = localState.value
        val candidate = current.refinementCandidates.firstOrNull { it.id == candidateId } ?: return
        localState.value = current.copy(refinementPreviewId = candidate.id)
    }

    private fun updateCandidate(id: String, transform: (RefinementCandidate) -> RefinementCandidate) {
        localState.value = localState.value.copy(
            refinementCandidates = localState.value.refinementCandidates.map {
                if (it.id == id) transform(it) else it
            },
        )
    }

    private suspend fun saveCandidateRow(
        candidate: RefinementCandidate,
        parentItem: HistoryItemEntity,
        historyVisibility: String?,
    ): HistoryItemEntity {
        candidate.plan.toolChange?.let { option ->
            return repository.saveToolChangeCandidate(parentItem, option, candidate.elapsedMs, historyVisibility)
        }
        return repository.saveRefinementCandidate(
        result = candidate.pipelineResult ?: PaintResult(
            originalInput = sourceTextOf(parentItem),
            normalizedDdl = candidate.normalizedDdl,
            scoreJson = candidate.scoreJson,
            displaySvg = candidate.displaySvg,
            renderMetadataJson = candidate.renderMetadataJson,
            renderHash = candidate.renderHash,
            renderHashShort = candidate.renderHashShort,
            renderSeed = candidate.plan.seeds.renderSeed ?: renderSeedOf(candidate.renderMetadataJson),
            compositionSeed = candidate.plan.seeds.compositionSeed,
            instructionLangRequested = candidate.instructionLangRequested,
            instructionLangResolved = candidate.instructionLangResolved,
        ),
        plan = candidate.plan,
        parentNodeId = parentItem.lineageNodeId,
        elapsedMs = candidate.elapsedMs,
        historyVisibility = historyVisibility,
        // What drew this candidate, which is the parent's pair for a refinement
        // and the compared pair for a model comparison.
        stage1ModelId = candidate.stage1Model,
        stage2ModelId = candidate.stage2Model,
        sourceText = sourceTextOf(parentItem),
    )
    }

    /** The seed the drawing was performed with, when the plan left it to be drawn. */
    private fun renderSeedOf(renderMetadataJson: String): Long? = runCatching {
        val metadata = JSONObject(renderMetadataJson)
        if (metadata.isNull("render_seed")) null else metadata.getLong("render_seed")
    }.getOrNull()

    /**
     * Makes the work on screen into something the next save can hang off.
     *
     * A port of web's `ensureLineageParentId` (+page.svelte:4810). SPEC `:2105`:
     * an unsaved candidate the author drew on from is recorded as a
     * `lineage_only` node, so the branch keeps the step that was actually taken
     * instead of showing the new work hanging straight off its grandparent.
     */
    private suspend fun materializePreviewNode(current: InkuUiState): String? {
        val previewId = current.refinementPreviewId ?: return null
        val candidate = current.refinementCandidates.firstOrNull { it.id == previewId } ?: return null
        // Already in the database, either as an ordinary save or as an earlier
        // materialisation. Saving it twice would fork the branch.
        candidate.savedNodeId?.let { return it }
        val parentItem = current.refinementParent ?: return null
        val saved = withContext(Dispatchers.IO) {
            saveCandidateRow(candidate, parentItem, historyVisibility = "lineage_only")
        }
        updateCandidate(candidate.id) {
            it.copy(savedHistoryId = saved.id, savedNodeId = saved.lineageNodeId)
        }
        return saved.lineageNodeId
    }

    /**
     * The parent a save should really name.
     *
     * When the work on screen is an unsaved candidate, the next drawing comes
     * from *it*, not from the work it was refined out of; the declaration built
     * from `selectedHistory` names the grandparent, so the node is materialised
     * and swapped in here. A detached lineage keeps its empty declaration: the
     * author asked for a new root.
     */
    private suspend fun withPreviewParent(current: InkuUiState, declaration: LineageDeclaration): LineageDeclaration {
        if (current.refinementPreviewId == null) return declaration
        // Only from the work the candidate was refined out of, while its
        // refinement is still open. The mark outlives a move to another tab, and
        // without this a drawing from a different work hung off this candidate.
        if (!current.refinementOpen) return declaration
        val refinedFrom = current.refinementParent?.lineageNodeId ?: return declaration
        if (declaration.parentNodeId != refinedFrom) return declaration
        if (declaration.parentNodeId.isNullOrEmpty()) return declaration
        val nodeId = materializePreviewNode(current) ?: return declaration
        return declaration.copy(parentNodeId = nodeId)
    }

    fun acceptModelLicense() {
        acceptModelLicense(localState.value.selectedModelId)
    }

    fun acceptModelLicense(modelId: String) {
        viewModelScope.launch {
            runCatching {
                repository.acceptModelLicense(modelId)
            }.onFailure { error ->
                localState.value = localState.value.copy(message = messageFor(error, strings(), strings().licenseUpdateFailed))
            }
        }
    }

    fun refreshModelCatalog() {
        viewModelScope.launch {
            runCatching {
                repository.ensureDefaultModelAssets()
            }.onSuccess {
                localState.value = localState.value.copy(message = strings().modelCatalogRefreshed)
            }.onFailure { error ->
                localState.value = localState.value.copy(message = messageFor(error, strings(), strings().modelListFetchFailed))
            }
        }
    }

    fun fetchProviderModels(providerId: String) {
        if (localState.value.providerModelFetchStates[providerId]?.loading == true) return
        fun setFetchState(next: ProviderModelFetchState) {
            val current = localState.value
            localState.value = current.copy(
                providerModelFetchStates = current.providerModelFetchStates + (providerId to next),
            )
        }
        setFetchState(ProviderModelFetchState(strings().modelListFetching(providerId), loading = true))
        viewModelScope.launch {
            runCatching {
                repository.fetchProviderModels(providerId)
            }.onSuccess { models ->
                val gemma31b = models.firstOrNull { it.equals("google/gemma-4-31b-it", ignoreCase = true) }
                val suffix = if (providerId == "nvidia" && gemma31b != null) strings().modelListNvidiaSuffix else ""
                setFetchState(ProviderModelFetchState(strings().modelListFetched(models.size, suffix)))
            }.onFailure { error ->
                val message = if (error is ModelProviderHttpException && error.statusCode in setOf(401, 403)) {
                    strings().modelListAccessDenied(error.statusCode)
                } else {
                    messageFor(error, strings(), strings().modelListFetchFailed)
                }
                setFetchState(ProviderModelFetchState(message, failed = true))
            }
        }
    }

    fun checkModelAccess(providerId: String, modelId: String) {
        if (localState.value.providerModelFetchStates[providerId]?.loading == true) return
        fun report(message: String, loading: Boolean = false, failed: Boolean = false) {
            localState.value = localState.value.copy(providerModelFetchStates = localState.value.providerModelFetchStates +
                (providerId to ProviderModelFetchState(message, loading = loading, failed = failed)))
        }
        report(strings().modelAccessChecking, loading = true)
        viewModelScope.launch {
            runCatching { repository.checkModelAccess(providerId, modelId) }
                .onSuccess { report(when (it) { true -> strings().modelAccessAvailable; false -> strings().modelAccessUnavailable; null -> strings().modelAccessUnknown }) }
                .onFailure { report(messageFor(it, strings(), strings().modelAccessUnknown), failed = true) }
        }
    }

    fun saveProviderSetting(
        providerId: String,
        displayName: String,
        kind: String,
        baseUrl: String,
        apiKey: String,
        publishedModelsText: String,
        // Told whether the save went through: null when it did, otherwise the
        // reason, so the screen that asked can stay open and say why.
        onResult: (String?) -> Unit,
    ) {
        viewModelScope.launch {
            runCatching {
                repository.saveProviderSetting(
                    providerId = providerId,
                    displayName = displayName,
                    kind = kind,
                    baseUrl = baseUrl,
                    apiKey = apiKey,
                    publishedModels = publishedModelsText.lines().map { it.trim() }.filter { it.isNotBlank() },
                )
            }.onSuccess {
                localState.value = localState.value.copy(message = strings().modelSettingsSaved)
                onResult(null)
            }.onFailure { error ->
                val message = messageFor(error, strings(), strings().modelSettingsSaveFailed)
                localState.value = localState.value.copy(message = message)
                onResult(message)
            }
        }
    }

    fun clearProviderApiKey(providerId: String) {
        viewModelScope.launch {
            runCatching {
                repository.clearProviderApiKey(providerId)
            }.onSuccess {
                localState.value = localState.value.copy(message = strings().apiKeyDeleted)
            }.onFailure { error ->
                localState.value = localState.value.copy(message = messageFor(error, strings(), strings().apiKeyDeleteFailed))
            }
        }
    }

    fun deleteProvider(providerId: String) {
        viewModelScope.launch {
            runCatching {
                repository.deleteProvider(providerId)
            }.onSuccess {
                localState.value = localState.value.copy(message = strings().serviceDeleted)
            }.onFailure { error ->
                localState.value = localState.value.copy(message = messageFor(error, strings(), strings().serviceDeleteFailed))
            }
        }
    }

    fun downloadDefaultModel() {
        downloadModel(state.value.selectedModelId, force = false)
    }

    fun downloadModel(modelId: String, force: Boolean = false) {
        val current = state.value
        val selectedModel = current.modelAssets.firstOrNull { it.modelId == modelId }
        if (selectedModel?.licenseAcceptedAt == null) {
            localState.value = localState.value.copy(message = strings().modelLicenseFirst(selectedModel?.displayName ?: "Gemma"))
            return
        }
        if (modelDownloadInFlight(modelDownloadJob)) {
            localState.value = localState.value.copy(message = strings().modelDownloadAlreadyRunning)
            return
        }
        modelDownloadJob = viewModelScope.launch {
            localState.value = localState.value.copy(
                activeModelDownloadId = modelId,
                message = if (force) strings().modelRedownloadStarting else strings().modelDownloadStarting,
            )
            runCatching {
                repository.markModelDownloadQueued(modelId)
                repository.downloadModel(modelId, force = force)
            }.onSuccess {
                localState.value = localState.value.copy(
                    activeModelDownloadId = null,
                    message = if (force) strings().modelRedownloadFinished else strings().modelDownloadFinished,
                )
                warmupLiteRtModels(modelId)
            }.onFailure { error ->
                if (error is CancellationException) {
                    withContext(NonCancellable) {
                        repository.markModelDownloadCancelled(modelId)
                        localState.value = localState.value.copy(activeModelDownloadId = null, message = strings().modelDownloadCancelled)
                    }
                } else {
                    repository.markModelDownloadFailed(modelId, "failed")
                    localState.value = localState.value.copy(activeModelDownloadId = null, message = messageFor(error, strings(), strings().modelDownloadFailed))
                }
            }
        }
    }

    fun redownloadModel(modelId: String) {
        downloadModel(modelId, force = true)
    }

    fun cancelModelDownload() {
        modelDownloadJob?.cancel()
    }

    fun toggleStar(item: HistoryItemEntity) {
        viewModelScope.launch {
            val nextStarred = !item.starred
            repository.setStarred(item.id, nextStarred)
            if (localState.value.selectedHistory?.id == item.id) {
                localState.value = localState.value.copy(selectedHistory = item.copy(starred = nextStarred))
            }
            if (localState.value.presentationHistory?.id == item.id) {
                localState.value = localState.value.copy(presentationHistory = item.copy(starred = nextStarred))
            }
            if (localState.value.tab == AppTab.Lineage) refreshLineage()
        }
    }

    fun toggleStar(item: HistoryListItem) {
        viewModelScope.launch {
            repository.setStarred(item.id, !item.starred)
        }
    }

    fun setHistoryTrashView(on: Boolean) {
        localState.value = localState.value.copy(historyTrashView = on)
    }

    fun clearWorkNotice() {
        localState.value = localState.value.copy(workNotice = null)
    }

    /**
     * Moves a work to the trash: web's `/api/history/trash`, the server's
     * `HistoryTrashStateWriter.trash_items`. Only the flag moves -- the
     * lineage keeps the node, and the work can be brought back. A work on
     * screen stays there marked as in the trash, as web keeps its current
     * item with `trashed: true`, and the lineage is read again so its card
     * says so.
     */
    fun trashWork(item: HistoryItemEntity) {
        viewModelScope.launch {
            repository.trash(item.id)
            afterTrashFlagChanged(item.id, trashed = true, notice = strings().workTrashed)
        }
    }

    fun restoreWork(id: String) {
        viewModelScope.launch {
            repository.restore(id)
            afterTrashFlagChanged(id, trashed = false, notice = strings().workRestored)
        }
    }

    /**
     * Deletes a work in the trash for good: web's `/api/history/permanent-delete`
     * from its trash view, which the server limits to rows already in the
     * trash (`require_trashed`). A work that is not in the trash is left alone.
     * The lineage keeps a tombstone in the work's place.
     */
    fun deleteWorkForGood(id: String) {
        viewModelScope.launch {
            val row = repository.getHistoryById(id) ?: return@launch
            if (!row.trashed) return@launch
            repository.deleteHistoryPermanently(id)
            val current = localState.value
            localState.value = if (current.selectedHistory?.id == id || current.pendingDescriptionParent?.id == id) {
                current.copy(
                    selectedHistory = null,
                    pendingDescriptionParent = null,
                    lineageDetached = true,
                    lineageGraph = null,
                    pipelineView = null,
                    historyAuthority = null,
                    historyDescriptionLocked = null,
                    workNotice = strings().workDeleted,
                )
            } else {
                current.copy(workNotice = strings().workDeleted)
            }
        }
    }

    private fun afterTrashFlagChanged(id: String, trashed: Boolean, notice: String) {
        val current = localState.value
        localState.value = current.copy(
            selectedHistory = current.selectedHistory?.let { if (it.id == id) it.copy(trashed = trashed) else it },
            pendingDescriptionParent = current.pendingDescriptionParent?.let { if (it.id == id) it.copy(trashed = trashed) else it },
            // The full screen draws this row, and its menu reads the flag.
            presentationHistory = current.presentationHistory?.let { if (it.id == id) it.copy(trashed = trashed) else it },
            workNotice = notice,
        )
        if (current.tab == AppTab.Lineage) refreshLineage()
    }

    private fun validateSelectedModels(state: InkuUiState): String? =
        validateModelsForRun(state)

    private fun validateModelsForRun(state: InkuUiState): String? {
        val models = listOf(
            "Stage1" to state.selectedModelId,
            "Stage2" to state.selectedStage2ModelId,
        ).distinctBy { it.second }

        return models
            .firstNotNullOfOrNull { (stage, modelId) ->
                if (!modelId.startsWith("local-litert-lm:")) return@firstNotNullOfOrNull null
                val asset = state.modelAssets.firstOrNull { it.modelId == modelId }
                    ?: return@firstNotNullOfOrNull strings().modelLocalInfoMissing(stage, modelId)
                if (asset.downloadState != "ready") {
                    strings().modelNotDownloadedYet(stage, asset.displayName, asset.downloadState)
                } else {
                    null
                }
            }
    }

    private suspend fun restorePersistedSettings() {
        val settings = repository.getSettingsMap()
        val bundledPluginsEnabled = repository.isBundledPluginPackageEnabled()
        val bundledPluginWords = withContext(Dispatchers.IO) {
            runCatching { repository.bundledPluginWords(japanese = true) to repository.bundledPluginWords(japanese = false) }
                .getOrDefault(emptyList<String>() to emptyList())
        }
        // Read after the lookup suspended, not before. Startup runs while the
        // screen is already live: a description typed, a work picked from
        // history, a canvas ratio chosen -- all of it lands in the state while
        // this is waiting on the database, and writing back a copy taken before
        // the wait undoes it without a trace. `lineageDetached` is the newest
        // thing that would be undone, and undoing it is not a cosmetic slip:
        // the pick it erases is what decides whether the next save has a parent.
        val current = localState.value
        val catalog = settings["color_catalog"]?.let { JSONObject(it).optString("value", current.selectedCatalogId) } ?: current.selectedCatalogId
        val canvas = settings["canvas_aspect"]?.let { JSONObject(it).optString("value", current.selectedCanvasAspect) } ?: current.selectedCanvasAspect
        val legacyPixel9Paper = canvas == CanvasAspects.LEGACY_PIXEL9_LANDSCAPE_SAFE_ID
        val displaySafeMargins = settings[SETTING_KEY_DISPLAY_SAFE_MARGINS]
            ?.let { JSONObject(it).optBoolean("enabled", current.displaySafeMarginsEnabled) }
            ?: if (legacyPixel9Paper) true else current.displaySafeMarginsEnabled
        val pngAlpha = settings["png_alpha_white"]?.let { JSONObject(it).optBoolean("enabled", current.pngAlphaWhite) } ?: current.pngAlphaWhite
        val maxSvgMiB = app.inku.mobile.render.SvgOutputLimit.storedMiB(settings[app.inku.mobile.render.SvgOutputLimit.SETTING_KEY])
        val renderWild = settings[SETTING_KEY_RENDER_WILD]?.let { JSONObject(it).optBoolean("enabled", current.renderWild) } ?: current.renderWild
        val uiMode = settings["ui_mode"]?.let { JSONObject(it).optString("value", current.uiMode) } ?: current.uiMode
        // A stored code that is not one of the two falls back to Japanese
        // rather than being rejected -- the same thing the server does with an
        // unrecognised `ui_lang` (`api_core/common.py:68-70`).
        val uiLanguage = settings[SETTING_KEY_UI_LANGUAGE]
            ?.let { UiLanguage.fromCode(JSONObject(it).optString("value")) }
            ?: current.uiLanguage
        val uiTextScale = settings[SETTING_KEY_UI_TEXT_SCALE]
            ?.let { normalizeUiTextScale(JSONObject(it).optDouble("value", 1.0).toFloat()) }
            ?: current.uiTextScale
        val mascotKind = settings[SETTING_KEY_MASCOT_KIND]?.let { JSONObject(it).optString("value", current.mascotKind) } ?: current.mascotKind
        val demoSeed = settings["demo_seed_phrase"]?.let { JSONObject(it).optString("value", current.demoSeed) } ?: current.demoSeed
        val demoInterval = settings["demo_interval_seconds"]?.let { JSONObject(it).optInt("value", current.demoIntervalSeconds) } ?: current.demoIntervalSeconds
        val batchHistory = settings["batch_prompt_history"]?.let { parseStringArray(JSONObject(it).optJSONArray("items")) } ?: current.batchPromptHistory
        val refinementElement = settings[SETTING_KEY_REFINEMENT_ELEMENT]
            ?.let { RefinementElement.byId(JSONObject(it).optString("value")) }
            ?: current.refinementElement
        val modelSelection = settings["model_selection"]?.let(::JSONObject)
        val restoredStage1Model = modelSelection?.optString("stage1_model")?.takeIf { it.isNotBlank() }
        val restoredStage2Model = modelSelection?.optString("stage2_model")?.takeIf { it.isNotBlank() }
        val restoredUnifiedModel = (restoredStage1Model ?: restoredStage2Model)
            ?.let(DefaultModelDownloads::offeredOrStandard)
            ?: current.selectedModelId
        val thinking = modelSelection?.optBoolean("include_thinking", current.includeThinking)
            ?: settings["include_thinking"]?.let { JSONObject(it).optBoolean("enabled", current.includeThinking) }
            ?: current.includeThinking
        // A work picked while this was reading -- the latest one at start-up,
        // or the reader's own pick -- has already set the catalog and canvas it
        // was drawn with. The saved values are for a start with no work on
        // screen; laid over a pick, they made the result depend on which of the
        // two reads finished last.
        val picked = current.selectedHistory != null
        localState.value = current.copy(
            selectedCatalogId = if (picked) current.selectedCatalogId else CatalogSelection.normalizedSelectionId(catalog),
            selectedCanvasAspect = if (picked) current.selectedCanvasAspect else CanvasAspects.newSelectionOrDefault(canvas),
            displaySafeMarginsEnabled = displaySafeMargins,
            pngAlphaWhite = pngAlpha,
            maxSvgMiB = maxSvgMiB,
            renderWild = renderWild,
            bundledPluginsEnabled = bundledPluginsEnabled,
            bundledPluginWordsJa = bundledPluginWords.first,
            bundledPluginWordsEn = bundledPluginWords.second,
            uiMode = uiMode,
            uiLanguage = uiLanguage,
            uiTextScale = uiTextScale,
            mascotKind = mascotKind,
            demoSeed = demoSeed,
            demoIntervalSeconds = demoInterval.coerceIn(1, 999),
            batchPromptHistory = batchHistory,
            batchRetryLimit = settings["batch_retry_limit"]?.let { JSONObject(it).optInt("value", 0).coerceIn(0, 5) } ?: 0,
            refinementElement = refinementElement,
            includeThinking = thinking,
            selectedModelId = restoredUnifiedModel,
            selectedStage2ModelId = restoredUnifiedModel,
        )
        if (legacyPixel9Paper) {
            repository.saveSetting(
                "canvas_aspect",
                JSONObject().put("value", CanvasAspects.DEFAULT_ID).toString(),
            )
            if (SETTING_KEY_DISPLAY_SAFE_MARGINS !in settings) {
                repository.saveSetting(
                    SETTING_KEY_DISPLAY_SAFE_MARGINS,
                    JSONObject().put("enabled", true).toString(),
                )
            }
        }
        warmupLiteRtModels(restoredUnifiedModel)
    }

    private fun warmupLiteRtModels(vararg modelIds: String) {
        if (localState.value.cameraCaptureState == CameraCaptureState.Cancelling) return
        val targets = modelIds.distinct().filter { it.startsWith("local-litert-lm:") }
        if (targets.isEmpty()) return
        litertWarmupJob?.cancel()
        litertWarmupJob = viewModelScope.launch(Dispatchers.IO) {
            targets.forEach { modelId ->
                runCatching {
                    repository.warmupLocalModelIfReady(modelId)
                }
            }
        }
    }

    private fun parseStringArray(array: JSONArray?): List<String> {
        if (array == null) return emptyList()
        return (0 until array.length()).mapNotNull { index ->
            array.optString(index).trim().takeIf { it.isNotBlank() }
        }.take(10)
    }

    /**
     * The pack for the language the reader has chosen, read when a message is built.
     *
     * The ViewModel sits above the composition and cannot read `LocalStrings`.
     * Reading the state each time rather than holding a pack is what makes a
     * message written after the switch come out in the new language.
     */
    private fun strings(): InkuStrings = stringsFor(localState.value.uiLanguage)

    private fun persistSetting(key: String, valueJson: String) {
        viewModelScope.launch {
            repository.saveSetting(key, valueJson)
        }
    }

    private fun modelStatusText(asset: ModelAssetEntity): String {
        val progress = if (asset.bytesTotal != null && asset.bytesTotal > 0L) {
            val percent = (asset.bytesDownloaded * 100.0 / asset.bytesTotal).coerceIn(0.0, 100.0)
            " ${"%.1f".format(percent)}% (${formatBytes(asset.bytesDownloaded)} / ${formatBytes(asset.bytesTotal)})"
        } else if (asset.bytesDownloaded > 0L) {
            " ${formatBytes(asset.bytesDownloaded)}"
        } else {
            ""
        }
        return "${asset.displayName}: ${asset.downloadState}$progress"
    }

    private fun formatBytes(bytes: Long): String {
        val gb = 1024.0 * 1024.0 * 1024.0
        val mb = 1024.0 * 1024.0
        return if (bytes >= gb) {
            "%.2f GB".format(bytes / gb)
        } else {
            "%.1f MB".format(bytes / mb)
        }
    }
}

internal fun modelDownloadInFlight(job: Job?): Boolean = job != null && !job.isCompleted
