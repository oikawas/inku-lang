package app.inku.mobile.pipeline

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
) {
    private val configBuilder = SharedPipelineConfigBuilder(binding)
    private val host = SharedPipelineHost(
        binding = binding,
        providerEffect = SingleAttemptModelEffectProvider(modelProvider),
        commitStore = commitStore,
        executionStore = executionStore,
        maxEffectSteps = configBuilder.policy.maximumEffectSteps,
        onProviderAttempt = onProviderAttempt,
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
            expandedDdl = ddl,
            ddlForDisplay = ddl,
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
     * one, changed run options (models, colors, canvas, seeds, Wild, variation,
     * language) fork a new variation from the saved policy. Otherwise the edit
     * is committed to the same execution, declining a pending patch proposal
     * first. Unchanged DDL is drawn without a commit, unless a patch proposal
     * still waits for an answer.
     */
    suspend fun composeFromDdl(
        ddl: String,
        rawRequest: PaintRequest,
        onProgress: suspend (ComposeFromDdlProgress) -> Unit = {},
    ): PaintResult {
        val request = authoringRequest(rawRequest)
        onProgress(ComposeFromDdlProgress.Rendering)
        val existingId = request.executionId
        if (existingId == null) {
            return readyResult(authoring.startDirectDdl(prepare(request, descriptionFlow = false, text = ddl).request))
        }

        val current = host.view(OWNER_ID, existingId)
        val stored = restoredRun(existingId)
        if (runtimeOptionsChanged(request, stored)) {
            val renderSeed = request.renderSeed ?: stored.renderSeed ?: newRenderSeed()
            val derivedConfig = deriveSavedConfig(stored.config, request, renderSeed)
            val fork = prepare(
                request.copy(executionId = null),
                descriptionFlow = false,
                text = ddl,
                parentVariationId = current.variationId,
                configOverride = derivedConfig,
                renderSeedOverride = renderSeed,
            )
            return readyResult(authoring.startDirectDdl(fork.request))
        }
        val editable = if (current.phaseTag == "awaiting_patch_approval") {
            if (current.visibleDdl == ddl) throw PipelineInteractionRequired(current)
            val proposal = current.patchProposal ?: throw PipelineHostException("patch_proposal_required")
            host.command(
                OWNER_ID,
                existingId,
                PipelineCommand.DeclinePatch(proposal.proposalDigest),
            )
        } else {
            current
        }
        val next = if (editable.visibleDdl == ddl) {
            editable
        } else {
            host.command(
                OWNER_ID,
                existingId,
                PipelineCommand.CommitUserDdl(editable.revision, ddl),
                hostContextJson = activeEditorHostContext(stored, request),
            )
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

    suspend fun approvePatch(executionId: String): PaintResult {
        val current = host.view(OWNER_ID, executionId)
        val proposal = current.patchProposal ?: throw PipelineHostException("patch_proposal_required")
        val next = host.command(
            OWNER_ID,
            executionId,
            PipelineCommand.ApprovePatch(current.revision, proposal.proposalDigest),
        )
        if (next.phaseTag != "score_ready" && next.phaseTag != "completed") {
            throw PipelineInteractionRequired(next)
        }
        val stored = restoredRun(executionId)
        return project(authoring.renderReady(OWNER_ID, next, stored.config, stored.renderSeed, stored.wild))
    }

    suspend fun declinePatch(executionId: String): PipelineView {
        val current = host.view(OWNER_ID, executionId)
        val proposal = current.patchProposal ?: throw PipelineHostException("patch_proposal_required")
        return host.command(
            OWNER_ID,
            executionId,
            PipelineCommand.DeclinePatch(proposal.proposalDigest),
        )
    }

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
            return replayResult(scoreJson, request, rendered.svg, metadata, replaySource)
        }

        val saved = renderSaved(scoreJson, request, svgProfile = "display")
        val catalogId = saved.catalogId
        val colors = saved.colors
        val canvas = saved.canvas
        val renderSeed = saved.renderSeed
        val output = saved.output
        val metadata = output.requiredObject("metadata")
            .put("catalog_id", catalogId)
            .put("canvas_aspect_id", request.canvasAspect)
            .put("render_canvas_aspect", request.canvasAspect)
            .put("render_canvas_aspect_id", request.canvasAspect)
            .put("render_canvas_aspect_ratio", canvas.ratio)
            .put("render_color_catalog_id", catalogId)
            .put("render_color_map", JSONObject(colors))
            .put("render_seed", java.lang.Long.toUnsignedString(renderSeed))
            .put("render_wild", request.renderWild == true)
        val replayRequest = request.copy(renderSeed = renderSeed)
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
        val renderSeed = request.renderSeed ?: newRenderSeed()
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
        if (output.has("error")) throw PipelineHostException(output.requiredString("error"))
        return SavedRender(output, catalogId, colors, canvas, renderSeed)
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

    private suspend fun project(view: PipelineView): PaintResult {
        if (view.phaseTag != "completed" || view.renderedJson == null) {
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
        metadata.put("pipeline_diagnostics", diagnostics)
        val renderHash = renderHash(delivery.requiredObject("score"), metadata, catalogId)
        metadata.put("render_hash", renderHash).put("render_hash_short", renderHash.takeLast(4).uppercase())
        return PaintResult(
            originalInput = resultOptions.optString("original_input", execution.authoringContext.description),
            normalizedDdl = ddl,
            expandedDdl = ddl,
            scoreJson = delivery.requiredObject("score").toString(),
            displaySvg = svg,
            renderMetadataJson = metadata.toString(),
            renderHash = renderHash,
            renderHashShort = renderHash.takeLast(4).uppercase(),
            renderSeed = hostOptions.optionalUnsignedLong("render_seed"),
            compositionSeed = compiler.optionalUnsignedLong("composition_seed"),
            interpretationSeed = resultOptions.optionalString("interpretation_seed"),
            variationAmplitude = resultOptions.optionalString("variation_amplitude"),
            variationSeed = resultOptions.optionalUnsignedLong("variation_seed"),
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
            normalizedDdl = source?.history?.normalizedDdl ?: request.description,
            expandedDdl = source?.history?.expandedDdl ?: source?.history?.normalizedDdl ?: request.description,
            scoreJson = JSONObject(scoreJson).toString(),
            displaySvg = svg,
            renderMetadataJson = metadata.toString(),
            renderHash = hash,
            renderHashShort = hash.takeLast(4).uppercase(),
            renderSeed = request.renderSeed,
            compositionSeed = request.compositionSeed,
            interpretationSeed = request.interpretationSeed,
            variationAmplitude = request.variationAmplitude,
            variationSeed = request.variationSeed,
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
        configOverride: PreparedPipelineConfig? = null,
        renderSeedOverride: Long? = null,
    ): PreparedRun {
        // Legacy paper remains valid for display/replay; new works use the
        // canonical default even when started from a legacy history selection.
        val request = authoringRequest(rawRequest)
        val history = request.parentHistoryId?.let { historyId ->
            readHistory(historyId) ?: throw PipelineHostException("parent_history_not_found")
        }
        if (history != null && history.authority != "legacy_unknown" &&
            (history.warning != null || history.authority == null || history.forkContextJson == null)
        ) {
            throw PipelineHostException("saved_history_context_corrupt")
        }
        val saved = history?.forkContextJson?.let(::JSONObject)
        val renderSeed = renderSeedOverride ?: request.renderSeed ?: saved?.requiredObject("host_options")
            ?.optionalUnsignedLong("render_seed") ?: newRenderSeed()
        val config = configOverride ?: if (saved == null) {
            configBuilder.build(
                SharedPipelineConfigRequest(
                    resolvedLanguage = InstructionLanguages.resolveWithUiLang(
                        request.description.ifBlank { text },
                        InstructionLanguages.normalize(request.instructionLang),
                        request.uiLang,
                    ),
                    canvasFormatId = request.canvasAspect,
                    catalogSelectionId = request.colorCatalogId,
                    renderSeed = renderSeed,
                    compositionSeed = request.compositionSeed,
                    variationAmplitude = request.variationAmplitude,
                    variationSeed = request.variationSeed,
                    bundledPluginsEnabled = bundledPluginsEnabled(),
                    importedPlugins = request.importedPlugins,
                ),
            )
        } else {
            val macroCatalog = saved.requiredObject("macro_catalog")
            val inherited = configBuilder.fromSavedConfig(
                configJson = saved.requiredObject("config").toString(),
                renderColorMaps = saved.requiredObject("color_maps").stringMaps(),
                macroLocksJson = macroCatalog.requiredArray("definition_locks").toString(),
                macroDiagnosticsJson = macroCatalog.requiredArray("diagnostics").toString(),
            )
            deriveSavedConfig(inherited, request, renderSeed)
        }
        val requestedLang = InstructionLanguages.normalize(request.instructionLang)
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
                text = text,
                originalInput = request.originalText,
                config = config,
                models = PipelineModelSelection(request.stage1Model, request.stage2Model),
                context = context,
                renderSeed = renderSeed,
                wild = request.renderWild == true,
                interpretationSeed = request.interpretationSeed,
                variationAmplitude = request.variationAmplitude,
                variationSeed = request.variationSeed,
                seedText = request.seedText,
                instructionLangRequested = requestedLang,
                instructionLangResolved = resolvedLang,
                sketch = PipelineSketchRequest.from(request.sketch),
                parentHistoryId = request.parentHistoryId,
                inputProvenanceJson = request.inputProvenance?.toJson()?.toString(),
            ),
            instructionLangRequested = requestedLang,
            instructionLangResolved = resolvedLang,
        )
    }

    private fun deriveSavedConfig(
        saved: PreparedPipelineConfig,
        request: PaintRequest,
        renderSeed: Long,
    ): PreparedPipelineConfig {
        val config = JSONObject(saved.configJson)
        val compiler = config.requiredObject("compiler")
        val registryReport = JSONObject(binding.canvasRegistry())
        val registry = registryReport.requiredObject("registry")
        if (registry.requiredArray("formats").objects().none { it.requiredString("id") == request.canvasAspect }) {
            throw PipelineHostException("unknown_canvas_format")
        }
        val auto = request.colorCatalogId == "auto"
        val selectedCatalogId = if (auto) "default" else request.colorCatalogId
        if (!saved.renderColorMaps.containsKey(selectedCatalogId)) {
            throw PipelineHostException("saved_color_catalog_unavailable")
        }
        fun resolvedHost(catalogId: String): JSONObject {
            val colors = saved.renderColorMaps[catalogId]
                ?: throw PipelineHostException("saved_color_catalog_unavailable")
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
        compiler
            .put("host", resolvedHost(selectedCatalogId))
            .put(
                "composition_seed",
                request.compositionSeed?.let(java.lang.Long::toUnsignedString)
                    ?: compiler.opt("composition_seed")
                    ?: JSONObject.NULL,
            )
        if (request.variationAmplitude != null || request.variationSeed != null) {
            if ((request.variationAmplitude == null) != (request.variationSeed == null)) {
                throw PipelineHostException("variation_pair_required")
            }
            compiler.put(
                "stage15_variation",
                JSONObject()
                    .put("amplitude", request.variationAmplitude)
                    .put("seed", request.variationSeed?.let(java.lang.Long::toUnsignedString)),
            )
        }
        if (request.instructionLang != null) {
            config.put(
                "language",
                InstructionLanguages.resolveWithUiLang(
                    request.description,
                    InstructionLanguages.normalize(request.instructionLang),
                    request.uiLang,
                ),
            )
        }
        config.put(
            "catalogs",
            if (!auto) {
                JSONArray()
            } else {
                JSONArray().also { candidates ->
                    ColorCatalogs.all.forEach { catalog ->
                        if (saved.renderColorMaps.containsKey(catalog.id)) {
                            candidates.put(
                                JSONObject()
                                    .put(
                                        "prompt",
                                        JSONObject()
                                            .put("catalog_id", catalog.id)
                                            .put("label", catalog.name)
                                            .put(
                                                "description",
                                                if (config.requiredString("language") == "ja") catalog.subJa else catalog.sub,
                                            ),
                                    )
                                    .put("resolved", resolvedHost(catalog.id).put("catalog_mode", "explicit")),
                            )
                        }
                    }
                }
            },
        )
        return PreparedPipelineConfig(
            configJson = config.toString(),
            autoCatalog = auto,
            canvasFormatId = request.canvasAspect,
            catalogId = selectedCatalogId,
            renderColorMaps = saved.renderColorMaps,
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

    private fun runtimeOptionsChanged(request: PaintRequest, stored: RestoredRun): Boolean {
        val options = stored.hostOptions
        return request.stage1Model != stored.models.stage1ModelId ||
            request.stage2Model != stored.models.stage2ModelId ||
            (request.colorCatalogId == "auto") != (options.requiredString("catalog_mode") == "auto") ||
            (request.colorCatalogId != "auto" && request.colorCatalogId != options.requiredString("catalog_id")) ||
            request.canvasAspect != options.requiredString("canvas_aspect") ||
            (request.renderSeed != null && request.renderSeed != stored.renderSeed) ||
            (request.renderWild != null && request.renderWild != stored.wild) ||
            (request.compositionSeed != null &&
                request.compositionSeed != options.optionalUnsignedLong("composition_seed")) ||
            (request.variationAmplitude != null &&
                request.variationAmplitude != stored.resultOptions.optionalString("variation_amplitude")) ||
            (request.variationSeed != null &&
                request.variationSeed != stored.resultOptions.optionalUnsignedLong("variation_seed")) ||
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
        return "rh3:" + sha256(canonicalJson(payload))
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

    private fun canonicalJson(value: Any?): String = when (value) {
        null, JSONObject.NULL -> "null"
        is JSONObject -> value.keys().asSequence().toList().sorted().joinToString(
            separator = ",",
            prefix = "{",
            postfix = "}",
        ) { key -> JSONObject.quote(key) + ":" + canonicalJson(value.opt(key)) }
        is JSONArray -> (0 until value.length()).joinToString(
            separator = ",",
            prefix = "[",
            postfix = "]",
        ) { index -> canonicalJson(value.opt(index)) }
        is String -> JSONObject.quote(value)
        is Number, is Boolean -> value.toString()
        else -> JSONObject.quote(value.toString())
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
    }
}
