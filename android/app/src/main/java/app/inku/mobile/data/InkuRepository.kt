package app.inku.mobile.data

import app.inku.mobile.ui.i18n.inkuError
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.room.withTransaction
import app.inku.mobile.BuildConfig
import app.inku.mobile.data.db.AppSettingEntity
import app.inku.mobile.data.db.ExportTemplateEntity
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.HistoryListItem
import app.inku.mobile.data.db.drawnWild
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.LineageEdgeEntity
import app.inku.mobile.data.db.ManagedHistoryLinkInput
import app.inku.mobile.data.db.ManagedHistoryRead
import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.db.PluginSettingEntity
import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.db.RoomSharedPipelineStore
import app.inku.mobile.data.lineage.LineageDeclaration
import app.inku.mobile.data.lineage.LineageGraph
import app.inku.mobile.data.lineage.LineageGraphResult
import app.inku.mobile.data.lineage.LineagePlanner
import app.inku.mobile.data.model.CatalogSelection
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.data.model.CameraInputProvenance
import app.inku.mobile.data.model.mergeInputProvenance
import app.inku.mobile.data.refinement.PaintSeeds
import app.inku.mobile.data.refinement.RefinementParent
import app.inku.mobile.data.refinement.RefinementPlan
import app.inku.mobile.data.refinement.RefinementRoute
import app.inku.mobile.llm.DefaultModelDownloads
import app.inku.mobile.llm.RemoteVisionAnalyzer
import app.inku.mobile.llm.isLocalVisionModel
import app.inku.mobile.llm.LocalLiteRtLmProvider
import app.inku.mobile.llm.LocalModelDownloader
import app.inku.mobile.llm.ModelDownloadSpec
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.VisionAnalysisRequest
import app.inku.mobile.llm.VisionAnalysisResult
import app.inku.mobile.llm.ProviderUrlValidator
import app.inku.mobile.llm.RoutingModelProvider
import app.inku.mobile.pipeline.AndroidWorkPipeline
import app.inku.mobile.pipeline.BUNDLED_PLUGIN_PACKAGE
import app.inku.mobile.pipeline.ImportedPluginDefinition
import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.PipelineView
import app.inku.mobile.pipeline.ComposeFromDdlProgress
import app.inku.mobile.pipeline.PaintRequest
import app.inku.mobile.pipeline.PaintResult
import app.inku.mobile.pipeline.InterpretResult
import app.inku.mobile.pipeline.PipelineCommitStore
import app.inku.mobile.pipeline.PipelineExecutionStore
import app.inku.mobile.pipeline.SketchInput
import app.inku.mobile.render.RustArtworkRasterizer
import java.io.File
import java.io.FileOutputStream
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.job
import kotlinx.coroutines.joinAll
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
    private val artworkRasterizer by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
        RustArtworkRasterizer()
    }
    private val providerModelCandidatePrefix = "provider_model_candidates:"
    private val localLiteRtProvider = LocalLiteRtLmProvider(context.applicationContext, database.modelAssetDao())
    private val modelRouter = RoutingModelProvider(
        database = database,
        localProvider = localLiteRtProvider,
    )
    // Every model call in this class goes through this one, so an override
    // reaches Stage 1, Stage 2 and the demo prompt alike.
    private val activeModelProvider: ModelProvider = modelProviderOverride ?: modelRouter
    private val sharedPipelineStore = RoomSharedPipelineStore(database)
    private val pipeline by lazy {
        AndroidWorkPipeline(
            binding = NativePipelineBridge,
            modelProvider = activeModelProvider,
            commitStore = sharedPipelineStore,
            executionStore = sharedPipelineStore,
            readHistory = { id -> sharedPipelineStore.readHistory(AndroidWorkPipeline.OWNER_ID, id) },
            bundledPluginsEnabled = { isBundledPluginPackageEnabled() },
        )
    }
    private val modelDownloader = LocalModelDownloader(context.applicationContext, database.modelAssetDao())
    private val thumbnailScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val originalPhotos = app.inku.mobile.ui.camera.CameraOriginalPhotoStore(context.filesDir)

    /**
     * Every active work, newest first, as summaries.
     *
     * This stopped at the newest 100 with no way to read further, so an older
     * work could not be reached from the gallery, the full-screen stepping or
     * the search, which filters this list. A summary carries no SVG or Score,
     * a few hundred characters each, so the whole list fits in memory.
     */
    fun history(): Flow<List<HistoryListItem>> = database.historyDao().listActiveSummaries(Int.MAX_VALUE, 0)

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

    /**
     * Waits for the scheduled thumbnail writes, then tears the scope down.
     *
     * `cancel()` alone only asks; it does not wait. A write already inside
     * `updateThumbnail` keeps running, and a caller that closes the database
     * next takes it out from under the write. That throws on a background
     * coroutine rather than on the caller, so it kills the whole process --
     * which is why the instrumentation runs ended with most of their tests
     * unrecorded rather than with one red test (I-150).
     *
     * Joining before cancelling, rather than `cancelAndJoin`, is deliberate:
     * cancelling first abandons the write, so the thumbnail would never land
     * and there would be no property left to assert. Waiting means that once
     * this returns, the scheduled write is on disk and nothing is holding the
     * database.
     */
    suspend fun close() {
        thumbnailScope.coroutineContext.job.children.toList().joinAll()
        thumbnailScope.cancel()
        localLiteRtProvider.close()
    }

    suspend fun getHistoryById(id: String): HistoryItemEntity? = database.historyDao().getById(id)

    fun pipelineCommitStore(): PipelineCommitStore = sharedPipelineStore

    fun pipelineExecutionStore(): PipelineExecutionStore = sharedPipelineStore

    suspend fun pipelineViewFor(item: HistoryItemEntity): PipelineView? {
        val executionId = JSONObject(item.renderMetadataJson).optString("pipeline_execution_id")
        return executionId.takeIf { it.isNotBlank() }?.let { pipeline.view(it) }
    }

    suspend fun restoreActivePipeline(): PipelineView? {
        val execution = database.sharedPipelineDao().latestExecution(AndroidWorkPipeline.OWNER_ID) ?: return null
        val view = pipeline.restore(execution.executionId)
        if (view.phaseTag == "completed" && database.historyDao().getById(pipelineHistoryId(view)) != null) {
            return null
        }
        return view
    }

    private fun pipelineHistoryId(view: PipelineView): String =
        java.util.UUID.nameUUIDFromBytes("pipeline:${view.executionId}:${view.sequence}".encodeToByteArray()).toString()

    suspend fun declinePipelinePatch(executionId: String): PipelineView = pipeline.declinePatch(executionId)

    suspend fun cancelPipeline(executionId: String): PipelineView = pipeline.cancel(executionId)

    suspend fun approvePipelinePatch(executionId: String, originalPhoto: File? = null): HistoryItemEntity =
        saveResumedPerformance(pipeline.approvePatch(executionId), originalPhoto)

    suspend fun resumePipeline(executionId: String, originalPhoto: File? = null): HistoryItemEntity =
        saveResumedPerformance(pipeline.resume(executionId), originalPhoto)

    private suspend fun saveResumedPerformance(result: PaintResult, originalPhoto: File? = null): HistoryItemEntity {
        val metadata = JSONObject(result.renderMetadataJson)
        val parent = metadata.optString("parent_history_id").takeIf { it.isNotBlank() }
            ?.let { database.historyDao().getById(it) }
        val lineage = parent?.lineageNodeId?.let {
            val kind = when (metadata.optString("pipeline_derivation_kind")) {
                "description_fork", "legacy_description_fork" -> "description_edit"
                else -> "ddl_edit"
            }
            LineageDeclaration(parentNodeId = it, derivationKind = kind)
        } ?: LineageDeclaration()
        return saveResult(
            result,
            metadata.getString("catalog_id"),
            metadata.getString("canvas_aspect_id"),
            metadata.optString("stage1_model"),
            metadata.optString("stage2_model"),
            elapsedMs = 0,
            lineage = lineage,
            originalPhoto = originalPhoto,
        )
    }

    suspend fun readManagedHistory(ownerId: String, historyId: String): ManagedHistoryRead? =
        sharedPipelineStore.readHistory(ownerId, historyId)

    /**
     * The saved work as `inku.ddl-export.v1`: its visible DDL and the plugin
     * definitions that DDL names, from the work's own saved configuration.
     */
    suspend fun ddlExportJson(item: HistoryItemEntity): String {
        val config = readManagedHistory(AndroidWorkPipeline.OWNER_ID, item.id)
            ?.forkContextJson
            ?.let(::JSONObject)
            ?.optJSONObject("config")
        val language = config?.optString("language")?.takeIf { it.isNotBlank() }
            ?: item.instructionLangResolved
            ?: "ja"
        val engineVersion = runCatching { JSONObject(item.renderMetadataJson).opt("render_engine_version") }.getOrNull()
        return DdlExport.build(
            source = item.normalizedDdl,
            language = language,
            definitions = config?.optJSONArray("definitions"),
            summaries = config?.optJSONArray("macro_summaries"),
            exportedFrom = JSONObject()
                .put("build_number", BuildConfig.BUILD_NUMBER)
                .put("render_engine_version", engineVersion ?: JSONObject.NULL),
        ).toString(2)
    }

    /**
     * Saves one shared-core performance and its exact authoring revision as one
     * Room transaction. A caller never has a history row without its fork
     * context, or a fork context pointing at a rolled-back history row.
     */
    suspend fun saveManagedPerformance(
        item: HistoryItemEntity,
        lineage: LineageDeclaration,
        historyVisibility: String?,
        link: ManagedHistoryLinkInput,
    ): HistoryItemEntity {
        require(item.id.isNotEmpty() && item.normalizedDdl.isNotEmpty()) {
            "managed history identity and source must not be empty"
        }
        val nodeId = item.lineageNodeId ?: newLineageId()
        val saved = item.copy(lineageNodeId = nodeId)
        val descriptionSource = saved.sourceText ?: saved.originalInput
        val write = LineagePlanner.plan(
            nodeId = nodeId,
            edgeId = newLineageId(),
            historyId = saved.id,
            at = saved.createdAt,
            descriptionHash = pipeline.descriptionHash(descriptionSource),
            renderHash = saved.renderHash,
            historyVisibility = historyVisibility,
            declaration = lineage,
            parentNode = lineage.parentNodeId
                ?.takeIf { it.isNotEmpty() }
                ?.let { database.lineageDao().getNodeById(it) },
        )
        sharedPipelineStore.saveManagedHistory(saved, write, link)
        scheduleThumbnailGeneration(saved.id, saved.displaySvg, saved.renderHash)
        return saved
    }

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
        dropUntouchedRetiredProviders()
        defaultProviderSettings().forEach { setting ->
            val existing = database.providerSettingDao().get(setting.providerId)
            database.providerSettingDao().upsert(
                builtInProviderSetting(setting, existing).copy(
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

    /** The bundled `Nature.leaves` document's switch, as the server's plugin manager keeps one per document. */
    suspend fun isBundledPluginPackageEnabled(): Boolean = runCatching {
        database.pluginSettingDao().get(BUNDLED_PLUGIN_SETTING_KEY)
            ?.valueJson
            ?.let { JSONObject(it).optBoolean("enabled", true) }
    }.getOrNull() ?: true

    fun bundledPluginWords(japanese: Boolean): List<String> = pipeline.bundledPluginWords(japanese)

    suspend fun setBundledPluginPackageEnabled(enabled: Boolean) {
        database.pluginSettingDao().upsert(
            PluginSettingEntity(
                key = BUNDLED_PLUGIN_SETTING_KEY,
                pluginId = BUNDLED_PLUGIN_PACKAGE,
                valueJson = JSONObject().put("enabled", enabled).toString(),
                updatedAt = System.currentTimeMillis(),
            ),
        )
    }

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
        if (!cleanId.matches(Regex("[a-z0-9][a-z0-9_-]*"))) inkuError { it.errorServiceIdFormat }
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
        val existing = database.providerSettingDao().get(providerId) ?: inkuError { it.errorServiceNotFound(providerId) }
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

    /**
     * Removes a connection. A built-in one cannot leave the catalog -- the next
     * start would put it back with its defaults -- so, as the server does
     * (`model_settings.py` `update_model_settings`), it is switched off and
     * hidden instead, and its key is forgotten. Adding a service with the same
     * id brings it back.
     */
    suspend fun deleteProvider(providerId: String) {
        val builtIn = defaultProviderSettings().any { it.providerId == providerId && !it.isDefaultLocal }
        if (!builtIn) {
            database.providerSettingDao().deleteCustom(providerId)
            return
        }
        val existing = database.providerSettingDao().get(providerId) ?: return
        database.providerSettingDao().upsert(
            existing.copy(isEnabled = false, encryptedApiKey = null, updatedAt = System.currentTimeMillis()),
        )
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

    /** A local model analyzes on the device; any other model receives the normalized photo. */
    suspend fun analyzeVision(request: VisionAnalysisRequest): VisionAnalysisResult =
        if (isLocalVisionModel(request.modelId)) {
            localLiteRtProvider.analyze(request)
        } else {
            RemoteVisionAnalyzer(activeModelProvider).analyze(request)
        }

    suspend fun releaseLocalVisionModel(modelId: String) = localLiteRtProvider.releaseVisionModel(modelId)

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
        // The downloader has usually recorded why already (`failed_sha256`,
        // `failed_http_404`, `failed_size`); a generic `failed` over it would
        // throw the reason away.
        if (asset.downloadState.startsWith("failed")) return
        database.modelAssetDao().updateDownload(
            modelId = modelId,
            downloadState = state.take(48),
            bytesDownloaded = asset.bytesDownloaded,
            bytesTotal = asset.bytesTotal,
            localPath = asset.localPath,
            updatedAt = System.currentTimeMillis(),
        )
    }

    suspend fun paint(description: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, autoRepair: Boolean = true, historyInput: String? = null, litertStage1PromptOptimization: Boolean = false, lineage: LineageDeclaration = LineageDeclaration(), historyVisibility: String? = null, seeds: PaintSeeds = PaintSeeds(), instructionLang: String? = null, uiLang: String? = null, sourceText: String? = null, sketch: SketchInput = SketchInput(), parentHistoryId: String? = null, inputProvenance: CameraInputProvenance? = null, renderWild: Boolean? = null): HistoryItemEntity {
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
                renderSeed = seeds.renderSeed,
                compositionSeed = seeds.compositionSeed,
                interpretationSeed = seeds.interpretationSeed,
                variationAmplitude = seeds.variationAmplitude,
                variationSeed = seeds.variationSeed,
                seedText = seeds.seedText,
                instructionLang = instructionLang,
                uiLang = uiLang,
                sketch = sketch,
                parentHistoryId = parentHistoryId,
                inputProvenance = inputProvenance,
                renderWild = renderWild,
            ),
        )
        return saveResult(result, catalogId, canvasAspect, stage1ModelId, stage2ModelId, System.currentTimeMillis() - started, historyInput, lineage, historyVisibility, sourceText, inputProvenance)
    }

    suspend fun interpret(description: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, autoRepair: Boolean = true, litertStage1PromptOptimization: Boolean = false, instructionLang: String? = null, uiLang: String? = null, sketch: SketchInput = SketchInput(), inputProvenance: CameraInputProvenance? = null, renderWild: Boolean? = null): InterpretResult {
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
                instructionLang = instructionLang,
                uiLang = uiLang,
                sketch = sketch,
                inputProvenance = inputProvenance,
                renderWild = renderWild,
            ),
        )
    }

    suspend fun composeFromDdl(description: String, ddl: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, autoRepair: Boolean = true, litertStage1PromptOptimization: Boolean = false, lineage: LineageDeclaration = LineageDeclaration(), historyVisibility: String? = null, seeds: PaintSeeds = PaintSeeds(), instructionLang: String? = null, uiLang: String? = null, sourceText: String? = null, sketch: SketchInput = SketchInput(), inputProvenance: CameraInputProvenance? = null, onProgress: suspend (ComposeFromDdlProgress) -> Unit = {}, beforeSave: suspend () -> Unit = {}, parentHistoryId: String? = null, executionId: String? = null, originalPhoto: File? = null, importedPlugins: List<ImportedPluginDefinition> = emptyList(), renderWild: Boolean? = null): HistoryItemEntity {
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
                renderSeed = seeds.renderSeed,
                compositionSeed = seeds.compositionSeed,
                interpretationSeed = seeds.interpretationSeed,
                variationAmplitude = seeds.variationAmplitude,
                variationSeed = seeds.variationSeed,
                seedText = seeds.seedText,
                instructionLang = instructionLang,
                uiLang = uiLang,
                sketch = sketch,
                parentHistoryId = parentHistoryId,
                executionId = executionId,
                inputProvenance = inputProvenance,
                importedPlugins = importedPlugins,
                renderWild = renderWild,
            ),
            onProgress = onProgress,
        )
        currentCoroutineContext().ensureActive()
        onProgress(ComposeFromDdlProgress.Saving)
        currentCoroutineContext().ensureActive()
        beforeSave()
        currentCoroutineContext().ensureActive()
        return saveResult(result, catalogId, canvasAspect, stage1ModelId, stage2ModelId, System.currentTimeMillis() - started, lineage = lineage, historyVisibility = historyVisibility, sourceText = sourceText, inputProvenance = inputProvenance, originalPhoto = originalPhoto)
    }

    /**
     * The work as an SVG file in one of the three profiles the server offers.
     *
     * Display is the saved SVG itself. Editable and compat are drawn again from
     * the saved Score with the work's own colors, seeds and Wild, as the
     * server's `GET /api/history/{id}/svg?profile=` does; they used to be the
     * display SVG with a new title, so neither carried the groups and ids the
     * editable file promises nor the compat file's simplified effects.
     */
    suspend fun exportSvg(item: HistoryItemEntity, profile: String): String {
        if (profile == "display") return item.displaySvg
        val seeds = PaintSeeds.of(item)
        val description = item.sourceText ?: item.originalInput
        return pipeline.renderExportSvg(
            item.scoreJson,
            PaintRequest(
                description = description,
                originalText = description,
                stage1Model = item.stage1Model.orEmpty(),
                stage2Model = item.stage2Model.orEmpty(),
                colorCatalogId = item.colorCatalogId,
                canvasAspect = item.canvasAspect,
                autoRepair = false,
                renderSeed = seeds.renderSeed,
                compositionSeed = seeds.compositionSeed,
                workColorSnapshot = app.inku.mobile.data.model.workColorSnapshot(item.renderMetadataJson),
                renderWild = item.drawnWild,
                parentHistoryId = item.id,
            ),
            profile,
        )
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
            ?: inkuError { it.demoPromptGenerationEmpty }
    }

    suspend fun selectCatalogId(
        selectedCatalogId: String,
        sourceText: String,
        stage1ModelId: String,
    ): String = selectedCatalogId

    suspend fun renderFromScore(description: String, scoreJson: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, lineage: LineageDeclaration = LineageDeclaration(), historyVisibility: String? = null, seeds: PaintSeeds = PaintSeeds(), sourceText: String? = null, parentHistoryId: String? = null): HistoryItemEntity {
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
                parentHistoryId = parentHistoryId,
                renderSeed = seeds.renderSeed,
                compositionSeed = seeds.compositionSeed,
                interpretationSeed = seeds.interpretationSeed,
                variationAmplitude = seeds.variationAmplitude,
                variationSeed = seeds.variationSeed,
                seedText = seeds.seedText,
            ),
        )
        return saveResult(result, catalogId, canvasAspect, stage1ModelId, stage2ModelId, System.currentTimeMillis() - started, lineage = lineage, historyVisibility = historyVisibility, sourceText = sourceText)
    }

    /**
     * Draws one refinement candidate and does **not** save it.
     *
     * web's candidate grid asks for the same thing with `saveHistory: false`
     * (`interpretationVariationCandidate`): a candidate is the generating work's
     * temporary state until the author picks it, so nothing may reach the
     * history table on the way.
     */
    suspend fun renderRefinementCandidate(parent: RefinementParent, plan: RefinementPlan): PaintResult {
        val request = PaintRequest(
            description = parent.description,
            originalText = parent.description,
            // A comparison candidate is the only thing that overrides these; a
            // refinement leaves them null and inherits the parent's, which is
            // what「対象作品の設定を継承する」means for every other element.
            stage1Model = plan.stage1Model ?: parent.stage1Model,
            stage2Model = plan.stage2Model ?: parent.stage2Model,
            colorCatalogId = plan.catalogId,
            canvasAspect = plan.canvasAspect,
            // The colour and touch refinements replay a Score that is already
            // expanded; the other three go back through Stage 1.5.
            autoRepair = plan.route != RefinementRoute.RenderFromScore,
            renderSeed = plan.seeds.renderSeed,
            compositionSeed = plan.seeds.compositionSeed,
            interpretationSeed = plan.seeds.interpretationSeed,
            variationAmplitude = plan.seeds.variationAmplitude,
            variationSeed = plan.seeds.variationSeed,
            seedText = plan.seeds.seedText,
            // 写生 (Stage 0.5) is not re-run for a candidate: a refinement varies
            // a stage after it, and the layer is not deterministic, so asking it
            // again would move the one thing the refinement is not varying. The
            // parent's prose is carried instead, which is what web hands every
            // candidate (+page.svelte:5116). `requested` stays false: nothing is
            // being asked of the layer, and the state derives from the prose.
            sketch = SketchInput(text = parent.sketchText, grain = parent.sketchGrain),
            workColorSnapshot = refinementColorSnapshot(parent, plan),
            renderWild = parent.renderWild,
            parentHistoryId = parent.historyId,
        )
        return when (plan.route) {
            RefinementRoute.RenderFromScore -> pipeline.renderFromScore(parent.scoreJson, request)
            RefinementRoute.ComposeFromDdl -> pipeline.composeFromDdl(parent.ddl, request)
            RefinementRoute.Paint -> pipeline.paint(request)
        }
    }

    /**
     * Puts a candidate the author picked into the ordinary history.
     *
     * 「選択したものだけを通常履歴へ保存し、保存だけではスターを付けない」(SPEC `:678`):
     * the star is not touched here, and [HistoryItemEntity.starred] is false for
     * every row this path writes -- the same value an ordinary drawing gets.
     */
    suspend fun saveRefinementCandidate(
        result: PaintResult,
        plan: RefinementPlan,
        parentNodeId: String?,
        elapsedMs: Long,
        historyVisibility: String? = null,
        stage1ModelId: String,
        stage2ModelId: String,
        sourceText: String? = null,
    ): HistoryItemEntity = saveResult(
        result = result,
        sourceText = sourceText,
        catalogId = plan.catalogId,
        canvasAspect = plan.canvasAspect,
        stage1ModelId = stage1ModelId,
        stage2ModelId = stage2ModelId,
        elapsedMs = elapsedMs,
        lineage = if (parentNodeId.isNullOrEmpty()) {
            LineageDeclaration()
        } else {
            LineageDeclaration(
                parentNodeId = parentNodeId,
                derivationKind = plan.derivationKind,
                derivationMetadata = plan.derivationMetadata,
            )
        },
        historyVisibility = historyVisibility,
    )

    private suspend fun saveResult(result: PaintResult, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, elapsedMs: Long, historyInput: String? = null, lineage: LineageDeclaration = LineageDeclaration(), historyVisibility: String? = null, sourceText: String? = null, inputProvenance: CameraInputProvenance? = null, originalPhoto: File? = null): HistoryItemEntity {
        val now = System.currentTimeMillis()
        // The server writes every one of these as a string
        // (`db.py:2090-2097`), including the numeric ones.
        val renderSeedText = result.renderSeed?.let { java.lang.Long.toUnsignedString(it) }
        val renderMetadata = mergeInputProvenance(
            JSONObject(result.renderMetadataJson),
            inputProvenance ?: result.inputProvenance,
        )
        val renderMetadataJson = renderMetadata
            .put("render_hash", result.renderHash)
            .put("render_hash_short", result.renderHashShort)
            .toString()
        // The resolved catalog ID cannot say whether the run was requested as auto.
        // Resumed runs only pass that resolved ID here, so prefer their saved request mode.
        val catalogMode = result.managedHistoryLink?.contextJson
            ?.let { JSONObject(it).optJSONObject("host_options")?.optString("catalog_mode") }
            ?.takeIf { it.isNotBlank() }
            ?: result.managedHistoryReplay?.hostOptionsJson
                ?.let { JSONObject(it).optString("catalog_mode") }
                ?.takeIf { it.isNotBlank() }
            ?: if (catalogId == CatalogSelection.AUTO_ID) "auto" else "fixed"
        val historyId = result.pipelineView?.takeIf { result.managedHistoryLink != null }
            ?.let(::pipelineHistoryId) ?: pipeline.newHistoryId()
        database.historyDao().getById(historyId)?.let { saved ->
            check(saved.normalizedDdl == result.normalizedDdl && saved.renderHash == result.renderHash) {
                "pipeline_history_identity_conflict"
            }
            originalPhoto?.let { originalPhotos.persist(historyId, it) }
            return saved
        }
        val originalInput = historyInput ?: result.originalInput
        // `source_text` if there is one, `input` if there is not, and the
        // description hash is taken from whichever it was (`db.py:2049-2051`).
        // Hashing `original_input` instead would give a batch line a different
        // identity from the same prose typed by hand.
        val descriptionSource = sourceText ?: originalInput
        val nodeId = newLineageId()
        // The server decides all of this before it creates any row, so a
        // rejected declaration leaves the history table untouched too.
        val write = LineagePlanner.plan(
            nodeId = nodeId,
            edgeId = newLineageId(),
            historyId = historyId,
            at = now,
            descriptionHash = pipeline.descriptionHash(descriptionSource),
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
            colorCatalogId = renderMetadata.optString("catalog_id").ifBlank { catalogId },
            catalogMode = catalogMode,
            canvasAspect = renderMetadata.optString("canvas_aspect_id").ifBlank { canvasAspect },
            starred = false,
            trashed = false,
            elapsedMs = elapsedMs,
            tokenMetadataJson = null,
            thumbnailPath = null,
            thumbnailWidth = null,
            thumbnailHeight = null,
            lineageNodeId = nodeId,
            renderSeed = renderSeedText,
            compositionSeed = result.compositionSeed?.toString(),
            interpretationSeed = result.interpretationSeed,
            variationAmplitude = result.variationAmplitude,
            variationSeed = result.variationSeed?.toString(),
            seedText = result.seedText,
            instructionLangRequested = result.instructionLangRequested,
            instructionLangResolved = result.instructionLangResolved,
            sourceText = sourceText,
            // 写生 (Stage 0.5), as the drawing reported it. The prose and the
            // grain are absent on a run whose layer fell back; the state is
            // written on every path, and it is the only trace that fallback
            // leaves (`render.py:1917-1922`).
            sketchText = result.sketchText,
            sketchGrain = result.sketchGrain,
            sketchState = result.sketchState,
        )
        // One transaction, and the edge after the node: the edge points at a
        // child that has to exist first. A failing edge takes the node and the
        // history row down with it, the way the server's rollback does.
        val photoExisted = originalPhotos.savedPhoto(historyId) != null
        val attachedPhoto = originalPhoto?.let { originalPhotos.persist(historyId, it) }
        try {
            when {
                result.managedHistoryLink != null -> sharedPipelineStore.saveManagedHistory(item, write, result.managedHistoryLink)
                result.managedHistoryReplay != null -> sharedPipelineStore.saveManagedReplayHistory(item, write, result.managedHistoryReplay)
                else -> database.withTransaction {
                    database.historyDao().insert(item)
                    database.lineageDao().insertNode(write.node)
                    write.edge?.let { database.lineageDao().insertEdge(it) }
                }
            }
        } catch (error: Throwable) {
            // Cancellation can race a committed transaction; keep any committed row's photo.
            if (attachedPhoto != null && !photoExisted) {
                kotlinx.coroutines.withContext(kotlinx.coroutines.NonCancellable) {
                    if (database.historyDao().getById(historyId) == null) originalPhotos.deleteSaved(historyId)
                }
            }
            throw error
        }
        scheduleThumbnailGeneration(item.id, result.displaySvg, result.renderHash)
        return item
    }

    suspend fun backfillMissingThumbnails(limit: Int = 8) {
        database.historyDao().listMissingThumbnails(limit).forEach { item ->
            val thumbnail = createHistoryThumbnail(item.displaySvg, item.renderHash) ?: return@forEach
            attachThumbnail(item.id, thumbnail)
        }
    }

    private fun scheduleThumbnailGeneration(id: String, svgText: String, renderHash: String) {
        thumbnailScope.launch {
            val thumbnail = createHistoryThumbnail(svgText, renderHash) ?: return@launch
            attachThumbnail(id, thumbnail)
        }
    }

    /**
     * Points the row at its thumbnail. A work deleted while the thumbnail was
     * being drawn (a headless run that keeps no history does exactly that)
     * updates no row, and a file no row shows is removed rather than left.
     */
    private suspend fun attachThumbnail(id: String, thumbnail: ThumbnailInfo) {
        val history = database.historyDao()
        val updated = history.updateThumbnail(
            id = id,
            path = thumbnail.path,
            width = thumbnail.width,
            height = thumbnail.height,
            updatedAt = System.currentTimeMillis(),
        )
        if (updated == 0 && history.countWithThumbnail(thumbnail.path) == 0) {
            File(thumbnail.path).delete()
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

    /**
     * Deletes one work for good, as the server's `HistoryPermanentDeleteWriter`
     * does: in the same transaction its lineage node becomes a tombstone and
     * the edges touching it lose their metadata. The node keeps its place, so
     * its children still count their generation from the root, and the planner
     * refuses it as a parent. Deleting only the row left an `active` node
     * pointing at nothing.
     *
     * The original photo goes with the work, and so does the thumbnail unless
     * another row drawn to the same render hash still shows it.
     */
    suspend fun deleteHistoryPermanently(id: String) {
        val thumbnail = database.withTransaction {
            val history = database.historyDao()
            val nodeId = history.lineageNodeIdOf(id)
            val thumbnailPath = history.thumbnailPathOf(id)
            if (nodeId != null) {
                database.lineageDao().tombstoneNode(nodeId, System.currentTimeMillis())
                database.lineageDao().clearEdgeMetadataTouching(nodeId)
            }
            history.deletePermanently(id)
            thumbnailPath?.takeIf { history.countWithThumbnail(it) == 0 }
        }
        originalPhotos.deleteSaved(id)
        thumbnail?.let { path ->
            File(path).takeIf { isAppThumbnail(it) }?.delete()
        }
    }

    private fun isAppThumbnail(file: File): Boolean = runCatching {
        val root = File(context.filesDir, "thumbnails").canonicalFile
        file.canonicalFile.path.startsWith(root.path + File.separator)
    }.getOrDefault(false)

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
            // The server's catalog (model_settings.py): ovms left it on
            // 2026-07-30 and Ollama Cloud took its place beside local Ollama.
            ProviderSettingEntity(
                providerId = "ollama-cloud",
                displayName = "Ollama Cloud (ollama.com)",
                kind = "openai-compatible",
                baseUrl = "https://ollama.com/v1",
                encryptedApiKey = null,
                publishedModelsJson = models(),
                isEnabled = true,
                isDefaultLocal = false,
                updatedAt = System.currentTimeMillis(),
            ),
        )
    }

    /**
     * Removes a withdrawn built-in connection that is still as the catalog
     * seeded it.
     *
     * The server drops a withdrawn id on the way in (`RETIRED_PROVIDER_IDS`).
     * Here a row the author configured -- a key, or a name, address or model
     * list of their own -- is kept as a connection of their own, key and all,
     * and only an untouched one goes.
     */
    private suspend fun dropUntouchedRetiredProviders() {
        RETIRED_BUILT_IN_PROVIDERS.forEach { retired ->
            val existing = database.providerSettingDao().get(retired.providerId) ?: return@forEach
            val models = parseModelIds(existing.publishedModelsJson).toSet()
            val untouched = existing.encryptedApiKey == null &&
                existing.displayName == retired.displayName &&
                existing.baseUrl == retired.baseUrl &&
                (models.isEmpty() || models == retired.seededModels)
            if (untouched) database.providerSettingDao().deleteCustom(retired.providerId)
        }
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
            val artwork = artworkRasterizer.rasterize(
                svgText,
                targetWidth = sizePx,
                targetHeight = sizePx,
            )
            val bitmap = Bitmap.createBitmap(sizePx, sizePx, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            canvas.drawColor(android.graphics.Color.WHITE)
            val left = (sizePx - artwork.width) / 2f
            val top = (sizePx - artwork.height) / 2f
            canvas.drawBitmap(artwork, left, top, null)
            artwork.recycle()

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
            // The description is left empty for the builtin rows: it is derived from
            // the height, so the screen composes it in the reader's language
            // (`exportTemplateDescription`). A row written in one language at
            // first launch would keep that language for good.
            ExportTemplateEntity("png-1080", "PNG 1080px", "", 1080, 0, true, now),
            ExportTemplateEntity("png-2160", "PNG 2160px", "", 2160, 1, true, now),
            ExportTemplateEntity("png-4320", "PNG 4320px", "", 4320, 2, true, now),
        )
    }
}

/**
 * A built-in connection as it is stored again at start-up.
 *
 * The author may rename a built-in service and point it at another base URL
 * (ANDROID_SPEC 2026-05-08), and the server keeps both edits
 * (`model_settings.py` `normalize_model_settings`). This used to write the
 * catalog's name and URL back over them on every start and before every model
 * list fetch, so an edited Ollama URL was gone before the fetch it was made
 * for. The kind still comes from the catalog. The switch is kept, because
 * off is how a deleted built-in stays deleted; adding a service with the same
 * id turns it back on. The local provider's URL is only a marker and stays
 * the catalog's, and the local provider cannot be switched off.
 */
internal fun builtInProviderSetting(
    catalog: ProviderSettingEntity,
    existing: ProviderSettingEntity?,
): ProviderSettingEntity {
    if (existing == null) return catalog
    return catalog.copy(
        displayName = existing.displayName.takeIf { it.isNotBlank() } ?: catalog.displayName,
        baseUrl = if (catalog.isDefaultLocal) catalog.baseUrl else existing.baseUrl?.takeIf { it.isNotBlank() } ?: catalog.baseUrl,
        // Off means deleted (`deleteProvider`); the local model cannot be.
        isEnabled = catalog.isDefaultLocal || existing.isEnabled,
    )
}

internal fun refinementColorSnapshot(parent: RefinementParent, plan: RefinementPlan) =
    if (plan.route == RefinementRoute.RenderFromScore && plan.catalogId == parent.catalogId) {
        parent.workColorSnapshot
    } else {
        null
    }

/** `plugin_settings` key of the bundled plugin package switch. */
private const val BUNDLED_PLUGIN_SETTING_KEY = "bundled:$BUNDLED_PLUGIN_PACKAGE:enabled"

/** A built-in connection the server withdrew, as the catalog once seeded it. */
private data class RetiredProvider(
    val providerId: String,
    val displayName: String,
    val baseUrl: String,
    val seededModels: Set<String>,
)

private val RETIRED_BUILT_IN_PROVIDERS = listOf(
    RetiredProvider(
        providerId = "ovms",
        displayName = "Intel OVMS",
        baseUrl = "http://127.0.0.1:8101/v3",
        seededModels = setOf("qwen3-api", "qwen-api", "gemma3-12b-api", "gemma3-4b-api"),
    ),
)
