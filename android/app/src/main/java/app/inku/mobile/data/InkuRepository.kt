package app.inku.mobile.data

import android.content.Context
import app.inku.mobile.data.db.AppSettingEntity
import app.inku.mobile.data.db.ExportTemplateEntity
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.llm.DefaultModelDownloads
import app.inku.mobile.llm.LocalLiteRtLmProvider
import app.inku.mobile.llm.LocalModelDownloader
import app.inku.mobile.llm.ModelDownloadSpec
import app.inku.mobile.llm.RoutingModelProvider
import app.inku.mobile.pipeline.LocalFallbackPipeline
import app.inku.mobile.pipeline.PaintRequest
import app.inku.mobile.pipeline.PaintResult
import app.inku.mobile.pipeline.InterpretResult
import kotlinx.coroutines.flow.Flow
import org.json.JSONArray
import org.json.JSONObject

class InkuRepository(
    private val context: Context,
    private val database: InkuDatabase,
    private val pipeline: LocalFallbackPipeline = LocalFallbackPipeline(
        modelProvider = RoutingModelProvider(
            database = database,
            localProvider = LocalLiteRtLmProvider(context.applicationContext, database.modelAssetDao()),
        ),
    ),
) {
    private val modelDownloader = LocalModelDownloader(context.applicationContext, database.modelAssetDao())
    private val modelRouter = RoutingModelProvider(
        database = database,
        localProvider = LocalLiteRtLmProvider(context.applicationContext, database.modelAssetDao()),
    )

    fun history(): Flow<List<HistoryItemEntity>> = database.historyDao().listActive(100, 0)

    fun trashedHistory(): Flow<List<HistoryItemEntity>> = database.historyDao().listTrashed(100, 0)

    fun modelAssets(): Flow<List<ModelAssetEntity>> = database.modelAssetDao().observeAll()

    fun providerSettings(): Flow<List<ProviderSettingEntity>> = database.providerSettingDao().observeAll()

    fun exportTemplates(): Flow<List<ExportTemplateEntity>> = database.exportTemplateDao().observeAll()

    suspend fun ensureDefaultModelAssets() {
        ensureDefaultProviderSettings()
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

    suspend fun ensureDefaultProviderSettings() {
        defaultProviderSettings().forEach { setting ->
            val existing = database.providerSettingDao().get(setting.providerId)
            database.providerSettingDao().upsert(
                setting.copy(
                    encryptedApiKey = existing?.encryptedApiKey?.let { key ->
                        if (AndroidSecretBox.isEncrypted(key)) key else AndroidSecretBox.decryptOrPlain(key)?.let(AndroidSecretBox::encrypt)
                    } ?: setting.encryptedApiKey,
                    publishedModelsJson = existing?.publishedModelsJson ?: setting.publishedModelsJson,
                    updatedAt = System.currentTimeMillis(),
                ),
            )
        }
    }

    suspend fun ensureDefaultExportTemplates() {
        defaultExportTemplates().forEach { template ->
            database.exportTemplateDao().upsert(template)
        }
    }

    suspend fun getSetting(key: String): String? = database.settingsDao().get(key)?.valueJson

    suspend fun saveSetting(key: String, valueJson: String) {
        database.settingsDao().upsert(AppSettingEntity(key, valueJson, System.currentTimeMillis()))
    }

    suspend fun saveExportTemplate(id: String, name: String, description: String, heightPx: Int, sortOrder: Int, isBuiltin: Boolean = false) {
        database.exportTemplateDao().upsert(
            ExportTemplateEntity(
                id = id.take(80),
                name = name.trim().ifBlank { "PNG" }.take(80),
                description = description.trim().take(240),
                heightPx = heightPx.coerceIn(64, 12000),
                sortOrder = sortOrder,
                isBuiltin = isBuiltin,
                updatedAt = System.currentTimeMillis(),
            ),
        )
    }

    suspend fun deleteExportTemplate(id: String) {
        database.exportTemplateDao().delete(id)
    }

    suspend fun saveProviderSetting(
        providerId: String,
        displayName: String,
        kind: String,
        baseUrl: String?,
        apiKey: String?,
        publishedModels: List<String>,
        enabled: Boolean = true,
    ) {
        val cleanId = providerId.trim().lowercase()
        require(cleanId.matches(Regex("[a-z0-9][a-z0-9_-]*"))) { "Service ID は英数字・_・- で入力してください。" }
        val existing = database.providerSettingDao().get(cleanId)
        val next = ProviderSettingEntity(
            providerId = cleanId,
            displayName = displayName.trim().ifBlank { cleanId },
            kind = kind.trim().ifBlank { "openai-compatible" },
            baseUrl = baseUrl?.trim()?.ifBlank { null },
            encryptedApiKey = apiKey
                ?.takeIf { it.isNotBlank() }
                ?.let { AndroidSecretBox.encrypt(it) }
                ?: existing?.encryptedApiKey?.let { key ->
                    if (AndroidSecretBox.isEncrypted(key)) key else AndroidSecretBox.decryptOrPlain(key)?.let(AndroidSecretBox::encrypt)
                },
            publishedModelsJson = JSONArray(publishedModels.map { it.trim() }.filter { it.isNotBlank() }).toString(),
            isEnabled = enabled,
            isDefaultLocal = existing?.isDefaultLocal ?: false,
            updatedAt = System.currentTimeMillis(),
        )
        database.providerSettingDao().upsert(next)
    }

    suspend fun clearProviderApiKey(providerId: String) {
        val existing = database.providerSettingDao().get(providerId) ?: return
        database.providerSettingDao().upsert(existing.copy(encryptedApiKey = null, updatedAt = System.currentTimeMillis()))
    }

    suspend fun fetchProviderModels(providerId: String): List<String> {
        ensureDefaultProviderSettings()
        val models = modelRouter.fetchModels(providerId)
        val existing = database.providerSettingDao().get(providerId) ?: error("サービスが見つかりません: $providerId")
        database.providerSettingDao().upsert(
            existing.copy(
                publishedModelsJson = JSONArray(models).toString(),
                updatedAt = System.currentTimeMillis(),
            ),
        )
        return models
    }

    suspend fun deleteProvider(providerId: String) {
        database.providerSettingDao().deleteCustom(providerId)
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

    suspend fun paint(description: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, autoRepair: Boolean = true, historyInput: String? = null): HistoryItemEntity {
        val started = System.currentTimeMillis()
        val stage1Text = description + emotionHint(description)
        val result = pipeline.paint(
            PaintRequest(
                description = stage1Text,
                originalText = description,
                stage1Model = stage1ModelId,
                stage2Model = stage2ModelId,
                colorCatalogId = catalogId,
                canvasAspect = canvasAspect,
                autoRepair = autoRepair,
            ),
        )
        return saveResult(result, catalogId, canvasAspect, stage1ModelId, stage2ModelId, System.currentTimeMillis() - started, historyInput)
    }

    suspend fun interpret(description: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, autoRepair: Boolean = true): InterpretResult {
        val stage1Text = description + emotionHint(description)
        return pipeline.interpret(
            PaintRequest(
                description = stage1Text,
                originalText = description,
                stage1Model = stage1ModelId,
                stage2Model = stage2ModelId,
                colorCatalogId = catalogId,
                canvasAspect = canvasAspect,
                autoRepair = autoRepair,
            ),
        )
    }

    suspend fun composeFromDdl(description: String, ddl: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, autoRepair: Boolean = true): HistoryItemEntity {
        val started = System.currentTimeMillis()
        val result = pipeline.composeFromDdl(
            ddl,
            PaintRequest(
                description = description,
                originalText = description,
                stage1Model = stage1ModelId,
                stage2Model = stage2ModelId,
                colorCatalogId = catalogId,
                canvasAspect = canvasAspect,
                autoRepair = autoRepair,
            ),
        )
        return saveResult(result, catalogId, canvasAspect, stage1ModelId, stage2ModelId, System.currentTimeMillis() - started)
    }

    suspend fun renderFromScore(description: String, scoreJson: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String): HistoryItemEntity {
        val started = System.currentTimeMillis()
        val result = pipeline.renderFromScore(
            scoreJson,
            PaintRequest(
                description = description,
                originalText = description,
                stage1Model = stage1ModelId,
                stage2Model = stage2ModelId,
                colorCatalogId = catalogId,
                canvasAspect = canvasAspect,
                autoRepair = false,
            ),
        )
        return saveResult(result, catalogId, canvasAspect, stage1ModelId, stage2ModelId, System.currentTimeMillis() - started)
    }

    private suspend fun saveResult(result: PaintResult, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, elapsedMs: Long, historyInput: String? = null): HistoryItemEntity {
        val now = System.currentTimeMillis()
        val renderMetadataJson = JSONObject(result.renderMetadataJson)
            .put("render_hash", result.renderHash)
            .put("render_hash_short", result.renderHashShort)
            .toString()
        val item = HistoryItemEntity(
            id = pipeline.newHistoryId(),
            createdAt = now,
            updatedAt = now,
            originalInput = historyInput ?: result.originalInput,
            normalizedDdl = result.normalizedDdl,
            expandedDdl = result.expandedDdl,
            scoreJson = result.scoreJson,
            displaySvg = result.displaySvg,
            stage1Model = stage1ModelId,
            stage2Model = stage2ModelId,
            renderMetadataJson = renderMetadataJson,
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

    suspend fun restore(id: String) {
        database.historyDao().setTrashed(id, false, System.currentTimeMillis())
    }

    suspend fun deleteHistoryPermanently(id: String) {
        database.historyDao().deletePermanently(id)
    }

    private fun modelSpec(modelId: String): ModelDownloadSpec {
        return DefaultModelDownloads.all.firstOrNull { it.modelId == modelId }
            ?: error("Unknown model: $modelId")
    }

    private fun emotionHint(text: String): String {
        val hints = emotionDdlMap.mapNotNull { (word, hint) ->
            if (text.contains(word)) "「$word」→ $hint" else null
        }
        if (hints.isEmpty()) return ""
        return "\n\n[感情語をDDLに反映してください: ${hints.joinToString("、")}]"
    }

    private val emotionDdlMap: Map<String, String> = linkedMapOf(
        "美しい" to "線は細く(pencil)、揺らぎは小さく(fine)、動きはゆっくり(slow)",
        "美しく" to "線は細く(pencil)、揺らぎは小さく(fine)、動きはゆっくり(slow)",
        "激しい" to "線は太く(brush_thick)、揺らぎは大きく(broad)、動きは速く(high)",
        "激しく" to "線は太く(brush_thick)、揺らぎは大きく(broad)、動きは速く(high)",
        "静かな" to "揺らぎなし(none)、線は細く(hair)、密度を低く",
        "静かに" to "揺らぎなし(none)、線は細く(hair)、密度を低く",
        "素敵" to "線は細く(pen)、揺らぎは小さく(fine)、配置は整然と",
        "きれい" to "線は細く(pencil)、揺らぎは小さく(fine)、密度を低く",
        "やさしい" to "揺らぎは波(wave)、振幅は小さく(fine)、線は細く(pencil)",
        "切ない" to "色は青(blue)か灰(gray)、線は細く(hair)、揺らぎはゆっくり(slow)",
        "哀しい" to "色は青(blue)、線は細く(hair)、要素数は少なく",
        "儚い" to "線は最細(hair)、破線か点線(dashed/dotted)、要素は散らす(scatter)",
        "神秘的" to "背景は黒(black)、円や弧を使う(circle/arc)、放射状(radial)",
        "幻想的" to "揺らぎはperlin、振幅は大きく(broad)、複数色(color_cycle)",
        "寂しい" to "要素数は少なく、間隔を広く、色は灰(gray)",
        "爽やか" to "色は青(blue)か白(white)背景、線は細く(pen)、揺らぎなし(none)",
    )

    private fun defaultProviderSettings(): List<ProviderSettingEntity> {
        fun models(vararg ids: String): String = JSONArray(ids.toList()).toString()
        val localModels = JSONArray().apply {
            DefaultModelDownloads.all.forEach { spec -> put(spec.modelId) }
        }.toString()
        return listOf(
            ProviderSettingEntity(
                providerId = "local-litert-lm",
                displayName = "LiteRT-LM / Local",
                kind = "litert-lm",
                baseUrl = "local://litert-lm",
                encryptedApiKey = null,
                publishedModelsJson = localModels,
                isEnabled = true,
                isDefaultLocal = true,
                updatedAt = System.currentTimeMillis(),
            ),
            ProviderSettingEntity(
                providerId = "openai",
                displayName = "OpenAI API Platform",
                kind = "openai-compatible",
                baseUrl = "https://api.openai.com/v1",
                encryptedApiKey = null,
                publishedModelsJson = models("openai:gpt-5.1", "openai:gpt-5.1-mini", "openai:gpt-4.1", "openai:gpt-4.1-mini"),
                isEnabled = true,
                isDefaultLocal = false,
                updatedAt = System.currentTimeMillis(),
            ),
            ProviderSettingEntity(
                providerId = "nvidia",
                displayName = "NVIDIA NIM",
                kind = "openai-compatible",
                baseUrl = "https://integrate.api.nvidia.com/v1",
                encryptedApiKey = null,
                publishedModelsJson = models("google/gemma-4-31b-it", "meta/llama-3.3-70b-instruct", "mistralai/mistral-large-2-instruct"),
                isEnabled = true,
                isDefaultLocal = false,
                updatedAt = System.currentTimeMillis(),
            ),
            ProviderSettingEntity(
                providerId = "anthropic",
                displayName = "Claude API",
                kind = "anthropic",
                baseUrl = "https://api.anthropic.com",
                encryptedApiKey = null,
                publishedModelsJson = models("anthropic:claude-opus-4-7", "anthropic:claude-sonnet-4-6", "anthropic:claude-haiku-4-5-20251001"),
                isEnabled = true,
                isDefaultLocal = false,
                updatedAt = System.currentTimeMillis(),
            ),
            ProviderSettingEntity(
                providerId = "gemini",
                displayName = "Gemini API",
                kind = "gemini",
                baseUrl = "https://generativelanguage.googleapis.com",
                encryptedApiKey = null,
                publishedModelsJson = models("gemini:gemini-2.5-pro", "gemini:gemini-2.5-flash", "gemini:gemini-2.5-flash-lite"),
                isEnabled = true,
                isDefaultLocal = false,
                updatedAt = System.currentTimeMillis(),
            ),
            ProviderSettingEntity(
                providerId = "ollama",
                displayName = "Ollama",
                kind = "openai-compatible",
                baseUrl = "http://127.0.0.1:11434/v1",
                encryptedApiKey = null,
                publishedModelsJson = models("ollama:llama3.2", "ollama:gpt-oss:20b", "ollama:qwen3:8b"),
                isEnabled = true,
                isDefaultLocal = false,
                updatedAt = System.currentTimeMillis(),
            ),
            ProviderSettingEntity(
                providerId = "ovms",
                displayName = "Intel OVMS",
                kind = "openai-compatible",
                baseUrl = "http://127.0.0.1:8101/v3",
                encryptedApiKey = null,
                publishedModelsJson = models("qwen3-api", "qwen-api", "gemma3-12b-api", "gemma3-4b-api"),
                isEnabled = true,
                isDefaultLocal = false,
                updatedAt = System.currentTimeMillis(),
            ),
        )
    }

    private fun defaultExportTemplates(): List<ExportTemplateEntity> {
        val now = System.currentTimeMillis()
        return listOf(
            ExportTemplateEntity("png-1080", "PNG 1080px", "PNG / Y軸 1080px", 1080, 0, true, now),
            ExportTemplateEntity("png-2160", "PNG 2160px", "PNG / Y軸 2160px", 2160, 1, true, now),
            ExportTemplateEntity("png-4320", "PNG 4320px", "PNG / Y軸 4320px", 4320, 2, true, now),
        )
    }
}
