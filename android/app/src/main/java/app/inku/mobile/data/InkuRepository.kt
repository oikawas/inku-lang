package app.inku.mobile.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.room.withTransaction
import app.inku.mobile.data.db.AppSettingEntity
import app.inku.mobile.data.db.ExportTemplateEntity
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.HistoryListItem
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.LineageEdgeEntity
import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.lineage.LineageDeclaration
import app.inku.mobile.data.lineage.LineageGraph
import app.inku.mobile.data.lineage.LineageGraphResult
import app.inku.mobile.data.lineage.LineagePlanner
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.llm.DefaultModelDownloads
import app.inku.mobile.llm.LocalLiteRtLmProvider
import app.inku.mobile.llm.LocalModelDownloader
import app.inku.mobile.llm.ModelDownloadSpec
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ProviderUrlValidator
import app.inku.mobile.llm.RoutingModelProvider
import app.inku.mobile.pipeline.LocalFallbackPipeline
import app.inku.mobile.pipeline.PaintRequest
import app.inku.mobile.pipeline.PaintResult
import app.inku.mobile.pipeline.InterpretResult
import com.caverock.androidsvg.SVG
import java.io.File
import java.io.FileOutputStream
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

class InkuRepository(
    private val context: Context,
    private val database: InkuDatabase,
    // Injectable so a test can run the real drawing paths without reaching a
    // language model, the way the server's acceptance replaces `_ask_model`
    // and leaves the rest of the paint alone. `null` keeps the router built
    // from the database, which is what the app always uses.
    modelProviderOverride: ModelProvider? = null,
    // Injectable so a test can hand out a node id it already knows. Real ids
    // are uuid4, and a test that cannot name one in advance cannot make the
    // edge insert collide, which is the only way to observe whether the node
    // and the edge are really one transaction. Kept last so that the callers
    // passing it as a trailing lambda keep working.
    private val newLineageId: () -> String = { java.util.UUID.randomUUID().toString() },
) {
    private val providerModelCandidatePrefix = "provider_model_candidates:"
    private val localLiteRtProvider = LocalLiteRtLmProvider(context.applicationContext, database.modelAssetDao())
    private val modelRouter = RoutingModelProvider(
        database = database,
        localProvider = localLiteRtProvider,
    )
    // Every model call in this class goes through this one, so an override
    // reaches Stage 1, Stage 2 and the demo prompt alike.
    private val activeModelProvider: ModelProvider = modelProviderOverride ?: modelRouter
    private val pipeline = LocalFallbackPipeline(modelProvider = activeModelProvider)
    private val modelDownloader = LocalModelDownloader(context.applicationContext, database.modelAssetDao())
    private val thumbnailScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    fun history(): Flow<List<HistoryListItem>> = database.historyDao().listActiveSummaries(100, 0)

    fun trashedHistory(): Flow<List<HistoryItemEntity>> = database.historyDao().listTrashed(100, 0)

    fun modelAssets(): Flow<List<ModelAssetEntity>> = database.modelAssetDao().observeAll()

    fun providerSettings(): Flow<List<ProviderSettingEntity>> = database.providerSettingDao().observeAll()

    fun providerModelCandidates(): Flow<Map<String, List<String>>> =
        database.settingsDao().observeLike("$providerModelCandidatePrefix%").map { rows ->
            rows.associate { row ->
                row.key.removePrefix(providerModelCandidatePrefix) to parseModelIds(row.valueJson)
            }
        }

    fun exportTemplates(): Flow<List<ExportTemplateEntity>> = database.exportTemplateDao().observeAll()

    suspend fun close() {
        thumbnailScope.cancel()
        localLiteRtProvider.close()
    }

    suspend fun getHistoryById(id: String): HistoryItemEntity? = database.historyDao().getById(id)

    /**
     * Gathers the rows around [focusNodeId] and hands them to [LineageGraph].
     *
     * Only the fetching lives here; which rows become the graph is decided
     * there. Two of the walks below are deliberately wider than the graph that
     * comes out of them, because the server reads wider too:
     *
     *  - the climb to the root ignores the node limit, since a generation is
     *    counted from the root even for a node the limit truncated the graph
     *    below (`_lineage_generations`, `db.py:1033`);
     *  - the children of every gathered node are read whether or not they are
     *    drawn, since `child_count` counts all of them (`db.py:1119`).
     *
     * The clamps are not repeated here; they are asked of [LineageGraph], so
     * that there is one place where 0 becomes 1 and 999 becomes 200.
     */
    suspend fun loadLineage(
        focusNodeId: String,
        descendantDepth: Int = LineageGraph.DEFAULT_DESCENDANT_DEPTH,
        nodeLimit: Int = LineageGraph.DEFAULT_NODE_LIMIT,
    ): LineageGraphResult? {
        val dao = database.lineageDao()
        val edges = LinkedHashMap<String, LineageEdgeEntity>()

        // Up to the root. `uq_lineage_primary_parent` gives a child one parent,
        // so this is a walk; the set of seen edges stops a cycle.
        var cursor: String? = focusNodeId
        while (cursor != null) {
            val edge = dao.getEdgeByChildId(cursor)
            if (edge == null || edges.put(edge.id, edge) != null) break
            cursor = edge.parentNodeId
        }

        // Down as far as the clamped depth reaches, one generation per query.
        var frontier = listOf(focusNodeId)
        var level = 0
        val depth = LineageGraph.effectiveDescendantDepth(descendantDepth)
        while (level < depth && frontier.isNotEmpty()) {
            val found = dao.getEdgesByParentIds(frontier)
            val next = mutableListOf<String>()
            found.forEach { edge ->
                if (edges.put(edge.id, edge) == null) next.add(edge.childNodeId)
            }
            frontier = next
            level += 1
        }

        val nodeIds = LinkedHashSet<String>().apply {
            add(focusNodeId)
            edges.values.forEach {
                add(it.parentNodeId)
                add(it.childNodeId)
            }
        }
        // One more generation, for the child counts of the deepest nodes.
        dao.getEdgesByParentIds(nodeIds).forEach { edges.putIfAbsent(it.id, it) }

        val nodes = dao.getNodesByIds(nodeIds)
        val histories = nodes
            .mapNotNull { it.historyId }
            .distinct()
            .mapNotNull { database.historyDao().getById(it) }
            .associateBy { it.id }

        return LineageGraph.build(
            focusNodeId = focusNodeId,
            nodes = nodes,
            edges = edges.values.toList(),
            histories = histories,
            descendantDepth = descendantDepth,
            nodeLimit = nodeLimit,
        )
    }

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
                    publishedModelsJson = normalizedPublishedModels(setting, existing),
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

    suspend fun getSettingsMap(): Map<String, String> =
        database.settingsDao().listAll().associate { it.key to it.valueJson }

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
        val cleanBaseUrl = baseUrl?.trim()?.ifBlank { null }
        if (cleanId != "local-litert-lm" && cleanBaseUrl != null) {
            ProviderUrlValidator.validateRemoteBaseUrl(cleanBaseUrl)
        }
        val existing = database.providerSettingDao().get(cleanId)
        val next = ProviderSettingEntity(
            providerId = cleanId,
            displayName = displayName.trim().ifBlank { cleanId },
            kind = kind.trim().ifBlank { "openai-compatible" },
            baseUrl = cleanBaseUrl,
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
        val fetchedIds = models.toSet()
        val selected = parseModelIds(existing.publishedModelsJson).filter { it in fetchedIds }
        database.settingsDao().upsert(
            AppSettingEntity(
                key = "$providerModelCandidatePrefix$providerId",
                valueJson = JSONArray(models).toString(),
                updatedAt = System.currentTimeMillis(),
            ),
        )
        database.providerSettingDao().upsert(
            existing.copy(
                publishedModelsJson = JSONArray(selected).toString(),
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

    suspend fun downloadModel(modelId: String, force: Boolean = false) {
        ensureDefaultModelAssets()
        val spec = modelSpec(modelId)
        modelDownloader.download(spec, force = force)
    }

    suspend fun warmupLocalModelIfReady(modelId: String) {
        if (!modelId.startsWith("local-litert-lm:")) return
        val asset = database.modelAssetDao().getByModelId(modelId) ?: return
        if (asset.downloadState != "ready") return
        localLiteRtProvider.warmup(modelId)
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

    suspend fun paint(description: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, autoRepair: Boolean = true, historyInput: String? = null, litertStage1PromptOptimization: Boolean = false, lineage: LineageDeclaration = LineageDeclaration(), historyVisibility: String? = null): HistoryItemEntity {
        val started = System.currentTimeMillis()
        val stage1Text = description
        val result = pipeline.paint(
            PaintRequest(
                description = stage1Text,
                originalText = description,
                stage1Model = stage1ModelId,
                stage2Model = stage2ModelId,
                colorCatalogId = catalogId,
                canvasAspect = canvasAspect,
                autoRepair = autoRepair,
                litertStage1PromptOptimization = litertStage1PromptOptimization,
            ),
        )
        return saveResult(result, catalogId, canvasAspect, stage1ModelId, stage2ModelId, System.currentTimeMillis() - started, historyInput, lineage, historyVisibility)
    }

    suspend fun interpret(description: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, autoRepair: Boolean = true, litertStage1PromptOptimization: Boolean = false): InterpretResult {
        val stage1Text = description
        return pipeline.interpret(
            PaintRequest(
                description = stage1Text,
                originalText = description,
                stage1Model = stage1ModelId,
                stage2Model = stage2ModelId,
                colorCatalogId = catalogId,
                canvasAspect = canvasAspect,
                autoRepair = autoRepair,
                litertStage1PromptOptimization = litertStage1PromptOptimization,
            ),
        )
    }

    suspend fun composeFromDdl(description: String, ddl: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, autoRepair: Boolean = true, litertStage1PromptOptimization: Boolean = false, lineage: LineageDeclaration = LineageDeclaration(), historyVisibility: String? = null): HistoryItemEntity {
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
                litertStage1PromptOptimization = litertStage1PromptOptimization,
            ),
        )
        return saveResult(result, catalogId, canvasAspect, stage1ModelId, stage2ModelId, System.currentTimeMillis() - started, lineage = lineage, historyVisibility = historyVisibility)
    }

    suspend fun generateDemoPrompt(seedPhrase: String, modelId: String): String {
        val seed = seedPhrase.trim().ifBlank { "96文字以内の短い描画指示文を1つ作って。" }
        val response = activeModelProvider.generate(
            ModelRequest(
                modelId = modelId,
                prompt = seed,
                temperature = 0.85,
                maxTokens = 256,
                systemInstruction = "あなたはinkuのデモ用短文を作る。回答は日本語の短文1つだけ。前置き、箇条書き、番号、引用符、説明、Markdownを出さない。",
            ),
        )
        return response.text
            .trim()
            .trim('"', '“', '”', '\'', '「', '」')
            .lineSequence()
            .map { it.trim().removePrefix("-").trim() }
            .firstOrNull { it.isNotBlank() }
            ?: error("デモ指示文生成が空でした。")
    }

    suspend fun renderFromScore(description: String, scoreJson: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, lineage: LineageDeclaration = LineageDeclaration(), historyVisibility: String? = null): HistoryItemEntity {
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
        return saveResult(result, catalogId, canvasAspect, stage1ModelId, stage2ModelId, System.currentTimeMillis() - started, lineage = lineage, historyVisibility = historyVisibility)
    }

    private suspend fun saveResult(result: PaintResult, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, elapsedMs: Long, historyInput: String? = null, lineage: LineageDeclaration = LineageDeclaration(), historyVisibility: String? = null): HistoryItemEntity {
        val now = System.currentTimeMillis()
        val renderMetadataJson = JSONObject(result.renderMetadataJson)
            .put("render_hash", result.renderHash)
            .put("render_hash_short", result.renderHashShort)
            .toString()
        val historyId = pipeline.newHistoryId()
        val originalInput = historyInput ?: result.originalInput
        val nodeId = newLineageId()
        // The server decides all of this before it creates any row, so a
        // rejected declaration leaves the history table untouched too.
        val write = LineagePlanner.plan(
            nodeId = nodeId,
            edgeId = newLineageId(),
            historyId = historyId,
            at = now,
            descriptionHash = pipeline.descriptionHash(originalInput),
            renderHash = result.renderHash,
            historyVisibility = historyVisibility,
            declaration = lineage,
            parentNode = lineage.parentNodeId
                ?.takeIf { it.isNotEmpty() }
                ?.let { database.lineageDao().getNodeById(it) },
        )
        val item = HistoryItemEntity(
            id = historyId,
            createdAt = now,
            updatedAt = now,
            originalInput = originalInput,
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
            thumbnailPath = null,
            thumbnailWidth = null,
            thumbnailHeight = null,
            lineageNodeId = nodeId,
        )
        // One transaction, and the edge after the node: the edge points at a
        // child that has to exist first. A failing edge takes the node and the
        // history row down with it, the way the server's rollback does.
        database.withTransaction {
            database.historyDao().upsert(item)
            database.lineageDao().insertNode(write.node)
            write.edge?.let { database.lineageDao().insertEdge(it) }
        }
        scheduleThumbnailGeneration(item.id, result.displaySvg, result.renderHash)
        return item
    }

    suspend fun backfillMissingThumbnails(limit: Int = 8) {
        database.historyDao().listMissingThumbnails(limit).forEach { item ->
            val thumbnail = createHistoryThumbnail(item.displaySvg, item.renderHash) ?: return@forEach
            database.historyDao().updateThumbnail(
                id = item.id,
                path = thumbnail.path,
                width = thumbnail.width,
                height = thumbnail.height,
                updatedAt = System.currentTimeMillis(),
            )
        }
    }

    private fun scheduleThumbnailGeneration(id: String, svgText: String, renderHash: String) {
        thumbnailScope.launch {
            val thumbnail = createHistoryThumbnail(svgText, renderHash) ?: return@launch
            database.historyDao().updateThumbnail(
                id = id,
                path = thumbnail.path,
                width = thumbnail.width,
                height = thumbnail.height,
                updatedAt = System.currentTimeMillis(),
            )
        }
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
                publishedModelsJson = models(),
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
                publishedModelsJson = models("google/gemma-4-31b-it"),
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
                publishedModelsJson = models(),
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
                publishedModelsJson = models(),
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
                publishedModelsJson = models(),
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
                publishedModelsJson = models(),
                isEnabled = true,
                isDefaultLocal = false,
                updatedAt = System.currentTimeMillis(),
            ),
        )
    }

    private fun normalizedPublishedModels(defaultSetting: ProviderSettingEntity, existing: ProviderSettingEntity?): String {
        val current = existing?.publishedModelsJson ?: return defaultSetting.publishedModelsJson
        val currentIds = parseModelIds(current)
        val legacyIds = legacyDefaultPublishedModels(defaultSetting.providerId)
        return if (legacyIds.isNotEmpty() && currentIds.toSet() == legacyIds.toSet()) {
            defaultSetting.publishedModelsJson
        } else {
            current
        }
    }

    private fun legacyDefaultPublishedModels(providerId: String): List<String> = when (providerId) {
        "openai" -> listOf("openai:gpt-5.1", "openai:gpt-5.1-mini", "openai:gpt-4.1", "openai:gpt-4.1-mini")
        "nvidia" -> listOf("google/gemma-4-31b-it", "meta/llama-3.3-70b-instruct", "mistralai/mistral-large-2-instruct")
        "anthropic" -> listOf("anthropic:claude-opus-4-7", "anthropic:claude-sonnet-4-6", "anthropic:claude-haiku-4-5-20251001")
        "gemini" -> listOf("gemini:gemini-2.5-pro", "gemini:gemini-2.5-flash", "gemini:gemini-2.5-flash-lite")
        "ollama" -> listOf("ollama:llama3.2", "ollama:gpt-oss:20b", "ollama:qwen3:8b")
        "ovms" -> listOf("qwen3-api", "qwen-api", "gemma3-12b-api", "gemma3-4b-api")
        else -> emptyList()
    }

    private fun parseModelIds(value: String): List<String> {
        return runCatching {
            val array = JSONArray(value)
            List(array.length()) { index -> array.optString(index).trim() }.filter { it.isNotBlank() }
        }.getOrElse {
            value.lines().map { it.trim() }.filter { it.isNotBlank() }
        }
    }

    private fun createHistoryThumbnail(svgText: String, renderHash: String): ThumbnailInfo? {
        return runCatching {
            val sizePx = 384
            val svg = SVG.getFromString(svgText)
            val documentWidth = svg.documentWidth.takeIf { it > 0f } ?: 1000f
            val documentHeight = svg.documentHeight.takeIf { it > 0f } ?: 1000f
            val documentAspect = documentWidth / documentHeight
            val bitmap = Bitmap.createBitmap(sizePx, sizePx, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            canvas.drawColor(android.graphics.Color.WHITE)
            val drawWidth: Float
            val drawHeight: Float
            if (documentAspect >= 1f) {
                drawWidth = sizePx.toFloat()
                drawHeight = sizePx.toFloat() / documentAspect
            } else {
                drawHeight = sizePx.toFloat()
                drawWidth = sizePx.toFloat() * documentAspect
            }
            val left = (sizePx - drawWidth) / 2f
            val top = (sizePx - drawHeight) / 2f
            canvas.save()
            canvas.translate(left, top)
            svg.setDocumentWidth(drawWidth)
            svg.setDocumentHeight(drawHeight)
            svg.renderToCanvas(canvas)
            canvas.restore()

            val dir = File(context.filesDir, "thumbnails").also { it.mkdirs() }
            val file = File(dir, "$renderHash.webp")
            FileOutputStream(file).use { out ->
                bitmap.compress(Bitmap.CompressFormat.WEBP_LOSSY, 86, out)
            }
            bitmap.recycle()
            ThumbnailInfo(file.absolutePath, sizePx, sizePx)
        }.getOrNull()
    }

    private data class ThumbnailInfo(val path: String, val width: Int, val height: Int)

    private fun defaultExportTemplates(): List<ExportTemplateEntity> {
        val now = System.currentTimeMillis()
        return listOf(
            ExportTemplateEntity("png-1080", "PNG 1080px", "PNG / Y軸 1080px", 1080, 0, true, now),
            ExportTemplateEntity("png-2160", "PNG 2160px", "PNG / Y軸 2160px", 2160, 1, true, now),
            ExportTemplateEntity("png-4320", "PNG 4320px", "PNG / Y軸 4320px", 4320, 2, true, now),
        )
    }
}
