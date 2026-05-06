package app.inku.mobile.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import app.inku.mobile.InkuApplication
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.CompatibilityConstants
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class InkuUiState(
    val prompt: String = "青い鉛筆の線を12本、波打つ軌跡に沿って散らす",
    val ddl: String = "",
    val batchText: String = "赤い円を5個、横に並べる\n黒い太筆の線を3本、斜めに置く\n緑の四角を12個、散らす",
    val demoSeed: String = "春の光",
    val demoIntervalSeconds: Int = 30,
    val modelLicenseAccepted: Boolean = false,
    val modelDownloadState: String = "not downloaded",
    val modelAssets: List<ModelAssetEntity> = emptyList(),
    val selectedModelId: String = CompatibilityConstants.defaultStage1Model,
    val selectedCatalogId: String = "default",
    val selectedCanvasAspect: String = "square",
    val selectedHistory: HistoryItemEntity? = null,
    val isDrawing: Boolean = false,
    val message: String? = null,
    val tab: AppTab = AppTab.Draw,
    val renderTab: RenderTab = RenderTab.Artwork,
)

enum class AppTab {
    Draw,
    Batch,
    Demo,
    History,
    Settings,
}

enum class RenderTab {
    Artwork,
    Prompt,
    Json,
}

class InkuViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = InkuRepository(application.applicationContext, (application as InkuApplication).database)
    private val localState = MutableStateFlow(InkuUiState())
    private val history = repository.history()
    private val modelAssets = repository.modelAssets()
    private var modelDownloadJob: Job? = null

    val state: StateFlow<InkuUiState> = combine(localState, history, modelAssets) { state, items, assets ->
        val selected = state.selectedHistory?.let { current ->
            items.firstOrNull { it.id == current.id }
        } ?: items.firstOrNull()
        val selectedModel = assets.firstOrNull { it.modelId == state.selectedModelId }
        val modelState = selectedModel?.let { modelStatusText(it) } ?: "model catalog initializing"
        if (state.selectedHistory == null && selected != null) {
            state.copy(
                selectedHistory = selected,
                prompt = selected.originalInput,
                ddl = selected.normalizedDdl,
                selectedCatalogId = selected.colorCatalogId,
                selectedCanvasAspect = selected.canvasAspect,
                modelAssets = assets,
                modelLicenseAccepted = selectedModel?.licenseAcceptedAt != null,
                modelDownloadState = modelState,
            )
        } else {
            state.copy(
                selectedHistory = selected,
                modelAssets = assets,
                modelLicenseAccepted = selectedModel?.licenseAcceptedAt != null,
                modelDownloadState = modelState,
            )
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), InkuUiState())

    val historyItems: StateFlow<List<HistoryItemEntity>> = history.stateIn(
        viewModelScope,
        SharingStarted.WhileSubscribed(5000),
        emptyList(),
    )

    init {
        viewModelScope.launch {
            repository.ensureDefaultModelAssets()
        }
    }

    fun setPrompt(value: String) {
        localState.value = localState.value.copy(prompt = value, message = null)
    }

    fun setDdl(value: String) {
        localState.value = localState.value.copy(ddl = value, message = null)
    }

    fun setBatchText(value: String) {
        localState.value = localState.value.copy(batchText = value, message = null)
    }

    fun setDemoSeed(value: String) {
        localState.value = localState.value.copy(demoSeed = value, message = null)
    }

    fun setCatalog(id: String) {
        localState.value = localState.value.copy(selectedCatalogId = ColorCatalogs.get(id).id)
    }

    fun setCanvasAspect(id: String) {
        localState.value = localState.value.copy(selectedCanvasAspect = CanvasAspects.normalize(id))
    }

    fun setSelectedModel(modelId: String) {
        localState.value = localState.value.copy(selectedModelId = modelId, message = null)
    }

    fun setTab(tab: AppTab) {
        localState.value = localState.value.copy(tab = tab)
    }

    fun setRenderTab(tab: RenderTab) {
        localState.value = localState.value.copy(renderTab = tab)
    }

    fun selectHistory(item: HistoryItemEntity) {
        localState.value = localState.value.copy(
            selectedHistory = item,
            prompt = item.originalInput,
            ddl = item.normalizedDdl,
            selectedCatalogId = item.colorCatalogId,
            selectedCanvasAspect = item.canvasAspect,
            tab = AppTab.Draw,
        )
    }

    fun draw() {
        val current = localState.value
        if (current.prompt.isBlank()) {
            localState.value = current.copy(message = "Prompt is empty.")
            return
        }
        viewModelScope.launch {
            localState.value = localState.value.copy(isDrawing = true, message = null)
            runCatching {
                repository.paint(current.prompt, current.selectedCatalogId, current.selectedCanvasAspect, current.selectedModelId)
            }.onSuccess { item ->
                localState.value = localState.value.copy(
                    ddl = item.normalizedDdl,
                    selectedHistory = item,
                    isDrawing = false,
                    message = "Rendered ${item.renderHashShort}",
                )
            }.onFailure { error ->
                localState.value = localState.value.copy(isDrawing = false, message = error.message ?: "Draw failed.")
            }
        }
    }

    fun drawFromDdl() {
        val current = localState.value
        val ddl = current.ddl.ifBlank { current.prompt }
        viewModelScope.launch {
            localState.value = localState.value.copy(isDrawing = true, message = null)
            runCatching {
                repository.composeFromDdl(current.prompt, ddl, current.selectedCatalogId, current.selectedCanvasAspect, current.selectedModelId)
            }.onSuccess { item ->
                localState.value = localState.value.copy(
                    ddl = item.normalizedDdl,
                    selectedHistory = item,
                    isDrawing = false,
                    message = "Composed ${item.renderHashShort}",
                )
            }.onFailure { error ->
                localState.value = localState.value.copy(isDrawing = false, message = error.message ?: "Compose failed.")
            }
        }
    }

    fun runBatch() {
        val current = localState.value
        val prompts = current.batchText.lines().map { it.trim() }.filter { it.isNotBlank() }
        if (prompts.isEmpty()) {
            localState.value = current.copy(message = "Batch is empty.")
            return
        }
        viewModelScope.launch {
            localState.value = localState.value.copy(isDrawing = true, message = "Batch running: 0/${prompts.size}")
            var last: HistoryItemEntity? = null
            prompts.forEachIndexed { index, prompt ->
                last = repository.paint(prompt, current.selectedCatalogId, current.selectedCanvasAspect, current.selectedModelId)
                localState.value = localState.value.copy(message = "Batch running: ${index + 1}/${prompts.size}")
            }
            localState.value = localState.value.copy(
                selectedHistory = last,
                ddl = last?.normalizedDdl.orEmpty(),
                prompt = last?.originalInput ?: current.prompt,
                isDrawing = false,
                message = "Batch completed: ${prompts.size}",
            )
        }
    }

    fun runDemoOnce() {
        val current = localState.value
        val prompt = demoPrompt(current.demoSeed)
        viewModelScope.launch {
            localState.value = localState.value.copy(isDrawing = true, message = "Demo drawing")
            runCatching {
                repository.paint(prompt, current.selectedCatalogId, current.selectedCanvasAspect, current.selectedModelId)
            }.onSuccess { item ->
                localState.value = localState.value.copy(
                    selectedHistory = item,
                    prompt = item.originalInput,
                    ddl = item.normalizedDdl,
                    isDrawing = false,
                    message = "Demo rendered ${item.renderHashShort}",
                )
            }.onFailure { error ->
                localState.value = localState.value.copy(isDrawing = false, message = error.message ?: "Demo failed.")
            }
        }
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

    fun downloadDefaultModel() {
        downloadModel(state.value.selectedModelId)
    }

    fun downloadModel(modelId: String) {
        val current = state.value
        val selectedModel = current.modelAssets.firstOrNull { it.modelId == modelId }
        if (selectedModel?.licenseAcceptedAt == null) {
            localState.value = localState.value.copy(selectedModelId = modelId, message = "先に${selectedModel?.displayName ?: "Gemma"}のライセンス同意を押してください。")
            return
        }
        if (modelDownloadJob?.isActive == true) {
            localState.value = localState.value.copy(message = "モデル取得はすでに実行中です。")
            return
        }
        modelDownloadJob = viewModelScope.launch {
            localState.value = localState.value.copy(selectedModelId = modelId, message = "モデル取得を開始しています...")
            runCatching {
                repository.markModelDownloadQueued(modelId)
                repository.downloadModel(modelId)
            }.onSuccess {
                localState.value = localState.value.copy(message = "モデル取得が完了しました。")
            }.onFailure { error ->
                if (error is CancellationException) {
                    repository.markModelDownloadCancelled(modelId)
                    localState.value = localState.value.copy(message = "モデル取得を中断しました。")
                } else {
                    repository.markModelDownloadFailed(modelId, "failed")
                    localState.value = localState.value.copy(message = error.message ?: "モデル取得に失敗しました。")
                }
            }
        }
    }

    fun cancelModelDownload() {
        val modelId = state.value.selectedModelId
        modelDownloadJob?.cancel()
        modelDownloadJob = null
        viewModelScope.launch {
            repository.markModelDownloadCancelled(modelId)
            localState.value = localState.value.copy(message = "モデル取得を中断しました。")
        }
    }

    fun toggleStar(item: HistoryItemEntity) {
        viewModelScope.launch {
            repository.setStarred(item.id, !item.starred)
        }
    }

    fun trash(item: HistoryItemEntity) {
        viewModelScope.launch {
            repository.trash(item.id)
            localState.value = localState.value.copy(selectedHistory = null)
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
