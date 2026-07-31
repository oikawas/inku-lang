package app.inku.mobile.ui

import android.app.Application
import android.os.SystemClock
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import app.inku.mobile.InkuApplication
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.HistoryListItem
import app.inku.mobile.data.db.ExportTemplateEntity
import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.CompatibilityConstants
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
import org.json.JSONArray
import org.json.JSONObject
import kotlin.random.Random

const val DefaultDemoSeedPhrase = "世界の人と動物、自然と都市を主題として96文字の短文を作って。感情豊かに、季節や、人生と人のつながり、人生、世代、神。色々な観点から。"
const val DemoCanvasAspectId = "pixel9_landscape_safe"
private const val MaxBatchItems = 100
private const val MaxDemoCycles = 100

data class InkuUiState(
    val prompt: String = "青い鉛筆の線を12本、波打つ軌跡に沿って散らす",
    val ddl: String = "",
    val ddlEditedAfterGeneration: Boolean = false,
    val confirmDdlOverwrite: Boolean = false,
    val batchText: String = "赤い円を5個、横に並べる\n黒い太筆の線を3本、斜めに置く\n緑の四角を12個、散らす",
    val batchPromptHistory: List<String> = emptyList(),
    val batchRandomColorCatalog: Boolean = false,
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
    val demoRandomColorCatalog: Boolean = true,
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
    val historySearchQuery: String = "",
    val historyStarredOnly: Boolean = false,
    val canvasAspectPluginEnabled: Boolean = true,
    val pngAlphaWhite: Boolean = false,
    val showKiwi: Boolean = true,
    val showCrab: Boolean = false,
    val saveReplayAsNewVersion: Boolean = true,
    val historySelectionCanvas: HistorySelectionBehavior = HistorySelectionBehavior.Current,
    val historySelectionCatalog: HistorySelectionBehavior = HistorySelectionBehavior.Current,
    val ddlAutoRepairEnabled: Boolean = false,
    val litertStage1PromptOptimization: Boolean = false,
    val saijikiOpen: Boolean = false,
    val ddlEditorOpen: Boolean = false,
    val isDrawing: Boolean = false,
    val message: String? = null,
    val tab: AppTab = AppTab.Compose,
    val settingsPane: SettingsPane = SettingsPane.Home,
    val composeMode: ComposeMode = ComposeMode.Write,
    val renderTab: RenderTab = RenderTab.Artwork,
    val canvasZoom: Float = 1.0f,
    val canvasPanX: Float = 0f,
    val canvasPanY: Float = 0f,
    val canvasPresentationMode: Boolean = false,
    val renderWild: Boolean = false,
)

data class BatchFailure(
    val line: Int,
    val input: String,
    val message: String,
)

enum class AppTab {
    Compose,
    History,
    Demo,
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

class InkuViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = InkuRepository(application.applicationContext, (application as? InkuApplication)?.database ?: app.inku.mobile.data.db.InkuDatabase.open(application))
    private val localState = MutableStateFlow(InkuUiState())
    private val history = repository.history()
    private val modelAssets = repository.modelAssets()
    private val providerSettings = repository.providerSettings()
    private val providerModelCandidates = repository.providerModelCandidates()
    private val exportTemplates = repository.exportTemplates()
    private var modelDownloadJob: Job? = null
    private var drawingJob: Job? = null
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
            val current = localState.value
            if (!restoredInitialHistory && !promptEditedByUser && current.selectedHistory == null) {
                repository.getHistoryById(latest.id)?.let { full ->
                    restoredInitialHistory = true
                    localState.value = current.copy(
                        selectedHistory = full,
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

    fun setBatchRandomColorCatalog(enabled: Boolean) {
        localState.value = localState.value.copy(batchRandomColorCatalog = enabled)
        persistSetting("batch_random_color_catalog", JSONObject().put("enabled", enabled).toString())
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

    fun setDemoRandomColorCatalog(enabled: Boolean) {
        localState.value = localState.value.copy(demoRandomColorCatalog = enabled)
        persistSetting("demo_random_color_catalog", JSONObject().put("enabled", enabled).toString())
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

    fun setRenderTab(tab: RenderTab) {
        localState.value = localState.value.copy(renderTab = tab)
    }

    fun setCanvasZoom(value: Float) {
        localState.value = localState.value.copy(canvasZoom = value.coerceIn(0.5f, 8.0f), canvasPresentationMode = false)
    }

    fun scaleCanvasZoom(multiplier: Float) {
        val current = localState.value
        localState.value = current.copy(canvasZoom = (current.canvasZoom * multiplier).coerceIn(0.5f, 8.0f))
    }

    fun resetCanvasZoom() {
        localState.value = localState.value.copy(canvasZoom = 1.0f, canvasPanX = 0f, canvasPanY = 0f, canvasPresentationMode = false)
    }

    fun enterCanvasPresentationMode() {
        localState.value = localState.value.copy(
            canvasZoom = 1.0f,
            canvasPanX = 0f,
            canvasPanY = 0f,
            canvasPresentationMode = true,
        )
    }

    fun panCanvas(dx: Float, dy: Float) {
        val current = localState.value
        if (current.canvasZoom <= 1.0f) return
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

    fun setShowKiwi(enabled: Boolean) {
        localState.value = localState.value.copy(showKiwi = enabled)
        persistSetting("show_kiwi", JSONObject().put("enabled", enabled).toString())
    }

    fun setRenderWild(wild: Boolean) {
        localState.value = localState.value.copy(renderWild = wild)
    }

    fun setShowCrab(enabled: Boolean) {
        localState.value = localState.value.copy(showCrab = enabled)
        persistSetting("show_crab", JSONObject().put("enabled", enabled).toString())
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
                description = "PNG / Y軸 2160px",
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

    fun closeDdlEditor() {
        localState.value = localState.value.copy(ddlEditorOpen = false)
    }

    fun selectHistory(item: HistoryItemEntity) {
        restoredInitialHistory = true
        promptEditedByUser = false
        localState.value = localState.value.copy(
            selectedHistory = item,
            prompt = item.originalInput,
            ddl = item.normalizedDdl,
            ddlEditedAfterGeneration = false,
            confirmDdlOverwrite = false,
            selectedCatalogId = item.colorCatalogId,
            selectedCanvasAspect = item.canvasAspect,
            tab = AppTab.Compose,
            composeMode = ComposeMode.Write,
        )
    }

    fun selectHistory(item: HistoryListItem) {
        viewModelScope.launch {
            repository.getHistoryById(item.id)?.let { selectHistory(it) }
        }
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

    private fun runSubmit(current: InkuUiState) {
        if (current.prompt.isBlank()) {
            localState.value = current.copy(message = "Prompt is empty.")
            return
        }
        val runId = beginDrawingRun()
        drawingJob = viewModelScope.launch {
            localState.value = localState.value.copy(
                isDrawing = true,
                selectedHistory = null,
                ddl = "",
                ddlEditedAfterGeneration = false,
                confirmDdlOverwrite = false,
                message = "Stage 1: DDL生成中...",
            )
            runCatching {
                val interpreted = withContext(Dispatchers.IO) {
                    repository.interpret(
                        current.prompt,
                        current.selectedCatalogId,
                        current.selectedCanvasAspect,
                        current.selectedModelId,
                        current.selectedStage2ModelId,
                        current.ddlAutoRepairEnabled,
                        current.litertStage1PromptOptimization,
                    )
                }
                if (!isCurrentDrawingRun(runId)) return@launch
                localState.value = localState.value.copy(
                    ddl = interpreted.ddlForDisplay,
                    ddlEditedAfterGeneration = false,
                    message = "Stage 2: 画像生成中...",
                )
                withContext(Dispatchers.IO) {
                    repository.composeFromDdl(
                        current.prompt,
                        interpreted.ddlForDisplay,
                        current.selectedCatalogId,
                        current.selectedCanvasAspect,
                        current.selectedModelId,
                        current.selectedStage2ModelId,
                        current.ddlAutoRepairEnabled,
                        current.litertStage1PromptOptimization,
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
                    isDrawing = false,
                    message = "Rendered ${item.renderHashShort}",
                )
            }.onFailure { error ->
                if (!isCurrentDrawingRun(runId)) return@onFailure
                val message = if (error is CancellationException) "停止しました。" else error.message ?: "Draw failed."
                localState.value = localState.value.copy(isDrawing = false, message = message)
            }
        }
    }

    fun drawFromDdl() {
        val current = state.value
        validateSelectedModels(current)?.let { message ->
            localState.value = localState.value.copy(message = message)
            return
        }
        val ddl = current.ddl.ifBlank { current.prompt }
        val runId = beginDrawingRun()
        drawingJob = viewModelScope.launch {
            localState.value = localState.value.copy(isDrawing = true, message = "DDLからScoreを構成しています...")
            runCatching {
                withContext(Dispatchers.IO) {
                    repository.composeFromDdl(current.prompt, ddl, current.selectedCatalogId, current.selectedCanvasAspect, current.selectedModelId, current.selectedStage2ModelId, current.ddlAutoRepairEnabled, current.litertStage1PromptOptimization)
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
                    isDrawing = false,
                    message = "Composed ${item.renderHashShort}",
                )
            }.onFailure { error ->
                if (!isCurrentDrawingRun(runId)) return@onFailure
                val message = if (error is CancellationException) "停止しました。" else error.message ?: "Compose failed."
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
            localState.value = current.copy(message = "バッチは最大 ${MaxBatchItems} 件までです。現在: ${lines.size} 件")
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
                    message = "Batch running: ${index + 1}/${lines.size}",
                )
                runCatching {
                    val catalogId = if (current.batchRandomColorCatalog) randomColorCatalogId() else current.selectedCatalogId
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
                        )
                    }
                }.onSuccess { item ->
                    if (!isCurrentDrawingRun(runId)) return@onSuccess
                    success += 1
                    last = item
                    localState.value = localState.value.copy(
                        selectedHistory = item,
                        ddl = item.normalizedDdl,
                        ddlEditedAfterGeneration = false,
                        batchSuccess = success,
                        batchFailures = failures,
                        batchActiveDdl = item.normalizedDdl,
                        batchActiveElapsedMs = System.currentTimeMillis() - itemStartedAt,
                        batchElapsedMs = System.currentTimeMillis() - startedAt,
                        batchLatestHashShort = item.renderHashShort,
                        message = "Batch running: ${index + 1}/${lines.size}",
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
                        message = "Batch running: ${index + 1}/${lines.size}",
                    )
                }
            }
            if (!isCurrentDrawingRun(runId)) return@launch
            localState.value = localState.value.copy(
                selectedHistory = last,
                ddl = last?.normalizedDdl.orEmpty(),
                ddlEditedAfterGeneration = false,
                prompt = last?.originalInput?.removePrefix("#${localState.value.batchActiveLine} ") ?: current.prompt,
                isDrawing = false,
                batchCurrent = 0,
                batchActiveLine = null,
                batchActiveDdl = null,
                batchActiveElapsedMs = null,
                batchElapsedMs = System.currentTimeMillis() - startedAt,
                message = "Batch completed: 成功 $success / 失敗 ${failures.size} / 全 ${lines.size}",
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

    private fun randomColorCatalogId(): String {
        val ids = ColorCatalogs.all.map { it.id }
        return ids[Random.nextInt(ids.size)]
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
                message = "デモ実行中",
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
                        message = "デモ指示文生成中",
                    )
                    val prompt = withContext(Dispatchers.IO) {
                        repository.generateDemoPrompt(cycle.demoSeed, cycle.selectedModelId)
                    }
                    if (!isCurrentDrawingRun(runId)) return@launch
                    val catalogId = randomColorCatalogId()
                    localState.value = localState.value.copy(
                        demoGeneratedPrompt = prompt,
                        demoGeneratedDdl = null,
                        demoCurrentCatalogId = catalogId,
                        demoWaitingSeconds = null,
                        demoCurrentElapsedMs = null,
                        message = "デモ描画中",
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
                                historyInput = "[demo] $prompt",
                                litertStage1PromptOptimization = cycle.litertStage1PromptOptimization,
                            )
                        }
                    }.onSuccess { item ->
                        if (!isCurrentDrawingRun(runId)) return@onSuccess
                        val elapsed = System.currentTimeMillis() - startedAt
                        val latest = localState.value
                        localState.value = latest.copy(
                            selectedHistory = item,
                            prompt = item.originalInput.removePrefix("[demo] "),
                            ddl = item.normalizedDdl,
                            ddlEditedAfterGeneration = false,
                            demoGeneratedDdl = item.normalizedDdl,
                            demoCurrentElapsedMs = elapsed,
                            demoTotalElapsedMs = latest.demoTotalElapsedMs + elapsed,
                            demoRenderCount = latest.demoRenderCount + 1,
                            message = "デモ描画完了 ${item.renderHashShort}",
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
                        localState.value = localState.value.copy(demoWaitingSeconds = left, message = "次の描画まで ${left}秒")
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
                        message = if (reachedLimit) "デモ上限 ${MaxDemoCycles} 件で停止しました。" else "停止しました。",
                    )
                }
            }
        }
    }

    fun stopDrawing() {
        drawingRunSerial += 1
        drawingJob?.cancel()
        drawingJob = null
        localState.value = localState.value.copy(isDrawing = false, demoWaitingSeconds = null, message = "停止しました。")
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
                localState.value = localState.value.copy(message = "ローカルモデルカタログを更新しました。")
            }.onFailure { error ->
                localState.value = localState.value.copy(message = error.message ?: "モデルリスト取得に失敗しました。")
            }
        }
    }

    fun fetchProviderModels(providerId: String) {
        viewModelScope.launch {
            localState.value = localState.value.copy(message = "$providerId のモデルリストを取得しています...")
            runCatching {
                repository.fetchProviderModels(providerId)
            }.onSuccess { models ->
                val gemma31b = models.firstOrNull { it.equals("google/gemma-4-31b-it", ignoreCase = true) }
                val suffix = if (providerId == "nvidia" && gemma31b != null) " Gemma-4-31bを選択できます。" else ""
                localState.value = localState.value.copy(message = "${models.size}件のモデルを取得しました。$suffix")
            }.onFailure { error ->
                localState.value = localState.value.copy(message = error.message ?: "モデルリスト取得に失敗しました。")
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
                localState.value = localState.value.copy(message = "モデル設定を保存しました。")
            }.onFailure { error ->
                localState.value = localState.value.copy(message = error.message ?: "モデル設定の保存に失敗しました。")
            }
        }
    }

    fun clearProviderApiKey(providerId: String) {
        viewModelScope.launch {
            runCatching {
                repository.clearProviderApiKey(providerId)
            }.onSuccess {
                localState.value = localState.value.copy(message = "APIキーを削除しました。")
            }.onFailure { error ->
                localState.value = localState.value.copy(message = error.message ?: "APIキー削除に失敗しました。")
            }
        }
    }

    fun deleteProvider(providerId: String) {
        viewModelScope.launch {
            runCatching {
                repository.deleteProvider(providerId)
            }.onSuccess {
                localState.value = localState.value.copy(message = "サービスを削除しました。")
            }.onFailure { error ->
                localState.value = localState.value.copy(message = error.message ?: "サービス削除に失敗しました。")
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
            localState.value = localState.value.copy(message = "先に${selectedModel?.displayName ?: "Gemma"}のライセンス同意を押してください。")
            return
        }
        if (modelDownloadJob?.isActive == true) {
            localState.value = localState.value.copy(message = "モデル取得はすでに実行中です。")
            return
        }
        modelDownloadJob = viewModelScope.launch {
            localState.value = localState.value.copy(
                activeModelDownloadId = modelId,
                message = if (force) "モデルを再取得しています..." else "モデル取得を開始しています...",
            )
            runCatching {
                repository.markModelDownloadQueued(modelId)
                repository.downloadModel(modelId, force = force)
            }.onSuccess {
                localState.value = localState.value.copy(
                    activeModelDownloadId = null,
                    message = if (force) "モデル再取得が完了しました。" else "モデル取得が完了しました。",
                )
                warmupLiteRtModels(modelId)
            }.onFailure { error ->
                if (error is CancellationException) {
                    repository.markModelDownloadCancelled(modelId)
                    localState.value = localState.value.copy(activeModelDownloadId = null, message = "モデル取得を中断しました。")
                } else {
                    repository.markModelDownloadFailed(modelId, "failed")
                    localState.value = localState.value.copy(activeModelDownloadId = null, message = error.message ?: "モデル取得に失敗しました。")
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
            localState.value = localState.value.copy(activeModelDownloadId = null, message = "モデル取得を中断しました。")
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
                    ?: return@firstNotNullOfOrNull "$stage のローカルモデル情報がありません: $modelId"
                if (asset.downloadState != "ready") {
                    "$stage の ${asset.displayName} は未取得です。モデル設定で取得を完了してください。現在: ${asset.downloadState}"
                } else {
                    null
                }
            }
    }

    private suspend fun restorePersistedSettings() {
        val current = localState.value
        val settings = repository.getSettingsMap()
        val catalog = settings["color_catalog"]?.let { JSONObject(it).optString("value", current.selectedCatalogId) } ?: current.selectedCatalogId
        val canvas = settings["canvas_aspect"]?.let { JSONObject(it).optString("value", current.selectedCanvasAspect) } ?: current.selectedCanvasAspect
        val canvasPlugin = settings["canvas_aspect_plugin"]?.let { JSONObject(it).optBoolean("enabled", current.canvasAspectPluginEnabled) } ?: current.canvasAspectPluginEnabled
        val pngAlpha = settings["png_alpha_white"]?.let { JSONObject(it).optBoolean("enabled", current.pngAlphaWhite) } ?: current.pngAlphaWhite
        val kiwi = settings["show_kiwi"]?.let { JSONObject(it).optBoolean("enabled", current.showKiwi) } ?: current.showKiwi
        val crab = settings["show_crab"]?.let { JSONObject(it).optBoolean("enabled", current.showCrab) } ?: current.showCrab
        val replay = settings["save_replay_as_new_version"]?.let { JSONObject(it).optBoolean("enabled", current.saveReplayAsNewVersion) } ?: current.saveReplayAsNewVersion
        val histCanvas = settings["history_selection_canvas"]?.let { parseHistorySelection(JSONObject(it).optString("value")) } ?: current.historySelectionCanvas
        val histCatalog = settings["history_selection_catalog"]?.let { parseHistorySelection(JSONObject(it).optString("value")) } ?: current.historySelectionCatalog
        val ddlAutoRepair = settings["ddl_auto_repair"]?.let { JSONObject(it).optBoolean("enabled", current.ddlAutoRepairEnabled) } ?: current.ddlAutoRepairEnabled
        val litertPromptOptimization = settings["litert_stage1_prompt_optimization"]?.let { JSONObject(it).optBoolean("enabled", current.litertStage1PromptOptimization) } ?: current.litertStage1PromptOptimization
        val batchRandom = settings["batch_random_color_catalog"]?.let { JSONObject(it).optBoolean("enabled", current.batchRandomColorCatalog) } ?: current.batchRandomColorCatalog
        val demoSeed = settings["demo_seed_phrase"]?.let { JSONObject(it).optString("value", current.demoSeed) } ?: current.demoSeed
        val demoInterval = settings["demo_interval_seconds"]?.let { JSONObject(it).optInt("value", current.demoIntervalSeconds) } ?: current.demoIntervalSeconds
        val demoRandom = true
        val batchHistory = settings["batch_prompt_history"]?.let { parseStringArray(JSONObject(it).optJSONArray("items")) } ?: current.batchPromptHistory
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
            showKiwi = kiwi,
            showCrab = crab,
            saveReplayAsNewVersion = replay,
            historySelectionCanvas = histCanvas,
            historySelectionCatalog = histCatalog,
            ddlAutoRepairEnabled = ddlAutoRepair,
            litertStage1PromptOptimization = litertPromptOptimization,
            batchRandomColorCatalog = batchRandom,
            demoSeed = demoSeed,
            demoIntervalSeconds = demoInterval.coerceIn(1, 999),
            demoRandomColorCatalog = demoRandom,
            batchPromptHistory = batchHistory,
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
