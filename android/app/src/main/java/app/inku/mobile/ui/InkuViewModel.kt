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
import app.inku.mobile.data.db.HistoryListItem
import app.inku.mobile.data.db.ExportTemplateEntity
import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.CatalogSelection
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.data.lineage.LineageDeclaration
import app.inku.mobile.data.lineage.LineageGraphNode
import app.inku.mobile.data.lineage.LineageGraphResult
import app.inku.mobile.data.lineage.SubmitDerivationKind
import app.inku.mobile.data.refinement.ComparisonPlanner
import app.inku.mobile.data.refinement.LanguageCombo
import app.inku.mobile.data.refinement.ModelCompareMode
import app.inku.mobile.data.refinement.RefinementElement
import app.inku.mobile.data.refinement.RefinementParent
import app.inku.mobile.data.refinement.RefinementPlan
import app.inku.mobile.data.refinement.RefinementPlanner
import app.inku.mobile.data.refinement.VariationAmplitude
import app.inku.mobile.pipeline.InstructionLanguages
import app.inku.mobile.pipeline.PaintResult
import app.inku.mobile.pipeline.SketchInput
import app.inku.mobile.pipeline.SketchMode
import app.inku.mobile.pipeline.Sketches
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.abs
import org.json.JSONArray
import org.json.JSONObject

const val DefaultDemoSeedPhrase = "世界の人と動物、自然と都市を主題として96文字の短文を作って。感情豊かに、季節や、人生と人のつながり、人生、世代、神。色々な観点から。"
const val DemoCanvasAspectId = "pixel9_landscape_safe"
/** Bookkeeping the demo loop puts in front of the prose it saves. */
const val DemoHistoryInputPrefix = "[demo] "

/** The prose that determines a history row's parent description. */
internal fun sourceTextOf(item: HistoryItemEntity): String =
    (item.sourceText ?: item.originalInput).trim()

const val SETTING_KEY_MASCOT_KIND = "mascot_kind"
const val SETTING_KEY_UI_LANGUAGE = "ui_lang"
/** 「推敲要素の選択は前回値をブラウザに記憶する」-- here, the device remembers it. */
const val SETTING_KEY_REFINEMENT_ELEMENT = "refinement_element"
/** 写生 (Stage 0.5): which of the three states the control was left in. */
const val SETTING_KEY_SKETCH_MODE = "sketch_mode"
/** Said by every generating entry point that refuses while candidates are drawn. */
val REFINEMENT_IN_PROGRESS: (InkuStrings) -> String = { it.refinementInProgress }
/** 「固定モードでは固定側を1モデル、比較側を最大4モデル選ぶ」(SPEC `:616`). */
const val MAX_COMPARE_SELECTION = 4
val MODEL_SELECT_PROMPT: (InkuStrings) -> String = { it.comparisonModelSelectPrompt }
val MODEL_FIXED_MISSING: (InkuStrings) -> String = { it.comparisonModelFixedMissing }
val MODEL_CHOICE_BLOCKED: (InkuStrings) -> String = { it.comparisonModelChoiceBlocked }
val LANGUAGE_SELECT_PROMPT: (InkuStrings) -> String = { it.comparisonLanguageSelectPrompt }
val LANGUAGE_COMBO_BLOCKED: (InkuStrings) -> String = { it.comparisonLanguageComboBlocked }
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

/** 日本語 / English, the two names the language grid shows. */
fun languageLabel(lang: String): String = if (lang == "en") "English" else "日本語"

data class InkuUiState(
    val prompt: String = "青い鉛筆の線を12本、波打つ軌跡に沿って散らす",
    val ddl: String = "",
    val ddlEditedAfterGeneration: Boolean = false,
    val confirmDdlOverwrite: Boolean = false,
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
    val providerModelCandidates: Map<String, List<String>> = emptyMap(),
    val exportTemplates: List<ExportTemplateEntity> = emptyList(),
    val activeModelDownloadId: String? = null,
    val selectedModelId: String = CompatibilityConstants.defaultStage1Model,
    val selectedStage2ModelId: String = CompatibilityConstants.defaultStage2Model,
    val includeThinking: Boolean = false,
    val modelSelectionOpen: Boolean = false,
    val catalogSelectionOpen: Boolean = false,
    val canvasSelectionOpen: Boolean = false,
    val selectedCatalogId: String = "default",
    val selectedCanvasAspect: String = "square",
    val selectedHistory: HistoryItemEntity? = null,
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
    val canvasAspectPluginEnabled: Boolean = true,
    val pngAlphaWhite: Boolean = false,
    val saveReplayAsNewVersion: Boolean = true,
    val historySelectionCanvas: HistorySelectionBehavior = HistorySelectionBehavior.Current,
    val historySelectionCatalog: HistorySelectionBehavior = HistorySelectionBehavior.Current,
    val ddlAutoRepairEnabled: Boolean = false,
    val litertStage1PromptOptimization: Boolean = false,
    val saijikiOpen: Boolean = false,
    // Whether the description is being written. The bottom bar reads it: while
    // the keyboard is up, the four destinations give their place to the one
    // action the writing is heading for.
    val descriptionFocused: Boolean = false,
    val ddlEditorOpen: Boolean = false,
    val isDrawing: Boolean = false,
    val message: String? = null,
    val tab: AppTab = AppTab.Compose,
    val settingsPane: SettingsPane = SettingsPane.Home,
    val composeMode: ComposeMode = ComposeMode.Write,
    val renderTab: RenderTab = RenderTab.Artwork,
    val uiMode: String = "full",
    val uiLanguage: UiLanguage = UiLanguage.DEFAULT,
    val mascotKind: String = "incu",
    val canvasZoom: Float = 1.0f,
    val canvasPanX: Float = 0f,
    val canvasPanY: Float = 0f,
    val canvasPresentationMode: Boolean = false,
    val renderWild: Boolean = false,
    // 写生 (Stage 0.5). One control, three states, and the author's default is
    // that the layer runs cutting fine (`sketch.ts:26`, `sketch.py:36`).
    val sketchMode: SketchMode = Sketches.DEFAULT_MODE,
    // 推敲 (SPEC :614). The element is one value, never a set: the radio is
    // exclusive because a lineage edge has one cause.
    val refinementOpen: Boolean = false,
    val refinementParent: HistoryItemEntity? = null,
    val refinementElement: RefinementElement = RefinementElement.Touch,
    val refinementAmplitude: VariationAmplitude = VariationAmplitude.Default,
    val refinementTouchWords: String = "",
    val refinementCount: Int = 1,
    val refinementBusy: Boolean = false,
    // 「開始3秒後から共通デザインの停止ボタンでAPI要求を中断できる」.
    val refinementCanAbort: Boolean = false,
    val refinementStatus: String? = null,
    val refinementCandidates: List<RefinementCandidate> = emptyList(),
    // The candidate on the canvas that has not been saved. Drawing on from here
    // has to put it in the lineage first (SPEC :2105).
    val refinementPreviewId: String? = null,
    // 検分 (SPEC :616, :686). The two comparisons are sub-views beside 調整
    // rather than screens of their own, and they share every field above:
    // the candidates, the busy flag, the stop and the save are the refinement's.
    val refinementSubview: RefinementSubview = RefinementSubview.Adjust,
    val modelCompareMode: ModelCompareMode = ModelCompareMode.Default,
    val modelCompareFixedModel: String = "",
    val modelCompareSelectedModels: List<String> = emptyList(),
    val languageCompareSelectedCombos: List<String> = emptyList(),
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
    val isRunning: Boolean get() = isDrawing || refinementBusy
}

/**
 * The three sub-views of 推敲 (SPEC `:616`, `:686`).
 *
 * 調整 varies one of the five elements; the other two vary a model or a
 * language. They are one screen with three faces rather than three screens,
 * which is what「比較のロジックを複製しない」(SPEC `:688`) asks for.
 */
enum class RefinementSubview(val id: String) {
    Adjust("adjust"),
    Model("model"),
    Language("language"),
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
    ModelSelection,
    Models,
    Demo,
    Export,
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

enum class HistorySelectionBehavior {
    History,
    Current,
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
    private val history = repository.history()
    private val modelAssets = repository.modelAssets()
    private val providerSettings = repository.providerSettings()
    private val providerModelCandidates = repository.providerModelCandidates()
    private val exportTemplates = repository.exportTemplates()
    private var modelDownloadJob: Job? = null
    private var drawingJob: Job? = null
    private var lineageJob: Job? = null
    private var refinementJob: Job? = null
    private var litertWarmupJob: Job? = null
    private var drawingRunSerial: Long = 0L
    private var restoredInitialHistory = false
    private var promptEditedByUser = false
    private var modelSelectionSnapshot: Pair<String, String>? = null
    private var catalogSelectionSnapshot: String? = null
    private var lastHistorySwipeAt = 0L

    private val providerConfig = combine(providerSettings, providerModelCandidates) { providers, candidates ->
        providers to candidates
    }

    val state: StateFlow<InkuUiState> = combine(localState, history, modelAssets, providerConfig, exportTemplates) { state, items, assets, providerPair, templates ->
        val (providers, candidates) = providerPair
        val selectedModel = assets.firstOrNull { it.modelId == state.selectedModelId }
        val modelState = selectedModel?.let { modelStatusText(it) } ?: "model catalog initializing"
        state.copy(
            modelAssets = assets,
            providerSettings = providers,
            providerModelCandidates = candidates,
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

    init {
        viewModelScope.launch {
            repository.ensureDefaultModelAssets()
            repository.ensureDefaultProviderSettings()
            repository.ensureDefaultExportTemplates()
            restorePersistedSettings()
            withContext(Dispatchers.IO) {
                repeat(4) {
                    repository.backfillMissingThumbnails(limit = 8)
                    delay(750)
                }
            }
        }
        viewModelScope.launch {
            val latest = history.first { it.isNotEmpty() }.first()
            if (restoredInitialHistory || promptEditedByUser || localState.value.selectedHistory != null) return@launch
            repository.getHistoryById(latest.id)?.let { full ->
                // Re-read after the lookup suspended. The first history row can
                // arrive because a drawing just saved it, and that drawing sets
                // the selection itself a moment later; writing a value captured
                // before the suspension back over it would restore the flags of
                // a state that no longer exists -- among them `lineageDetached`,
                // which decides whether the next save has a parent at all.
                val current = localState.value
                if (!restoredInitialHistory && !promptEditedByUser && current.selectedHistory == null) {
                    restoredInitialHistory = true
                    localState.value = current.copy(
                        selectedHistory = full,
                        // Restored for display only. web has no such restore --
                        // `displayedHistoryItem` starts null (+page.svelte:2604)
                        // and `onMount` (:5789) puts nothing back -- so counting
                        // it as a parent would make this client alone record a
                        // `replay` for opening the app and drawing. Only an
                        // explicit pick from history becomes a parent, which is
                        // what web's `loadIterationItem` does.
                        lineageDetached = true,
                        prompt = full.originalInput,
                        ddl = full.normalizedDdl,
                        ddlEditedAfterGeneration = false,
                        selectedCatalogId = full.colorCatalogId,
                        selectedCanvasAspect = full.canvasAspect,
                    )
                }
            }
        }
    }

    override fun onCleared() {
        drawingRunSerial += 1
        drawingJob?.cancel()
        lineageJob?.cancel()
        refinementJob?.cancel()
        modelDownloadJob?.cancel()
        litertWarmupJob?.cancel()
        (getApplication() as InkuApplication).applicationScope.launch {
            repository.close()
        }
        super.onCleared()
    }

    fun setPrompt(value: String) {
        promptEditedByUser = true
        localState.value = localState.value.copy(prompt = value, message = null)
    }

    fun clearPrompt() {
        if (state.value.isDrawing) return
        promptEditedByUser = true
        localState.value = localState.value.copy(
            prompt = "",
            ddl = "",
            ddlEditedAfterGeneration = false,
            message = null,
        )
    }

    fun setDdl(value: String) {
        localState.value = localState.value.copy(ddl = value, ddlEditedAfterGeneration = true, message = null)
    }

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
        localState.value = localState.value.copy(selectedCatalogId = ColorCatalogs.get(id).id)
        persistSetting("color_catalog", JSONObject().put("value", ColorCatalogs.get(id).id).toString())
    }

    fun setCanvasAspect(id: String) {
        localState.value = localState.value.copy(selectedCanvasAspect = CanvasAspects.normalize(id))
        persistSetting("canvas_aspect", JSONObject().put("value", CanvasAspects.normalize(id)).toString())
    }

    fun setSelectedModel(modelId: String) {
        localState.value = localState.value.copy(
            selectedModelId = modelId,
            selectedStage2ModelId = modelId,
            message = null,
        )
        warmupLiteRtModels(modelId)
    }

    fun setStage1Model(modelId: String) {
        localState.value = localState.value.copy(selectedModelId = modelId, message = null)
        warmupLiteRtModels(modelId)
    }

    fun setStage2Model(modelId: String) {
        localState.value = localState.value.copy(selectedStage2ModelId = modelId, message = null)
        warmupLiteRtModels(modelId)
    }

    fun setIncludeThinking(enabled: Boolean) {
        localState.value = localState.value.copy(includeThinking = enabled)
        persistSetting("include_thinking", JSONObject().put("enabled", enabled).toString())
    }

    fun setTab(tab: AppTab) {
        val current = localState.value
        val restoredModelSelection = if (tab != AppTab.Settings && current.settingsPane == SettingsPane.ModelSelection) modelSelectionSnapshot else null
        if (restoredModelSelection != null) modelSelectionSnapshot = null
        localState.value = current.copy(
            tab = tab,
            selectedModelId = restoredModelSelection?.first ?: current.selectedModelId,
            selectedStage2ModelId = restoredModelSelection?.second ?: current.selectedStage2ModelId,
            settingsPane = if (tab == AppTab.Settings && current.tab != AppTab.Settings) {
                SettingsPane.Home
            } else if (tab == AppTab.Settings && current.settingsPane == SettingsPane.ModelSelection) {
                SettingsPane.Home
            } else {
                current.settingsPane
            },
        )
        // web refetches when the lineage tab comes up (+page.svelte:4556).
        if (tab == AppTab.Lineage) refreshLineage()
    }

    fun setSettingsPane(panel: SettingsPane) {
        localState.value = localState.value.copy(settingsPane = panel, message = null)
    }

    fun openModelSelection() {
        val current = localState.value
        modelSelectionSnapshot = current.selectedModelId to current.selectedStage2ModelId
        localState.value = current.copy(modelSelectionOpen = true, message = null)
    }

    fun confirmModelSelection() {
        modelSelectionSnapshot = null
        val current = localState.value
        val unifiedModelId = current.selectedModelId
        persistSetting("model_selection", JSONObject()
            .put("stage1_model", unifiedModelId)
            .put("stage2_model", unifiedModelId)
            .put("include_thinking", current.includeThinking)
            .toString())
        localState.value = current.copy(
            selectedModelId = unifiedModelId,
            selectedStage2ModelId = unifiedModelId,
            modelSelectionOpen = false,
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
        localState.value = localState.value.copy(
            canvasZoom = CANVAS_FIT_ZOOM,
            canvasPanX = 0f,
            canvasPanY = 0f,
            canvasPresentationMode = true,
        )
    }

    /**
     * Leave the full screen.
     *
     * This used to be `resetCanvasZoom`, which meant the close button and the
     * zoom reset were the same call and neither could be done without the other.
     */
    fun exitCanvasPresentationMode() {
        localState.value = localState.value.copy(
            canvasZoom = CANVAS_FIT_ZOOM,
            canvasPanX = 0f,
            canvasPanY = 0f,
            canvasPresentationMode = false,
        )
    }

    fun panCanvas(dx: Float, dy: Float) {
        val current = localState.value
        if (current.canvasZoom <= CANVAS_FIT_ZOOM) return
        localState.value = current.copy(
            canvasPanX = (current.canvasPanX + dx).coerceIn(-500f, 500f),
            canvasPanY = (current.canvasPanY + dy).coerceIn(-500f, 500f),
        )
    }

    fun setCanvasAspectPluginEnabled(enabled: Boolean) {
        localState.value = localState.value.copy(canvasAspectPluginEnabled = enabled)
        persistSetting("canvas_aspect_plugin", JSONObject().put("enabled", enabled).toString())
    }

    fun setPngAlphaWhite(enabled: Boolean) {
        localState.value = localState.value.copy(pngAlphaWhite = enabled)
        persistSetting("png_alpha_white", JSONObject().put("enabled", enabled).toString())
    }

    fun setRenderWild(wild: Boolean) {
        localState.value = localState.value.copy(renderWild = wild)
    }

    fun setSketchMode(mode: SketchMode) {
        localState.value = localState.value.copy(sketchMode = mode)
        persistSetting(SETTING_KEY_SKETCH_MODE, JSONObject().put("value", mode.wire).toString())
    }

    fun setSaveReplayAsNewVersion(enabled: Boolean) {
        localState.value = localState.value.copy(saveReplayAsNewVersion = enabled)
        persistSetting("save_replay_as_new_version", JSONObject().put("enabled", enabled).toString())
    }

    fun setHistorySelectionCanvas(value: HistorySelectionBehavior) {
        localState.value = localState.value.copy(historySelectionCanvas = value)
        persistSetting("history_selection_canvas", JSONObject().put("value", value.name.lowercase()).toString())
    }

    fun setHistorySelectionCatalog(value: HistorySelectionBehavior) {
        localState.value = localState.value.copy(historySelectionCatalog = value)
        persistSetting("history_selection_catalog", JSONObject().put("value", value.name.lowercase()).toString())
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

    fun toggleDdlAutoRepair() {
        val current = localState.value
        val enabled = !current.ddlAutoRepairEnabled
        localState.value = current.copy(ddlAutoRepairEnabled = enabled, message = null)
        persistSetting("ddl_auto_repair", JSONObject().put("enabled", enabled).toString())
    }

    fun setLiteRtStage1PromptOptimization(enabled: Boolean) {
        localState.value = localState.value.copy(litertStage1PromptOptimization = enabled, message = null)
        persistSetting("litert_stage1_prompt_optimization", JSONObject().put("enabled", enabled).toString())
    }

    fun setUiMode(mode: String) {
        val normalized = if (mode == "simple") "simple" else "full"
        localState.value = localState.value.copy(uiMode = normalized, message = null)
        persistSetting("ui_mode", JSONObject().put("value", normalized).toString())
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

    /**
     * @param tab where the pick leaves the reader. Picking out of history opens
     *   the work to be drawn again; picking a node in the lineage re-centres the
     *   graph and stays on it, which is what web's `openLineageNode` does
     *   (+page.svelte:4225-4230) -- there it is the double click
     *   (`openLineageNodeInCanvas`, :4234) that moves to the canvas.
     */
    private fun applyHistorySelection(item: HistoryItemEntity, tab: AppTab) {
        restoredInitialHistory = true
        promptEditedByUser = false
        localState.value = localState.value.copy(
            selectedHistory = item,
            // An explicit pick is what makes a work the parent of the next save
            // (web's `loadIterationItem`, +page.svelte:4600).
            lineageDetached = false,
            prompt = item.originalInput,
            ddl = item.normalizedDdl,
            ddlEditedAfterGeneration = false,
            confirmDdlOverwrite = false,
            selectedCatalogId = item.colorCatalogId,
            selectedCanvasAspect = item.canvasAspect,
            tab = tab,
            composeMode = ComposeMode.Write,
        )
    }

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
        applyHistorySelection(item, AppTab.Lineage)
        refreshLineage()
    }

    fun selectPreviousHistory() {
        selectAdjacentHistory(-1)
    }

    fun selectNextHistory() {
        selectAdjacentHistory(1)
    }

    fun selectLatestHistory() {
        viewModelScope.launch {
            val latest = historyItems.value.firstOrNull() ?: history.first().firstOrNull() ?: return@launch
            selectHistory(latest)
        }
    }

    private fun selectAdjacentHistory(offset: Int) {
        val now = SystemClock.elapsedRealtime()
        if (now - lastHistorySwipeAt < 450L) return
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

    fun draw() {
        val current = state.value
        // 「候補生成中は他の生成・描画操作を禁止し」. Before the model check, because
        // what stops this drawing has to be the refinement rather than whichever
        // reason happens to be found first.
        if (current.refinementBusy) {
            localState.value = localState.value.copy(message = REFINEMENT_IN_PROGRESS(strings()))
            return
        }
        validateSelectedModels(current)?.let { message ->
            localState.value = localState.value.copy(message = message)
            return
        }
        runSubmit(current)
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

    private fun beginDrawingRun(): Long {
        drawingRunSerial += 1
        drawingJob?.cancel()
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
        kindOf: (parent: HistoryItemEntity?, canvasAspectChanged: Boolean) -> String?,
    ): LineageDeclaration {
        val parent = lineageParent(current)
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
        lineageFor(current) { parent, canvasAspectChanged ->
            SubmitDerivationKind.forDescribeSubmit(
                hasParent = parent != null,
                canvasAspectChanged = canvasAspectChanged,
                textChanged = parent != null && descriptionChanged(current.prompt, parent),
                grainChanged = parent != null && grainChanged(current.sketchMode, parent),
            )
        }

    /**
     * Whether the 写生 (Stage 0.5) grain differs from the one its parent was
     * painted at. web reaches the same judgment with
     * `normalizeSketchGrain(displayedHistoryItem?.sketch_grain) !==
     * sketchGrainOf(sketchMode)` (+page.svelte:3225-3227), and this is that
     * comparison, both halves included.
     *
     * **What a parent with no grain is compared against: nothing.** The
     * normalizer used here is web's -- [Sketches.recordedGrainOf], which answers
     * `null` for an absent value, for `off`, and for a row written before the
     * column. It is NOT [Sketches.normalizeGrain], which rounds an unknown value
     * up to the default `fine` because it is resolving a *requested* grain.
     * Using that one here would invert both readings: redrawing a work that
     * predates the column with the layer off would look like a grain change,
     * and redrawing it at `fine` would look like a replay. `off` carries no
     * grain either ([Sketches.grainOf]), so absence compares equal to absence
     * and a redraw with the layer off stays a replay -- which is what it is.
     */
    private fun grainChanged(mode: SketchMode, parent: HistoryItemEntity): Boolean =
        Sketches.grainOf(mode) != Sketches.recordedGrainOf(parent.sketchGrain)

    /**
     * What the describe screen asks 写生 (Stage 0.5) for.
     *
     * A redraw that moved neither the description nor the grain replays the
     * prose its parent was painted from rather than asking the layer again
     * (+page.svelte:3238-3241): the layer is not deterministic, so calling it a
     * second time would produce a different sketch, and that is not a replay.
     * Anything else -- an edited description, a moved grain, no parent at all --
     * carries no prose, and the layer runs if the control asks it to.
     */
    private fun describeSketchInput(current: InkuUiState): SketchInput {
        val parent = lineageParent(current)
        val replaying = parent != null &&
            !descriptionChanged(current.prompt, parent) &&
            !grainChanged(current.sketchMode, parent)
        return SketchInput(
            requested = current.sketchMode != SketchMode.Off,
            text = if (replaying) parent?.sketchText else null,
            grain = Sketches.grainOf(current.sketchMode)?.wire,
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

    private fun runSubmit(current: InkuUiState) {
        if (current.prompt.isBlank()) {
            localState.value = current.copy(message = "Prompt is empty.")
            return
        }
        if (current.refinementBusy) {
            localState.value = current.copy(message = REFINEMENT_IN_PROGRESS(strings()))
            return
        }
        // Read before the coroutine starts: the first thing it does is clear
        // `selectedHistory` (below), so a parent read from inside would be gone.
        val declared = describeLineage(current)
        // Read here for the same reason: it is decided against the parent, and
        // the coroutine clears the parent before it draws.
        val sketchRequest = describeSketchInput(current)
        val runId = beginDrawingRun()
        drawingJob = viewModelScope.launch {
            val lineage = withPreviewParent(current, declared)
            localState.value = localState.value.copy(
                isDrawing = true,
                selectedHistory = null,
                ddl = "",
                ddlEditedAfterGeneration = false,
                confirmDdlOverwrite = false,
                message = strings().statusStage1,
            )
            runCatching {
                val interpreted = withContext(Dispatchers.IO) {
                    repository.interpret(
                        current.prompt,
                        CatalogSelection.resolvedCatalogIdForRun(current.selectedCatalogId),
                        current.selectedCanvasAspect,
                        current.selectedModelId,
                        current.selectedStage2ModelId,
                        current.ddlAutoRepairEnabled,
                        current.litertStage1PromptOptimization,
                        instructionLang = InstructionLanguages.AUTO,
                        uiLang = current.uiLanguage.code,
                        sketch = sketchRequest,
                    )
                }
                if (!isCurrentDrawingRun(runId)) return@launch
                localState.value = localState.value.copy(
                    ddl = interpreted.ddlForDisplay,
                    ddlEditedAfterGeneration = false,
                    message = strings().statusStage2,
                )
                withContext(Dispatchers.IO) {
                    repository.composeFromDdl(
                        current.prompt,
                        interpreted.ddlForDisplay,
                        CatalogSelection.resolvedCatalogIdForRun(current.selectedCatalogId),
                        current.selectedCanvasAspect,
                        current.selectedModelId,
                        current.selectedStage2ModelId,
                        current.ddlAutoRepairEnabled,
                        current.litertStage1PromptOptimization,
                        lineage = lineage,
                        instructionLang = InstructionLanguages.AUTO,
                        uiLang = current.uiLanguage.code,
                        // 0.5 ran in the step above and is not run again: what it
                        // produced -- and what it did, including a fallback the
                        // prose cannot show -- travels to the save from there.
                        sketch = sketchRequest.copy(
                            text = interpreted.sketchText,
                            grain = interpreted.sketchGrain,
                            claimedState = interpreted.sketchState,
                        ),
                    )
                }
            }.onSuccess { item ->
                if (!isCurrentDrawingRun(runId)) return@onSuccess
                promptEditedByUser = false
                localState.value = localState.value.copy(
                    prompt = item.originalInput,
                    ddl = item.normalizedDdl,
                    ddlEditedAfterGeneration = false,
                    confirmDdlOverwrite = false,
                    selectedHistory = item,
                    // A saved work is what the next one comes from (web lowers
                    // the same flag on every save, +page.svelte:2883, :3304).
                    lineageDetached = false,
                    isDrawing = false,
                    message = "Rendered ${item.renderHashShort}",
                )
            }.onFailure { error ->
                if (!isCurrentDrawingRun(runId)) return@onFailure
                val message = if (error is CancellationException) strings().statusStopped else messageFor(error, strings(), strings().statusDrawFailed)
                localState.value = localState.value.copy(isDrawing = false, message = message)
            }
        }
    }

    fun drawFromDdl() {
        val current = state.value
        val returnToLineage = current.tab == AppTab.Lineage
        if (current.refinementBusy) {
            localState.value = localState.value.copy(message = REFINEMENT_IN_PROGRESS(strings()))
            return
        }
        validateSelectedModels(current)?.let { message ->
            localState.value = localState.value.copy(message = message)
            return
        }
        val ddl = current.ddl.ifBlank { current.prompt }
        val declared = ddlLineage(current)
        val runId = beginDrawingRun()
        drawingJob = viewModelScope.launch {
            val lineage = withPreviewParent(current, declared)
            localState.value = localState.value.copy(isDrawing = true, message = strings().statusComposingFromDdl)
            runCatching {
                withContext(Dispatchers.IO) {
                    repository.composeFromDdl(current.prompt, ddl, CatalogSelection.resolvedCatalogIdForRun(current.selectedCatalogId), current.selectedCanvasAspect, current.selectedModelId, current.selectedStage2ModelId, current.ddlAutoRepairEnabled, current.litertStage1PromptOptimization, lineage = lineage, instructionLang = InstructionLanguages.AUTO, uiLang = current.uiLanguage.code)
                }
            }.onSuccess { item ->
                if (!isCurrentDrawingRun(runId)) return@onSuccess
                promptEditedByUser = false
                localState.value = localState.value.copy(
                    prompt = item.originalInput,
                    ddl = item.normalizedDdl,
                    ddlEditedAfterGeneration = false,
                    confirmDdlOverwrite = false,
                    selectedHistory = item,
                    lineageDetached = false,
                    isDrawing = false,
                    message = "Composed ${item.renderHashShort}",
                )
                if (returnToLineage) refreshLineage()
            }.onFailure { error ->
                if (!isCurrentDrawingRun(runId)) return@onFailure
                val message = if (error is CancellationException) strings().statusStopped else messageFor(error, strings(), strings().statusComposeFailed)
                localState.value = localState.value.copy(isDrawing = false, message = message)
            }
        }
    }

    fun runBatch() {
        val current = state.value
        validateSelectedModels(current)?.let { message ->
            localState.value = localState.value.copy(message = message)
            return
        }
        val lines = current.batchText.lines()
            .mapIndexed { index, line -> index + 1 to line.trim() }
            .filter { it.second.isNotBlank() }
        if (lines.isEmpty()) {
            localState.value = current.copy(message = "Batch is empty.")
            return
        }
        if (lines.size > MaxBatchItems) {
            localState.value = current.copy(message = strings().batchTooManyItems(MaxBatchItems, lines.size))
            return
        }
        rememberBatchPrompt(current.batchText)
        val runId = beginDrawingRun()
        drawingJob = viewModelScope.launch {
            val startedAt = System.currentTimeMillis()
            var last: HistoryItemEntity? = null
            var success = 0
            var failures = emptyList<BatchFailure>()
            localState.value = localState.value.copy(
                isDrawing = true,
                batchTotal = lines.size,
                batchCurrent = 0,
                batchSuccess = 0,
                batchFailures = emptyList(),
                batchActiveLine = null,
                batchActiveDdl = null,
                batchActiveElapsedMs = null,
                batchElapsedMs = 0L,
                batchLatestHashShort = null,
                message = "Batch running: 0/${lines.size}",
            )
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
                    val catalogId = CatalogSelection.resolvedCatalogIdForRun(current.selectedCatalogId)
                    withContext(Dispatchers.IO) {
                        repository.paint(
                            description = prompt,
                            catalogId = catalogId,
                            canvasAspect = current.selectedCanvasAspect,
                            stage1ModelId = current.selectedModelId,
                            stage2ModelId = current.selectedStage2ModelId,
                            autoRepair = current.ddlAutoRepairEnabled,
                            historyInput = "#$lineNumber $prompt",
                            litertStage1PromptOptimization = current.litertStage1PromptOptimization,
                            instructionLang = InstructionLanguages.AUTO,
                            uiLang = current.uiLanguage.code,
                            // The prose without the line number: the same split
                            // the server keeps between `input` and `source_text`.
                            sourceText = prompt,
                        )
                    }
                }.onSuccess { item ->
                    if (!isCurrentDrawingRun(runId)) return@onSuccess
                    success += 1
                    last = item
                    localState.value = localState.value.copy(
                        selectedHistory = item,
                        // The line itself declared no parent -- every batch line
                        // is a root of its own, as web's does (+page.svelte:3327-3345)
                        // -- but the work now on screen is one, and web lowers
                        // this flag on every saved paint (:2883).
                        lineageDetached = false,
                        ddl = item.normalizedDdl,
                        ddlEditedAfterGeneration = false,
                        batchSuccess = success,
                        batchFailures = failures,
                        batchActiveDdl = item.normalizedDdl,
                        batchActiveElapsedMs = System.currentTimeMillis() - itemStartedAt,
                        batchElapsedMs = System.currentTimeMillis() - startedAt,
                        batchLatestHashShort = item.renderHashShort,
                        message = strings().batchRunning(index + 1, lines.size),
                    )
                }.onFailure { error ->
                    if (error is CancellationException) throw error
                    if (!isCurrentDrawingRun(runId)) return@onFailure
                    failures = (failures + BatchFailure(lineNumber, prompt, error.message ?: "Draw failed.")).take(30)
                    localState.value = localState.value.copy(
                        batchSuccess = success,
                        batchFailures = failures,
                        batchActiveElapsedMs = System.currentTimeMillis() - itemStartedAt,
                        batchElapsedMs = System.currentTimeMillis() - startedAt,
                        message = strings().batchRunning(index + 1, lines.size),
                    )
                }
            }
            if (!isCurrentDrawingRun(runId)) return@launch
            localState.value = localState.value.copy(
                selectedHistory = last,
                lineageDetached = false,
                ddl = last?.normalizedDdl.orEmpty(),
                ddlEditedAfterGeneration = false,
                prompt = last?.originalInput?.removePrefix("#${localState.value.batchActiveLine} ") ?: current.prompt,
                isDrawing = false,
                batchCurrent = 0,
                batchActiveLine = null,
                batchActiveDdl = null,
                batchActiveElapsedMs = null,
                batchElapsedMs = System.currentTimeMillis() - startedAt,
                message = strings().batchCompleted(success, failures.size, lines.size),
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
                    val catalogId = CatalogSelection.resolvedCatalogIdForRun(cycle.selectedCatalogId)
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
                                autoRepair = cycle.ddlAutoRepairEnabled,
                                historyInput = "$DemoHistoryInputPrefix$prompt",
                                litertStage1PromptOptimization = cycle.litertStage1PromptOptimization,
                                instructionLang = InstructionLanguages.AUTO,
                                uiLang = cycle.uiLanguage.code,
                                // The prose without the demo marker, for the
                                // same reason the batch line strips its number.
                                sourceText = prompt,
                            )
                        }
                    }.onSuccess { item ->
                        if (!isCurrentDrawingRun(runId)) return@onSuccess
                        val elapsed = System.currentTimeMillis() - startedAt
                        val latest = localState.value
                        localState.value = latest.copy(
                            selectedHistory = item,
                            lineageDetached = false,
                            prompt = item.originalInput.removePrefix(DemoHistoryInputPrefix),
                            ddl = item.normalizedDdl,
                            ddlEditedAfterGeneration = false,
                            demoGeneratedDdl = item.normalizedDdl,
                            demoCurrentElapsedMs = elapsed,
                            demoTotalElapsedMs = latest.demoTotalElapsedMs + elapsed,
                            demoRenderCount = latest.demoRenderCount + 1,
                            message = strings().demoDrawn(item.renderHashShort),
                        )
                    }.onFailure { error ->
                        if (error is CancellationException) throw error
                        if (!isCurrentDrawingRun(runId)) return@onFailure
                        localState.value = localState.value.copy(
                            demoCurrentElapsedMs = System.currentTimeMillis() - startedAt,
                            message = error.message ?: "Demo failed.",
                        )
                        delay(1000)
                    }
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
        localState.value = localState.value.copy(isDrawing = false, demoWaitingSeconds = null, message = strings().statusStopped)
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
        // 「対象作品変更時は結果を破棄し、進行中の要求を中断する」(SPEC :616, :686,
        // :2143). The running job is cancelled first: a candidate that lands
        // after the target changed belongs to a work that is no longer here.
        refinementJob?.cancel()
        val previous = localState.value.refinementParent
        localState.value = localState.value.copy(
            refinementOpen = true,
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
            languageCompareSelectedCombos = if (previous?.id == item.id) localState.value.languageCompareSelectedCombos else emptyList(),
            modelCompareFixedModel = if (previous?.id == item.id) localState.value.modelCompareFixedModel else "",
            tab = AppTab.Lineage,
        )
    }

    fun setRefinementSubview(subview: RefinementSubview) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(
            refinementSubview = subview,
            refinementStatus = null,
            refinementCandidates = emptyList(),
            refinementPreviewId = null,
        )
    }

    /**
     * The comparison mode. Changing it re-seeds the fixed side with the target's
     * own model for that stage and drops the selection, the way web does
     * (`setModelCompareMode`, `state.svelte.ts:200-211`): the previous choices
     * were legal against a different pair.
     */
    fun setModelCompareMode(mode: ModelCompareMode) {
        if (localState.value.refinementBusy) return
        val parent = localState.value.refinementParent
        val fixed = when (mode) {
            ModelCompareMode.Stage1Fixed -> parent?.stage1Model.orEmpty()
            ModelCompareMode.Stage2Fixed -> parent?.stage2Model.orEmpty()
            ModelCompareMode.Common -> ""
        }
        localState.value = localState.value.copy(
            modelCompareMode = mode,
            modelCompareFixedModel = fixed,
            modelCompareSelectedModels = emptyList(),
            refinementCandidates = emptyList(),
            refinementPreviewId = null,
            refinementStatus = null,
        )
    }

    fun setModelCompareFixedModel(modelId: String) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(
            modelCompareFixedModel = modelId,
            refinementCandidates = emptyList(),
            refinementPreviewId = null,
            refinementStatus = null,
        )
    }

    /** 「固定モードでは固定側を1モデル、比較側を最大4モデル選ぶ」(SPEC `:616`). */
    fun toggleModelCompareSelection(modelId: String) {
        val current = localState.value
        if (current.refinementBusy) return
        val parent = current.refinementParent
        if (ComparisonPlanner.isModelChoiceBlocked(
                mode = current.modelCompareMode,
                fixedModel = current.modelCompareFixedModel,
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

    fun toggleLanguageCombo(comboId: String) {
        val current = localState.value
        if (current.refinementBusy) return
        val combo = LanguageCombo.byId(comboId) ?: return
        if (ComparisonPlanner.isLanguageComboBlocked(combo, targetInstructionLang(current.refinementParent))) {
            localState.value = current.copy(refinementStatus = LANGUAGE_COMBO_BLOCKED(strings()))
            return
        }
        val selected = current.languageCompareSelectedCombos
        val next = if (comboId in selected) selected - comboId else selected + comboId
        localState.value = current.copy(languageCompareSelectedCombos = next, refinementStatus = null)
    }

    /**
     * The language the target work was drawn in.
     *
     * web reads the resolved column and falls back to the UI language
     * (`languageInspectionTargetLang`, `state.svelte.ts:365-368`). This client
     * has no UI-language setting, so the fallback is the same `"ja"` its
     * instruction-language resolution uses.
     */
    private fun targetInstructionLang(parent: HistoryItemEntity?): String =
        parent?.instructionLangResolved
            ?.takeIf { it in InstructionLanguages.SUPPORTED }
            ?: InstructionLanguages.DEFAULT_LANG

    fun closeRefinement() {
        refinementJob?.cancel()
        localState.value = localState.value.copy(
            refinementOpen = false,
            refinementParent = null,
            refinementCandidates = emptyList(),
            refinementPreviewId = null,
            refinementBusy = false,
            refinementCanAbort = false,
            refinementStatus = null,
        )
    }

    /** The radio. One value replaces the previous one; two are not spellable. */
    fun setRefinementElement(element: RefinementElement) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(refinementElement = element, refinementStatus = null)
        // 「推敲要素の選択は前回値をブラウザに記憶する」.
        persistSetting(SETTING_KEY_REFINEMENT_ELEMENT, JSONObject().put("value", element.id).toString())
    }

    fun setRefinementAmplitude(amplitude: VariationAmplitude) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(refinementAmplitude = amplitude)
    }

    fun setRefinementTouchWords(value: String) {
        localState.value = localState.value.copy(refinementTouchWords = value, refinementStatus = null)
    }

    /**
     * 1 案 or 4 案. The count is kept independent of the element, as web keeps
     * its own pair: four touches is refused when the button is pressed, and a
     * count silently clamped here would make that refusal unreachable.
     */
    fun setRefinementCount(count: Int) {
        if (localState.value.refinementBusy) return
        localState.value = localState.value.copy(refinementCount = count.coerceIn(1, 4), refinementStatus = null)
    }

    /** One candidate's orders plus the two strings the grid shows it under. */
    private data class CandidateJob(val id: String, val label: String, val plan: RefinementPlan)

    /** A refusal the author has to read, not a failure: it carries the sentence. */
    // A refusal used to be its own exception carrying a finished sentence. It is
    // an InkuFailure now for the same reason every other message became one: the
    // sentence reaches the reader, so the language is chosen where it is shown.

    /**
     * What to draw, for whichever sub-view is showing.
     *
     * The three lists are built here and nowhere else, so the drawing loop below
     * has no idea which comparison it is running -- that is what stops the two
     * inspections from growing a second copy of it (SPEC `:688`).
     */
    private fun candidateJobs(current: InkuUiState, parent: RefinementParent): List<CandidateJob> =
        when (current.refinementSubview) {
            RefinementSubview.Adjust -> adjustJobs(current, parent)
            RefinementSubview.Model -> modelJobs(current, parent)
            RefinementSubview.Language -> languageJobs(current, parent)
        }

    private fun adjustJobs(current: InkuUiState, parent: RefinementParent): List<CandidateJob> {
        val element = current.refinementElement
        val count = current.refinementCount
        if (element == RefinementElement.Touch && current.refinementTouchWords.isBlank()) {
            inkuError { it.refinementTouchWordsRequired }
        }
        // The same words give the same seed, so four touch candidates would be
        // four copies. web refuses in the same place with the same sentence.
        if (count > RefinementPlanner.maxCandidates(element)) {
            throw InkuFailure(RefinementPlanner.TOUCH_FANOUT_REFUSAL)
        }
        val catalogIds = if (element == RefinementElement.Color) {
            RefinementPlanner.catalogCandidateIds(parent.catalogId, ColorCatalogs.all.map { it.id }, count)
        } else {
            emptyList()
        }
        return (0 until count).map { index ->
            CandidateJob(
                id = "${element.id}-$index",
                label = "${strings().refinementElementLabel(element.id)} ${index + 1}",
                plan = RefinementPlanner.plan(
                    element = element,
                    parent = parent,
                    amplitude = current.refinementAmplitude,
                    newCatalogId = catalogIds.getOrNull(index),
                    seedText = current.refinementTouchWords.takeIf { element == RefinementElement.Touch },
                ),
            )
        }
    }

    /**
     * 「比較対象はユーザーが明示的に選び、未選択モデルをfallback実行しない」(SPEC `:616`):
     * an empty selection draws nothing and says so.
     */
    private fun modelJobs(current: InkuUiState, parent: RefinementParent): List<CandidateJob> {
        val mode = current.modelCompareMode
        val fixed = current.modelCompareFixedModel
        if (mode != ModelCompareMode.Common && fixed.isBlank()) {
            throw InkuFailure(MODEL_FIXED_MISSING)
        }
        val chosen = current.modelCompareSelectedModels
            .take(MAX_COMPARE_SELECTION)
            .filterNot {
                ComparisonPlanner.isModelChoiceBlocked(
                    mode = mode,
                    fixedModel = fixed,
                    model = it,
                    targetStage1Model = current.refinementParent?.stage1Model.orEmpty(),
                    targetStage2Model = current.refinementParent?.stage2Model.orEmpty(),
                )
            }
        if (chosen.isEmpty()) throw InkuFailure(MODEL_SELECT_PROMPT)
        return chosen.map { model ->
            val plan = ComparisonPlanner.modelPlan(mode, fixed, model, parent)
            CandidateJob(
                id = "${mode.id}:${plan.stage1Model}:${plan.stage2Model}",
                label = model,
                plan = plan,
            )
        }
    }

    private fun languageJobs(current: InkuUiState, parent: RefinementParent): List<CandidateJob> {
        val targetLang = targetInstructionLang(current.refinementParent)
        val chosen = current.languageCompareSelectedCombos
            .mapNotNull { LanguageCombo.byId(it) }
            .filterNot { ComparisonPlanner.isLanguageComboBlocked(it, targetLang) }
        if (chosen.isEmpty()) throw InkuFailure(LANGUAGE_SELECT_PROMPT)
        return chosen.map { combo ->
            CandidateJob(
                id = combo.id,
                label = "${languageLabel(combo.stage1)} / ${languageLabel(combo.stage2)}",
                plan = ComparisonPlanner.languagePlan(combo, parent),
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
        // One entry point for all three sub-views: what differs between them is
        // the list of orders, not the drawing, the stopping or the saving.
        val jobs = try {
            candidateJobs(current, parent)
        } catch (refusal: InkuFailure) {
            localState.value = current.copy(refinementStatus = refusal.text(strings()))
            return
        }
        refinementJob?.cancel()
        localState.value = current.copy(
            refinementBusy = true,
            refinementCanAbort = false,
            refinementStatus = null,
            refinementCandidates = emptyList(),
            refinementPreviewId = null,
        )
        refinementJob = viewModelScope.launch {
            // The stop appears three seconds in, not at once: a candidate that
            // is already done needs no stop button.
            val abortTimer = launch {
                delay(3000)
                if (localState.value.refinementBusy) {
                    localState.value = localState.value.copy(refinementCanAbort = true)
                }
            }
            runCatching {
                val made = mutableListOf<RefinementCandidate>()
                jobs.forEach { job ->
                    val started = System.currentTimeMillis()
                    val result = withContext(Dispatchers.IO) {
                        repository.renderRefinementCandidate(parent, job.plan)
                    }
                    // 「対象作品変更時は結果を破棄し」: the target may have moved while
                    // this candidate was being drawn, and a result that arrives
                    // for a work nobody is looking at is thrown away rather than
                    // shown against the new one.
                    if (localState.value.refinementParent?.id != parentItem.id) return@forEach
                    made.add(
                        RefinementCandidate(
                            id = "${job.id}-${result.renderHash.takeLast(8)}",
                            label = job.label,
                            plan = job.plan,
                            displaySvg = result.displaySvg,
                            scoreJson = result.scoreJson,
                            normalizedDdl = result.normalizedDdl,
                            renderHash = result.renderHash,
                            renderHashShort = result.renderHashShort,
                            renderMetadataJson = result.renderMetadataJson,
                            elapsedMs = System.currentTimeMillis() - started,
                            stage1Model = job.plan.stage1Model ?: parent.stage1Model,
                            stage2Model = job.plan.stage2Model ?: parent.stage2Model,
                            instructionLangRequested = result.instructionLangRequested,
                            instructionLangResolved = result.instructionLangResolved,
                        ),
                    )
                    // Shown as they arrive, the way web fills its grid.
                    localState.value = localState.value.copy(refinementCandidates = made.toList())
                }
            }.onFailure { error ->
                if (error is CancellationException) throw error
                localState.value = localState.value.copy(refinementStatus = messageFor(error, strings(), strings().refinementFailed))
            }
            abortTimer.cancel()
            localState.value = localState.value.copy(refinementBusy = false, refinementCanAbort = false)
        }
        refinementJob?.invokeOnCompletion { cause ->
            if (cause is CancellationException) {
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
        val parentItem = current.refinementParent ?: return
        updateCandidate(candidateId) { it.copy(saveState = RefinementSaveState.Saving) }
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    saveCandidateRow(candidate, parentItem, historyVisibility = null)
                }
            }.onSuccess { item ->
                updateCandidate(candidateId) {
                    it.copy(
                        saveState = RefinementSaveState.Saved,
                        savedHistoryId = item.id,
                        savedNodeId = item.lineageNodeId,
                    )
                }
                localState.value = localState.value.copy(refinementStatus = strings().statusSaved(item.renderHashShort))
            }.onFailure { error ->
                updateCandidate(candidateId) { it.copy(saveState = RefinementSaveState.Unsaved) }
                localState.value = localState.value.copy(refinementStatus = messageFor(error, strings(), strings().statusSaveFailed))
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
    ): HistoryItemEntity = repository.saveRefinementCandidate(
        result = PaintResult(
            originalInput = sourceTextOf(parentItem),
            normalizedDdl = candidate.normalizedDdl,
            expandedDdl = candidate.normalizedDdl,
            scoreJson = candidate.scoreJson,
            displaySvg = candidate.displaySvg,
            renderMetadataJson = candidate.renderMetadataJson,
            renderHash = candidate.renderHash,
            renderHashShort = candidate.renderHashShort,
            renderSeed = candidate.plan.seeds.renderSeed ?: renderSeedOf(candidate.renderMetadataJson),
            compositionSeed = candidate.plan.seeds.compositionSeed,
            interpretationSeed = candidate.plan.seeds.interpretationSeed,
            variationAmplitude = candidate.plan.seeds.variationAmplitude,
            variationSeed = candidate.plan.seeds.variationSeed,
            seedText = candidate.plan.seeds.seedText,
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
                localState.value = localState.value.copy(message = error.message ?: "License update failed.")
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
        viewModelScope.launch {
            localState.value = localState.value.copy(message = strings().modelListFetching(providerId))
            runCatching {
                repository.fetchProviderModels(providerId)
            }.onSuccess { models ->
                val gemma31b = models.firstOrNull { it.equals("google/gemma-4-31b-it", ignoreCase = true) }
                val suffix = if (providerId == "nvidia" && gemma31b != null) strings().modelListNvidiaSuffix else ""
                localState.value = localState.value.copy(message = strings().modelListFetched(models.size, suffix))
            }.onFailure { error ->
                localState.value = localState.value.copy(message = messageFor(error, strings(), strings().modelListFetchFailed))
            }
        }
    }

    fun saveProviderSetting(
        providerId: String,
        displayName: String,
        kind: String,
        baseUrl: String,
        apiKey: String,
        publishedModelsText: String,
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
            }.onFailure { error ->
                localState.value = localState.value.copy(message = messageFor(error, strings(), strings().modelSettingsSaveFailed))
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
        if (modelDownloadJob?.isActive == true) {
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
                    repository.markModelDownloadCancelled(modelId)
                    localState.value = localState.value.copy(activeModelDownloadId = null, message = strings().modelDownloadCancelled)
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
        val modelId = state.value.activeModelDownloadId ?: state.value.selectedModelId
        modelDownloadJob?.cancel()
        modelDownloadJob = null
        viewModelScope.launch {
            repository.markModelDownloadCancelled(modelId)
            localState.value = localState.value.copy(activeModelDownloadId = null, message = strings().modelDownloadCancelled)
        }
    }

    fun toggleStar(item: HistoryItemEntity) {
        viewModelScope.launch {
            val nextStarred = !item.starred
            repository.setStarred(item.id, nextStarred)
            if (localState.value.selectedHistory?.id == item.id) {
                localState.value = localState.value.copy(selectedHistory = item.copy(starred = nextStarred))
            }
        }
    }

    fun toggleStar(item: HistoryListItem) {
        viewModelScope.launch {
            repository.setStarred(item.id, !item.starred)
        }
    }

    private fun validateSelectedModels(state: InkuUiState): String? {
        return listOf("Stage1" to state.selectedModelId, "Stage2" to state.selectedStage2ModelId)
            .distinctBy { it.second }
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
        val canvasPlugin = settings["canvas_aspect_plugin"]?.let { JSONObject(it).optBoolean("enabled", current.canvasAspectPluginEnabled) } ?: current.canvasAspectPluginEnabled
        val pngAlpha = settings["png_alpha_white"]?.let { JSONObject(it).optBoolean("enabled", current.pngAlphaWhite) } ?: current.pngAlphaWhite
        val replay = settings["save_replay_as_new_version"]?.let { JSONObject(it).optBoolean("enabled", current.saveReplayAsNewVersion) } ?: current.saveReplayAsNewVersion
        val histCanvas = settings["history_selection_canvas"]?.let { parseHistorySelection(JSONObject(it).optString("value")) } ?: current.historySelectionCanvas
        val histCatalog = settings["history_selection_catalog"]?.let { parseHistorySelection(JSONObject(it).optString("value")) } ?: current.historySelectionCatalog
        val ddlAutoRepair = settings["ddl_auto_repair"]?.let { JSONObject(it).optBoolean("enabled", current.ddlAutoRepairEnabled) } ?: current.ddlAutoRepairEnabled
        val litertPromptOptimization = settings["litert_stage1_prompt_optimization"]?.let { JSONObject(it).optBoolean("enabled", current.litertStage1PromptOptimization) } ?: current.litertStage1PromptOptimization
        val uiMode = settings["ui_mode"]?.let { JSONObject(it).optString("value", current.uiMode) } ?: current.uiMode
        // A stored code that is not one of the two falls back to Japanese
        // rather than being rejected -- the same thing the server does with an
        // unrecognised `ui_lang` (`api_core/common.py:68-70`).
        val uiLanguage = settings[SETTING_KEY_UI_LANGUAGE]
            ?.let { UiLanguage.fromCode(JSONObject(it).optString("value")) }
            ?: current.uiLanguage
        val mascotKind = settings[SETTING_KEY_MASCOT_KIND]?.let { JSONObject(it).optString("value", current.mascotKind) } ?: current.mascotKind
        val demoSeed = settings["demo_seed_phrase"]?.let { JSONObject(it).optString("value", current.demoSeed) } ?: current.demoSeed
        val demoInterval = settings["demo_interval_seconds"]?.let { JSONObject(it).optInt("value", current.demoIntervalSeconds) } ?: current.demoIntervalSeconds
        val batchHistory = settings["batch_prompt_history"]?.let { parseStringArray(JSONObject(it).optJSONArray("items")) } ?: current.batchPromptHistory
        // A stored word that is not one of the three is not the author's choice,
        // so the author's default stands rather than a silent `off`.
        val sketchMode = settings[SETTING_KEY_SKETCH_MODE]
            ?.let { stored -> Sketches.MODES.firstOrNull { it.wire == JSONObject(stored).optString("value") } }
            ?: current.sketchMode
        val refinementElement = settings[SETTING_KEY_REFINEMENT_ELEMENT]
            ?.let { RefinementElement.byId(JSONObject(it).optString("value")) }
            ?: current.refinementElement
        val modelSelection = settings["model_selection"]?.let(::JSONObject)
        val restoredStage1Model = modelSelection?.optString("stage1_model")?.takeIf { it.isNotBlank() }
        val restoredStage2Model = modelSelection?.optString("stage2_model")?.takeIf { it.isNotBlank() }
        val restoredUnifiedModel = restoredStage1Model ?: restoredStage2Model ?: current.selectedModelId
        val thinking = modelSelection?.optBoolean("include_thinking", current.includeThinking)
            ?: settings["include_thinking"]?.let { JSONObject(it).optBoolean("enabled", current.includeThinking) }
            ?: current.includeThinking
        localState.value = current.copy(
            selectedCatalogId = ColorCatalogs.get(catalog).id,
            selectedCanvasAspect = CanvasAspects.normalize(canvas),
            canvasAspectPluginEnabled = canvasPlugin,
            pngAlphaWhite = pngAlpha,
            saveReplayAsNewVersion = replay,
            historySelectionCanvas = histCanvas,
            historySelectionCatalog = histCatalog,
            ddlAutoRepairEnabled = ddlAutoRepair,
            litertStage1PromptOptimization = litertPromptOptimization,
            uiMode = uiMode,
            uiLanguage = uiLanguage,
            mascotKind = mascotKind,
            demoSeed = demoSeed,
            demoIntervalSeconds = demoInterval.coerceIn(1, 999),
            batchPromptHistory = batchHistory,
            sketchMode = sketchMode,
            refinementElement = refinementElement,
            includeThinking = thinking,
            selectedModelId = restoredUnifiedModel,
            selectedStage2ModelId = restoredUnifiedModel,
        )
        warmupLiteRtModels(restoredUnifiedModel)
    }

    private fun warmupLiteRtModels(vararg modelIds: String) {
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

    private fun parseHistorySelection(value: String): HistorySelectionBehavior {
        return if (value == "history") HistorySelectionBehavior.History else HistorySelectionBehavior.Current
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
