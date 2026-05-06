package app.inku.mobile.data

import android.content.Context
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.llm.DefaultModelDownloads
import app.inku.mobile.llm.LocalModelDownloader
import app.inku.mobile.llm.ModelDownloadSpec
import app.inku.mobile.pipeline.LocalFallbackPipeline
import app.inku.mobile.pipeline.PaintRequest
import app.inku.mobile.pipeline.PaintResult
import kotlinx.coroutines.flow.Flow

class InkuRepository(
    private val context: Context,
    private val database: InkuDatabase,
    private val pipeline: LocalFallbackPipeline = LocalFallbackPipeline(),
) {
    private val modelDownloader = LocalModelDownloader(context.applicationContext, database.modelAssetDao())

    fun history(): Flow<List<HistoryItemEntity>> = database.historyDao().listActive(100, 0)

    fun modelAssets(): Flow<List<ModelAssetEntity>> = database.modelAssetDao().observeAll()

    suspend fun ensureDefaultModelAssets() {
        DefaultModelDownloads.all.forEach { spec ->
            val existing = database.modelAssetDao().getByModelId(spec.modelId)
            val downloadState = when (existing?.downloadState) {
                "queued", "connecting", "downloading", "verifying" -> "interrupted"
                null -> "license_required"
                else -> existing.downloadState
            }
            database.modelAssetDao().upsert(
                ModelAssetEntity(
                    id = existing?.id ?: spec.modelId,
                    providerId = "local-litert-lm",
                    modelId = spec.modelId,
                    displayName = spec.displayName,
                    qualityTier = spec.qualityTier,
                    downloadUrl = spec.downloadUrl,
                    licenseUrl = spec.licenseUrl,
                    licenseAcceptedAt = existing?.licenseAcceptedAt,
                    localPath = existing?.localPath,
                    expectedSha256 = spec.expectedSha256,
                    downloadState = downloadState,
                    bytesDownloaded = existing?.bytesDownloaded ?: 0L,
                    bytesTotal = existing?.bytesTotal,
                    updatedAt = System.currentTimeMillis(),
                ),
            )
        }
    }

    suspend fun acceptModelLicense(modelId: String) {
        ensureDefaultModelAssets()
        database.modelAssetDao().acceptLicense(modelId, System.currentTimeMillis(), "ready_to_download", System.currentTimeMillis())
    }

    suspend fun downloadModel(modelId: String) {
        ensureDefaultModelAssets()
        val spec = modelSpec(modelId)
        modelDownloader.download(spec)
    }

    suspend fun markModelDownloadQueued(modelId: String) {
        val asset = database.modelAssetDao().getByModelId(modelId) ?: return
        database.modelAssetDao().updateDownload(
            modelId = modelId,
            downloadState = "queued",
            bytesDownloaded = asset.bytesDownloaded,
            bytesTotal = asset.bytesTotal,
            localPath = asset.localPath,
            updatedAt = System.currentTimeMillis(),
        )
    }

    suspend fun markModelDownloadCancelled(modelId: String) {
        val asset = database.modelAssetDao().getByModelId(modelId) ?: return
        database.modelAssetDao().updateDownload(
            modelId = modelId,
            downloadState = "cancelled",
            bytesDownloaded = asset.bytesDownloaded,
            bytesTotal = asset.bytesTotal,
            localPath = asset.localPath,
            updatedAt = System.currentTimeMillis(),
        )
    }

    suspend fun markModelDownloadFailed(modelId: String, state: String = "failed") {
        val asset = database.modelAssetDao().getByModelId(modelId) ?: return
        database.modelAssetDao().updateDownload(
            modelId = modelId,
            downloadState = state.take(48),
            bytesDownloaded = asset.bytesDownloaded,
            bytesTotal = asset.bytesTotal,
            localPath = asset.localPath,
            updatedAt = System.currentTimeMillis(),
        )
    }

    suspend fun paint(description: String, catalogId: String, canvasAspect: String, modelId: String): HistoryItemEntity {
        val started = System.currentTimeMillis()
        val result = pipeline.paint(
            PaintRequest(
                description = description,
                stage1Model = modelId,
                stage2Model = modelId,
                colorCatalogId = catalogId,
                canvasAspect = canvasAspect,
                autoRepair = true,
            ),
        )
        return saveResult(result, catalogId, canvasAspect, modelId, System.currentTimeMillis() - started)
    }

    suspend fun composeFromDdl(description: String, ddl: String, catalogId: String, canvasAspect: String, modelId: String): HistoryItemEntity {
        val started = System.currentTimeMillis()
        val result = pipeline.composeFromDdl(
            ddl,
            PaintRequest(
                description = description,
                stage1Model = modelId,
                stage2Model = modelId,
                colorCatalogId = catalogId,
                canvasAspect = canvasAspect,
                autoRepair = true,
            ),
        )
        return saveResult(result, catalogId, canvasAspect, modelId, System.currentTimeMillis() - started)
    }

    private suspend fun saveResult(result: PaintResult, catalogId: String, canvasAspect: String, modelId: String, elapsedMs: Long): HistoryItemEntity {
        val now = System.currentTimeMillis()
        val item = HistoryItemEntity(
            id = pipeline.newHistoryId(),
            createdAt = now,
            updatedAt = now,
            originalInput = result.originalInput,
            normalizedDdl = result.normalizedDdl,
            expandedDdl = result.expandedDdl,
            scoreJson = result.scoreJson,
            displaySvg = result.displaySvg,
            stage1Model = modelId,
            stage2Model = modelId,
            renderMetadataJson = result.renderMetadataJson,
            renderHash = result.renderHash,
            renderHashShort = result.renderHashShort,
            colorCatalogId = catalogId,
            canvasAspect = canvasAspect,
            starred = false,
            trashed = false,
            elapsedMs = elapsedMs,
            tokenMetadataJson = null,
        )
        database.historyDao().upsert(item)
        return item
    }

    suspend fun setStarred(id: String, starred: Boolean) {
        database.historyDao().setStarred(id, starred, System.currentTimeMillis())
    }

    suspend fun trash(id: String) {
        database.historyDao().setTrashed(id, true, System.currentTimeMillis())
    }

    private fun modelSpec(modelId: String): ModelDownloadSpec {
        return DefaultModelDownloads.all.firstOrNull { it.modelId == modelId }
            ?: error("Unknown model: $modelId")
    }
}
