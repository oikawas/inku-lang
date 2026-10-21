package app.inku.mobile.data

import app.inku.mobile.ui.export.PngExportSize
import app.inku.mobile.ui.i18n.inkuError
import app.inku.mobile.ui.DemoHistoryInputPrefix
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.database.sqlite.SQLiteConstraintException
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
import app.inku.mobile.data.lineage.DescriptionLock
import app.inku.mobile.data.lineage.LineageDeclaration
import app.inku.mobile.data.lineage.LineageGraph
import app.inku.mobile.data.lineage.LineageGraphResult
import app.inku.mobile.data.lineage.LineagePlanner
import app.inku.mobile.data.model.CatalogSelection
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.WorkColorSnapshot
import app.inku.mobile.data.model.workColorSnapshot
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.data.model.CameraInputProvenance
import app.inku.mobile.data.model.mergeInputProvenance
import app.inku.mobile.data.refinement.PaintSeeds
import app.inku.mobile.data.refinement.RefinementParent
import app.inku.mobile.data.refinement.RefinementPlan
import app.inku.mobile.data.refinement.RefinementRoute
import app.inku.mobile.data.refinement.ColorArrangementPage
import app.inku.mobile.data.refinement.GroundVariantPlan
import app.inku.mobile.data.refinement.GroundVariants
import app.inku.mobile.data.refinement.ReplayComparison
import app.inku.mobile.data.refinement.SavedColorArrangements
import app.inku.mobile.data.refinement.SentPrompts
import app.inku.mobile.data.refinement.SharedJuxtaposition
import app.inku.mobile.data.refinement.sentPromptsFromHistoryRecord
import app.inku.mobile.llm.DefaultModelDownloads
import app.inku.mobile.llm.CameraDescriptionRequest
import app.inku.mobile.llm.CameraDescriptionResult
import app.inku.mobile.llm.CameraDescriptionWriter
import app.inku.mobile.llm.RemoteVisionAnalyzer
import app.inku.mobile.llm.isLocalVisionModel
import app.inku.mobile.llm.LocalLiteRtLmProvider
import app.inku.mobile.llm.LocalModelDownloader
import app.inku.mobile.llm.ModelDownloadSpec
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.DemoInstructionWriter
import app.inku.mobile.llm.VisionAnalysisRequest
import app.inku.mobile.llm.VisionAnalysisResult
import app.inku.mobile.llm.deleteWithdrawnModelFiles
import app.inku.mobile.llm.ProviderUrlValidator
import app.inku.mobile.llm.RoutingModelProvider
import app.inku.mobile.pipeline.AndroidWorkPipeline
import app.inku.mobile.pipeline.BUNDLED_PLUGIN_PACKAGE
import app.inku.mobile.pipeline.ImportedPluginDefinition
import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.PipelineView
import app.inku.mobile.pipeline.ComposeFromDdlProgress
import app.inku.mobile.pipeline.PaintRequest
import app.inku.mobile.pipeline.drawingModelOf
import app.inku.mobile.pipeline.PaintResult
import app.inku.mobile.pipeline.InterpretResult
import app.inku.mobile.pipeline.PipelineCommitStore
import app.inku.mobile.pipeline.PipelineExecutionStore
import app.inku.mobile.pipeline.SketchInput
import app.inku.mobile.pipeline.ProviderAttempt
import app.inku.mobile.render.RustArtworkRasterizer
import app.inku.mobile.render.SvgOutputLimit
import java.io.File
import java.io.FileOutputStream
import java.math.BigInteger
import java.security.MessageDigest
import java.util.UUID
import kotlin.coroutines.AbstractCoroutineContextElement
import kotlin.coroutines.CoroutineContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.job
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
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
    private val thumbnailVersionSuffix = "-rgba2.webp"
    private val artworkRasterizer by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
        RustArtworkRasterizer()
    }
    private val providerModelCandidatePrefix = "provider_model_candidates:"
    private val modelObservationPrefix = "model_catalog_observations:"
    val modelCatalog: ModelCatalog by lazy { ModelCatalog.load(context) }
    private val localLiteRtProvider = LocalLiteRtLmProvider(context.applicationContext, database.modelAssetDao())
    val chatGptPlan: app.inku.mobile.llm.ChatGptPlanManager
        get() = (context.applicationContext as app.inku.mobile.InkuApplication).chatGptPlan
    private val modelRouter = RoutingModelProvider(
        database = database,
        localProvider = localLiteRtProvider,
        chatGptPlan = { chatGptPlan },
        observeAccess = { provider, model, accessible -> recordModelAccess(provider, model, accessible) },
    )
    // Every model call in this class goes through this one, so an override
    // reaches Stage 1, Stage 2 and the demo prompt alike.
    private val activeModelProvider: ModelProvider = modelProviderOverride ?: modelRouter
    private val sharedPipelineStore = RoomSharedPipelineStore(database)
    private val providerAttemptState = MutableStateFlow<ProviderAttempt?>(null)

    /**
     * The model call the running drawing waits on, for the running row (the
     * Server review's W4). A run clears only its own attempt, so the end of one
     * run cannot blank another's.
     */
    val providerAttempt: StateFlow<ProviderAttempt?> = providerAttemptState.asStateFlow()

    private val pipeline by lazy {
        AndroidWorkPipeline(
            binding = NativePipelineBridge,
            modelProvider = activeModelProvider,
            commitStore = sharedPipelineStore,
            executionStore = sharedPipelineStore,
            readHistory = { id -> sharedPipelineStore.readHistory(AndroidWorkPipeline.OWNER_ID, id) },
            bundledPluginsEnabled = { isBundledPluginPackageEnabled() },
            readSvgLimitBytes = { SvgOutputLimit.storedMiB(getSetting(SvgOutputLimit.SETTING_KEY)) * SvgOutputLimit.BYTES_PER_MIB },
            pinModelSession = { models ->
                if (modelProviderOverride == null) {
                    // A DDL with no holes can render without credentials. The provider
                    // checks this fixed reference if the run actually needs a model,
                    // including an unqualified model routed to the stage's plan provider.
                    models.copy(chatGptSession = chatGptPlan.state.value.activeSession)
                } else models
            },
            onProviderAttempt = { executionId, attempt ->
                providerAttemptState.update { current ->
                    attempt ?: current.takeIf { it?.executionId != executionId }
                }
            },
            saveSafePerformance = { result ->
                result.pipelineView?.let { view ->
                    safePerformances[view.executionId] = saveResumedPerformance(result)
                    currentCoroutineContext()[PerformanceSaveObserver]?.onSaved?.invoke()
                }
            },
        )
    }
    private val modelDownloader = LocalModelDownloader(context.applicationContext, database.modelAssetDao())
    private val thumbnailScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val autonomousScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    val autonomousRefinement by lazy {
        app.inku.mobile.data.refinement.AutonomousRefinementRunner(
            autonomousHost,
            app.inku.mobile.data.refinement.AutonomousRunFile(File(context.filesDir, "autonomous-refinement-runs.json")),
            autonomousScope,
        )
    }

    private val autonomousHost = object : app.inku.mobile.data.refinement.AutonomousHost {
        private suspend fun item(id: String) = getHistoryById(id)?.takeUnless { it.trashed }
            ?: throw app.inku.mobile.data.refinement.AutonomousMoveFailure("unavailable", "autonomous_source_not_found")

        override suspend fun work(id: String): app.inku.mobile.data.refinement.AutonomousWork {
            val item = item(id)
            val basis = JSONObject(item.renderMetadataJson).optJSONObject("laws_basis")
            val names = buildList {
                (basis?.opt("main_law") as? String)?.let(::add)
                basis?.optJSONObject("laws")?.keys()?.forEach { if (it !in this) add(it) }
            }
            val description = NativePipelineBridge.pipelineDescription(item.sourceText ?: item.originalInput).trim()
            val facts = JSONObject().put("description_locked", isDescriptionLocked(item))
                .put("ddl_work", description.isEmpty()).put("laws", JSONArray(names))
            basis?.opt("main_law")?.let { facts.put("main_law", it) }
            return app.inku.mobile.data.refinement.AutonomousWork(id, item.displaySvg, facts, basis)
        }

        override suspend fun laws(parent: String, settings: app.inku.mobile.data.refinement.AutonomousSettings,
            language: String, direction: JSONObject, onSaved: suspend (app.inku.mobile.data.refinement.AutonomousWork) -> Unit) =
            draw(parent, settings, language, "laws_change", null, emptyMap(), direction, onSaved)

        override suspend fun juxtapose(parent: String, settings: app.inku.mobile.data.refinement.AutonomousSettings,
            language: String, exclude: List<String>): app.inku.mobile.data.refinement.JuxtapositionResult {
            val item = item(parent)
            val inputs = juxtapositionInputs(item)
            val written = item.sourceText ?: item.originalInput
            val description = NativePipelineBridge.pipelineDescription(written).trim()
            val candidates = SharedJuxtaposition.gather(inputs.sources, description, inputs.lineage, inputs.added,
                exclude, kotlin.random.Random.nextLong().toULong())
            if (candidates.length() < SharedJuxtaposition.CHOICES) {
                throw app.inku.mobile.data.refinement.AutonomousMoveFailure("unavailable", "juxtaposition_too_few")
            }
            return try {
                juxtapose(app.inku.mobile.llm.JuxtapositionRequest(settings.modelId, description, written, inputs.lineage,
                    candidates, language, app.inku.mobile.llm.RefinementVisionImage.fromSvg(item.displaySvg)))
            } catch (error: CancellationException) { throw error
            } catch (error: Exception) {
                throw app.inku.mobile.data.refinement.AutonomousMoveFailure("failed", error.message ?: "juxtaposition_failed")
            }
        }

        override suspend fun drawJuxtaposition(parent: String, settings: app.inku.mobile.data.refinement.AutonomousSettings,
            language: String, choice: app.inku.mobile.data.refinement.JuxtapositionChoice,
            result: app.inku.mobile.data.refinement.JuxtapositionResult,
            onSaved: suspend (app.inku.mobile.data.refinement.AutonomousWork) -> Unit) =
            draw(parent, settings, language, "description_edit", choice.joined,
                mapOf("edited_from_history_id" to parent) + app.inku.mobile.data.refinement.juxtapositionMetadata(choice, result), null, onSaved)

        private suspend fun draw(id: String, settings: app.inku.mobile.data.refinement.AutonomousSettings,
            language: String, kind: String, joined: String?, metadata: Map<String, Any?>,
            direction: JSONObject?, onSaved: suspend (app.inku.mobile.data.refinement.AutonomousWork) -> Unit) {
            val item = item(id)
            val parent = RefinementParent.of(item, item.sourceText ?: item.originalInput)
            val plan = RefinementPlan(null, RefinementRoute.Paint, parent.catalogId, parent.canvasAspect,
                parent.seeds, kind, metadata, stage1Model = settings.modelId, stage2Model = settings.modelId,
                renderWildOverride = settings.wildOverride)
            val request = refinementRequest(parent, plan).copy(description = joined ?: parent.description,
                originalText = joined ?: parent.description, uiLang = language)
            val started = System.currentTimeMillis()
            val result = try {
                if (direction != null) pipeline.savedLaws(request, parent.ddl, direction.toString()) else pipeline.paint(request)
            } catch (error: CancellationException) { throw error
            } catch (error: app.inku.mobile.pipeline.PipelineInteractionRequired) {
                val reason = error.view.phaseReason ?: error.view.phaseTag
                withContext(NonCancellable) { pipeline.cancel(error.view.executionId) }
                val outcome = if (direction != null && reason !in setOf("laws_refused", "laws_compile", "laws_unavailable"))
                    "unavailable" else "failed"
                throw app.inku.mobile.data.refinement.AutonomousMoveFailure(outcome, reason)
            } catch (error: Exception) {
                throw app.inku.mobile.data.refinement.AutonomousMoveFailure(
                    if (direction != null) "unavailable" else "failed", error.message ?: "pipeline_failed")
            }
            withContext(NonCancellable) {
                val child = saveResult(result, parent.catalogId, parent.canvasAspect, settings.modelId, settings.modelId,
                    System.currentTimeMillis() - started,
                    lineage = LineageDeclaration(parentNodeId = requireNotNull(item.lineageNodeId),
                        derivationKind = kind, derivationMetadata = metadata), historyVisibility = "lineage_only",
                    sourceText = joined ?: parent.description)
                onSaved(work(child.id))
            }
        }

        override suspend fun annotate(child: String, metadata: JSONObject) {
            database.withTransaction {
                val node = requireNotNull(item(child).lineageNodeId)
                val edge = requireNotNull(database.lineageDao().getEdgeByChildId(node))
                val merged = JSONObject(edge.metadataJson)
                metadata.keys().forEach { merged.put(it, metadata.get(it)) }
                database.lineageDao().setEdgeMetadata(node, LineagePlanner.canonicalJson(merged))
            }
        }

        override suspend fun promote(child: String) {
            getHistoryById(child)?.takeUnless { it.trashed }?.lineageNodeId?.let { database.lineageDao().promoteNode(it) }
        }
    }
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

    /** The trash, all of it, as the same summaries the works screen lists. */
    fun trashedHistory(): Flow<List<HistoryListItem>> = database.historyDao().listTrashedSummaries(Int.MAX_VALUE, 0)

    fun modelAssets(): Flow<List<ModelAssetEntity>> = database.modelAssetDao().observeAll()

    fun providerSettings(): Flow<List<ProviderSettingEntity>> = kotlinx.coroutines.flow.combine(
        database.providerSettingDao().observeAll(), chatGptPlan.state,
    ) { providers, plan ->
        providers.filter { it.providerId != "chatgpt" } + ProviderSettingEntity(
            providerId = "chatgpt", displayName = "ChatGPT", kind = "chatgpt-responses",
            baseUrl = "https://api.openai.com/v1", encryptedApiKey = null,
            publishedModelsJson = JSONArray(plan.publishedModels).toString(),
            isEnabled = plan.canUsePlan, isDefaultLocal = false, updatedAt = 0,
        )
    }

    fun providerModelCandidates(): Flow<Map<String, List<String>>> =
        database.settingsDao().observeLike("$providerModelCandidatePrefix%").map { rows ->
            rows.filter { it.valueJson != "null" }.associate { row ->
                row.key.removePrefix(providerModelCandidatePrefix) to parseModelIds(row.valueJson)
            }
        }

    fun modelCatalogObservations(): Flow<Map<String, ModelCatalogObservation>> =
        database.settingsDao().observeLike("$modelObservationPrefix%").map { rows ->
            rows.associate { it.key.removePrefix(modelObservationPrefix) to ModelCatalogObservation.read(it.valueJson) }
        }

    private suspend fun recordModelAccess(provider: ProviderSettingEntity, modelId: String, accessible: Boolean) {
        database.withTransaction {
            val current = database.providerSettingDao().get(provider.providerId) ?: return@withTransaction
            if (current.encryptedApiKey != provider.encryptedApiKey || current.baseUrl != provider.baseUrl || current.kind != provider.kind) return@withTransaction
            val key = "$modelObservationPrefix${provider.providerId}"
            val old = ModelCatalogObservation.read(database.settingsDao().get(key)?.valueJson)
            val id = ModelCatalog.rawId(provider.providerId, modelId)
            saveSetting(key, old.copy(access = old.access + (id to accessible)).json())
        }
    }

    suspend fun checkModelAccess(providerId: String, modelId: String): Boolean? {
        require(providerId == "ollama-cloud")
        val provider = database.providerSettingDao().get(providerId) ?: inkuError { it.errorServiceNotFound(providerId) }
        val key = provider.encryptedApiKey?.let(AndroidSecretBox::decryptOrPlain)
        if (key.isNullOrBlank()) inkuError { it.errorProviderApiKeyMissing(provider.displayName) }
        val result = app.inku.mobile.llm.ModelAccessProbe.check(requireNotNull(provider.baseUrl), key, ModelCatalog.rawId(providerId, modelId))
        result?.let { recordModelAccess(provider, modelId, it) }
        return result
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
        autonomousScope.coroutineContext.job.cancel()
        autonomousScope.coroutineContext.job.children.toList().joinAll()
        thumbnailScope.coroutineContext.job.children.toList().joinAll()
        thumbnailScope.cancel()
        localLiteRtProvider.close()
    }

    suspend fun getHistoryById(id: String): HistoryItemEntity? = database.historyDao().getById(id)

    fun observeHistoryById(id: String): Flow<HistoryItemEntity?> = database.historyDao().observeById(id)

    suspend fun canvasSearchEntries(): List<app.inku.mobile.data.db.CanvasSearchEntry> =
        database.historyDao().canvasSearchEntries()

    /**
     * What juxtaposition gathers from for [item] (Server's `api_juxtaposition`):
     * the other works that may lend a sentence, and the lineage from its root
     * to [item]. Android decides which works lend: the list already leaves out
     * the trash and works kept only in a lineage; here go the works with no
     * description (drawn straight from DDL), demo works, works held by their
     * DDL and [item] itself. Android keeps no display label or comment, so
     * Server's "DDL" label is the empty description, its "[demo]" label is the
     * input's prefix, and no "test data" comment is read. Labels are removed
     * by the one shared rule.
     */
    internal suspend fun juxtapositionInputs(item: HistoryItemEntity): JuxtapositionInputs {
        val describe = NativePipelineBridge::pipelineDescription
        val entries = canvasSearchEntries()
        val locked = juxtapositionSources(entries, item.id, emptySet()) { it }.map { it.id }
            .chunked(JUXTAPOSITION_LOCK_BATCH)
            .flatMapTo(mutableSetOf()) { DescriptionLock.lockedHistoryIds(descriptionLockStore, it) }
        val sources = juxtapositionSources(entries, item.id, locked, describe)

        // Root to the work, one primary parent at a time; the set of seen
        // edges stops a cycle, as in `loadLineage`.
        val dao = database.lineageDao()
        val path = mutableListOf<LineageEdgeEntity>()
        var cursor = item.lineageNodeId
        while (cursor != null) {
            val edge = dao.getEdgeByChildId(cursor)
            if (edge == null || path.any { it.id == edge.id }) break
            path.add(0, edge)
            cursor = edge.parentNodeId
        }
        val nodeIds = (path.map { it.parentNodeId } + listOfNotNull(item.lineageNodeId)).distinct()
        val historyOfNode = dao.getNodesByIds(nodeIds).associate { it.id to it.historyId }
        val descriptions = nodeIds.mapNotNull { nodeId ->
            historyOfNode[nodeId]?.let { database.historyDao().getById(it) }
                ?.let { describe(it.sourceText ?: it.originalInput) }
        }
        return JuxtapositionInputs(sources, juxtapositionLineage(descriptions), juxtapositionAdded(path.map { it.metadataJson }))
    }

    suspend fun juxtapose(request: app.inku.mobile.llm.JuxtapositionRequest): app.inku.mobile.data.refinement.JuxtapositionResult =
        app.inku.mobile.llm.JuxtapositionAdviser(
            activeModelProvider,
            chatGptSession = chatGptPlan.state.value.activeSession,
        ).suggest(request)

    fun pipelineCommitStore(): PipelineCommitStore = sharedPipelineStore

    fun pipelineExecutionStore(): PipelineExecutionStore = sharedPipelineStore

    suspend fun pipelineViewFor(item: HistoryItemEntity): PipelineView? {
        val executionId = JSONObject(item.renderMetadataJson).optString("pipeline_execution_id")
        return executionId.takeIf { it.isNotBlank() }?.let { pipeline.view(it) }
    }

    /** Read only the exact execution attached to this history row. */
    suspend fun sentPrompts(historyId: String): SentPrompts {
        val item = getHistoryById(historyId) ?: return SentPrompts.Unavailable
        val metadata = runCatching { JSONObject(item.renderMetadataJson) }.getOrNull()
            ?: return SentPrompts.Unavailable
        val executionId = metadata.optString("pipeline_execution_id").takeIf(String::isNotBlank)
            ?: return SentPrompts.NotRecorded
        return try {
            val history = sharedPipelineStore.readHistory(AndroidWorkPipeline.OWNER_ID, historyId)
                ?: return SentPrompts.Unavailable
            if (history.warning != null || history.variationId == null || history.revision == null ||
                metadata.optString("pipeline_variation_id") != history.variationId ||
                metadata.optString("pipeline_revision") != history.revision
            ) return SentPrompts.Unavailable
            sentPromptsFromHistoryRecord(item.renderMetadataJson, executionId, history.variationId, history.revision)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            SentPrompts.Unavailable
        }
    }

    suspend fun completionRangeStates(source: String, executionId: String?, historyId: String?) =
        pipeline.completionRangeStates(source, executionId, historyId)

    /**
     * The drawing to put back on screen at start, if one was left behind: an
     * execution still running or waiting on the author, or one that completed
     * without its work being saved. One that failed or was cancelled has
     * already said so and is not brought back -- before, a failed run (a
     * refinement candidate among them) came back at every start in place of
     * the newest work. web restores nothing on opening; this exists for an
     * app the system stopped mid-drawing.
     */
    suspend fun restoreActivePipeline(): PipelineView? {
        val execution = database.sharedPipelineDao().latestExecution(AndroidWorkPipeline.OWNER_ID) ?: return null
        val view = pipeline.restore(execution.executionId)
        if (JSONObject(view.hostContextJson).optJSONObject("result_options")?.optBoolean("save_history", true) == false) {
            if (!view.terminal) pipeline.cancel(view.executionId)
            return null
        }
        if (view.phaseReason == "svg_output_too_large") return view
        if (view.phaseTag == "completed") {
            return view.takeIf { database.historyDao().getById(pipelineHistoryId(view)) == null }
        }
        return view.takeIf { !it.terminal }
    }

    // Named after the execution's step, so saving the same completed run again
    // (a restore after the process ended) finds the row saved first.
    private fun pipelineHistoryId(view: PipelineView): String =
        if (view.phaseTag == "completed") {
            java.util.UUID.nameUUIDFromBytes("pipeline:${view.executionId}:${view.sequence}".encodeToByteArray()).toString()
        } else {
            // A drawing saved before its holes were completed, or when its run
            // stopped: one work per revision, as the server keys it, so the
            // same drawing saved again (a failure after it, a restore) is found.
            java.util.UUID.nameUUIDFromBytes("pipeline-safe:${view.executionId}:${view.revision}".encodeToByteArray()).toString()
        }

    private val safePerformances = java.util.concurrent.ConcurrentHashMap<String, HistoryItemEntity>()

    /** The work saved from [executionId] before it stopped for the author, if any. */
    fun safePerformance(executionId: String): HistoryItemEntity? = safePerformances[executionId]

    suspend fun declinePipelinePatch(executionId: String, proposalDigest: String): PipelineView =
        pipeline.declinePatch(executionId, proposalDigest)

    suspend fun cancelPipeline(executionId: String): PipelineView = pipeline.cancel(executionId)

    suspend fun approvePipelinePatch(
        executionId: String,
        expectedRevision: String,
        proposalDigest: String,
        originalPhoto: File? = null,
    ): HistoryItemEntity =
        saveResumedPerformance(pipeline.approvePatch(executionId, expectedRevision, proposalDigest), originalPhoto)

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
     * Whether [item] is held by its DDL rather than by its description: the
     * server's `description_locked` mark, from the same lineage, DDL and
     * variation authority rows (`DescriptionLock`).
     */
    suspend fun isDescriptionLocked(item: HistoryItemEntity): Boolean =
        item.id in DescriptionLock.lockedHistoryIds(descriptionLockStore, listOf(item.id))

    private val descriptionLockStore = object : DescriptionLock.Store {
        override suspend fun nodesOfHistories(historyIds: Collection<String>) =
            database.lineageDao().lockNodesOfHistories(historyIds)
        override suspend fun nodesByIds(nodeIds: Collection<String>) =
            database.lineageDao().lockNodesByIds(nodeIds)
        override suspend fun edgesOfChildren(childNodeIds: Collection<String>) =
            database.lineageDao().lockEdgesOfChildren(childNodeIds)
        override suspend fun ddlOfHistories(historyIds: Collection<String>) =
            database.historyDao().lockDdlOfHistories(historyIds)
        override suspend fun historyLinks(historyIds: Collection<String>) =
            database.sharedPipelineDao().lockHistoryLinks(historyIds)
        override suspend fun authorities(variationIds: Collection<String>) =
            database.sharedPipelineDao().lockAuthorities(variationIds)
    }

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
            ddlSourceOrigin = item.ddlSourceOrigin,
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
        require(item.id.isNotEmpty() && DdlSource.hasBody(item.normalizedDdl)) {
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
        removeWithdrawnModelAssets()
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

    /**
     * Drops the rows of on-device models the catalog no longer offers (Gemma 4
     * E4B, 2026-09-26) and the files they point at. The row would still list
     * the model for selection, and its file -- 3.7 GB for E4B -- would have no
     * screen left to delete it from.
     */
    private suspend fun removeWithdrawnModelAssets() {
        database.modelAssetDao().getAllExcept(DefaultModelDownloads.all.map { it.modelId }).forEach { asset ->
            asset.localPath?.let { path ->
                withContext(Dispatchers.IO) { deleteWithdrawnModelFiles(context.filesDir, context.cacheDir, path) }
            }
            database.modelAssetDao().deleteByModelId(asset.modelId)
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
        // The built-in 4320px row is retired with the 2160px ceiling (the
        // author, 2026-10-06). Only the built-in row goes: a template the
        // author made has its own id and is left as it is.
        database.exportTemplateDao().deleteBuiltin("png-4320")
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
                heightPx = heightPx.coerceIn(PngExportSize.MIN_HEIGHT_PX, PngExportSize.MAX_HEIGHT_PX),
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
        if (cleanId == "chatgpt") throw app.inku.mobile.llm.ChatGptException("chatgpt_reserved_provider")
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
        if (!apiKey.isNullOrBlank() || existing?.baseUrl != next.baseUrl || existing?.kind != next.kind) {
            saveSetting("$modelObservationPrefix$cleanId", ModelCatalogObservation().json())
            saveSetting("$providerModelCandidatePrefix$cleanId", "null")
        }
    }

    suspend fun clearProviderApiKey(providerId: String) {
        if (providerId == "chatgpt") throw app.inku.mobile.llm.ChatGptException("chatgpt_reserved_provider")
        val existing = database.providerSettingDao().get(providerId) ?: return
        database.providerSettingDao().upsert(existing.copy(encryptedApiKey = null, updatedAt = System.currentTimeMillis()))
        saveSetting("$modelObservationPrefix$providerId", ModelCatalogObservation().json())
        saveSetting("$providerModelCandidatePrefix$providerId", "null")
    }

    suspend fun fetchProviderModels(providerId: String): List<String> {
        if (providerId == "chatgpt") return chatGptPlan.refreshModels()
        ensureDefaultProviderSettings()
        val before = database.providerSettingDao().get(providerId) ?: inkuError { it.errorServiceNotFound(providerId) }
        val models = modelRouter.fetchModels(providerId)
        database.withTransaction {
            val existing = database.providerSettingDao().get(providerId) ?: inkuError { it.errorServiceNotFound(providerId) }
            check(existing.encryptedApiKey == before.encryptedApiKey && existing.baseUrl == before.baseUrl && existing.kind == before.kind) { "Connection changed while fetching models." }
            val selected = parseModelIds(existing.publishedModelsJson).filter { ModelCatalog.rawId(providerId, it) in models }
            val observationKey = "$modelObservationPrefix$providerId"
            val old = ModelCatalogObservation.read(database.settingsDao().get(observationKey)?.valueJson)
            val previous = database.settingsDao().get("$providerModelCandidatePrefix$providerId")?.valueJson?.takeUnless { it == "null" }?.let(::parseModelIds).orEmpty()
            saveSetting(observationKey, old.copy(seen = (old.seen + previous + models + parseModelIds(existing.publishedModelsJson).map { ModelCatalog.rawId(providerId, it) }).distinct()).json())
            saveSetting("$providerModelCandidatePrefix$providerId", JSONArray(models).toString())
            database.providerSettingDao().upsert(existing.copy(publishedModelsJson = JSONArray(selected).toString(), updatedAt = System.currentTimeMillis()))
        }
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
        if (providerId == "chatgpt") throw app.inku.mobile.llm.ChatGptException("chatgpt_reserved_provider")
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

    suspend fun writeCameraDescription(request: CameraDescriptionRequest): CameraDescriptionResult =
        CameraDescriptionWriter(activeModelProvider).write(request)

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

    /** A call's successful early saves notify only the UI run that started that call. */
    private class PerformanceSaveObserver(val onSaved: suspend () -> Unit) : AbstractCoroutineContextElement(Key) {
        companion object Key : CoroutineContext.Key<PerformanceSaveObserver>
    }

    suspend fun paint(description: String, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, autoRepair: Boolean = true, historyInput: String? = null, litertStage1PromptOptimization: Boolean = false, lineage: LineageDeclaration = LineageDeclaration(), historyVisibility: String? = null, seeds: PaintSeeds = PaintSeeds(), instructionLang: String? = null, uiLang: String? = null, sourceText: String? = null, sketch: SketchInput = SketchInput(), parentHistoryId: String? = null, inputProvenance: CameraInputProvenance? = null, renderWild: Boolean? = null, onPerformanceSaved: suspend () -> Unit = {}): HistoryItemEntity {
        val started = System.currentTimeMillis()
        val stage1Text = description
        val result = withContext(PerformanceSaveObserver(onPerformanceSaved)) {
            pipeline.paint(
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
                    instructionLang = instructionLang,
                    uiLang = uiLang,
                    sketch = sketch,
                    parentHistoryId = parentHistoryId,
                    inputProvenance = inputProvenance,
                    renderWild = renderWild,
                ),
            )
        }
        val model = drawingModelOf(stage1ModelId, stage2ModelId)
        return saveResult(result, catalogId, canvasAspect, model, model, System.currentTimeMillis() - started, historyInput, lineage, historyVisibility, sourceText, inputProvenance).also { onPerformanceSaved() }
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
        val model = drawingModelOf(stage1ModelId, stage2ModelId)
        return saveResult(result, catalogId, canvasAspect, model, model, System.currentTimeMillis() - started, lineage = lineage, historyVisibility = historyVisibility, sourceText = sourceText, inputProvenance = inputProvenance, originalPhoto = originalPhoto)
    }

    /**
     * The work as an SVG file in one of the three profiles the server offers.
     *
     * Display is the saved SVG with the description it was drawn from in a
     * `<desc>`, as web's download writes it. Editable and compat are drawn again from
     * the saved Score with the work's own colors, seeds and Wild, as the
     * server's `GET /api/history/{id}/svg?profile=` does; they used to be the
     * display SVG with a new title, so neither carried the groups and ids the
     * editable file promises nor the compat file's simplified effects.
     */
    suspend fun exportSvg(item: HistoryItemEntity, profile: String): String {
        if (profile == "display") return withDescription(item.displaySvg, item.sourceText ?: item.originalInput)
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

    suspend fun generateDemoPrompt(seedPhrase: String, modelId: String): String =
        DemoInstructionWriter(activeModelProvider).write(seedPhrase, modelId)

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
            ),
        )
        val model = drawingModelOf(stage1ModelId, stage2ModelId)
        return saveResult(result, catalogId, canvasAspect, model, model, System.currentTimeMillis() - started, lineage = lineage, historyVisibility = historyVisibility, sourceText = sourceText)
    }

    /** Eight distinct assignments per page, excluding the saved SVG's visible assignment. */
    suspend fun colorArrangementPage(parent: RefinementParent, cursor: BigInteger = BigInteger.ZERO): ColorArrangementPage {
        val item = savedVariantParent(parent.historyId)
        val colors = savedColorSnapshot(item)
        return SavedColorArrangements.fromSaved(item.displaySvg, colors.colorMap, item.id).page(cursor)
    }

    suspend fun renderColorArrangementCandidate(
        parent: RefinementParent,
        index: BigInteger,
        renderWildOverride: Boolean? = null,
    ): Pair<RefinementPlan, PaintResult> {
        val item = savedVariantParent(parent.historyId)
        val savedParent = RefinementParent.of(item, (item.sourceText ?: item.originalInput).trim())
        require(savedParent.seeds.renderSeed != null) { "saved work has no performance seed to preserve its drawing" }
        val colors = savedColorSnapshot(item)
        val arranged = SavedColorArrangements.fromSaved(item.displaySvg, colors.colorMap, item.id)
            .render(index, colors.catalogId)
        val plan = RefinementPlan(
            element = null,
            route = RefinementRoute.RenderFromScore,
            catalogId = colors.catalogId,
            canvasAspect = savedParent.canvasAspect,
            seeds = savedParent.seeds,
            derivationKind = "color_arrangement_change",
            derivationMetadata = arranged.derivationMetadata,
            workColorSnapshotOverride = colors.copy(colorMap = arranged.colorMap),
            renderWildOverride = renderWildOverride,
        )
        return plan to renderRefinementCandidate(savedParent, plan)
    }

    fun groundVariantPlan(parent: RefinementParent): GroundVariantPlan = GroundVariants.plan(parent.scoreJson)

    suspend fun renderGroundVariantCandidate(
        parent: RefinementParent,
        material: String,
        renderWildOverride: Boolean? = null,
    ): Pair<RefinementPlan, PaintResult> {
        val item = savedVariantParent(parent.historyId)
        val savedParent = RefinementParent.of(item, (item.sourceText ?: item.originalInput).trim())
        require(savedParent.seeds.renderSeed != null) { "saved work has no performance seed to preserve its drawing" }
        val changed = GroundVariants.render(savedParent.scoreJson, savedParent.ddl, material, item.instructionLangResolved)
        val plan = RefinementPlan(
            element = null,
            route = RefinementRoute.RenderFromScore,
            catalogId = savedParent.catalogId,
            canvasAspect = savedParent.canvasAspect,
            seeds = savedParent.seeds,
            derivationKind = "ground_change",
            derivationMetadata = changed.derivationMetadata,
            scoreOverrideJson = changed.scoreJson,
            ddlOverride = changed.ddl,
            renderWildOverride = renderWildOverride,
        )
        return plan to renderRefinementCandidate(savedParent, plan)
    }

    private suspend fun savedVariantParent(historyId: String): HistoryItemEntity =
        getHistoryById(historyId)?.takeUnless { it.trashed } ?: error("saved variant parent was not found")

    private fun savedColorSnapshot(item: HistoryItemEntity): WorkColorSnapshot {
        workColorSnapshot(item.renderMetadataJson)?.let { return it }
        val catalog = ColorCatalogs.find(item.colorCatalogId)
            ?: error("saved color catalog is unknown and has no snapshot")
        return WorkColorSnapshot(catalog.id, catalog.renderMap, catalog.name, catalog.sub)
    }

    /** Compare a stored SVG with the current engine's rendering of its exact Score. */
    suspend fun replaySavedWork(historyId: String): ReplayComparison {
        val item = savedVariantParent(historyId)
        val parentNode = requireNotNull(item.lineageNodeId) { "replay parent has no lineage node" }
        val seeds = PaintSeeds.of(item)
        val description = item.sourceText ?: item.originalInput
        val started = System.currentTimeMillis()
        val result = pipeline.renderFromScore(item.scoreJson, PaintRequest(
            description = description,
            originalText = description,
            stage1Model = item.stage1Model.orEmpty(),
            stage2Model = item.stage2Model.orEmpty(),
            colorCatalogId = item.colorCatalogId,
            canvasAspect = item.canvasAspect,
            autoRepair = false,
            parentHistoryId = item.id,
            renderSeed = seeds.renderSeed ?: 0L,
            compositionSeed = seeds.compositionSeed,
            workColorSnapshot = workColorSnapshot(item.renderMetadataJson),
            renderWild = item.drawnWild,
            sketch = SketchInput(text = item.sketchText, grain = item.sketchGrain),
            saveHistory = false,
        ))
        val originalMetadata = JSONObject(item.renderMetadataJson)
        val replayMetadata = JSONObject(result.renderMetadataJson)
        return ReplayComparison(
            parentHistoryId = item.id,
            parentLineageNodeId = parentNode,
            originalSvg = item.displaySvg,
            replayedSvg = result.displaySvg,
            recordedVersion = originalMetadata.optString("render_engine_version").takeIf(String::isNotBlank),
            currentVersion = replayMetadata.optString("render_engine_version").takeIf(String::isNotBlank),
            provisionalSeed = seeds.renderSeed == null,
            originalSvgBytes = item.displaySvg.toByteArray(Charsets.UTF_8).size,
            replayedSvgBytes = result.displaySvg.toByteArray(Charsets.UTF_8).size,
            renderHash = result.renderHash,
            svgSha256 = sha256(result.displaySvg),
            elapsedMs = System.currentTimeMillis() - started,
            result = result,
            catalogId = replayMetadata.optString("catalog_id").ifBlank { item.colorCatalogId },
            canvasAspect = replayMetadata.optString("canvas_aspect_id").ifBlank { item.canvasAspect },
            stage1ModelId = item.stage1Model.orEmpty(),
            stage2ModelId = item.stage2Model.orEmpty(),
            sourceText = description,
            saveId = UUID.randomUUID().toString(),
        )
    }

    /** A retry with the same comparison returns its one child. */
    suspend fun saveReplayChild(comparison: ReplayComparison): HistoryItemEntity {
        val parent = savedVariantParent(comparison.parentHistoryId)
        require(parent.lineageNodeId == comparison.parentLineageNodeId &&
            parent.displaySvg == comparison.originalSvg &&
            LineagePlanner.canonicalJson(JSONObject(parent.scoreJson)) ==
                LineagePlanner.canonicalJson(JSONObject(comparison.result.scoreJson))) {
            "replay parent changed"
        }
        require(comparison.renderHash == comparison.result.renderHash &&
            comparison.replayedSvg == comparison.result.displaySvg &&
            comparison.svgSha256 == sha256(comparison.result.displaySvg)) { "replay preview changed" }
        suspend fun verified(item: HistoryItemEntity): HistoryItemEntity {
            val edge = item.lineageNodeId?.let { database.lineageDao().getEdgeByChildId(it) }
            require(item.renderHash == comparison.renderHash && sha256(item.displaySvg) == comparison.svgSha256 &&
                edge?.parentNodeId == comparison.parentLineageNodeId && edge.derivationKind == "replay") {
                "replay save identity conflicts with another work"
            }
            return item
        }
        getHistoryById(comparison.saveId)?.let { return verified(it) }
        val saved = try {
            saveResult(
                result = comparison.result,
                catalogId = comparison.catalogId,
                canvasAspect = comparison.canvasAspect,
                stage1ModelId = comparison.stage1ModelId,
                stage2ModelId = comparison.stage2ModelId,
                elapsedMs = comparison.elapsedMs,
                sourceText = comparison.sourceText,
                lineage = LineageDeclaration(
                    parentNodeId = comparison.parentLineageNodeId,
                    derivationKind = "replay",
                    derivationMetadata = mapOf(
                        "replay_work_id" to comparison.parentHistoryId,
                        "replay_render_hash" to comparison.renderHash,
                        "replay_svg_sha256" to comparison.svgSha256,
                        "provisional_render_seed" to comparison.provisionalSeed,
                    ),
                ),
                historyIdOverride = comparison.saveId,
            )
        } catch (conflict: SQLiteConstraintException) {
            getHistoryById(comparison.saveId)?.let { return verified(it) }
            throw conflict
        }
        return verified(saved)
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it.toInt() and 0xff) }

    /**
     * Draws one refinement candidate and does **not** save it.
     *
     * web's candidate grid asks for the same thing with `saveHistory: false`
     * (`interpretationVariationCandidate`): a candidate is the generating work's
     * temporary state until the author picks it, so nothing may reach the
     * history table on the way.
     */
    suspend fun renderRefinementCandidate(parent: RefinementParent, plan: RefinementPlan): PaintResult {
        val request = refinementRequest(parent, plan)
        return when (plan.route) {
            RefinementRoute.RenderFromScore -> if (plan.derivationKind == "ground_change") {
                val result = pipeline.renderGroundVariant(
                    parent.scoreJson,
                    plan.derivationMetadata["ground_material"] as String,
                    request,
                )
                check(result.normalizedDdl == plan.ddlOverride &&
                    LineagePlanner.canonicalJson(JSONObject(result.scoreJson)) ==
                    LineagePlanner.canonicalJson(JSONObject(requireNotNull(plan.scoreOverrideJson)))) {
                    "ground variant differs from its plan"
                }
                result
            } else pipeline.renderFromScore(parent.scoreJson, request)
            RefinementRoute.ComposeFromDdl -> pipeline.composeFromDdl(parent.ddl, request)
            RefinementRoute.Paint -> pipeline.paint(request)
        }
    }

    private fun refinementRequest(parent: RefinementParent, plan: RefinementPlan): PaintRequest =
        PaintRequest(
            description = parent.description,
            originalText = parent.description,
            // A comparison candidate is the only thing that overrides these; a
            // refinement leaves them null and inherits the parent's, which is
            // what「対象作品の設定を継承する」means for every other element.
            stage1Model = plan.stage1Model ?: parent.stage1Model,
            stage2Model = plan.stage2Model ?: parent.stage2Model,
            colorCatalogId = plan.catalogId,
            canvasAspect = plan.canvasAspect,
            // The colour refinement replays a Score that is already
            // expanded; layout and model comparison go through Stage 1.5.
            autoRepair = plan.route != RefinementRoute.RenderFromScore,
            renderSeed = plan.seeds.renderSeed,
            compositionSeed = plan.seeds.compositionSeed,
            recomposeMode = plan.recomposeMode,
            // 写生 (Stage 0.5) is not re-run for a candidate: a refinement varies
            // a stage after it, and the layer is not deterministic, so asking it
            // again would move the one thing the refinement is not varying. The
            // parent's prose is carried instead, which is what web hands every
            // candidate (+page.svelte:5116). `requested` stays false: nothing is
            // being asked of the layer, and the state derives from the prose.
            sketch = SketchInput(text = parent.sketchText, grain = parent.sketchGrain),
            workColorSnapshot = refinementColorSnapshot(parent, plan),
            renderWild = plan.renderWildOverride ?: parent.renderWild,
            parentHistoryId = parent.historyId,
            saveHistory = false,
        )
    private fun toolChangePlan(
        parent: RefinementParent,
        option: app.inku.mobile.data.refinement.ToolChangeOption? = null,
    ) = RefinementPlan(
        element = null, route = RefinementRoute.RenderFromScore,
        catalogId = parent.catalogId, canvasAspect = parent.canvasAspect, seeds = parent.seeds,
        derivationKind = "tool_change", derivationMetadata = option?.metadata().orEmpty(), toolChange = option,
    )

    suspend fun toolChangeOptions(
        parent: RefinementParent,
        mode: app.inku.mobile.data.refinement.ToolChangeMode,
    ): List<app.inku.mobile.data.refinement.ToolChangeOption> {
        val source = pipeline.toolChangeSource(parent.ddl, parent.scoreJson, refinementRequest(parent, toolChangePlan(parent)))
        return app.inku.mobile.data.refinement.ToolChangePlanner.options(source, mode)
    }

    suspend fun renderToolChangeCandidate(
        parent: RefinementParent,
        option: app.inku.mobile.data.refinement.ToolChangeOption,
    ): Pair<RefinementPlan, PaintResult>? {
        val plan = toolChangePlan(parent, option)
        return pipeline.renderToolChange(option, refinementRequest(parent, plan))?.let { plan to it }
    }

    /** Redraw from the saved parent/tools at save time; candidate Score/DDL are never trusted. */
    suspend fun saveToolChangeCandidate(
        parentItem: HistoryItemEntity,
        option: app.inku.mobile.data.refinement.ToolChangeOption,
        elapsedMs: Long,
        historyVisibility: String?,
    ): HistoryItemEntity {
        val item = getHistoryById(parentItem.id)?.takeUnless { it.trashed }
            ?: error("tool parent was not found")
        val parent = RefinementParent.of(item, (item.sourceText ?: item.originalInput).trim())
        val source = pipeline.toolChangeSource(parent.ddl, parent.scoreJson, refinementRequest(parent, toolChangePlan(parent)))
        val fresh = option.copy(source = source)
        val (plan, result) = renderToolChangeCandidate(parent, fresh) ?: error("touch change could not be verified")
        return saveRefinementCandidate(
            result, plan, item.lineageNodeId, elapsedMs, historyVisibility,
            parent.stage1Model, parent.stage2Model, parent.description,
        )
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
        stage1ModelId = drawingModelOf(stage1ModelId, stage2ModelId),
        stage2ModelId = drawingModelOf(stage1ModelId, stage2ModelId),
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

    private suspend fun saveResult(result: PaintResult, catalogId: String, canvasAspect: String, stage1ModelId: String, stage2ModelId: String, elapsedMs: Long, historyInput: String? = null, lineage: LineageDeclaration = LineageDeclaration(), historyVisibility: String? = null, sourceText: String? = null, inputProvenance: CameraInputProvenance? = null, originalPhoto: File? = null, historyIdOverride: String? = null): HistoryItemEntity {
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
        val historyId = historyIdOverride ?: result.pipelineView?.takeIf { result.managedHistoryLink != null }
            ?.let(::pipelineHistoryId) ?: pipeline.newHistoryId()
        database.historyDao().getById(historyId)?.let { saved ->
            check(saved.normalizedDdl == result.normalizedDdl && saved.renderHash == result.renderHash &&
                saved.displaySvg == result.displaySvg) {
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
            ddlSourceOrigin = result.ddlSourceOrigin,
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
                result.managedToolChange != null -> sharedPipelineStore.saveManagedToolHistory(item, write, result.managedToolChange)
                result.managedGroundVariant != null -> sharedPipelineStore.saveManagedGroundVariantHistory(item, write, result.managedGroundVariant)
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

    data class ThumbnailBackfillBatch(val scanned: Int, val refreshed: Int)

    suspend fun backfillMissingThumbnails(limit: Int = 8, offset: Int = 0): ThumbnailBackfillBatch {
        val items = database.historyDao().listMissingThumbnails("%$thumbnailVersionSuffix", limit, offset)
        var refreshed = 0
        items.forEach { item ->
            val thumbnail = createHistoryThumbnail(item.displaySvg, item.renderHash) ?: return@forEach
            if (attachThumbnail(item.id, thumbnail)) refreshed++
        }
        return ThumbnailBackfillBatch(items.size, refreshed)
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
    private suspend fun attachThumbnail(id: String, thumbnail: ThumbnailInfo): Boolean {
        val history = database.historyDao()
        val previous = history.thumbnailPathOf(id)
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
        // The file this one replaced, once no work points at it: a format
        // change draws every thumbnail again, and the old files were left behind.
        if (updated != 0 && previous != null && previous != thumbnail.path && history.countWithThumbnail(previous) == 0) {
            File(previous).takeIf { isAppThumbnail(it) }?.delete()
        }
        return updated != 0
    }

    /** Deletes the earlier-format thumbnails left behind ([staleThumbnailFiles]); returns how many. */
    suspend fun removeStaleThumbnails(): Int = withContext(Dispatchers.IO) {
        val root = File(context.filesDir, "thumbnails")
        val referenced = database.historyDao().thumbnailPaths()
            .mapNotNull { runCatching { File(it).canonicalPath }.getOrNull() }
            .toSet()
        staleThumbnailFiles(
            files = root.listFiles()?.toList().orEmpty(),
            referenced = referenced,
            currentSuffix = thumbnailVersionSuffix,
            cutoffMillis = System.currentTimeMillis() - STALE_THUMBNAIL_AGE_MS,
        ).count { it.delete() }
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
                publishedModelsJson = models(),
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
            // The server's catalog (model_settings.py): ovms left it on
            // 2026-07-30 and Ollama Cloud took its place. Local Ollama is not
            // offered on Android (RETIRED_BUILT_IN_PROVIDERS).
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
        ).map { setting ->
            if (setting.isDefaultLocal) setting else setting.copy(publishedModelsJson = JSONArray(modelCatalog.defaults(setting.providerId)).toString())
        }
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
        if (defaultSetting.isDefaultLocal) {
            // The author's pick among the on-device models, less the ones the
            // catalog no longer offers.
            val offered = parseModelIds(defaultSetting.publishedModelsJson)
            return JSONArray(currentIds.filter { it in offered }.ifEmpty { offered }).toString()
        }
        return current
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
            val file = File(dir, "$renderHash$thumbnailVersionSuffix")
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
    if (plan.workColorSnapshotOverride != null) {
        plan.workColorSnapshotOverride
    } else if (plan.route == RefinementRoute.RenderFromScore && plan.catalogId == parent.catalogId) {
        parent.workColorSnapshot
    } else {
        null
    }

/** `plugin_settings` key of the bundled plugin package switch. */
private const val BUNDLED_PLUGIN_SETTING_KEY = "bundled:$BUNDLED_PLUGIN_PACKAGE:enabled"

/** What juxtaposition gathers from: other works' descriptions, the lineage's, and the sentences it added. */
internal data class JuxtapositionInputs(
    val sources: List<SharedJuxtaposition.Source>,
    val lineage: List<String>,
    val added: List<String>,
)

/** Works whose description lock is read in one pass, as Server's `_LOCK_BATCH`. */
private const val JUXTAPOSITION_LOCK_BATCH = 500

/**
 * The works that may lend a sentence to [workId]'s juxtaposition, from the
 * list that already leaves out the trash and works kept only in a lineage.
 * Left out here: [workId], demo works, works with no description and [locked]
 * ones. Each text is the description as kept, through [describe].
 */
internal fun juxtapositionSources(
    entries: List<app.inku.mobile.data.db.CanvasSearchEntry>,
    workId: String,
    locked: Set<String>,
    describe: (String) -> String,
): List<SharedJuxtaposition.Source> = entries.mapNotNull { entry ->
    val text = entry.sourceText ?: entry.originalInput
    entry.takeIf {
        it.id != workId && it.id !in locked && !it.originalInput.startsWith(DemoHistoryInputPrefix) && text.isNotBlank()
    }?.let { SharedJuxtaposition.Source(it.id, describe(text)) }
}

/** The lineage's descriptions, root to the work, labels removed: one kept where the same runs on. */
internal fun juxtapositionLineage(descriptions: List<String>): List<String> =
    descriptions.map { it.trim() }.filter { it.isNotEmpty() }
        .fold(mutableListOf()) { kept, text -> if (kept.lastOrNull() != text) kept.add(text); kept }

/** The sentences the lineage's edges record as added (`juxtaposition.sentence`). */
internal fun juxtapositionAdded(edgeMetadata: List<String>): List<String> = edgeMetadata.mapNotNull { json ->
    runCatching { JSONObject(json.ifEmpty { "{}" }).optJSONObject("juxtaposition") }.getOrNull()
        ?.optString("sentence")?.trim()?.takeIf { it.isNotEmpty() }
}

/**
 * Thumbnail files of an earlier format that no row points at and that were
 * not written just now. Only earlier formats are candidates: a row still on
 * one is always drawn again, so its old file is never needed, while a
 * current-format file may be one being attached right now, or one another
 * database points at -- an instrumented test's in-memory one shares this
 * directory with the app's.
 */
internal fun staleThumbnailFiles(
    files: List<File>,
    referenced: Set<String>,
    currentSuffix: String,
    cutoffMillis: Long,
): List<File> = files.filter { file ->
    file.isFile && !file.name.endsWith(currentSuffix) && file.lastModified() < cutoffMillis &&
        runCatching { file.canonicalPath }.getOrNull() !in referenced
}

private const val STALE_THUMBNAIL_AGE_MS = 10 * 60_000L

/** A built-in connection that was withdrawn, as the catalog once seeded it. */
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
    // Withdrawn on Android only, by the author's ruling of 2026-09-27: it
    // pointed at the phone itself, where no Ollama runs, and plain http to a
    // LAN Ollama is refused. The server still offers it on its own host.
    RetiredProvider(
        providerId = "ollama",
        displayName = "Ollama",
        baseUrl = "http://127.0.0.1:11434/v1",
        seededModels = setOf("ollama:llama3.2", "ollama:gpt-oss:20b", "ollama:qwen3:8b"),
    ),
)
