package app.inku.mobile.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import app.inku.mobile.InkuApplication
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.ExportTemplateEntity
import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.CompatibilityConstants
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import kotlin.random.Random

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
    val demoSeed: String = "春の光",
    val demoIntervalSeconds: Int = 30,
    val modelLicenseAccepted: Boolean = false,
    val modelDownloadState: String = "not downloaded",
    val modelAssets: List<ModelAssetEntity> = emptyList(),
    val providerSettings: List<ProviderSettingEntity> = emptyList(),
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
    val ddlAutoRepairEnabled: Boolean = true,
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
    Export,
    Misc,
    OutputFiles,
    ColorCatalog,
    Canvas,
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
    private val repository = InkuRepository(application.applicationContext, (application as InkuApplication).database)
    private val localState = MutableStateFlow(InkuUiState())
    private val history = repository.history()
    private val modelAssets = repository.modelAssets()
    private val providerSettings = repository.providerSettings()
    private val exportTemplates = repository.exportTemplates()
    private var modelDownloadJob: Job? = null
    private var drawingJob: Job? = null
    private var restoredInitialHistory = false
    private var promptEditedByUser = false
    private var modelSelectionSnapshot: Pair<String, String>? = null
    private var catalogSelectionSnapshot: String? = null

    val state: StateFlow<InkuUiState> = combine(localState, history, modelAssets, providerSettings, exportTemplates) { state, items, assets, providers, templates ->
        val selected = state.selectedHistory?.let { current ->
            items.firstOrNull { it.id == current.id }
        } ?: items.firstOrNull()
        val selectedModel = assets.firstOrNull { it.modelId == state.selectedModelId }
        val modelState = selectedModel?.let { modelStatusText(it) } ?: "model catalog initializing"
        state.copy(
            selectedHistory = selected,
            modelAssets = assets,
            providerSettings = providers,
            exportTemplates = templates,
            modelLicenseAccepted = selectedModel?.licenseAcceptedAt != null,
            modelDownloadState = modelState,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), InkuUiState())

    val historyItems: StateFlow<List<HistoryItemEntity>> = history.stateIn(
        viewModelScope,
        SharingStarted.WhileSubscribed(5000),
        emptyList(),
    )

    init {
        viewModelScope.launch {
            repository.ensureDefaultModelAssets()
            repository.ensureDefaultProviderSettings()
            repository.ensureDefaultExportTemplates()
            restorePersistedSettings()
        }
        viewModelScope.launch {
            val latest = history.first { it.isNotEmpty() }.first()
            val current = localState.value
            if (!restoredInitialHistory && !promptEditedByUser && current.selectedHistory == null) {
                restoredInitialHistory = true
                localState.value = current.copy(
                    selectedHistory = latest,
                    prompt = latest.originalInput,
                    ddl = latest.normalizedDdl,
                    ddlEditedAfterGeneration = false,
                    selectedCatalogId = latest.colorCatalogId,
                    selectedCanvasAspect = latest.canvasAspect,
                )
            }
        }
    }

    fun setPrompt(value: String) {
        promptEditedByUser = true
        localState.value = localState.value.copy(prompt = value, message = null)
    }

    fun clearPrompt() {
        if (state.value.isDrawing) return
        promptEditedByUser = true
        localState.value = localState.value.copy(prompt = "", message = null)
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
        localState.value = localState.value.copy(selectedModelId = modelId, message = null)
    }

    fun setStage1Model(modelId: String) {
        localState.value = localState.value.copy(selectedModelId = modelId, message = null)
    }

    fun setStage2Model(modelId: String) {
        localState.value = localState.value.copy(selectedStage2ModelId = modelId, message = null)
    }

    fun setIncludeThinking(enabled: Boolean) {
        localState.value = localState.value.copy(includeThinking = enabled)
        persistSetting("include_thinking", JSONObject().put("enabled", enabled).toString())
    }

    fun setTab(tab: AppTab) {
        val current = localState.value
        val restoredModelSelection = if (tab != AppTab.Settings && current.settingsPane == SettingsPane.ModelSelection) modelSelectionSnapshot else null
        val restoredCatalog = if (tab != AppTab.Settings && current.settingsPane == SettingsPane.ColorCatalog) catalogSelectionSnapshot else null
        if (restoredModelSelection != null) modelSelectionSnapshot = null
        if (restoredCatalog != null) catalogSelectionSnapshot = null
        localState.value = current.copy(
            tab = tab,
            selectedModelId = restoredModelSelection?.first ?: current.selectedModelId,
            selectedStage2ModelId = restoredModelSelection?.second ?: current.selectedStage2ModelId,
            selectedCatalogId = restoredCatalog ?: current.selectedCatalogId,
            settingsPane = if (tab == AppTab.Settings && current.tab != AppTab.Settings) {
                SettingsPane.Home
            } else if (tab == AppTab.Settings && current.settingsPane in setOf(SettingsPane.ModelSelection, SettingsPane.ColorCatalog, SettingsPane.Canvas)) {
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
        persistSetting("model_selection", JSONObject()
            .put("stage1_model", current.selectedModelId)
            .put("stage2_model", current.selectedStage2ModelId)
            .put("include_thinking", current.includeThinking)
            .toString())
        localState.value = current.copy(modelSelectionOpen = false, message = null)
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
        localState.value = localState.value.copy(canvasZoom = value.coerceIn(0.5f, 3.0f))
    }

    fun scaleCanvasZoom(multiplier: Float) {
        val current = localState.value
        localState.value = current.copy(canvasZoom = (current.canvasZoom * multiplier).coerceIn(0.5f, 3.0f))
    }

    fun resetCanvasZoom() {
        localState.value = localState.value.copy(canvasZoom = 1.0f, canvasPanX = 0f, canvasPanY = 0f)
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
        localState.value = current.copy(ddlAutoRepairEnabled = !current.ddlAutoRepairEnabled, message = null)
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

    private fun runSubmit(current: InkuUiState) {
        if (current.prompt.isBlank()) {
            localState.value = current.copy(message = "Prompt is empty.")
            return
        }
        drawingJob?.cancel()
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
                    )
                }
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
                    )
                }
            }.onSuccess { item ->
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
        drawingJob?.cancel()
        drawingJob = viewModelScope.launch {
            localState.value = localState.value.copy(isDrawing = true, message = "DDLからScoreを構成しています...")
            runCatching {
                withContext(Dispatchers.IO) {
                    repository.composeFromDdl(current.prompt, ddl, current.selectedCatalogId, current.selectedCanvasAspect, current.selectedModelId, current.selectedStage2ModelId, current.ddlAutoRepairEnabled)
                }
            }.onSuccess { item ->
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
        rememberBatchPrompt(current.batchText)
        drawingJob?.cancel()
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
                        )
                    }
                }.onSuccess { item ->
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

    fun runDemoOnce() {
        val current = state.value
        validateSelectedModels(current)?.let { message ->
            localState.value = localState.value.copy(message = message)
            return
        }
        val prompt = demoPrompt(current.demoSeed)
        drawingJob?.cancel()
        drawingJob = viewModelScope.launch {
            localState.value = localState.value.copy(isDrawing = true, message = "Demo drawing")
            runCatching {
                withContext(Dispatchers.IO) {
                    repository.paint(prompt, current.selectedCatalogId, current.selectedCanvasAspect, current.selectedModelId, current.selectedStage2ModelId, current.ddlAutoRepairEnabled)
                }
            }.onSuccess { item ->
                localState.value = localState.value.copy(
                    selectedHistory = item,
                    prompt = item.originalInput,
                    ddl = item.normalizedDdl,
                    ddlEditedAfterGeneration = false,
                    isDrawing = false,
                    message = "Demo rendered ${item.renderHashShort}",
                )
            }.onFailure { error ->
                val message = if (error is CancellationException) "停止しました。" else error.message ?: "Demo failed."
                localState.value = localState.value.copy(isDrawing = false, message = message)
            }
        }
    }

    fun stopDrawing() {
        drawingJob?.cancel()
        drawingJob = null
        localState.value = localState.value.copy(isDrawing = false, message = "停止しました。")
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
        downloadModel(state.value.selectedModelId)
    }

    fun downloadModel(modelId: String) {
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
            localState.value = localState.value.copy(activeModelDownloadId = modelId, message = "モデル取得を開始しています...")
            runCatching {
                repository.markModelDownloadQueued(modelId)
                repository.downloadModel(modelId)
            }.onSuccess {
                localState.value = localState.value.copy(activeModelDownloadId = null, message = "モデル取得が完了しました。")
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
            repository.setStarred(item.id, !item.starred)
        }
    }

    private fun demoPrompt(seed: String): String {
        val clean = seed.ifBlank { "静かな光" }
        val variants = listOf(
            "$clean の中に青い線を12本、波打つ軌跡に沿って置く",
            "$clean を赤い円5個と灰色の弧で散らす",
            "$clean から黒い細筆の線を3本、斜めに引く",
        )
        val index = ((System.currentTimeMillis() / 1000) % variants.size).toInt()
        return variants[index]
    }

    private fun validateSelectedModels(state: InkuUiState): String? {
        return listOf("Stage1" to state.selectedModelId, "Stage2" to state.selectedStage2ModelId)
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
        val catalog = repository.getSetting("color_catalog")?.let { JSONObject(it).optString("value", current.selectedCatalogId) } ?: current.selectedCatalogId
        val canvas = repository.getSetting("canvas_aspect")?.let { JSONObject(it).optString("value", current.selectedCanvasAspect) } ?: current.selectedCanvasAspect
        val canvasPlugin = repository.getSetting("canvas_aspect_plugin")?.let { JSONObject(it).optBoolean("enabled", current.canvasAspectPluginEnabled) } ?: current.canvasAspectPluginEnabled
        val pngAlpha = repository.getSetting("png_alpha_white")?.let { JSONObject(it).optBoolean("enabled", current.pngAlphaWhite) } ?: current.pngAlphaWhite
        val kiwi = repository.getSetting("show_kiwi")?.let { JSONObject(it).optBoolean("enabled", current.showKiwi) } ?: current.showKiwi
        val crab = repository.getSetting("show_crab")?.let { JSONObject(it).optBoolean("enabled", current.showCrab) } ?: current.showCrab
        val replay = repository.getSetting("save_replay_as_new_version")?.let { JSONObject(it).optBoolean("enabled", current.saveReplayAsNewVersion) } ?: current.saveReplayAsNewVersion
        val histCanvas = repository.getSetting("history_selection_canvas")?.let { parseHistorySelection(JSONObject(it).optString("value")) } ?: current.historySelectionCanvas
        val histCatalog = repository.getSetting("history_selection_catalog")?.let { parseHistorySelection(JSONObject(it).optString("value")) } ?: current.historySelectionCatalog
        val batchRandom = repository.getSetting("batch_random_color_catalog")?.let { JSONObject(it).optBoolean("enabled", current.batchRandomColorCatalog) } ?: current.batchRandomColorCatalog
        val batchHistory = repository.getSetting("batch_prompt_history")?.let { parseStringArray(JSONObject(it).optJSONArray("items")) } ?: current.batchPromptHistory
        val modelSelection = repository.getSetting("model_selection")?.let(::JSONObject)
        val thinking = modelSelection?.optBoolean("include_thinking", current.includeThinking)
            ?: repository.getSetting("include_thinking")?.let { JSONObject(it).optBoolean("enabled", current.includeThinking) }
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
            batchRandomColorCatalog = batchRandom,
            batchPromptHistory = batchHistory,
            includeThinking = thinking,
            selectedModelId = modelSelection?.optString("stage1_model", current.selectedModelId)?.takeIf { it.isNotBlank() } ?: current.selectedModelId,
            selectedStage2ModelId = modelSelection?.optString("stage2_model", current.selectedStage2ModelId)?.takeIf { it.isNotBlank() } ?: current.selectedStage2ModelId,
        )
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
