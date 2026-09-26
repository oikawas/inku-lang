package app.inku.mobile.pipeline

data class SharedPipelineRunRequest(
    val ownerId: String,
    val text: String,
    val originalInput: String = text,
    val config: PreparedPipelineConfig,
    val models: PipelineModelSelection,
    val context: AuthoringContext,
    val renderSeed: Long? = null,
    val wild: Boolean = false,
    val interpretationSeed: String? = null,
    val variationAmplitude: String? = null,
    val variationSeed: Long? = null,
    val seedText: String? = null,
    val instructionLangRequested: String? = null,
    val instructionLangResolved: String? = null,
    val sketch: PipelineSketchRequest = PipelineSketchRequest.Off,
    val parentHistoryId: String? = null,
    val inputProvenanceJson: String? = null,
)

sealed interface PipelineRunOutcome {
    data class Ready(val view: PipelineView) : PipelineRunOutcome
    data class InteractionRequired(val view: PipelineView) : PipelineRunOutcome
}

/** Existing callers use this facade while visible patch approval remains an explicit outcome. */
class SharedAuthoringPipeline(
    private val host: SharedPipelineHost,
    private val configBuilder: SharedPipelineConfigBuilder,
) {
    suspend fun startDescription(request: SharedPipelineRunRequest): PipelineRunOutcome {
        val view = startDescriptionView(request)
        return complete(request.ownerId, view, request.config, request.renderSeed, request.wild)
    }

    suspend fun startDescriptionView(request: SharedPipelineRunRequest): PipelineView =
        host.start(
            PipelineStartRequest(
                ownerId = request.ownerId,
                configJson = request.config.configJson,
                authoring = PipelineAuthoring.Description(
                    text = request.text,
                    autoCatalog = request.config.autoCatalog,
                    sketch = request.sketch,
                ),
                models = request.models,
                context = request.context,
                hostContextJson = durableHostContext(request),
            ),
        )

    suspend fun startDirectDdl(request: SharedPipelineRunRequest): PipelineRunOutcome {
        val view = startDirectDdlView(request)
        return complete(request.ownerId, view, request.config, request.renderSeed, request.wild)
    }

    suspend fun startDirectDdlView(request: SharedPipelineRunRequest): PipelineView =
        host.start(
            PipelineStartRequest(
                ownerId = request.ownerId,
                configJson = request.config.configJson,
                authoring = PipelineAuthoring.DirectDdl(request.text),
                models = request.models,
                context = request.context,
                hostContextJson = durableHostContext(request),
            ),
        )

    suspend fun renderReady(
        ownerId: String,
        view: PipelineView,
        config: PreparedPipelineConfig,
        renderSeed: Long?,
        wild: Boolean,
    ): PipelineView = if (view.phaseTag == "score_ready") {
        host.command(
            ownerId,
            view.executionId,
            configBuilder.renderCommand(config, view, renderSeed, wild),
        )
    } else {
        view
    }

    suspend fun approvePatch(
        ownerId: String,
        view: PipelineView,
        config: PreparedPipelineConfig,
        renderSeed: Long?,
        wild: Boolean,
    ): PipelineRunOutcome {
        val proposal = view.patchProposal ?: throw PipelineHostException("patch_proposal_required")
        val next = host.command(
            ownerId,
            view.executionId,
            PipelineCommand.ApprovePatch(
                expectedRevision = view.revision,
                proposalDigest = proposal.proposalDigest,
            ),
        )
        return complete(ownerId, next, config, renderSeed, wild)
    }

    suspend fun declinePatch(ownerId: String, view: PipelineView): PipelineRunOutcome {
        val proposal = view.patchProposal ?: throw PipelineHostException("patch_proposal_required")
        val next = host.command(
            ownerId,
            view.executionId,
            PipelineCommand.DeclinePatch(proposal.proposalDigest),
        )
        return PipelineRunOutcome.InteractionRequired(next)
    }

    suspend fun commitUserDdl(
        ownerId: String,
        view: PipelineView,
        source: String,
        config: PreparedPipelineConfig,
        renderSeed: Long?,
        wild: Boolean,
    ): PipelineRunOutcome {
        val next = host.command(
            ownerId,
            view.executionId,
            PipelineCommand.CommitUserDdl(view.revision, source),
        )
        return complete(ownerId, next, config, renderSeed, wild)
    }

    suspend fun regenerateDescription(
        ownerId: String,
        view: PipelineView,
        description: String,
        config: PreparedPipelineConfig,
        renderSeed: Long?,
        wild: Boolean,
        sketch: PipelineSketchRequest = PipelineSketchRequest.Off,
    ): PipelineRunOutcome {
        val next = host.command(
            ownerId,
            view.executionId,
            PipelineCommand.GenerateFromDescription(
                expectedRevision = view.revision,
                description = description,
                autoCatalog = config.autoCatalog,
                sketch = sketch,
            ),
        )
        return complete(ownerId, next, config, renderSeed, wild)
    }

    suspend fun cancel(ownerId: String, executionId: String): PipelineView =
        host.cancel(ownerId, executionId)

    /**
     * The host's options, saved with the execution. A later command and a run
     * resumed after the process ended read them back, and the saved work keeps
     * its options, colors and macro catalog for forks and replays
     * (`RoomSharedPipelineStore`). Seeds are unsigned decimal strings, the
     * way the core reads 64-bit values.
     */
    private fun durableHostContext(request: SharedPipelineRunRequest): String =
        org.json.JSONObject()
            .put("schema", "inku.android-pipeline-host-context.v1")
            .put(
                "host_options",
                org.json.JSONObject()
                    .put("render_seed", request.renderSeed?.let(java.lang.Long::toUnsignedString))
                    .put("composition_seed", request.config.compositionSeed?.let(java.lang.Long::toUnsignedString))
                    .put("wild", request.wild)
                    .put("error_policy", request.config.errorPolicy)
                    .put("canvas_aspect", request.config.canvasFormatId)
                    .put("catalog_id", request.config.catalogId)
                    .put("catalog_mode", if (request.config.autoCatalog) "auto" else "fixed"),
            )
            .put(
                "macro_catalog",
                org.json.JSONObject()
                    .put("definition_locks", org.json.JSONArray(request.config.macroLocksJson))
                    .put("diagnostics", org.json.JSONArray(request.config.macroDiagnosticsJson)),
            )
            .put("auto_catalog", request.config.autoCatalog)
            .put(
                "result_options",
                org.json.JSONObject()
                    .put("original_input", request.originalInput)
                    .put("interpretation_seed", request.interpretationSeed)
                    .put("variation_amplitude", request.variationAmplitude)
                    .put("variation_seed", request.variationSeed?.let(java.lang.Long::toUnsignedString))
                    .put("seed_text", request.seedText)
                    .put("instruction_lang_requested", request.instructionLangRequested)
                    .put("instruction_lang_resolved", request.instructionLangResolved)
                    .put("parent_history_id", request.parentHistoryId)
                    .put("input_provenance", request.inputProvenanceJson?.let { org.json.JSONObject(it) }),
            )
            .put(
                "color_maps",
                org.json.JSONObject().also { maps ->
                    request.config.renderColorMaps.forEach { (catalogId, colors) ->
                        maps.put(catalogId, org.json.JSONObject(colors))
                    }
                },
            )
            .toString()

    private suspend fun complete(
        ownerId: String,
        initial: PipelineView,
        config: PreparedPipelineConfig,
        renderSeed: Long?,
        wild: Boolean,
    ): PipelineRunOutcome {
        val view = renderReady(ownerId, initial, config, renderSeed, wild)
        return if (view.phaseTag == "completed" && view.renderedJson != null) {
            PipelineRunOutcome.Ready(view)
        } else {
            PipelineRunOutcome.InteractionRequired(view)
        }
    }
}
