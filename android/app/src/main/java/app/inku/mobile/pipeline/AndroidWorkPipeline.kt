package app.inku.mobile.pipeline

import android.util.Log
import app.inku.mobile.data.DdlSource
import app.inku.mobile.data.db.ManagedHistoryLinkInput
import app.inku.mobile.data.db.ManagedHistoryRead
import app.inku.mobile.data.db.ManagedHistoryReplayInput
import app.inku.mobile.data.lineage.LineagePlanner
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.cameraInputProvenance
import app.inku.mobile.data.refinement.SeedFactory
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.render.AndroidRenderHost
import app.inku.mobile.render.SvgRenderer
import app.inku.mobile.render.srgbColorProfile
import app.inku.mobile.ui.i18n.InkuFailure
import java.math.BigInteger
import java.security.MessageDigest
import java.text.Normalizer
import java.util.UUID
import org.json.JSONArray
import org.json.JSONObject

class PipelineInteractionRequired(val view: PipelineView) :
    IllegalStateException("pipeline interaction required: ${view.phaseTag}")

/** App-facing coordinator. Rust owns all authoring and compilation decisions. */
class AndroidWorkPipeline(
    private val binding: SharedPipelineBinding = NativePipelineBridge,
    modelProvider: ModelProvider,
    commitStore: PipelineCommitStore,
    executionStore: PipelineExecutionStore,
    private val readHistory: suspend (String) -> ManagedHistoryRead?,
    private val legacyRenderer: SvgRenderer = AndroidRenderHost(),
    /** Whether the author left the bundled plugin package enabled. */
    private val bundledPluginsEnabled: suspend () -> Boolean = { true },
    /** Told which model call a run waits on (see [SharedPipelineHost]). */
    onProviderAttempt: (executionId: String, attempt: ProviderAttempt?) -> Unit = { _, _ -> },
    private val pinModelSession: (PipelineModelSelection) -> PipelineModelSelection = { it },
    /**
     * Saves a drawing made before a run's holes are completed, or one a run
     * stopped with (the server's safe performance). The work it saves is the
     * one [PaintResult.pipelineView] names; saving it again finds that work.
     */
    private val saveSafePerformance: suspend (PaintResult) -> Unit = {},
) {
    private val configBuilder = SharedPipelineConfigBuilder(binding)
    /** Why the last attempt of each action failed, until the host records it. */
    private val failureDetails = java.util.concurrent.ConcurrentHashMap<String, String>()
    private val host = SharedPipelineHost(
        binding = binding,
        providerEffect = SingleAttemptModelEffectProvider(modelProvider) { actionId, _, detail, _ ->
            if (detail != null) failureDetails[actionId] = detail else failureDetails.remove(actionId)
        },
        failureDetail = { actionId -> failureDetails.remove(actionId) },
        commitStore = commitStore,
        executionStore = executionStore,
        maxEffectSteps = configBuilder.policy.maximumEffectSteps,
        onProviderAttempt = onProviderAttempt,
        safePerformance = object : SafePerformancePort {
            override fun renderCommand(view: PipelineView): PipelineCommand.Render? {
                val context = JSONObject(view.hostContextJson)
                val hostOptions = context.optJSONObject("host_options") ?: return null
                val colors = context.optJSONObject("color_maps")?.stringMaps() ?: return null
                return configBuilder.renderCommand(
                    colors,
                    view,
                    hostOptions.optionalUnsignedLong("render_seed"),
                    hostOptions.optBoolean("wild", false),
                )
            }

            override suspend fun save(view: PipelineView) {
                val resultOptions = JSONObject(view.hostContextJson).optJSONObject("result_options")
                // A refinement candidate is not a work until the author keeps it.
                if (resultOptions?.optBoolean("save_history", true) == false) return
                saveSafePerformance(project(view, safePerformance = true))
            }
        },
    )
    private val authoring = SharedAuthoringPipeline(host, configBuilder)

    /**
     * The bundled package's words for display: the Japanese alias in Japanese,
     * the canonical English heading otherwise (DDL Spec 14).
     */
    fun bundledPluginWords(japanese: Boolean): List<String> {
        val definitions = configBuilder.bundledPluginDefinitions(if (japanese) "ja" else "en")
        return (0 until definitions.length()).mapNotNull { index ->
            val definition = definitions.optJSONObject(index) ?: return@mapNotNull null
            val alias = definition.optJSONArray("aliases")?.optString(0)?.takeIf { it.isNotEmpty() }
            if (japanese && alias != null) alias else definition.optString("heading").takeIf { it.isNotEmpty() }
        }
    }

    suspend fun paint(request: PaintRequest): PaintResult {
        val run = prepare(request, descriptionFlow = true)
        val outcome = authoring.startDescription(run.request)
        return readyResult(outcome)
    }

    suspend fun interpret(request: PaintRequest): InterpretResult {
        val run = prepare(request, descriptionFlow = true)
        val view = authoring.startDescriptionView(run.request)
        if (view.phaseTag != "score_ready" && view.phaseTag != "completed") {
            throw PipelineInteractionRequired(view)
        }
        val ddl = view.visibleDdl ?: throw PipelineHostException("visible_ddl_unavailable")
        val sketch = savedSketchResult(view.sketch)
        return InterpretResult(
            originalInput = request.originalText,
            normalizedDdl = ddl,
            instructionLangRequested = run.instructionLangRequested,
            instructionLangResolved = run.instructionLangResolved,
            sketchText = sketch.text,
            sketchGrain = null,
            sketchState = sketch.state,
            executionId = view.executionId,
        )
    }

    /**
     * Draws edited DDL. Without an execution it starts a direct-DDL run. With
     * one, changed run options (models, colors, canvas, seeds, Wild,
     * language) fork a new variation from the saved policy. Otherwise the edit
     * is committed to the same execution; while a patch proposal waits the
     * core refuses it. Unchanged DDL is drawn without a commit, unless a patch
     * proposal still waits for an answer.
     */
    suspend fun composeFromDdl(
        ddl: String,
        rawRequest: PaintRequest,
        onProgress: suspend (ComposeFromDdlProgress) -> Unit = {},
    ): PaintResult {
        require(DdlSource.hasBody(ddl)) { "ddl_body_required" }
        val request = authoringRequest(rawRequest)
        onProgress(ComposeFromDdlProgress.Rendering)
        val existingId = request.executionId
        if (existingId == null) {
            val run = prepare(request, descriptionFlow = false, text = ddl)
            return composePrepared(ddl, run, request.recomposeMode)
        }

        val current = host.view(OWNER_ID, existingId)
        val stored = restoredRun(existingId)
        if (request.recomposeMode != null || runtimeOptionsChanged(request, stored, ddl)) {
            val fork = prepare(
                request.copy(executionId = null),
                descriptionFlow = false,
                text = ddl,
                parentVariationId = current.variationId,
                inherited = InheritedRun(
                    config = stored.config,
                    renderSeed = stored.renderSeed,
                    seedText = stored.resultOptions.optionalString("seed_text"),
                    instructionLang = stored.resultOptions.optionalString("instruction_lang_requested"),
                    uiLang = stored.resultOptions.optionalString("ui_lang"),
                ),
            )
            return composePrepared(ddl, fork, request.recomposeMode)
        }
        val awaitingApproval = current.phaseTag == "awaiting_patch_approval"
        if (awaitingApproval && current.visibleDdl == ddl) throw PipelineInteractionRequired(current)
        val next = if (current.visibleDdl == ddl) {
            current
        } else {
            // The edit goes to the core as it is. While a proposal waits the
            // core refuses it, as it refuses the server's `author_ddl`: the
            // author answers the proposal, the host does not decline it for them.
            try {
                host.command(
                    OWNER_ID,
                    existingId,
                    PipelineCommand.CommitUserDdl(current.revision, ddl),
                    hostContextJson = activeEditorHostContext(stored, request),
                )
            } catch (error: PipelineHostException) {
                if (awaitingApproval) throw InkuFailure { it.pipelineAnswerProposalFirst }
                throw error
            }
        }
        if (next.phaseTag != "score_ready" && next.phaseTag != "completed") {
            throw PipelineInteractionRequired(next)
        }
        val rendered = authoring.renderReady(
            OWNER_ID,
            next,
            stored.config,
            stored.renderSeed,
            stored.wild,
        )
        return project(rendered)
    }

    /**
     * Selection and compilation share one prepared configuration and composition
     * seed. The work identity and seed are the server's (`pipeline_compat.py`):
     * the source's digest, and the composition seed or else the render seed.
     */
    private suspend fun composePrepared(
        ddl: String,
        run: PreparedRun,
        mode: RecomposeMode?,
    ): PaintResult {
        val selected = mode?.let {
            recomposeDdl(
                binding,
                ddl,
                run.request.config,
                it,
                workId = "sha256:" + sha256(ddl),
                seed = run.request.config.compositionSeed ?: run.request.renderSeed
                    ?: throw PipelineHostException("render_seed_required"),
            )
        }
        val request = run.request.copy(text = selected?.source ?: ddl)
        return readyResult(authoring.startDirectDdl(request)).copy(recomposition = selected?.info)
    }

    /**
     * Approves the proposal the author saw: its revision and digest go to the
     * core as shown, so a proposal that changed since is refused rather than
     * approved in its place (web `controller.ts`).
     */
    suspend fun approvePatch(executionId: String, expectedRevision: String, proposalDigest: String): PaintResult {
        val next = host.command(
            OWNER_ID,
            executionId,
            PipelineCommand.ApprovePatch(expectedRevision, proposalDigest),
        )
        if (next.phaseTag != "score_ready" && next.phaseTag != "completed") {
            throw PipelineInteractionRequired(next)
        }
        val stored = restoredRun(executionId)
        return project(authoring.renderReady(OWNER_ID, next, stored.config, stored.renderSeed, stored.wild))
    }

    suspend fun declinePatch(executionId: String, proposalDigest: String): PipelineView =
        host.command(OWNER_ID, executionId, PipelineCommand.DeclinePatch(proposalDigest))

    suspend fun view(executionId: String): PipelineView = host.view(OWNER_ID, executionId)

    suspend fun restore(executionId: String): PipelineView = host.restore(OWNER_ID, executionId)

    suspend fun resume(executionId: String): PaintResult {
        val restored = host.restore(OWNER_ID, executionId)
        if (restored.phaseTag != "score_ready" && restored.phaseTag != "completed") {
            throw PipelineInteractionRequired(restored)
        }
        val run = restoredRun(executionId)
        return project(authoring.renderReady(OWNER_ID, restored, run.config, run.renderSeed, run.wild))
    }

    suspend fun cancel(executionId: String): PipelineView = host.cancel(OWNER_ID, executionId)

    suspend fun renderFromScore(scoreJson: String, request: PaintRequest): PaintResult {
        val replaySource = replaySource(request.parentHistoryId, scoreJson)
        if (request.canvasAspect == PIXEL9_HOST_ONLY_FORMAT) {
            val rendered = legacyRenderer.render(
                RenderRequest(
                    scoreJson = scoreJson,
                    colorCatalogId = request.colorCatalogId,
                    canvasAspect = request.canvasAspect,
                    svgProfile = "display",
                    renderSeed = request.renderSeed,
                    compositionSeed = request.compositionSeed,
                    workColorSnapshot = request.workColorSnapshot,
                    wild = request.renderWild,
                ),
            )
            val metadata = JSONObject(rendered.metadataJson)
                .put("catalog_id", request.workColorSnapshot?.catalogId ?: request.colorCatalogId)
                .put("canvas_aspect_id", request.canvasAspect)
            loggedRenderWarnings(metadata, "legacy replay")
            return replayResult(scoreJson, request, rendered.svg, metadata, replaySource)
        }

        val saved = renderSaved(scoreJson, request, svgProfile = "display")
        val catalogId = saved.catalogId
        val colors = saved.colors
        val canvas = saved.canvas
        val renderSeed = saved.renderSeed
        val output = saved.output
        // The fields the server's saved replay records (`pipeline_product.py`
        // `replay_saved`), so a redrawn work reads the same on both.
        val catalog = ColorCatalogs.find(catalogId)
        val parentMetadata = replaySource?.history?.renderMetadataJson
            ?.let { runCatching { JSONObject(it) }.getOrNull() }
        val metadata = output.requiredObject("metadata")
            .put("catalog_id", catalogId)
            .put("canvas_aspect_id", request.canvasAspect)
            .put("render_canvas_aspect", request.canvasAspect)
            .put("render_canvas_aspect_id", request.canvasAspect)
            .put("render_canvas_aspect_ratio", canvas.ratio)
            .put("render_color_catalog_id", catalogId)
            .put(
                "render_color_catalog_name",
                parentMetadata?.optionalString("render_color_catalog_name") ?: catalog?.name ?: catalogId,
            )
            .put(
                "render_color_catalog_sub",
                parentMetadata?.optionalString("render_color_catalog_sub") ?: catalog?.sub ?: "",
            )
            .put("render_color_map", JSONObject(colors))
            .put("render_color_source", saved.colorSource)
            .put("render_color_profile", srgbColorProfile())
            .put("render_seed", java.lang.Long.toUnsignedString(renderSeed))
            .put("render_wild", request.renderWild == true)
            .put("seed_text", saved.seedText ?: JSONObject.NULL)
            .put("render_limits", saved.limits)
            .put(
                "render_limits_source",
                when {
                    replaySource == null -> "settings"
                    parentMetadata?.optJSONObject("render_limits") != null -> "work"
                    else -> "work_unrecorded"
                },
            )
        val replayRequest = request.copy(renderSeed = renderSeed, seedText = saved.seedText)
        return replayResult(
            scoreJson,
            replayRequest,
            output.requiredString("svg"),
            metadata,
            replaySource,
            replayPersistence(replaySource, replayRequest, catalogId, colors, metadata),
        )
    }

    /**
     * A saved work drawn again as an editable, compat or live SVG file, the way the
     * server's `GET /api/history/{id}/svg?profile=` redraws it
     * (`routers/history.py`): the work's own colors, seeds and Wild through
     * today's engine, under the same restored policy as a replay. Nothing is
     * saved; the display profile is the saved SVG and needs no drawing.
     */
    suspend fun renderExportSvg(scoreJson: String, request: PaintRequest, svgProfile: String): String {
        if (request.canvasAspect == PIXEL9_HOST_ONLY_FORMAT) {
            return legacyRenderer.render(
                RenderRequest(
                    scoreJson = scoreJson,
                    colorCatalogId = request.colorCatalogId,
                    canvasAspect = request.canvasAspect,
                    svgProfile = svgProfile,
                    renderSeed = request.renderSeed,
                    compositionSeed = request.compositionSeed,
                    workColorSnapshot = request.workColorSnapshot,
                    wild = request.renderWild,
                ),
            ).svg
        }
        return renderSaved(scoreJson, request, svgProfile).output.requiredString("svg")
    }

    private class SavedRender(
        val output: JSONObject,
        val catalogId: String,
        val colors: Map<String, String>,
        val canvas: CanvasInfo,
        val renderSeed: Long,
        val seedText: String?,
        val colorSource: String,
        val limits: JSONObject,
    )

    /** A saved Score through `renderSaved`, with the policy the work was compiled under. */
    private suspend fun renderSaved(scoreJson: String, request: PaintRequest, svgProfile: String): SavedRender {
        // A saved color snapshot is the render authority even if its catalog ID
        // has since been retired. Older work without one uses today's default.
        val useDefaultPolicy = request.workColorSnapshot != null ||
            (request.parentHistoryId != null && ColorCatalogs.find(request.colorCatalogId) == null)
        val policyRequest = if (useDefaultPolicy) {
            request.copy(colorCatalogId = "default")
        } else {
            request
        }
        val run = prepare(policyRequest, descriptionFlow = false)
        val score = JSONObject(scoreJson)
        val compiler = JSONObject(run.request.config.configJson).requiredObject("compiler")
        // A Score cannot authorize its own budget. The independently restored
        // compiler policy is the authority; renderSaved verifies any recorded
        // Score resource snapshot against it.
        val hardPolicy = compiler.requiredObject("hard_resource_policy")
        val operationalBudget = compiler.requiredObject("operational_resource_budget")
        val catalogId = request.workColorSnapshot?.catalogId ?: policyRequest.colorCatalogId
        val colors = request.workColorSnapshot?.colorMap ?: run.request.config.renderColorMaps[catalogId]
            ?: throw PipelineHostException("saved_color_catalog_unavailable")
        val canvas = canvas(request.canvasAspect)
        val (textSeed, seedText) = textSeed(request.seedText, request.renderSeed)
        val renderSeed = textSeed ?: newRenderSeed()
        val options = JSONObject()
            .put("resolved_color_map", JSONObject(colors))
            .put("catalog_id", catalogId)
            .put("canvas", JSONObject().put("width", canvas.width).put("height", canvas.height))
            .put("canvas_aspect_id", request.canvasAspect)
            .put("svg_profile", svgProfile)
            .put("render_seed", BigInteger(java.lang.Long.toUnsignedString(renderSeed)))
            .put("composition_seed", request.compositionSeed?.let { BigInteger(java.lang.Long.toUnsignedString(it)) })
            .put("wild", request.renderWild == true)
            .put("error_policy", compiler.requiredString("error_policy"))
        val input = JSONObject()
            .put("request", JSONObject().put("score", score).put("options", options))
            .put("hard_policy", hardPolicy)
            .put("operational_budget", operationalBudget)
            .put("clip", clipPolicy())
        val output = JSONObject(binding.renderSaved(input.toString().encodeToByteArray()).toString(Charsets.UTF_8))
        if (output.has("error")) {
            // A code per reason, worded where it is shown; the core's own
            // reason goes to the log only, as the server logs it.
            val code = output.requiredString("error")
            output.optString("message").takeIf { it.isNotEmpty() }
                ?.let { Log.w(RENDER_LOG_TAG, "saved replay refused ($code): $it") }
            throw InkuFailure { it.savedRenderRefused(code) }
        }
        loggedRenderWarnings(output.requiredObject("metadata"), "saved replay ($svgProfile)")
        return SavedRender(
            output,
            catalogId,
            colors,
            canvas,
            renderSeed,
            seedText,
            colorSource = if (request.workColorSnapshot != null) "snapshot" else "catalog",
            limits = renderLimits(operationalBudget),
        )
    }

    /** The server's `description_hash` (`identity.py`): an identity, not a secret. */
    fun descriptionHash(input: String): String {
        val normalized = Normalizer.normalize(input, Normalizer.Form.NFC)
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .trim()
        return "dh1:" + sha256(normalized)
    }

    fun newHistoryId(): String = UUID.randomUUID().toString()

    private suspend fun readyResult(outcome: PipelineRunOutcome): PaintResult = when (outcome) {
        is PipelineRunOutcome.Ready -> project(outcome.view)
        is PipelineRunOutcome.InteractionRequired -> throw PipelineInteractionRequired(outcome.view)
    }

    private suspend fun project(view: PipelineView, safePerformance: Boolean = false): PaintResult {
        if (view.renderedJson == null || (view.phaseTag != "completed" && !safePerformance)) {
            throw PipelineInteractionRequired(view)
        }
        val execution = host.executionContext(OWNER_ID, view.executionId)
        val sketch = savedSketchResult(view.sketch)
        val hostContext = JSONObject(execution.hostContextJson)
        val resultOptions = hostContext.requiredObject("result_options")
        val hostOptions = hostContext.requiredObject("host_options")
        val colorMaps = hostContext.requiredObject("color_maps")
        val snapshot = JSONObject(execution.snapshotJson)
        val document = snapshot.requiredObject("document")
        val delivery = snapshot.requiredObject("delivery")
        val compiler = delivery.requiredObject("compiler_options")
        val resolvedHost = compiler.requiredObject("host")
        val catalogId = resolvedHost.requiredString("resolved_catalog_id")
        val canvasId = resolvedHost.requiredString("canvas_format_id")
        val colors = colorMaps.requiredObject(catalogId)
        val rendered = JSONObject(view.renderedJson)
        val svg = rendered.requiredString("svg")
        val metadata = rendered.requiredObject("metadata")
        val canvas = canvas(canvasId)
        val catalog = ColorCatalogs.find(catalogId)
        metadata
            .put("catalog_id", catalogId)
            .put("canvas_aspect_id", canvasId)
            .put("render_canvas_aspect", canvasId)
            .put("render_canvas_aspect_id", canvasId)
            .put("render_canvas_aspect_ratio", canvas.ratio)
            .put("render_color_catalog_id", catalogId)
            .put("render_color_catalog_name", catalog?.name ?: catalogId)
            .put("render_color_catalog_sub", catalog?.sub ?: "")
            .put("render_color_map", colors)
            .put("render_seed", hostOptions.opt("render_seed") ?: JSONObject.NULL)
            .put("render_wild", hostOptions.optBoolean("wild", false))
            .put("pipeline_execution_id", view.executionId)
            .put("pipeline_variation_id", view.variationId)
            .put("pipeline_revision", view.revision)
            .put("stage1_model", execution.models.stage1ModelId)
            .put("stage2_model", execution.models.stage2ModelId)
            .put("parent_history_id", resultOptions.optionalString("parent_history_id"))
            .put("pipeline_derivation_kind", resultOptions.optionalString("derivation_kind")
                ?: execution.authoringContext.derivationKind)
            // The server's saved fields (`pipeline_product.py` `save_result`).
            // The DDL and engine version constants and the web build number are
            // the server's own and have no Android counterpart (ANDROID_SPEC).
            .put("render_color_profile", srgbColorProfile())
            .put("compiler_outcome", delivery.requiredString("outcome"))
            .put("render_limits", renderLimits(compiler.requiredObject("operational_resource_budget")))
            .put("render_limits_source", resultOptions.optionalString("render_limits_source") ?: JSONObject.NULL)
            .put("ui_lang", resultOptions.optionalString("ui_lang") ?: JSONObject.NULL)
            .put("elapsed_stage1_ms", execution.metrics["stage1"] ?: 0L)
            .put("elapsed_stage2_ms", execution.metrics["stage2"] ?: 0L)
            .put("elapsed_total_ms", execution.metrics.values.sum())
        val ddl = document.requiredString("source")
        val diagnostics = pipelineDiagnostics(delivery, metadata)
            .put(
                "plugin_diagnostics",
                pluginDiagnostics(
                    ddl,
                    delivery.requiredArray("upstream_diagnostics"),
                    JSONObject(execution.configJson),
                ),
            )
        // Kept with the work only when there are any, as the server keeps them.
        loggedRenderWarnings(metadata, "pipeline performance")?.let { diagnostics.put("render_warnings", it) }
        metadata.put("pipeline_diagnostics", diagnostics)
        val renderHash = renderHash(delivery.requiredObject("score"), metadata, catalogId)
        metadata.put("render_hash", renderHash).put("render_hash_short", renderHash.takeLast(4).uppercase())
        return PaintResult(
            originalInput = resultOptions.optString("original_input", execution.authoringContext.description),
            normalizedDdl = ddl,
            scoreJson = delivery.requiredObject("score").toString(),
            displaySvg = svg,
            renderMetadataJson = metadata.toString(),
            renderHash = renderHash,
            renderHashShort = renderHash.takeLast(4).uppercase(),
            renderSeed = hostOptions.optionalUnsignedLong("render_seed"),
            compositionSeed = compiler.optionalUnsignedLong("composition_seed"),
            interpretationSeed = resultOptions.optionalString("interpretation_seed"),
            seedText = resultOptions.optionalString("seed_text"),
            instructionLangRequested = resultOptions.optionalString("instruction_lang_requested"),
            instructionLangResolved = resultOptions.optionalString("instruction_lang_resolved"),
            sketchText = sketch.text,
            sketchGrain = null,
            sketchState = sketch.state,
            managedHistoryLink = ManagedHistoryLinkInput(
                ownerId = OWNER_ID,
                variationId = view.variationId,
                revision = view.revision,
                ddlDigest = delivery.requiredString("source_digest"),
                snapshotJson = execution.snapshotJson,
                contextJson = execution.hostContextJson,
                pipelineDiagnosticsJson = diagnostics.toString(),
            ),
            pipelineView = view,
            inputProvenance = cameraInputProvenance(
                JSONObject().put("input_provenance", resultOptions.optJSONObject("input_provenance")).toString(),
            ),
        )
    }

    private fun replayResult(
        scoreJson: String,
        request: PaintRequest,
        svg: String,
        metadata: JSONObject,
        source: ManagedHistoryRead?,
        managedReplay: ManagedHistoryReplayInput? = null,
    ): PaintResult {
        val hash = renderHash(JSONObject(scoreJson), metadata, metadata.optString("catalog_id", "default"))
        metadata.put("render_hash", hash).put("render_hash_short", hash.takeLast(4).uppercase())
        return PaintResult(
            originalInput = request.originalText,
            normalizedDdl = if (source != null) source.history.normalizedDdl else null,
            ddlSourceOrigin = source?.history?.ddlSourceOrigin,
            scoreJson = JSONObject(scoreJson).toString(),
            displaySvg = svg,
            renderMetadataJson = metadata.toString(),
            renderHash = hash,
            renderHashShort = hash.takeLast(4).uppercase(),
            renderSeed = request.renderSeed,
            compositionSeed = request.compositionSeed,
            interpretationSeed = request.interpretationSeed,
            seedText = request.seedText,
            sketchText = request.sketch.text,
            sketchGrain = request.sketch.grain,
            sketchState = request.sketch.claimedState,
            managedHistoryReplay = managedReplay,
        )
    }

    private suspend fun replaySource(historyId: String?, scoreJson: String): ManagedHistoryRead? {
        if (historyId == null) return null
        val source = readHistory(historyId) ?: throw PipelineHostException("parent_history_not_found")
        if (source.authority != "legacy_unknown" &&
            (source.warning != null || source.authority == null || source.forkContextJson == null)
        ) {
            throw PipelineHostException("saved_history_context_corrupt")
        }
        if (
            LineagePlanner.canonicalJson(JSONObject(scoreJson)) !=
            LineagePlanner.canonicalJson(JSONObject(source.history.scoreJson))
        ) {
            throw PipelineHostException("saved_score_replay_mismatch")
        }
        return source
    }

    private fun replayPersistence(
        source: ManagedHistoryRead?,
        request: PaintRequest,
        catalogId: String,
        colors: Map<String, String>,
        metadata: JSONObject,
    ): ManagedHistoryReplayInput? {
        val saved = source?.forkContextJson?.let(::JSONObject) ?: return null
        val savedHostOptions = saved.requiredObject("host_options")
        val hostOptions = JSONObject(savedHostOptions.toString())
            .put("render_seed", request.renderSeed?.let(java.lang.Long::toUnsignedString) ?: JSONObject.NULL)
            .put("composition_seed", request.compositionSeed?.let(java.lang.Long::toUnsignedString) ?: JSONObject.NULL)
            .put("wild", request.renderWild == true)
            .put("canvas_aspect", request.canvasAspect)
            .put("catalog_id", catalogId)
            .put("catalog_mode", "fixed")
        val priorDiagnostics = saved.requiredObject("pipeline_diagnostics")
        val diagnostics = JSONObject()
            .put("upstream_diagnostics", priorDiagnostics.requiredArray("upstream_diagnostics"))
            .put("downstream_diagnostics", priorDiagnostics.requiredArray("downstream_diagnostics"))
            .put("resource_omissions", priorDiagnostics.requiredArray("resource_omissions"))
            .put("relation_omissions", priorDiagnostics.requiredArray("relation_omissions"))
            .put("render_diagnostics", metadata.optJSONObject("execution") ?: JSONObject.NULL)
            .put("resource_execution", metadata.optJSONObject("resource_execution") ?: JSONObject.NULL)
        // Logged by renderSaved already.
        metadata.optJSONArray("render_warnings")?.takeIf { it.length() > 0 }
            ?.let { diagnostics.put("render_warnings", it) }
        return ManagedHistoryReplayInput(
            ownerId = OWNER_ID,
            sourceHistoryId = source.history.id,
            hostOptionsJson = hostOptions.toString(),
            resolvedColorMapJson = JSONObject(colors).toString(),
            pipelineDiagnosticsJson = diagnostics.toString(),
        )
    }

    private fun authoringRequest(request: PaintRequest): PaintRequest =
        if (request.canvasAspect == PIXEL9_HOST_ONLY_FORMAT) {
            request.copy(canvasAspect = CanvasAspects.DEFAULT_ID)
        } else {
            request
        }

    private suspend fun prepare(
        rawRequest: PaintRequest,
        descriptionFlow: Boolean,
        text: String = rawRequest.description,
        parentVariationId: String? = null,
        inherited: InheritedRun? = null,
    ): PreparedRun {
        // Legacy paper remains valid for display/replay; new works use the
        // canonical default even when started from a legacy history selection.
        val request = authoringRequest(rawRequest)
        checkInputLength(request, text, descriptionFlow)
        // Every layer reads the description without the author's labels; the
        // work keeps it as written (server `pipeline_api.py` `_drawn_description`).
        val drawn = if (descriptionFlow) binding.pipelineDescription(text) else text
        if (descriptionFlow && text.isNotBlank() && drawn.isBlank()) {
            throw InkuFailure { it.descriptionOnlyLabels }
        }
        val history = request.parentHistoryId?.let { historyId ->
            readHistory(historyId) ?: throw PipelineHostException("parent_history_not_found")
        }
        if (history != null && history.authority != "legacy_unknown" &&
            (history.warning != null || history.authority == null || history.forkContextJson == null)
        ) {
            throw PipelineHostException("saved_history_context_corrupt")
        }
        val saved = history?.forkContextJson?.let(::JSONObject)
        // The server merges the parent's options under the request's
        // (`pipeline_product.py` `prepare`): words, seeds and languages a request
        // leaves out are the parent's. A legacy parent passes on its languages
        // but not its words.
        val parentMetadata = history?.history?.renderMetadataJson
            ?.let { runCatching { JSONObject(it) }.getOrNull() }
        val inheritedSeedText = inherited?.seedText ?: history?.takeIf { saved != null }?.history?.seedText
        val inheritedRenderSeed = inherited?.renderSeed
            ?: saved?.requiredObject("host_options")?.optionalUnsignedLong("render_seed")
        val (textSeed, seedText) = textSeed(request.seedText ?: inheritedSeedText, request.renderSeed ?: inheritedRenderSeed)
        val renderSeed = textSeed ?: newRenderSeed()
        val requestedLang = InstructionLanguages.normalize(
            request.instructionLang
                ?: inherited?.instructionLang
                ?: history?.history?.instructionLangRequested
                ?: InstructionLanguages.AUTO,
        )
        val uiLang = request.uiLang ?: inherited?.uiLang ?: parentMetadata?.optionalString("ui_lang")
        // The labels are gone before the language is read, and DDL is read as DDL.
        val language = InstructionLanguages.resolveWithUiLang(drawn, requestedLang, uiLang)
        val config = when {
            inherited != null -> deriveSavedConfig(inherited.config, request, renderSeed, language)
            saved == null -> configBuilder.build(
                SharedPipelineConfigRequest(
                    resolvedLanguage = language,
                    canvasFormatId = request.canvasAspect,
                    catalogSelectionId = request.colorCatalogId,
                    renderSeed = renderSeed,
                    compositionSeed = request.compositionSeed,
                    bundledPluginsEnabled = bundledPluginsEnabled(),
                    importedPlugins = request.importedPlugins,
                    drawingModelId = request.drawingModel,
                ),
            )
            else -> {
                val macroCatalog = saved.requiredObject("macro_catalog")
                val parentConfig = configBuilder.fromSavedConfig(
                    configJson = saved.requiredObject("config").toString(),
                    renderColorMaps = saved.requiredObject("color_maps").stringMaps(),
                    macroLocksJson = macroCatalog.requiredArray("definition_locks").toString(),
                    macroDiagnosticsJson = macroCatalog.requiredArray("diagnostics").toString(),
                )
                deriveSavedConfig(parentConfig, request, renderSeed, language)
            }
        }
        val resolvedLang = JSONObject(config.configJson).requiredString("language")
        val context = when {
            parentVariationId != null -> AuthoringContext(
                description = request.description,
                derivationKind = if (descriptionFlow) "description_fork" else "variation_ddl_fork",
                parentVariationId = parentVariationId,
            )
            history?.forkContextJson != null -> AuthoringContext(
                description = request.description,
                derivationKind = if (descriptionFlow) "description_fork" else "variation_ddl_fork",
                parentVariationId = history.variationId,
            )
            history?.authority == "legacy_unknown" -> AuthoringContext(
                description = request.description,
                derivationKind = if (descriptionFlow) "legacy_description_fork" else "legacy_ddl_fork",
                parentLegacyHistoryId = request.parentHistoryId,
            )
            else -> AuthoringContext(request.description)
        }
        return PreparedRun(
            request = SharedPipelineRunRequest(
                ownerId = OWNER_ID,
                text = drawn,
                originalInput = request.originalText,
                config = config,
                models = pinModelSession(PipelineModelSelection(request.drawingModel, request.drawingModel)),
                context = context,
                renderSeed = renderSeed,
                wild = request.renderWild == true,
                interpretationSeed = request.interpretationSeed,
                seedText = seedText,
                instructionLangRequested = requestedLang,
                instructionLangResolved = resolvedLang,
                uiLang = uiLang,
                renderLimitsSource = if (inherited != null || saved != null) "work" else "settings",
                saveHistory = request.saveHistory,
                sketch = PipelineSketchRequest.from(request.sketch),
                parentHistoryId = request.parentHistoryId,
                inputProvenanceJson = request.inputProvenance?.toJson()?.toString(),
            ),
            instructionLangRequested = requestedLang,
            instructionLangResolved = resolvedLang,
        )
    }

    /**
     * The server's `_render_seed_from_text` (`api_core/rendering.py`): words,
     * when there are any, decide the render seed through the shared rule, and
     * the normalized words are what the work records.
     */
    private fun textSeed(seedText: String?, renderSeed: Long?): Pair<Long?, String?> {
        if (seedText.isNullOrEmpty()) return renderSeed to null
        val derived = binding.renderSeedFromText(seedText)?.let(::JSONObject) ?: return renderSeed to null
        return java.lang.Long.parseUnsignedLong(derived.requiredString("render_seed")) to
            derived.requiredString("seed_text")
    }

    /**
     * The compatibility API's request limit (`api_core/routers/render.py`):
     * a description, DDL or sketch text past 100,000 characters is refused
     * before anything runs. Characters are code points, as Python counts them.
     */
    private fun checkInputLength(request: PaintRequest, text: String, descriptionFlow: Boolean) {
        fun check(kind: String, value: String?) {
            val length = value?.let { it.codePointCount(0, it.length) } ?: return
            if (length > MAX_INPUT_CHARACTERS) throw InkuFailure { it.inputTooLong(kind, length, MAX_INPUT_CHARACTERS) }
        }
        check(if (descriptionFlow) "description" else "ddl", text)
        check("sketch", request.sketch.text)
    }

    /**
     * A fork's configuration from its parent's: the parent's compiler policy and
     * plugins with this request's canvas, catalog, seeds and language. Colors
     * come from today's catalogs, as the server resolves them for every fork
     * (`pipeline_product.py`); only a replay keeps the work's own colors.
     */
    private fun deriveSavedConfig(
        saved: PreparedPipelineConfig,
        request: PaintRequest,
        renderSeed: Long,
        language: String,
    ): PreparedPipelineConfig {
        val colorMaps = ColorCatalogs.all.associate { it.id to it.renderMap }
        val config = JSONObject(saved.configJson)
        val compiler = config.requiredObject("compiler")
        // A new fork must not inherit a retired request from its saved parent.
        // The original saved configuration remains untouched.
        compiler.remove("stage15_variation")
        val registryReport = JSONObject(binding.canvasRegistry())
        val registry = registryReport.requiredObject("registry")
        if (registry.requiredArray("formats").objects().none { it.requiredString("id") == request.canvasAspect }) {
            throw PipelineHostException("unknown_canvas_format")
        }
        val auto = request.colorCatalogId == "auto"
        val selectedCatalogId = if (auto) "default" else request.colorCatalogId
        if (!colorMaps.containsKey(selectedCatalogId)) {
            throw PipelineHostException("unknown_color_catalog")
        }
        fun resolvedHost(catalogId: String): JSONObject {
            val colors = colorMaps[catalogId]
                ?: throw PipelineHostException("unknown_color_catalog")
            val paletteInput = JSONObject()
                .put("color_map", JSONObject(colors))
                .put("catalog_id", catalogId)
                .put("render_seed", java.lang.Long.toUnsignedString(renderSeed))
                .put("background", "white")
            val palette = JSONObject(
                binding.resolvePalette(paletteInput.toString().encodeToByteArray()).toString(Charsets.UTF_8),
            )
            if (palette.has("error")) throw PipelineHostException(palette.requiredString("error"))
            return JSONObject()
                .put("canvas_format_id", request.canvasAspect)
                .put("canvas_format_registry_id", registry.requiredString("schema"))
                .put("canvas_format_registry_digest", registryReport.requiredString("digest"))
                .put("resolved_catalog_id", catalogId)
                .put("catalog_mode", if (catalogId == "default") "default" else "explicit")
                .put("background", "white")
                .put("palette", palette)
        }
        // Old saved configurations keep composition absent. A new fork that
        // changes the model retains composition but must respect the local limit.
        if (config.has("composition")) {
            config.put("composition", compositionForModel(request.drawingModel))
        }
        compiler
            .put("host", resolvedHost(selectedCatalogId))
            .put(
                "composition_seed",
                request.compositionSeed?.let(java.lang.Long::toUnsignedString)
                    ?: compiler.opt("composition_seed")
                    ?: JSONObject.NULL,
            )
        config.put("language", language)
        config.put(
            "catalogs",
            if (!auto) {
                JSONArray()
            } else {
                JSONArray().also { candidates ->
                    ColorCatalogs.all.forEach { catalog ->
                        candidates.put(
                            JSONObject()
                                .put(
                                    "prompt",
                                    JSONObject()
                                        .put("catalog_id", catalog.id)
                                        .put("label", catalog.name)
                                        .put("description", if (language == "ja") catalog.subJa else catalog.sub),
                                )
                                .put("resolved", resolvedHost(catalog.id).put("catalog_mode", "explicit")),
                        )
                    }
                }
            },
        )
        return PreparedPipelineConfig(
            configJson = config.toString(),
            autoCatalog = auto,
            canvasFormatId = request.canvasAspect,
            catalogId = selectedCatalogId,
            renderColorMaps = colorMaps,
            compositionSeed = compiler.optionalUnsignedLong("composition_seed"),
            errorPolicy = compiler.requiredString("error_policy"),
            macroLocksJson = saved.macroLocksJson,
            macroDiagnosticsJson = saved.macroDiagnosticsJson,
        )
    }

    private suspend fun restoredRun(executionId: String): RestoredRun {
        val execution = host.executionContext(OWNER_ID, executionId)
        val context = JSONObject(execution.hostContextJson)
        val macroCatalog = context.requiredObject("macro_catalog")
        val config = configBuilder.fromSavedConfig(
            configJson = execution.configJson,
            renderColorMaps = context.requiredObject("color_maps").stringMaps(),
            macroLocksJson = macroCatalog.requiredArray("definition_locks").toString(),
            macroDiagnosticsJson = macroCatalog.requiredArray("diagnostics").toString(),
        )
        val hostOptions = context.requiredObject("host_options")
        return RestoredRun(
            config = config,
            models = execution.models,
            renderSeed = hostOptions.optionalUnsignedLong("render_seed"),
            wild = hostOptions.optBoolean("wild", false),
            hostOptions = hostOptions,
            resultOptions = context.requiredObject("result_options"),
            hostContextJson = execution.hostContextJson,
        )
    }

    private fun activeEditorHostContext(stored: RestoredRun, request: PaintRequest): String {
        val context = JSONObject(stored.hostContextJson)
        val resultOptions = context.requiredObject("result_options")
            .put("original_input", request.originalText)
            .put("derivation_kind", "ddl_edit")
        request.parentHistoryId?.let { resultOptions.put("parent_history_id", it) }
        request.inputProvenance?.let { resultOptions.put("input_provenance", it.toJson()) }
        return context.toString()
    }

    /**
     * Whether an edit draws under other settings and so forks, as the server's
     * `author_ddl` compares a re-prepared configuration. The language is read
     * from the edited DDL, so an edit that changes it forks too.
     */
    private fun runtimeOptionsChanged(request: PaintRequest, stored: RestoredRun, ddl: String): Boolean {
        val options = stored.hostOptions
        val language = InstructionLanguages.resolveWithUiLang(
            ddl,
            InstructionLanguages.normalize(
                request.instructionLang
                    ?: stored.resultOptions.optionalString("instruction_lang_requested")
                    ?: InstructionLanguages.AUTO,
            ),
            request.uiLang ?: stored.resultOptions.optionalString("ui_lang"),
        )
        return language != JSONObject(stored.config.configJson).requiredString("language") ||
            request.drawingModel != stored.models.stage1ModelId ||
            request.drawingModel != stored.models.stage2ModelId ||
            (request.colorCatalogId == "auto") != (options.requiredString("catalog_mode") == "auto") ||
            (request.colorCatalogId != "auto" && request.colorCatalogId != options.requiredString("catalog_id")) ||
            request.canvasAspect != options.requiredString("canvas_aspect") ||
            (request.renderSeed != null && request.renderSeed != stored.renderSeed) ||
            (request.renderWild != null && request.renderWild != stored.wild) ||
            (request.compositionSeed != null &&
                request.compositionSeed != options.optionalUnsignedLong("composition_seed")) ||
            (request.instructionLang != null &&
                InstructionLanguages.normalize(request.instructionLang) !=
                stored.resultOptions.optionalString("instruction_lang_requested"))
    }

    /**
     * Author-facing reasons for withheld plugin sentences, as the server stores
     * them. The work's own definitions count as enabled; the bundled package's
     * names are enabled or disabled with its switch.
     */
    private suspend fun pluginDiagnostics(source: String, upstream: JSONArray, config: JSONObject): JSONArray {
        if (upstream.length() == 0) return JSONArray()
        val bundled = configBuilder.bundledPluginNames(config.optString("language", "ja"))
        val enabledBundled = bundledPluginsEnabled()
        val enabled = (pluginVisibleNames(config.optJSONArray("definitions")) + if (enabledBundled) bundled else emptyList())
            .toSortedSet()
        val disabled = if (enabledBundled) emptyList() else bundled.filterNot { it in enabled }.sorted()
        val input = JSONObject()
            .put("source", source)
            .put("upstream_diagnostics", upstream)
            .put("enabled", JSONArray(enabled.toList()))
            .put("disabled", JSONArray(disabled))
        val output = JSONObject(binding.explainPluginDiagnostics(input.toString().encodeToByteArray()).decodeToString())
        return output.optJSONArray("plugins")
            ?.takeIf { output.optString("schema") == "inku.plugin-diagnostics.v1" }
            ?: JSONArray()
    }

    private fun pipelineDiagnostics(delivery: JSONObject, metadata: JSONObject) = JSONObject()
        .put("upstream_diagnostics", delivery.requiredArray("upstream_diagnostics"))
        .put("downstream_diagnostics", delivery.requiredArray("downstream_diagnostics"))
        .put("resource_omissions", delivery.requiredArray("resource_omissions"))
        .put("relation_omissions", delivery.requiredArray("relation_omissions"))
        .put("render_diagnostics", metadata.optJSONObject("execution") ?: JSONObject.NULL)
        .put("resource_execution", metadata.optJSONObject("resource_execution") ?: JSONObject.NULL)

    private fun canvas(id: String): CanvasInfo {
        val format = JSONObject(binding.canvasRegistry())
            .requiredObject("registry")
            .requiredArray("formats")
            .objects()
            .firstOrNull { it.requiredString("id") == id }
            ?: throw PipelineHostException("unknown_canvas_format")
        val ratio = format.getDouble("width_units") / format.getDouble("height_units")
        return CanvasInfo(Math.rint(CANVAS_BASE_PX * ratio), CANVAS_BASE_PX, ratio)
    }

    /**
     * The four limits a work records, in the server's names (`limits.py`),
     * read from the compiler budget the work was drawn under.
     */
    private fun renderLimits(operationalBudget: JSONObject): JSONObject {
        val maximum = operationalBudget.requiredObject("maximum")
        return JSONObject()
            .put("max_expanded_primitives", maximum.get("primitive_marks"))
            .put("max_expanded_per_instruction", maximum.get("maximum_per_template_primitive_marks"))
            .put("schema_count_max", maximum.get("maximum_resolved_count"))
            .put("max_instructions", maximum.get("object_templates"))
    }

    /** The server's render clip limits (`pipeline_defaults.py`). */
    private fun clipPolicy() = JSONObject()
        .put("tolerance_pixels", 0.1)
        .put("max_nodes", "50000")
        .put("max_path_elements", "200000")
        .put("max_flattened_points", "200000")
        .put("max_work", "10000000")
        .put("max_output_vertices", "200000")

    // JavaScript-safe, as SPEC and the server's pipeline issue it (c2571ac6):
    // a work Android makes may be redrawn where its seed is a JavaScript number.
    private fun newRenderSeed(): Long = SeedFactory.newRenderSeed()

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.encodeToByteArray())
        .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }

    /** The server's `render_hash_for_item` (`persistence/history.py`), so a work has one hash on both. */
    private fun renderHash(score: JSONObject, metadata: JSONObject, fallbackCatalogId: String): String {
        val payload = JSONObject()
            .put(
                "render_color_catalog_id",
                metadata.optString("render_color_catalog_id", fallbackCatalogId).ifBlank { fallbackCatalogId },
            )
            .put("render_engine_id", metadata.optionalString("render_engine_id") ?: JSONObject.NULL)
            .put("render_engine_version", metadata.optionalString("render_engine_version") ?: JSONObject.NULL)
            .put("render_seed", canonicalSeed(metadata.opt("render_seed")) ?: JSONObject.NULL)
            .put("render_wild", metadata.optBoolean("render_wild", metadata.optBoolean("wild", false)))
            .put("score", score)
            .put("version", "rh3")
        return "rh3:" + sha256(PythonJson.canonical(payload))
    }

    private fun canonicalSeed(value: Any?): Any? = when (value) {
        null, JSONObject.NULL -> null
        is BigInteger -> value
        is Long -> if (value >= 0L) value else BigInteger(java.lang.Long.toUnsignedString(value))
        is Int, is Short, is Byte -> (value as Number).toLong()
        is Number -> value
        is String -> value.toBigIntegerOrNull() ?: value
        else -> value
    }

    private fun JSONObject.optionalString(name: String): String? =
        if (!has(name) || isNull(name)) null else optString(name).takeIf(String::isNotEmpty)

    private fun JSONObject.optionalUnsignedLong(name: String): Long? =
        optionalString(name)?.let { value ->
            runCatching { java.lang.Long.parseUnsignedLong(value) }
                .getOrElse { throw PipelineHostException("pipeline_schema_violation", it) }
        }

    private fun JSONObject.requiredArray(name: String): JSONArray =
        optJSONArray(name) ?: throw PipelineHostException("pipeline_schema_violation")

    private fun JSONArray.objects(): List<JSONObject> =
        (0 until length()).map { index ->
            optJSONObject(index) ?: throw PipelineHostException("pipeline_schema_violation")
        }

    private fun JSONObject.stringMaps(): Map<String, Map<String, String>> =
        keys().asSequence().associateWith { catalogId ->
            requiredObject(catalogId).let { colors ->
                colors.keys().asSequence().associateWith { color -> colors.requiredString(color) }
            }
        }

    private data class PreparedRun(
        val request: SharedPipelineRunRequest,
        val instructionLangRequested: String,
        val instructionLangResolved: String,
    )

    /** A running execution's settings, inherited by a fork made from it. */
    private data class InheritedRun(
        val config: PreparedPipelineConfig,
        val renderSeed: Long?,
        val seedText: String?,
        val instructionLang: String?,
        val uiLang: String?,
    )

    private data class RestoredRun(
        val config: PreparedPipelineConfig,
        val models: PipelineModelSelection,
        val renderSeed: Long?,
        val wild: Boolean,
        val hostOptions: JSONObject,
        val resultOptions: JSONObject,
        val hostContextJson: String,
    )

    private data class CanvasInfo(val width: Double, val height: Double, val ratio: Double)

    companion object {
        /** Convert only completed sketch outcomes to the saved-column vocabulary. */
        internal fun savedSketchResult(sketch: PipelineSketchResult): PipelineSketchResult = when (sketch.state) {
            "supplemented", "supplied" -> if (sketch.text.isNullOrBlank()) {
                PipelineSketchResult(state = "fallback")
            } else {
                sketch.copy(state = "supplemented")
            }
            "off", "not_needed", "fallback" -> PipelineSketchResult(state = sketch.state)
            else -> throw PipelineHostException("sketch_outcome_not_ready")
        }

        const val OWNER_ID = "local"
        // A canvas only Android had. Its works still draw through the legacy
        // renderer; a new work started from one uses the default canvas.
        private const val PIXEL9_HOST_ONLY_FORMAT = "pixel9_landscape_safe"
        private const val CANVAS_BASE_PX = 1000.0
        private const val MAX_INPUT_CHARACTERS = 100_000
    }
}
