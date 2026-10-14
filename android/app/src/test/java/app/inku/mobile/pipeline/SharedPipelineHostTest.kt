package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.data.DdlSource
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.ManagedHistoryRead
import app.inku.mobile.data.db.LineageNodeEntity
import app.inku.mobile.data.lineage.LineageDeclaration
import app.inku.mobile.data.lineage.LineagePlanner
import app.inku.mobile.render.SvgRenderer
import app.inku.mobile.render.RenderResult
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.ui.InkuUiState
import app.inku.mobile.ui.InkuViewModel
import app.inku.mobile.ui.beginDescriptionDrawing
import app.inku.mobile.ui.descriptionDrawingParent
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.Job
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.yield
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.fail
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedPipelineHostTest {
    @Test
    fun descriptionRedrawKeepsItsSavedParentAfterOnePrecommitStop() = descriptionRedrawAfterStops(true, 1)

    @Test
    fun descriptionRedrawKeepsItsSavedParentAfterRepeatedPrecommitStops() = descriptionRedrawAfterStops(true, 2)

    @Test
    fun descriptionRedrawWithoutAParentRemainsARootAfterAPrecommitStop() = descriptionRedrawAfterStops(false, 1)

    @Test
    fun descriptionRedrawParentDoesNotSurviveSaveDetachOrAnotherDrawingOperation() {
        val parent = HistoryItemEntity(
            id = "saved-parent", createdAt = 1, updatedAt = 2, originalInput = "old mist",
            normalizedDdl = "place one circle.", scoreJson = "{}", displaySvg = "<svg/>",
            stage1Model = "fixture:model", stage2Model = "fixture:model", renderMetadataJson = "{}",
            renderHash = "hash", renderHashShort = "0000", colorCatalogId = "default", canvasAspect = "square",
            starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null, lineageNodeId = "saved-parent-node",
        )
        val stopped = InkuUiState(selectedHistory = parent).beginDescriptionDrawing().copy(isDrawing = false)
        assertEquals(parent, stopped.descriptionDrawingParent)
        assertEquals("newly-saved", stopped.copy(selectedHistory = parent.copy(id = "newly-saved")).descriptionDrawingParent?.id)
        assertNull(stopped.copy(lineageDetached = true).descriptionDrawingParent)
        val state = MutableStateFlow(stopped)
        val viewModel = unconstructedViewModel(state)
        val saved = InkuViewModel::class.java.getDeclaredMethod("descriptionPerformanceSaved", Long::class.javaPrimitiveType)
            .apply { isAccessible = true }
        saved.invoke(viewModel, -1L)
        assertEquals("a stale run cannot clear a newer run's parent", parent, state.value.descriptionDrawingParent)
        saved.invoke(viewModel, 0L)
        assertNull("the first successful save ends retention", state.value.descriptionDrawingParent)
        state.value = stopped
        viewModel.detachLineage()
        assertNull(state.value.pendingDescriptionParent)
        assertNull(state.value.descriptionDrawingParent)
        state.value = stopped
        InkuViewModel::class.java.getDeclaredMethod("beginDrawingRun", Boolean::class.javaPrimitiveType)
            .apply { isAccessible = true }.invoke(viewModel, false)
        assertNull("another drawing operation cannot inherit the pending description parent", state.value.pendingDescriptionParent)
    }

    /** Exercise the UI start/stop boundary without constructing the application or opening SQLite. */
    private fun descriptionRedrawAfterStops(hasSavedParent: Boolean, stopCount: Int) = runBlocking {
        val binding = ScriptedBinding(uniqueExecutions = true).apply { holeDelivers = true }
        val memoryExecutions = MemoryExecutionStore()
        var latestExecutionId: String? = null
        val executions = object : PipelineExecutionStore by memoryExecutions {
            override suspend fun create(ownerId: String, executionId: String, variationId: String, sequence: String, stateBytes: ByteArray) {
                latestExecutionId = executionId
                memoryExecutions.create(ownerId, executionId, variationId, sequence, stateBytes)
            }
        }
        val recording = RecordingCommitStore()
        val contexts = mutableListOf<AuthoringContext>()
        val commits = object : PipelineCommitStore {
            override suspend fun commit(ownerId: String, actionJson: String, createIfMissing: Boolean, context: AuthoringContext): String {
                contexts += context
                return recording.commit(ownerId, actionJson, createIfMissing, context)
            }
        }
        val entered = Channel<Unit>(Channel.UNLIMITED)
        var stage1Calls = 0
        val provider = object : ModelProvider {
            override val providerId = "fixture-only"
            override suspend fun generate(request: ModelRequest): ModelResponse {
                if (request.pipelineAction == "generate_normalized_ddl" && ++stage1Calls <= stopCount) {
                    entered.send(Unit)
                    awaitCancellation()
                }
                return ModelResponse("{}", request.modelId)
            }
        }
        val parent = HistoryItemEntity(
            id = "saved-parent", createdAt = 1, updatedAt = 2, originalInput = "old mist",
            normalizedDdl = "place one circle.", scoreJson = "{}", displaySvg = "<svg/>",
            stage1Model = "fixture:model", stage2Model = "fixture:model", renderMetadataJson = "{}",
            renderHash = "hash", renderHashShort = "0000", colorCatalogId = "default", canvasAspect = "square",
            starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null, lineageNodeId = "saved-parent-node",
        )
        val config = SharedPipelineConfigBuilder(binding).build(
            SharedPipelineConfigRequest("en", "square", "default", bundledPluginsEnabled = false),
        )
        val forkContext = JSONObject()
            .put("config", JSONObject(config.configJson))
            .put("color_maps", JSONObject().put("default", JSONObject(config.renderColorMaps.getValue("default"))))
            .put("macro_catalog", JSONObject().put("definition_locks", JSONArray()).put("diagnostics", JSONArray()))
            .put("host_options", JSONObject().put("render_seed", "7"))
        val safeResults = mutableListOf<PaintResult>()
        val pipeline = AndroidWorkPipeline(
            binding = binding, modelProvider = provider, commitStore = commits, executionStore = executions,
            readHistory = { id ->
                check(id == parent.id)
                ManagedHistoryRead(parent, "description_authoritative", variationId = "saved-parent-variation", forkContextJson = forkContext.toString())
            },
            legacyRenderer = object : SvgRenderer {
                override fun render(request: RenderRequest): RenderResult = error("legacy renderer must not run")
            },
            bundledPluginsEnabled = { false },
            saveSafePerformance = { safeResults += it },
        )
        fun request(parentId: String?) = PaintRequest(
            description = "new mist", originalText = "new mist", stage1Model = "fixture:model", stage2Model = "fixture:model",
            colorCatalogId = "default", canvasAspect = "square", autoRepair = true, renderSeed = 7, instructionLang = "en", parentHistoryId = parentId,
        )
        val state = MutableStateFlow(InkuUiState(prompt = "new mist", selectedHistory = parent.takeIf { hasSavedParent }))
        val viewModel = unconstructedViewModel(state)
        val stoppedParents = mutableListOf<String?>()
        val stoppedVariations = mutableListOf<String>()
        repeat(stopCount) {
            val source = state.value
            val savedParentId = source.descriptionDrawingParent?.id
            state.value = source.beginDescriptionDrawing()
            val drawing = async { pipeline.paint(request(savedParentId)) }
            InkuViewModel::class.java.getDeclaredField("drawingJob").apply { isAccessible = true }.set(viewModel, drawing as Job)
            withTimeout(5_000) { entered.receive() }
            assertTrue("no commit before each stop", contexts.isEmpty())
            assertTrue("no saved performance before each stop", safeResults.isEmpty())
            viewModel.stopDrawing()
            withTimeout(5_000) { drawing.join() }
            assertTrue(drawing.isCancelled)
            assertFalse(state.value.isDrawing)
            assertNull("a stopped run is not a displayed saved work", state.value.selectedHistory)
            val stopped = pipeline.view(requireNotNull(latestExecutionId))
            assertEquals("cancelled", stopped.phaseTag)
            stoppedVariations += stopped.variationId
            val stored = JSONObject(executions.load(AndroidWorkPipeline.OWNER_ID, stopped.executionId)!!.toString(Charsets.UTF_8))
            stoppedParents += stored.getJSONObject("context").optString("parent_variation_id").takeIf(String::isNotEmpty)
        }
        val source = state.value
        val declaration = InkuViewModel::class.java.getDeclaredMethod("describeLineage", InkuUiState::class.java)
            .apply { isAccessible = true }.invoke(viewModel, source) as LineageDeclaration
        val nextParentId = source.descriptionDrawingParent?.id
        state.value = source.beginDescriptionDrawing()
        val interaction = runCatching { pipeline.paint(request(nextParentId)) }.exceptionOrNull()
        assertTrue("the scripted core reached approval after its first commit", interaction is PipelineInteractionRequired)
        val awaiting = (interaction as PipelineInteractionRequired).view
        assertFalse(stoppedVariations.contains(awaiting.variationId))
        assertEquals(1, contexts.size)
        assertTrue("the first committed work can be performed and saved", safeResults.isNotEmpty())
        val finished = pipeline.approvePatch(awaiting.executionId, awaiting.revision, awaiting.patchProposal!!.proposalDigest)
        assertEquals("completed", finished.pipelineView!!.phaseTag)
        val parentNode = parent.takeIf { hasSavedParent }?.let {
            LineageNodeEntity(id = it.lineageNodeId!!, historyId = it.id, state = "active", descriptionHash = "parent-description",
                renderHash = "hash", at = 1, rootNodeId = it.lineageNodeId)
        }
        val write = LineagePlanner.plan(
            nodeId = "redrawn-node", edgeId = "redrawn-edge", historyId = "redrawn-history", at = 3,
            descriptionHash = "description", renderHash = finished.renderHash, historyVisibility = null,
            declaration = declaration, parentNode = parentNode,
        )
        println("DESCRIPTION_REDRAW " + JSONObject()
            .put("saved_parent", hasSavedParent).put("stop_count", stopCount)
            .put("stopped_parent_variations", JSONArray(stoppedParents.map { it ?: JSONObject.NULL }))
            .put("commits_before_redraw", 0).put("redraw_parent_history_id", nextParentId ?: JSONObject.NULL)
            .put("redraw_parent_variation_id", contexts.first().parentVariationId ?: JSONObject.NULL)
            .put("redraw_phase", finished.pipelineView.phaseTag)
            .put("lineage_parent_node_id", write.edge?.parentNodeId ?: JSONObject.NULL)
            .put("lineage_root_node_id", write.node.rootNodeId)
            .put("fake_stage1_calls", stage1Calls).put("llm_calls", 0).put("real_db_writes", 0))
        val expectedVariationParent = "saved-parent-variation".takeIf { hasSavedParent }
        assertEquals("the next run must keep the saved history", parent.id.takeIf { hasSavedParent }, nextParentId)
        assertEquals(List(stopCount) { expectedVariationParent }, stoppedParents)
        assertTrue(contexts.all { it.parentVariationId == expectedVariationParent && it.parentLegacyHistoryId == null })
        assertTrue(contexts.none { stoppedVariations.contains(it.parentVariationId) })
        assertEquals(if (hasSavedParent) "description_fork" else "new", contexts.first().derivationKind)
        assertEquals(parent.lineageNodeId.takeIf { hasSavedParent }, write.edge?.parentNodeId)
        assertEquals(if (hasSavedParent) parent.lineageNodeId else "redrawn-node", write.node.rootNodeId)
        assertEquals(nextParentId.orEmpty(), JSONObject(finished.renderMetadataJson).optString("parent_history_id"))
    }

    private fun unconstructedViewModel(state: MutableStateFlow<InkuUiState>): InkuViewModel {
        val unsafeType = Class.forName("sun.misc.Unsafe")
        val unsafe = unsafeType.getDeclaredField("theUnsafe").apply { isAccessible = true }.get(null)
        val viewModel = unsafeType.getMethod("allocateInstance", Class::class.java).invoke(unsafe, InkuViewModel::class.java) as InkuViewModel
        InkuViewModel::class.java.getDeclaredField("localState").apply { isAccessible = true }.set(viewModel, state)
        return viewModel
    }

    @Test
    fun svgLimitRefusalPersistsWithoutStaleSuccessAndRerenderReadsCurrentAllowance() = runBlocking {
        val scripted = ScriptedBinding()
        var limit = app.inku.mobile.render.SvgOutputLimit.BYTES_PER_MIB
        val boundarySvg = "<svg>" + "あ".repeat(349521) + "ab</svg>"
        assertEquals(limit, boundarySvg.toByteArray(Charsets.UTF_8).size.toLong())
        var svg = boundarySvg
        val allowances = mutableListOf<Long>()
        val binding = object : SharedPipelineBinding by scripted {
            override fun stepSvgLimited(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray, maxSvgBytes: Long): NativeSvgOutput {
                allowances += maxSvgBytes
                val output = JSONObject(scripted.step(snapshotBytes, inputEnvelopeBytes).toString(Charsets.UTF_8))
                val rendered = output.getJSONObject("payload").getJSONObject("result").optJSONObject("rendered")
                rendered?.put("svg", "")
                return NativeSvgOutput(output.toString().encodeToByteArray(), if (rendered != null) svg else null)
            }
        }
        val executions = MemoryExecutionStore()
        val commits = RecordingCommitStore()
        val provider = RecordingEffectProvider()
        val render = PipelineCommand.Render("{}", "{}")
        var safeSaves = 0
        fun newHost() = SharedPipelineHost(binding, provider, commits, executions, readSvgLimitBytes = { limit },
            safePerformance = object : SafePerformancePort {
                override fun renderCommand(view: PipelineView) = render
                override suspend fun save(view: PipelineView) { safeSaves += 1 }
            })
        val host = newHost()
        val ready = host.start(startRequest(PipelineAuthoring.DirectDdl("place one circle.")))
        val success = host.command(OWNER, ready.executionId, render)
        assertEquals(boundarySvg, JSONObject(success.renderedJson!!).getString("svg"))
        svg += "!"
        val refused = host.command(OWNER, ready.executionId, render)
        assertEquals("failed", refused.phaseTag)
        assertEquals("svg_output_too_large", refused.phaseReason)
        assertTrue(refused.terminal)
        assertFalse(refused.busy)
        assertNull(refused.renderedJson)
        assertEquals(1, refused.svgOutputLimitMiB)
        assertEquals(0, safeSaves)
        val stored = JSONObject(executions.load(OWNER, ready.executionId)!!.toString(Charsets.UTF_8))
        assertTrue(stored.getBoolean("svg_output_failure"))
        assertFalse(stored.has("rendered_json"))
        val calls = allowances.size
        val restored = newHost().restore(OWNER, ready.executionId)
        assertEquals("failed", restored.phaseTag)
        assertEquals(1, restored.svgOutputLimitMiB)
        assertNull(restored.renderedJson)
        assertEquals(calls, allowances.size)
        limit *= 2
        assertEquals(1, newHost().restore(OWNER, ready.executionId).svgOutputLimitMiB)
        assertTrue(app.inku.mobile.ui.pipelineAttentionText("svg_output_too_large", null,
            app.inku.mobile.ui.i18n.InkuStringsEn, 1).contains("1 MiB"))
        val retried = newHost().command(OWNER, ready.executionId, render)
        assertEquals("completed", retried.phaseTag)
        assertEquals(svg, JSONObject(retried.renderedJson!!).getString("svg"))
        assertEquals(limit, allowances.last())
        assertEquals(0, safeSaves)
        assertEquals(CONFIG.toString(), JSONObject(newHost().snapshotJson(OWNER, ready.executionId)).getJSONObject("config").toString())
        assertFalse(JSONObject(executions.load(OWNER, ready.executionId)!!.toString(Charsets.UTF_8)).getBoolean("svg_output_failure"))

        val exportAllowances = mutableListOf<Long>()
        val exportBinding = object : SharedPipelineBinding by ScriptedBinding() {
            override fun renderSavedSvgLimited(inputBytes: ByteArray, maxSvgBytes: Long): NativeSvgOutput {
                exportAllowances += maxSvgBytes
                return NativeSvgOutput("""{"svg":"","metadata":{}}""".encodeToByteArray(), svg)
            }
        }
        val pipeline = androidPipeline(exportBinding, readSvgLimitBytes = { app.inku.mobile.render.SvgOutputLimit.BYTES_PER_MIB })
        val work = pipeline.composeFromDdl("place one circle.", describe(""))
        assertEquals(svg, pipeline.renderExportSvg(work.scoreJson, describe(""), "editable"))
        assertEquals(app.inku.mobile.render.SvgOutputLimit.CONSUMER_BYTES, exportAllowances.last())
        try {
            pipeline.renderFromScore(work.scoreJson, describe(""))
            fail("a fresh replay still uses the current generation allowance")
        } catch (failure: app.inku.mobile.ui.i18n.InkuFailure) {
            assertEquals("svg_output_too_large", failure.detail)
        }
        assertEquals(app.inku.mobile.render.SvgOutputLimit.BYTES_PER_MIB, exportAllowances.last())
    }

    @Test
    fun svgLimitSettingsAcceptOnlyIntegerMiBAndDefaultSafely() {
        val policy = app.inku.mobile.render.SvgOutputLimit
        assertEquals(12, policy.storedMiB(null))
        assertEquals(1, policy.parseMiB("1"))
        assertEquals(32, policy.parseMiB("32"))
        listOf("0", "33", "12.0", "", "-1", "NaN").forEach { assertNull(policy.parseMiB(it)) }
        assertEquals(32, policy.storedMiB("""{"value":33554432}"""))
        listOf("{}", "broken", """{"value":33554433}""", """{"value":12582912.0}""", """{"value":"12582912"}""")
            .forEach { assertEquals(12, policy.storedMiB(it)) }
    }

    @Test
    fun completionRecordSurvivesSavedWorkForkAndExecutionForkButNotANewImportedRun() = runBlocking {
        val record = JSONObject("""{"schema":"inku.completion-ranges.v1","ranges":[{"words":"右下","horizontal":["2/3","1"],"vertical":["2/3","1"],"sentence":"\uFFFCに、赤い円。"}],"future":{"keep":"opaque"}}""")
        val binding = ScriptedBinding(uniqueExecutions = true).apply { completionRecord = record }
        val source = "右下（横2/3〜1、縦2/3〜1）に、赤い円。"
        val initial = androidPipeline(binding).composeFromDdl(source, describe(""))
        assertEquals(record.toString(), JSONObject(initial.renderMetadataJson).getJSONObject("completion_ranges").toString())
        assertEquals(record.toString(), initial.pipelineView!!.completionRangesJson)
        val link = initial.managedHistoryLink!!
        val savedContext = JSONObject(link.contextJson).put("config", JSONObject(link.snapshotJson).getJSONObject("config"))
        val parent = HistoryItemEntity(
            id = "parent", createdAt = 1, updatedAt = 2, originalInput = "", normalizedDdl = source,
            scoreJson = initial.scoreJson, displaySvg = initial.displaySvg, stage1Model = null, stage2Model = null,
            renderMetadataJson = initial.renderMetadataJson, renderHash = "hash", renderHashShort = "0000",
            colorCatalogId = "default", canvasAspect = "square", starred = false, trashed = false,
            elapsedMs = null, tokenMetadataJson = null,
        )
        val saved = ManagedHistoryRead(parent, "ddl_authoritative", variationId = link.variationId, forkContextJson = savedContext.toString())
        val replayBinding = object : SharedPipelineBinding by binding {
            override fun renderSaved(inputBytes: ByteArray) =
                """{"svg":"<svg/>","metadata":{}}""".encodeToByteArray()
        }
        val replayContext = JSONObject(savedContext.toString()).put("pipeline_diagnostics", JSONObject()
            .put("upstream_diagnostics", JSONArray()).put("downstream_diagnostics", JSONArray())
            .put("resource_omissions", JSONArray()).put("relation_omissions", JSONArray()))
        val replay = androidPipeline(replayBinding) { saved.copy(forkContextJson = replayContext.toString()) }
            .renderFromScore(initial.scoreJson, describe("").copy(parentHistoryId = "parent"))
        assertEquals(record.toString(), JSONObject(replay.renderMetadataJson).getJSONObject("completion_ranges").toString())
        val safe = mutableListOf<PaintResult>()
        val safeBinding = ScriptedBinding().apply { completionRecord = record; holeDelivers = true }
        val waiting = runCatching { answeringPipeline(safeBinding) { safe += it }.paint(describe("a circle")) }.exceptionOrNull()
        assertTrue(waiting is PipelineInteractionRequired)
        assertEquals(record.toString(), JSONObject(safe.single().renderMetadataJson).getJSONObject("completion_ranges").toString())
        binding.completionRecord = null
        val pipeline = androidPipeline(binding) { saved }
        pipeline.completionRangeStates(source, null, "parent")
        assertEquals(record.toString(), binding.completionStatesRequests.single().getJSONObject("completion_ranges").toString())
        assertEquals(savedContext.getJSONObject("config").toString(), binding.completionStatesRequests.single().getJSONObject("config").toString())
        val fork = pipeline.composeFromDdl(source, describe("").copy(parentHistoryId = "parent"))
        assertEquals(record.toString(), binding.inputs.last { it.optString("tag") == "start" }
            .getJSONObject("authoring").getJSONObject("completion_ranges").toString())
        assertEquals(record.toString(), JSONObject(fork.renderMetadataJson).getJSONObject("completion_ranges").toString())
        val starts = binding.inputs.count { it.optString("tag") == "start" }
        pipeline.composeFromDdl(source, describe("").copy(parentHistoryId = "parent", executionId = fork.pipelineView!!.executionId))
        assertEquals(starts, binding.inputs.count { it.optString("tag") == "start" })

        val currentRecord = JSONObject(record.toString()).put("future", JSONObject().put("keep", "current snapshot"))
        binding.completionRecord = currentRecord
        val current = pipeline.composeFromDdl(source, describe("").copy(parentHistoryId = "parent"))
        binding.completionRecord = null
        pipeline.composeFromDdl(source, describe("").copy(parentHistoryId = "parent",
            executionId = current.pipelineView!!.executionId, compositionSeed = 43L))
        assertEquals(currentRecord.toString(), binding.inputs.last { it.optString("tag") == "start" }
            .getJSONObject("authoring").getJSONObject("completion_ranges").toString())

        androidPipeline(binding).composeFromDdl(source, describe(""))
        assertFalse(binding.inputs.last { it.optString("tag") == "start" }.getJSONObject("authoring").has("completion_ranges"))
        val older = saved.copy(history = parent.copy(renderMetadataJson = "{}"))
        androidPipeline(binding) { older }.composeFromDdl(source, describe("").copy(parentHistoryId = "parent"))
        assertFalse(binding.inputs.last { it.optString("tag") == "start" }.getJSONObject("authoring").has("completion_ranges"))
    }

    @Test
    fun completionRangeStatesPassTheWorksConfigAndOpaqueRecordWithCoreUtf16Positions() = runBlocking {
        val record = JSONObject("""{"schema":"inku.completion-ranges.v1","ranges":[],"future":"keep"}""")
        val binding = ScriptedBinding(uniqueExecutions = true).apply { completionRecord = record }
        val pipeline = androidPipeline(binding)
        val work = pipeline.composeFromDdl("place one red circle.", describe(""))
        val source = "🖼 completed range, numbers range, words range"
        binding.completionStatesResponse = """{"schema":"inku.completion-range-states.v1","ranges":[
            {"utf16_start":3,"utf16_end":18,"state":"completed"},
            {"utf16_start":20,"utf16_end":33,"state":"numbers_changed"},
            {"utf16_start":35,"utf16_end":46,"state":"words_changed"}
        ]}"""
        val answer = pipeline.completionRangeStates(source, work.pipelineView!!.executionId, null)
        assertEquals(listOf(CompletionRangeState(3, 18, "completed"), CompletionRangeState(20, 33, "numbers_changed"),
            CompletionRangeState(35, 46, "words_changed")), answer)
        val input = binding.completionStatesRequests.single()
        assertEquals(source, input.getString("source"))
        assertEquals(record.toString(), input.getJSONObject("completion_ranges").toString())
        assertEquals(JSONObject(work.managedHistoryLink!!.snapshotJson).getJSONObject("config").toString(), input.getJSONObject("config").toString())
        assertTrue(completionRangeStates(binding, "{}", source, null).isEmpty())
        assertEquals(1, binding.completionStatesRequests.size)
        binding.completionStatesResponse = null
        assertTrue(pipeline.completionRangeStates(source, work.pipelineView!!.executionId, null).isEmpty())
        binding.completionStatesResponse = """{"error":"invalid_request"}"""
        assertTrue(pipeline.completionRangeStates(source, work.pipelineView!!.executionId, null).isEmpty())
    }

    @Test
    fun aHolesAuthorSourceAndCheckSurviveViewProjectionAndReload() = runBlocking {
        val original = "  右下に、赤い円。\n"
        val binding = ScriptedBinding().apply {
            holeCompletionCheck = JSONObject().put("results", JSONArray().put(
                JSONObject().put("hole_id", "hole-1").put("source", original)
                    .put("status", "rejected").put("reason", "numeric_range_outside_words")
                    .put("replacement", "a different model proposal"),
            ))
        }
        val provider = RecordingEffectProvider()
        val executions = MemoryExecutionStore()
        val runningHost = host(binding, provider, RecordingCommitStore(), executions)
        val pending = runningHost.start(startRequest(PipelineAuthoring.Description("mist", false)))
        val expected = listOf(HoleCompletionResult("hole-1", original, "rejected", "numeric_range_outside_words"))
        assertEquals("awaiting_patch_approval", pending.phaseTag)
        assertEquals(expected, pending.holeCompletionResults)

        val calls = provider.tags.toList()
        val restored = host(binding, provider, RecordingCommitStore(), executions).restore(OWNER, pending.executionId)
        assertEquals(expected, restored.holeCompletionResults)
        assertEquals("reload must not call the model", calls, provider.tags)
    }

    @Test
    fun recompositionRewritesANewRunWithTheSamePreparedSeedWithoutAModelCall() = runBlocking {
        val binding = ScriptedBinding(uniqueExecutions = true)
        val original = "Place one red circle at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1)."
        val selected = "Place one red circle at the top left (horizontal 0 to 1/3, vertical 0 to 1/3)."
        binding.recompositionResponse = JSONObject()
            .put("schema", "inku.composition-recompose.v1").put("outcome", "recomposed")
            .put("source", selected).put("answer", "chance")
            .put("moves", JSONArray().put(JSONObject().put("layer", 0).put("from", "bottom right").put("to", "top left")))
        val result = androidPipeline(binding).composeFromDdl(original, layoutRequest(RecomposeMode.Chance, 42L))

        val input = binding.recompositionRequests.single()
        assertEquals(original, input.getString("source"))
        assertEquals("chance", input.getString("mode"))
        assertEquals("42", input.getString("seed"))
        assertEquals("42", input.getJSONObject("config").getJSONObject("compiler").getString("composition_seed"))
        assertEquals("sha256:" + sha256(original), input.getString("work_id"))
        val start = binding.inputs.first()
        assertEquals(selected, start.getJSONObject("authoring").getString("source"))
        assertEquals(input.getJSONObject("config").toString(), start.getJSONObject("config").toString())
        assertEquals(selected, result.normalizedDdl)
        assertEquals(42L, result.compositionSeed)
        assertEquals(listOf(RecompositionMove(0, "bottom right", "top left")), result.recomposition!!.moves)
        assertNull(result.recomposition!!.unchangedReason)
    }

    @Test
    fun recompositionOfAnExecutionForkKeepsUnmarkedInstructionsAndTheParent() = runBlocking {
        val binding = ScriptedBinding(uniqueExecutions = true)
        val pipeline = androidPipeline(binding)
        val original = "place one red circle."
        val request = layoutRequest(RecomposeMode.Principled, 42L)
        val parent = pipeline.composeFromDdl(original, request.copy(recomposeMode = null))
        binding.recompositionResponse = JSONObject()
            .put("schema", "inku.composition-recompose.v1").put("outcome", "unchanged").put("reason", "nothing_to_move")
        val result = pipeline.composeFromDdl(
            original,
            request.copy(executionId = parent.pipelineView!!.executionId, compositionSeed = 43L),
        )

        val input = binding.recompositionRequests.single()
        assertEquals("principled", input.getString("mode"))
        assertEquals("43", input.getString("seed"))
        assertEquals("sha256:" + sha256(original), input.getString("work_id"))
        val starts = binding.inputs.filter { it.optString("tag") == "start" }
        assertEquals(2, starts.size)
        assertEquals("42", starts.first().getJSONObject("config").getJSONObject("compiler").getString("composition_seed"))
        assertEquals("43", starts.last().getJSONObject("config").getJSONObject("compiler").getString("composition_seed"))
        assertEquals(original, starts.last().getJSONObject("authoring").getString("source"))
        assertEquals(original, result.normalizedDdl)
        assertEquals(43L, result.compositionSeed)
        assertEquals("nothing_to_move", result.recomposition!!.unchangedReason)
        assertTrue(parent.pipelineView!!.variationId != result.pipelineView!!.variationId)
    }

    @Test
    fun recompositionErrorsKeepTheNormalComposePath() = runBlocking {
        val binding = ScriptedBinding(uniqueExecutions = true)
        binding.recompositionResponse = JSONObject().put("error", "invalid_request")
        val original = "place one red circle."
        val result = androidPipeline(binding).composeFromDdl(original, layoutRequest(RecomposeMode.Principled, 44L))

        assertEquals(original, result.normalizedDdl)
        assertEquals(44L, result.compositionSeed)
        assertEquals("unavailable", result.recomposition!!.unchangedReason)
        assertEquals("completed", result.pipelineView!!.phaseTag)
    }

    @Test
    fun recompositionWithoutACompositionSeedUsesTheRenderSeed() = runBlocking {
        val binding = ScriptedBinding(uniqueExecutions = true)
        binding.recompositionResponse = JSONObject()
            .put("schema", "inku.composition-recompose.v1").put("outcome", "unchanged").put("reason", "nothing_to_move")
        androidPipeline(binding).composeFromDdl(
            "place one red circle.",
            layoutRequest(RecomposeMode.Chance, 42L).copy(compositionSeed = null, renderSeed = 7L),
        )

        assertEquals("7", binding.recompositionRequests.single().getString("seed"))
    }

    @Test
    fun theDescriptionReachesTheCoreWithoutItsLabelsAndTheWorkKeepsThemAsWritten() = runBlocking {
        val binding = ScriptedBinding()
        binding.labelCut = { if (it == "1. 春の雪 [出典]") "春の雪" else it }
        runCatching { androidPipeline(binding).interpret(describe("1. 春の雪 [出典]")) }

        val start = binding.inputs.first()
        assertEquals("春の雪", start.getJSONObject("authoring").getString("description"))
    }

    @Test
    fun aDescriptionThatIsOnlyLabelsIsRefusedBeforeTheCore() = runBlocking {
        val binding = ScriptedBinding()
        binding.labelCut = { "" }
        try {
            androidPipeline(binding).interpret(describe("1. [出典]"))
            fail("a description of labels alone must not start a drawing")
        } catch (error: app.inku.mobile.ui.i18n.InkuFailure) {
            assertEquals(app.inku.mobile.ui.i18n.InkuStringsEn.descriptionOnlyLabels, error.text(app.inku.mobile.ui.i18n.InkuStringsEn))
        }
        assertTrue(binding.inputs.isEmpty())
    }

    @Test
    fun handWrittenDdlIsReadInItsOwnLanguageNotTheDescriptions() = runBlocking {
        val binding = ScriptedBinding()
        val result = androidPipeline(binding).composeFromDdl(
            "Place one red circle.",
            describe("雨の日").copy(instructionLang = "auto"),
        )

        assertEquals("en", binding.inputs.first().getJSONObject("config").getString("language"))
        assertEquals("en", result.instructionLangResolved)
    }

    @Test
    fun anUnstatedLanguageIsAutoAsTheServerReadsIt() = runBlocking {
        val binding = ScriptedBinding()
        val result = androidPipeline(binding).composeFromDdl("Place one red circle.", describe("").copy(instructionLang = null))

        assertEquals("auto", result.instructionLangRequested)
        assertEquals("en", result.instructionLangResolved)
    }

    @Test
    fun drawingRequestsUseTheirRenderSeedWithoutSendingRetiredSeedInputs() = runBlocking {
        val binding = ScriptedBinding().apply { wordSeed = { error("retired word seed must not be called") } }
        val store = MemoryExecutionStore()
        val pipeline = AndroidWorkPipeline(
            binding = binding,
            modelProvider = object : ModelProvider {
                override val providerId = "fixture"
                override suspend fun generate(request: ModelRequest): ModelResponse = error("no model call expected")
            },
            commitStore = RecordingCommitStore(), executionStore = store, readHistory = { null },
            legacyRenderer = object : SvgRenderer {
                override fun render(request: RenderRequest): RenderResult = error("shared renderer expected")
            }, bundledPluginsEnabled = { false },
        )
        val result = pipeline.composeFromDdl(
            "place one red circle.",
            describe("").copy(renderSeed = 9L),
        )

        assertEquals(9L, result.renderSeed)
        assertNull(result.seedText)
        assertNull(result.interpretationSeed)
        val options = JSONObject(store.load(AndroidWorkPipeline.OWNER_ID, result.pipelineView!!.executionId)!!
            .toString(Charsets.UTF_8)).getJSONObject("host_context").getJSONObject("result_options")
        assertFalse(options.has("seed_text"))
        assertFalse(options.has("interpretation_seed"))
    }

    @Test
    fun aSavedWorkWithSeedWordsReplaysItsStoredSeedWithoutDerivingTheWords() = runBlocking {
        val delegate = ScriptedBinding().apply { wordSeed = { error("retired word seed must not be called") } }
        val renderInputs = mutableListOf<JSONObject>()
        val binding = object : SharedPipelineBinding by delegate {
            override fun renderSaved(inputBytes: ByteArray): ByteArray {
                renderInputs += JSONObject(inputBytes.toString(Charsets.UTF_8))
                return """{"svg":"<svg/>","metadata":{}}""".encodeToByteArray()
            }
            override fun renderSavedSvgLimited(inputBytes: ByteArray, maxSvgBytes: Long) =
                NativeSvgOutput(renderSaved(inputBytes), null)
        }
        val initial = androidPipeline(binding).composeFromDdl("place one red circle.", describe("").copy(renderSeed = 9L))
        val link = initial.managedHistoryLink!!
        val savedContext = JSONObject(link.contextJson).put("config", JSONObject(link.snapshotJson).getJSONObject("config"))
            .put("pipeline_diagnostics", JSONObject().put("upstream_diagnostics", JSONArray())
                .put("downstream_diagnostics", JSONArray()).put("resource_omissions", JSONArray()).put("relation_omissions", JSONArray()))
        val parent = HistoryItemEntity(
            id = "word-parent", createdAt = 1, updatedAt = 2, originalInput = "", normalizedDdl = initial.normalizedDdl,
            scoreJson = initial.scoreJson, displaySvg = initial.displaySvg, stage1Model = null, stage2Model = null,
            renderMetadataJson = initial.renderMetadataJson, renderHash = "hash", renderHashShort = "0000",
            colorCatalogId = "default", canvasAspect = "square", starred = false, trashed = false,
            elapsedMs = null, tokenMetadataJson = null, renderSeed = "14859340650796947346", seedText = "しずかに",
            interpretationSeed = "historic-reading",
        )
        val stored = ManagedHistoryRead(parent, "ddl_authoritative", variationId = link.variationId, forkContextJson = savedContext.toString())
        val replay = androidPipeline(binding, readHistory = { stored }).renderFromScore(
            initial.scoreJson, describe("").copy(parentHistoryId = parent.id),
        )
        assertEquals(parent.renderSeed, renderInputs.single().getJSONObject("request").getJSONObject("options").get("render_seed").toString())
        assertEquals(parent.renderSeed, java.lang.Long.toUnsignedString(replay.renderSeed!!))
        assertEquals(parent.seedText, replay.seedText)
        assertEquals(parent.interpretationSeed, replay.interpretationSeed)
        assertEquals(parent.seedText, JSONObject(replay.renderMetadataJson).getString("seed_text"))
    }

    @Test
    fun anInputPastTheRequestLimitIsRefusedBeforeTheCore() = runBlocking {
        val binding = ScriptedBinding()
        try {
            androidPipeline(binding).composeFromDdl("円".repeat(100_001), describe(""))
            fail("an over-long DDL must be refused")
        } catch (error: app.inku.mobile.ui.i18n.InkuFailure) {
            assertTrue(error.text(app.inku.mobile.ui.i18n.InkuStringsEn).contains("100001"))
        }
        assertTrue(binding.inputs.isEmpty())
    }

    @Test
    fun aForkFromASavedWorkDrawsInTodaysCatalogsEvenOnesItsParentNeverSaved() = runBlocking {
        val binding = ScriptedBinding()
        val builder = SharedPipelineConfigBuilder(binding)
        val parentConfig = builder.build(
            SharedPipelineConfigRequest("en", "square", "default", bundledPluginsEnabled = false),
        )
        val forkContext = JSONObject()
            .put("config", JSONObject(parentConfig.configJson))
            .put("color_maps", JSONObject().put("default", JSONObject(parentConfig.renderColorMaps.getValue("default"))))
            .put("macro_catalog", JSONObject().put("definition_locks", JSONArray()).put("diagnostics", JSONArray()))
            .put("host_options", JSONObject().put("render_seed", "7"))
        val parent = HistoryItemEntity(
            id = "parent", createdAt = 1, updatedAt = 2, originalInput = "",
            normalizedDdl = "place one red circle.", ddlSourceOrigin = null,
            scoreJson = "{}", displaySvg = "<svg/>", stage1Model = null, stage2Model = null,
            renderMetadataJson = "{}", renderHash = "hash", renderHashShort = "0000",
            colorCatalogId = "default", canvasAspect = "square",
            starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null,
        )
        val pipeline = AndroidWorkPipeline(
            binding = binding,
            modelProvider = object : ModelProvider {
                override val providerId = "test"
                override suspend fun generate(request: ModelRequest): ModelResponse = error("no model call expected")
            },
            commitStore = RecordingCommitStore(), executionStore = MemoryExecutionStore(),
            readHistory = {
                ManagedHistoryRead(parent, "ddl_authoritative", variationId = "parent-variation", forkContextJson = forkContext.toString())
            },
            legacyRenderer = object : SvgRenderer {
                override fun render(request: RenderRequest): RenderResult = error("the shared pipeline renders this run")
            },
            bundledPluginsEnabled = { false },
        )
        val result = pipeline.composeFromDdl(
            "place one red circle.",
            describe("").copy(colorCatalogId = "moss_bark", parentHistoryId = "parent"),
        )

        val moss = app.inku.mobile.data.model.ColorCatalogs.find("moss_bark")!!.renderMap
        assertEquals(JSONObject(moss).toString(), JSONObject(result.renderMetadataJson).getJSONObject("render_color_map").toString())
        assertEquals("work", JSONObject(result.renderMetadataJson).getString("render_limits_source"))
    }

    @Test
    fun aSavedWorkRecordsTheServersProfileLimitsAndOutcome() = runBlocking {
        val result = androidPipeline(ScriptedBinding()).composeFromDdl("place one red circle.", describe("").copy(uiLang = "en"))

        val metadata = JSONObject(result.renderMetadataJson)
        assertEquals("srgb", metadata.getJSONObject("render_color_profile").getString("id"))
        assertEquals(64, metadata.getJSONObject("render_limits").getInt("max_instructions"))
        assertEquals("settings", metadata.getString("render_limits_source"))
        assertEquals("complete", metadata.getString("compiler_outcome"))
        assertEquals("en", metadata.getString("ui_lang"))
    }

    @Test
    fun aScoreIsDrawnAndSavedBeforeItsHolesAreCompleted() = runBlocking {
        val binding = ScriptedBinding()
        binding.holeDelivers = true
        val saved = mutableListOf<PaintResult>()
        val pipeline = answeringPipeline(binding) { saved += it }
        val waiting = try {
            pipeline.paint(describe("a circle"))
            fail("the proposal waits for the author")
            error("unreachable")
        } catch (interaction: PipelineInteractionRequired) {
            interaction.view
        }

        val render = binding.inputs.indexOfFirst { it.optString("tag") == "render" }
        val hole = binding.inputs.indexOfFirst {
            it.optJSONObject("result")?.optJSONObject("identity")?.optString("action_id") == "provider-2"
        }
        assertTrue("drawn before the hole call returned", render in 0 until hole)
        assertEquals("awaiting_llm", saved.single().pipelineView!!.phaseTag)
        assertTrue(JSONObject(saved.single().renderMetadataJson).has("elapsed_stage1_ms"))
        assertEquals("awaiting_patch_approval", waiting.phaseTag)
        assertNotNull("the drawing stays while the proposal waits", waiting.renderedJson)
    }

    @Test
    fun theProposalOnScreenIsTheOneApproved() = runBlocking {
        val binding = ScriptedBinding()
        val pipeline = answeringPipeline(binding)
        val waiting = runCatching { pipeline.paint(describe("a circle")) }.exceptionOrNull() as PipelineInteractionRequired
        pipeline.approvePatch(waiting.view.executionId, "0", "stale")

        val approve = binding.inputs.single { it.optString("tag") == "approve_patch" }
        assertEquals("0", approve.getString("expected_revision"))
        assertEquals("stale", approve.getString("proposal_digest"))
    }

    @Test
    fun anEditWhileAProposalWaitsIsLeftToTheCore() = runBlocking {
        val binding = ScriptedBinding()
        val pipeline = answeringPipeline(binding)
        val waiting = runCatching { pipeline.paint(describe("a circle")) }.exceptionOrNull() as PipelineInteractionRequired
        try {
            pipeline.composeFromDdl("an edited DDL.", describe("a circle").copy(executionId = waiting.view.executionId))
            fail("the core refuses an edit while a proposal waits")
        } catch (error: app.inku.mobile.ui.i18n.InkuFailure) {
            assertEquals(
                app.inku.mobile.ui.i18n.InkuStringsEn.pipelineAnswerProposalFirst,
                error.text(app.inku.mobile.ui.i18n.InkuStringsEn),
            )
        }
        assertTrue("the host declined nothing", binding.inputs.none { it.optString("tag") == "decline_patch" })
    }

    @Test
    fun aStoppedRunSaysWhyAsWebDoes() {
        val text = app.inku.mobile.ui.pipelineAttentionText(
            "stage1_failed",
            PipelineProviderFailure("transport_timeout", "stage1", 3, 1000),
            app.inku.mobile.ui.i18n.InkuStringsJa,
        )
        assertEquals(
            "処理の結果を確認してください。 理由: 記述の解釈を完了できませんでした（モデルの応答が制限時間内に返りませんでした。3回試しました）",
            text,
        )
    }

    private fun answeringPipeline(binding: SharedPipelineBinding, saveSafe: suspend (PaintResult) -> Unit = {}) = AndroidWorkPipeline(
        binding = binding,
        modelProvider = object : ModelProvider {
            override val providerId = "test"
            override suspend fun generate(request: ModelRequest): ModelResponse = ModelResponse("{}", "test")
        },
        commitStore = RecordingCommitStore(), executionStore = MemoryExecutionStore(), readHistory = { null },
        legacyRenderer = object : SvgRenderer {
            override fun render(request: RenderRequest): RenderResult = error("the shared pipeline renders this run")
        },
        bundledPluginsEnabled = { false },
        saveSafePerformance = saveSafe,
    )

    private fun describe(text: String) = PaintRequest(
        description = text, stage1Model = "local-litert-lm:gemma-4-e2b", stage2Model = "local-litert-lm:gemma-4-e2b",
        colorCatalogId = "default", canvasAspect = "square", autoRepair = false,
    )

    private fun layoutRequest(mode: RecomposeMode, seed: Long) = PaintRequest(
        description = "a red circle", stage1Model = "local-litert-lm:gemma-4-e2b", stage2Model = "local-litert-lm:gemma-4-e2b",
        colorCatalogId = "default", canvasAspect = "square", autoRepair = false,
        compositionSeed = seed, recomposeMode = mode, instructionLang = "en",
    )

    private fun androidPipeline(binding: SharedPipelineBinding,
        readSvgLimitBytes: suspend () -> Long = { app.inku.mobile.render.SvgOutputLimit.DEFAULT_BYTES },
        readHistory: suspend (String) -> ManagedHistoryRead? = { null }) = AndroidWorkPipeline(
        binding = binding,
        modelProvider = object : ModelProvider {
            override val providerId = "test"
            override suspend fun generate(request: ModelRequest): ModelResponse = error("recomposition must not call a model")
        },
        commitStore = RecordingCommitStore(), executionStore = MemoryExecutionStore(), readHistory = readHistory,
        legacyRenderer = object : SvgRenderer {
            override fun render(request: RenderRequest): RenderResult = error("the shared pipeline renders this run")
        },
        bundledPluginsEnabled = { false },
        readSvgLimitBytes = readSvgLimitBytes,
    )

    @Test
    fun newRunOmitsRetiredVariationSettingsAndStoredConfigRemainsReadable() = runBlocking {
        val binding = object : SharedPipelineBinding by ScriptedBinding() {
            override fun canvasRegistry() = """{"digest":"registry-digest","registry":{"schema":"inku.canvas-format-registry.v1","formats":[{"id":"square","width_units":1,"height_units":1}]}}"""
            override fun resolvePalette(inputBytes: ByteArray) = "{}".encodeToByteArray()
            override fun resolveMacroCatalog(inputBytes: ByteArray) =
                """{"schema":"inku.macro-catalog-resolution.v1","entries":[],"locks":[],"diagnostics":[]}""".encodeToByteArray()
        }
        val builder = SharedPipelineConfigBuilder(binding)
        val prepared = builder.build(
            SharedPipelineConfigRequest("ja", "square", "default", bundledPluginsEnabled = false),
        )
        assertFalse(JSONObject(prepared.configJson).getJSONObject("compiler").has("stage15_variation"))

        val host = host(binding, RecordingEffectProvider(), RecordingCommitStore(), MemoryExecutionStore())
        val view = SharedAuthoringPipeline(host, builder).startDirectDdlView(
            SharedPipelineRunRequest(
                ownerId = OWNER, text = "place one circle.", config = prepared,
                models = MODELS, context = AuthoringContext("one circle"),
            ),
        )
        val resultOptions = JSONObject(host.executionContext(OWNER, view.executionId).hostContextJson)
            .getJSONObject("result_options")
        assertFalse(resultOptions.has("variation_amplitude"))
        assertFalse(resultOptions.has("variation_seed"))

        val oldConfig = JSONObject(prepared.configJson).also {
            it.getJSONObject("compiler").put("stage15_variation", JSONObject().put("amplitude", "large").put("seed", "7"))
        }.toString()
        val restored = builder.fromSavedConfig(oldConfig, prepared.renderColorMaps)
        assertEquals(oldConfig, restored.configJson)
        assertEquals("7", JSONObject(oldConfig).getJSONObject("compiler").getJSONObject("stage15_variation").getString("seed"))
    }

    @Test
    fun chatGptRegistrationIsPinnedAcrossProviderEffectsAndHostReloadWithoutCredentials() = runBlocking {
        val ref = app.inku.mobile.llm.ChatGptSessionRef("personal-registration", 7)
        val executions = MemoryExecutionStore()
        val provider = PipelineProviderEffect { actionJson, models ->
            assertEquals(ref, models.chatGptSession)
            RecordingEffectProvider().perform(actionJson, models)
        }
        val first = host(ScriptedBinding(), provider, RecordingCommitStore(), executions)
            .start(startRequest(PipelineAuthoring.Description("mist", false)).copy(models = MODELS.copy(chatGptSession = ref)))
        val resumed = host(ScriptedBinding(), provider, RecordingCommitStore(), executions).view(OWNER, first.executionId)
        assertEquals(ref, resumed.models?.chatGptSession)
        val saved = executions.load(OWNER, first.executionId)!!.toString(Charsets.UTF_8)
        assertTrue(saved.contains("personal-registration"))
        assertFalse(saved.contains("access_token")); assertFalse(saved.contains("refresh_token"))
    }

    @Test
    fun savedScoreReplayKeepsTheUnifiedSourceAndOriginAndBlankDdlNeverFallsBackToDescription() = runBlocking {
        var saved = HistoryItemEntity(
            id = "legacy", createdAt = 1, updatedAt = 2, originalInput = "description",
            normalizedDdl = " \ncenter: circle\n ", ddlSourceOrigin = DdlSource.LEGACY_EXPANDED,
            scoreJson = "{}", displaySvg = "<svg/>", stage1Model = null, stage2Model = null,
            renderMetadataJson = "{}", renderHash = "hash", renderHashShort = "0000",
            colorCatalogId = "default", canvasAspect = "pixel9_landscape_safe",
            starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null,
        )
        val pipeline = AndroidWorkPipeline(
            binding = ScriptedBinding(),
            modelProvider = object : ModelProvider {
                override val providerId: String = "test"
                override suspend fun generate(request: ModelRequest): ModelResponse = error("no model call expected")
            },
            commitStore = RecordingCommitStore(),
            executionStore = MemoryExecutionStore(),
            readHistory = { ManagedHistoryRead(saved, "legacy_unknown") },
            legacyRenderer = object : SvgRenderer {
                override fun render(request: RenderRequest): RenderResult {
                    assertEquals(saved.scoreJson, request.scoreJson)
                    return RenderResult("<svg/>", "{}", "test")
                }
            },
        )
        val request = PaintRequest(
            description = "never use this description as DDL", stage1Model = "test", stage2Model = "test",
            colorCatalogId = "default", canvasAspect = "pixel9_landscape_safe", autoRepair = false,
            parentHistoryId = saved.id,
        )
        val replay = pipeline.renderFromScore(saved.scoreJson, request)
        assertEquals(saved.normalizedDdl, replay.normalizedDdl)
        assertEquals(saved.ddlSourceOrigin, replay.ddlSourceOrigin)
        assertEquals("{}", replay.scoreJson)
        saved = saved.copy(normalizedDdl = null, ddlSourceOrigin = null)
        val absent = pipeline.renderFromScore(saved.scoreJson, request)
        assertNull(absent.normalizedDdl)
        assertNull(absent.ddlSourceOrigin)
        try {
            pipeline.composeFromDdl("\u0085\u00a0\u3000", request)
            fail("A DDL without a body must not start a drawing")
        } catch (error: IllegalArgumentException) {
            assertEquals("ddl_body_required", error.message)
        }
    }

    @Test
    fun sketchChoiceReachesCoreAndGeneratedRecordSurvivesReloadAndRegeneration() = runBlocking {
        val binding = ScriptedBinding()
        val provider = RecordingEffectProvider()
        val executions = MemoryExecutionStore()
        val host = host(binding, provider, RecordingCommitStore(), executions)

        val pending = host.start(startRequest(PipelineAuthoring.Description("mist", false, PipelineSketchRequest.On)))

        assertEquals("on", binding.inputs.first().getJSONObject("authoring").getJSONObject("sketch").getString("mode"))
        assertEquals(listOf("generate_sketch", "generate_normalized_ddl", "complete_visible_ddl_holes"), provider.tags)
        assertEquals(PipelineSketchResult("light over mist", "supplemented"), pending.sketch)
        assertEquals(pending.sketch, host.view(OWNER, pending.executionId).sketch)

        val regenerated = host.command(
            OWNER,
            pending.executionId,
            PipelineCommand.GenerateFromDescription(pending.revision, "new mist", false, PipelineSketchRequest.Supplied("saved light")),
        )

        val command = binding.inputs.first { it.optString("tag") == "generate_from_description" }
        assertEquals("supplied", command.getJSONObject("sketch").getString("mode"))
        assertEquals("saved light", command.getJSONObject("sketch").getString("text"))
        assertEquals(1, provider.tags.count { it == "generate_sketch" })
        assertEquals(PipelineSketchResult("saved light", "supplied"), regenerated.sketch)
        assertEquals(PipelineSketchResult("saved light", "supplemented"), AndroidWorkPipeline.savedSketchResult(regenerated.sketch))
    }

    @Test
    fun sketchResultsWithoutTextPreserveTheCoreOutcome() {
        assertEquals("off", PipelineSketchResult.from(null).state)
        assertEquals("off", PipelineSketchResult.from(JSONObject().put("state", "off")).state)
        assertEquals("pending", PipelineSketchResult.from(JSONObject().put("state", "pending")).state)
        assertEquals("not_needed", PipelineSketchResult.from(JSONObject().put("state", "not_needed")).state)
        assertEquals(PipelineSketchResult(state = "fallback"), PipelineSketchResult.from(JSONObject().put("state", "fallback")))
        assertEquals(PipelineSketchRequest.Off, PipelineSketchRequest.from(SketchInput()))
        assertEquals(PipelineSketchRequest.On, PipelineSketchRequest.from(SketchInput(requested = true)))
        assertEquals(PipelineSketchRequest.Supplied("saved"), PipelineSketchRequest.from(SketchInput(text = " saved ")))
        val blankSupplied = PipelineSketchResult.from(JSONObject().put("state", "supplied").put("text", " \n "))
        assertEquals(PipelineSketchResult(state = "supplied"), blankSupplied)
        assertEquals(PipelineSketchResult(state = "fallback"), AndroidWorkPipeline.savedSketchResult(blankSupplied))
    }

    @Test
    fun descriptionRunCommitsThenRequestsKnownHoleAndWaitsForApproval() = runBlocking {
        val binding = ScriptedBinding()
        val provider = RecordingEffectProvider()
        val commits = RecordingCommitStore()
        val executions = MemoryExecutionStore()
        val host = host(binding, provider, commits, executions)

        val pending = host.start(startRequest(PipelineAuthoring.Description("mist", false)))

        assertEquals("awaiting_patch_approval", pending.phaseTag)
        assertEquals("off", binding.inputs.first().getJSONObject("authoring").getJSONObject("sketch").getString("mode"))
        assertEquals(listOf("generate_normalized_ddl", "complete_visible_ddl_holes"), provider.tags)
        assertEquals(1, provider.tags.count { it == "generate_normalized_ddl" })
        assertEquals(1, provider.tags.count { it == "complete_visible_ddl_holes" })
        assertEquals(1, commits.actions.size)
        assertNotNull(pending.patchProposal)
        assertFalse(pending.busy)

        val ready = host.command(
            OWNER,
            pending.executionId,
            PipelineCommand.ApprovePatch(pending.revision, pending.patchProposal!!.proposalDigest),
        )

        assertEquals("score_ready", ready.phaseTag)
        assertEquals("patched DDL", ready.visibleDdl)
        assertEquals(2, commits.actions.size)
        assertTrue(host.snapshotJson(OWNER, ready.executionId).contains("\"delivery\""))
        assertEquals(ready.sequence, JSONObject(executions.load(OWNER, ready.executionId)!!.toString(Charsets.UTF_8))
            .let { state -> JSONObject(String(java.util.Base64.getDecoder().decode(state.getString("snapshot_base64")))) }
            .getString("sequence"))
    }

    @Test
    fun directDdlUsesNoProviderAndReachesSharedScore() = runBlocking {
        val provider = RecordingEffectProvider()
        val commits = RecordingCommitStore()
        val host = host(ScriptedBinding(), provider, commits, MemoryExecutionStore())

        val ready = host.start(startRequest(PipelineAuthoring.DirectDdl("place one circle.")))

        assertEquals("score_ready", ready.phaseTag)
        assertTrue(provider.tags.isEmpty())
        assertEquals(1, commits.actions.size)
        assertEquals("user_authored_ddl", ready.origin)
        assertEquals("ddl_authoritative", ready.authority)
    }

    @Test
    fun cancellationInvalidatesLateProviderResult() = runBlocking {
        val started = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val provider = PipelineProviderEffect { actionJson, _ ->
            started.complete(Unit)
            release.await()
            effectResult(JSONObject(actionJson), "normalized_ddl_generated", "{}")
        }
        val host = host(ScriptedBinding(), provider, RecordingCommitStore(), MemoryExecutionStore())
        val running = async { host.start(startRequest(PipelineAuthoring.Description("mist", false))) }
        started.await()

        val cancelled = host.cancel(OWNER, EXECUTION_ID)
        release.complete(Unit)
        val completed = running.await()

        assertEquals("cancelled", cancelled.phaseTag)
        assertEquals("cancelled", completed.phaseTag)
        assertEquals(null, completed.visibleDdl)
    }

    /**
     * The start-up restore reads the latest execution, which can be a drawing
     * started a moment earlier. A second drive of it would race the first for
     * the next effect, and the drive that lost would hand its caller a view from
     * the middle of the run. The commit is held so that the restore queues on
     * the session between two effects, where the race is decided.
     */
    @Test
    fun restoringARunThatIsAlreadyBeingDrivenOnlyViewsIt() = runBlocking {
        val commitEntered = CompletableDeferred<Unit>()
        val releaseCommit = CompletableDeferred<Unit>()
        val recording = RecordingCommitStore()
        val commits = object : PipelineCommitStore {
            override suspend fun commit(
                ownerId: String,
                actionJson: String,
                createIfMissing: Boolean,
                context: AuthoringContext,
            ): String {
                commitEntered.complete(Unit)
                releaseCommit.await()
                return recording.commit(ownerId, actionJson, createIfMissing, context)
            }
        }
        // The call after the commit is held too: a real one takes seconds, and
        // it is while it is out that a losing drive returns mid-run.
        val holeEntered = CompletableDeferred<Unit>()
        val releaseHole = CompletableDeferred<Unit>()
        val recordingProvider = RecordingEffectProvider()
        val provider = PipelineProviderEffect { actionJson, models ->
            if (JSONObject(actionJson).getString("tag") == "complete_visible_ddl_holes") {
                holeEntered.complete(Unit)
                releaseHole.await()
            }
            recordingProvider.perform(actionJson, models)
        }
        val host = host(ScriptedBinding(), provider, commits, MemoryExecutionStore())
        val running = async { host.start(startRequest(PipelineAuthoring.Description("mist", false))) }
        commitEntered.await()

        val restoring = async { host.restore(OWNER, EXECUTION_ID) }
        repeat(10) { yield() }
        releaseCommit.complete(Unit)
        holeEntered.await()
        repeat(10) { yield() }

        assertFalse("the drawing is still driving its own run", running.isCompleted)
        releaseHole.complete(Unit)
        val finished = withTimeout(5_000) { running.await() }
        val restored = withTimeout(5_000) { restoring.await() }
        assertFalse("the restore reports the run, it does not finish it", restored.terminal)
        assertEquals("awaiting_patch_approval", finished.phaseTag)
        assertEquals(listOf("generate_normalized_ddl", "complete_visible_ddl_holes"), recordingProvider.tags)
    }

    @Test
    fun compositionReadUsesStageOneTransportAndReachesTheVisibleCommit() = runBlocking {
        val binding = ScriptedBinding()
        val requests = mutableListOf<ModelRequest>()
        val adapter = SingleAttemptModelEffectProvider(object : ModelProvider {
            override val providerId = "fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse {
                requests += request
                return ModelResponse("exact response", request.modelId)
            }
        })
        val commits = RecordingCommitStore()
        val host = host(binding, adapter, commits, MemoryExecutionStore())
        val config = JSONObject(CONFIG.toString()).put("composition", compositionForModel("gemini:model"))
        val pending = host.start(
            startRequest(PipelineAuthoring.Description("mist", false)).copy(configJson = config.toString()),
        )

        assertEquals("awaiting_patch_approval", pending.phaseTag)
        assertEquals(listOf("generate_normalized_ddl", "read_composition", "complete_visible_ddl_holes"), requests.map { it.pipelineAction })
        val reading = requests[1]
        assertEquals(MODELS.stage1ModelId, reading.modelId)
        assertEquals(MODELS.stage1MaxTokens, reading.maxTokens)
        assertEquals(0.0, reading.temperature, 0.0)
        assertEquals(1_000L, reading.timeoutMs)
        assertEquals("system", reading.systemInstruction)
        val result = binding.inputs.first { it.optJSONObject("result")?.optString("tag") == "composition_read" }.getJSONObject("result")
        assertEquals("provider-composition", result.getJSONObject("identity").getString("action_id"))
        assertEquals("exact response", result.getString("response"))
        assertTrue(result.getString("elapsed_ms").toLong() >= 0L)
        assertEquals(1, commits.actions.size)
    }

    @Test
    fun compositionIsReadOnTheCloudAndUsesTheDefaultReadingOnTheDevice() {
        assertTrue(compositionForModel("gemini:gemma-4-31b-it").getBoolean("read"))
        assertFalse(compositionForModel("local-litert-lm:gemma-4-e2b").getBoolean("read"))
    }

    @Test
    fun singleAttemptAdapterPassesCorePromptAndTimeoutOnce() = runBlocking {
        val requests = mutableListOf<ModelRequest>()
        val adapter = SingleAttemptModelEffectProvider(object : ModelProvider {
            override val providerId = "fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse {
                requests += request
                return ModelResponse("exact response", request.modelId)
            }
        })
        val action = providerAction("generate_sketch", "provider-1")

        val result = JSONObject(adapter.perform(action.toString(), MODELS))

        assertEquals("sketch_generated", result.getString("tag"))
        assertEquals(1, requests.size)
        assertEquals("system", requests.single().systemInstruction)
        assertEquals("message", requests.single().prompt)
        assertEquals(
            JSONObject().put("type", "object").put("properties", JSONObject()).toString(),
            requests.single().tool?.parametersJson,
        )
        assertEquals(1_000L, requests.single().timeoutMs)
        assertEquals(MODELS.stage1ModelId, requests.single().modelId)
        assertEquals(MODELS.stage1MaxTokens, requests.single().maxTokens)
        assertEquals("generate_sketch", requests.single().pipelineAction)
    }

    private fun host(
        binding: SharedPipelineBinding,
        provider: PipelineProviderEffect,
        commits: PipelineCommitStore,
        executions: PipelineExecutionStore,
    ): SharedPipelineHost {
        val ids = ArrayDeque(listOf("variation", "nonce", "message-0") + (1..100).map { "message-$it" })
        return SharedPipelineHost(
            binding = binding,
            providerEffect = provider,
            commitStore = commits,
            executionStore = executions,
            newId = { ids.removeFirst() },
        )
    }

    private fun startRequest(authoring: PipelineAuthoring) = PipelineStartRequest(
        ownerId = OWNER,
        configJson = CONFIG.toString(),
        authoring = authoring,
        models = MODELS,
        context = AuthoringContext("mist"),
    )

    private class RecordingEffectProvider : PipelineProviderEffect {
        val tags = mutableListOf<String>()

        override suspend fun perform(actionJson: String, models: PipelineModelSelection): String {
            val action = JSONObject(actionJson)
            val tag = action.getString("tag")
            tags += tag
            return when (tag) {
                "generate_sketch" -> effectResult(action, "sketch_generated", "{\"sketch\":\"light over mist\"}")
                "generate_normalized_ddl" -> effectResult(action, "normalized_ddl_generated", "{}")
                "read_composition" -> effectResult(action, "composition_read", "{}")
                "complete_visible_ddl_holes" -> effectResult(action, "visible_ddl_hole_patch_generated", "{}")
                else -> error("unexpected provider action")
            }
        }
    }

    private class RecordingCommitStore : PipelineCommitStore {
        val actions = mutableListOf<JSONObject>()

        override suspend fun commit(
            ownerId: String,
            actionJson: String,
            createIfMissing: Boolean,
            context: AuthoringContext,
        ): String {
            val action = JSONObject(actionJson)
            actions += action
            return JSONObject()
                .put("tag", "visible_normalized_ddl_committed")
                .put("identity", action.getJSONObject("identity"))
                .put("ddl_digest", action.getJSONObject("payload").getString("ddl_digest"))
                .put("revision", actions.size.toString())
                .put("authority_digest", "authority-${actions.size}")
                .toString()
        }
    }

    private class MemoryExecutionStore : PipelineExecutionStore {
        private val states = ConcurrentHashMap<String, Pair<String, ByteArray>>()

        override suspend fun create(
            ownerId: String,
            executionId: String,
            variationId: String,
            sequence: String,
            stateBytes: ByteArray,
        ) {
            check(states.putIfAbsent("$ownerId:$executionId", sequence to stateBytes.copyOf()) == null)
        }

        override suspend fun compareAndSet(
            ownerId: String,
            executionId: String,
            expectedSequence: String,
            nextSequence: String,
            stateBytes: ByteArray,
        ): Boolean {
            val key = "$ownerId:$executionId"
            val current = states[key] ?: return false
            if (current.first != expectedSequence) return false
            return states.replace(key, current, nextSequence to stateBytes.copyOf())
        }

        override suspend fun load(ownerId: String, executionId: String): ByteArray? =
            states["$ownerId:$executionId"]?.second?.copyOf()
    }

    private class ScriptedBinding(private val uniqueExecutions: Boolean = false) : SharedPipelineBinding {
        val inputs = mutableListOf<JSONObject>()
        /** The shared label cut, scripted; the rule itself is tested in Rust. */
        var labelCut: (String) -> String = { it }
        /** The shared word seed, scripted: words become seed 123 and their text stripped as Python strips it. */
        var wordSeed: (String) -> String? = { words ->
            words.trim { it.isWhitespace() || it == '\u0085' }.takeIf(String::isNotEmpty)?.let {
                JSONObject().put("render_seed", "123").put("seed_text", it).toString()
            }
        }
        /** A known-hole run whose Score is delivered while it waits, as the core delivers one. */
        var holeDelivers = false
        var holeCompletionCheck: JSONObject? = null
        var completionRecord: JSONObject? = null
        val completionStatesRequests = mutableListOf<JSONObject>()
        var completionStatesResponse: String? = null
        override fun completionRangeStates(inputBytes: ByteArray): ByteArray {
            completionStatesRequests += JSONObject(inputBytes.toString(Charsets.UTF_8))
            return completionStatesResponse?.encodeToByteArray() ?: super.completionRangeStates(inputBytes)
        }
        override fun pipelineDescription(text: String) = labelCut(text)
        override fun renderSeedFromText(seedText: String) = wordSeed(seedText)
        val recompositionRequests = mutableListOf<JSONObject>()
        var recompositionResponse: JSONObject? = null
        override fun versionReport() = """{"binding_version":"1.1.0","protocol_version":"1.0.0"}"""

        override fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray): ByteArray {
            val input = JSONObject(inputEnvelopeBytes.toString(Charsets.UTF_8))
            val payload = input.getJSONObject("payload")
            inputs += payload
            val previous = snapshotBytes.takeIf { it.isNotEmpty() }
                ?.let { JSONObject(it.toString(Charsets.UTF_8)) }
            val direct = payload.optString("tag") == "start" &&
                payload.getJSONObject("authoring").optString("tag") == "direct_ddl"
            val resultTag = payload.optJSONObject("result")?.optString("tag")
            val previousActionId = previous?.optJSONObject("action")
                ?.optJSONObject("identity")
                ?.optString("action_id")
            val sketchRequest = if (payload.optString("tag") == "start") {
                payload.getJSONObject("authoring").optJSONObject("sketch")
            } else if (payload.optString("tag") == "generate_from_description") {
                payload.optJSONObject("sketch")
            } else null
            val config = if (previous == null) payload.getJSONObject("config") else previous.getJSONObject("config")
            val previousPhase = previous?.optJSONObject("phase")?.optString("tag")
            if (payload.optString("tag") == "commit_user_ddl" && previousPhase == "awaiting_patch_approval") {
                return JSONObject()
                    .put("protocol", "inku.pipeline").put("version", "1.0.0").put("kind", "error")
                    .put("payload", JSONObject().put("code", "invalid_state"))
                    .toString().encodeToByteArray()
            }
            val previousState = when {
                previousPhase == "awaiting_patch_approval" -> State.AwaitingPatch
                previousActionId == "provider-2" -> State.Hole
                else -> null
            }
            val state = when {
                payload.optString("tag") == "render" && holeDelivers && previousState != null -> previousState
                payload.optString("tag") == "cancel" -> State.Cancelled
                payload.optString("tag") == "approve_patch" -> State.SecondCommit
                direct -> State.FirstCommit
                sketchRequest?.optString("mode") == "on" -> State.Sketch
                payload.optString("tag") == "generate_from_description" -> State.Stage1
                payload.optString("tag") == "start" -> State.Stage1
                resultTag == "sketch_generated" -> State.Stage1
                resultTag == "normalized_ddl_generated" -> if (config.optJSONObject("composition")?.optBoolean("read") == true) State.Composition else State.FirstCommit
                resultTag == "composition_read" -> State.FirstCommit
                resultTag == "visible_ddl_hole_patch_generated" -> State.AwaitingPatch
                resultTag == "visible_normalized_ddl_committed" && previousActionId == "commit-1" -> {
                    if (previous?.optString("origin_fixture") == "direct") State.Ready else State.Hole
                }
                resultTag == "visible_normalized_ddl_committed" -> State.Ready
                payload.optString("tag") == "render" -> State.Completed
                else -> error("unexpected transition: $payload")
            }
            val variationId = previous?.getString("variation_id") ?: payload.getString("variation_id")
            val executionId = previous?.getString("execution_id")
                ?: if (uniqueExecutions) "execution-$variationId" else EXECUTION_ID
            val origin = if (direct || previous?.optString("origin_fixture") == "direct") "direct" else "description"
            val directSource = if (direct) payload.getJSONObject("authoring").getString("source") else
                previous?.optJSONObject("document")?.optString("source") ?: "place one circle."
            val snapshot = snapshot(state, input.getString("sequence"), variationId, executionId, config, origin, directSource, holeDelivers)
            val sketch = when {
                sketchRequest?.optString("mode") == "supplied" -> JSONObject()
                    .put("state", "supplied").put("text", sketchRequest.getString("text"))
                sketchRequest != null -> if (state == State.Sketch) JSONObject().put("state", "pending") else null
                resultTag == "sketch_generated" -> JSONObject().put("state", "supplemented")
                    .put("text", JSONObject(payload.getJSONObject("result").getString("response")).getString("sketch"))
                else -> previous?.optJSONObject("sketch")
            }
            snapshot.put("sketch", sketch ?: JSONObject.NULL)
            val record = completionRecord ?: if (payload.optString("tag") == "start")
                payload.getJSONObject("authoring").optJSONObject("completion_ranges") else previous?.optJSONObject("completion_ranges")
            if (record != null) snapshot.put("completion_ranges", record)
            if (state == State.AwaitingPatch) snapshot.put("hole_completion_check", holeCompletionCheck)
            val rendered = if (state == State.Completed || payload.optString("tag") == "render") {
                JSONObject().put("svg", "<svg/>").put("metadata", JSONObject())
            } else {
                JSONObject.NULL
            }
            return JSONObject()
                .put("protocol", "inku.pipeline")
                .put("version", "1.0.0")
                .put("kind", "output")
                .put("execution_id", executionId)
                .put("message_id", input.getString("message_id"))
                .put("sequence", input.getString("sequence"))
                .put(
                    "payload",
                    JSONObject()
                        .put("tag", "step_result")
                        .put("version", 1)
                        .put(
                            "result",
                            JSONObject()
                                .put("snapshot", snapshot)
                                .put("events", JSONArray())
                                .put("rendered", rendered),
                        ),
                )
                .toString()
                .encodeToByteArray()
        }

        private fun snapshot(
            state: State,
            sequence: String,
            variationId: String,
            executionId: String,
            config: JSONObject,
            originFixture: String,
            directSource: String,
            holeDelivers: Boolean = false,
        ): JSONObject {
            val direct = originFixture == "direct"
            val revision = when (state) {
                State.Sketch, State.Stage1, State.Composition, State.FirstCommit -> "0"
                State.Hole, State.AwaitingPatch, State.SecondCommit -> "1"
                State.Ready, State.Completed -> if (direct) "1" else "2"
                State.Cancelled -> "0"
            }
            val document = when (state) {
                State.Sketch, State.Stage1, State.Composition, State.Cancelled -> null
                State.FirstCommit, State.Hole, State.AwaitingPatch -> if (direct) directSource else "DDL with hole"
                State.SecondCommit, State.Ready, State.Completed -> if (direct) directSource else "patched DDL"
            }
            val action = when (state) {
                State.Sketch -> providerAction("generate_sketch", "provider-sketch")
                State.Stage1 -> providerAction("generate_normalized_ddl", "provider-1")
                State.Composition -> providerAction("read_composition", "provider-composition")
                State.FirstCommit -> commitAction("commit-1", document!!, revision)
                State.Hole -> providerAction("complete_visible_ddl_holes", "provider-2")
                State.SecondCommit -> commitAction("commit-2", document!!, revision)
                else -> null
            }
            val phase = when (state) {
                State.Sketch, State.Stage1, State.Composition, State.Hole -> JSONObject().put("tag", "awaiting_llm")
                State.FirstCommit, State.SecondCommit -> JSONObject().put("tag", "awaiting_visible_ddl_commit")
                State.AwaitingPatch -> JSONObject()
                    .put("tag", "awaiting_patch_approval")
                    .put("patch", JSONObject().put("edits", JSONArray()))
                    .put("candidate", visibleDocument("patched DDL"))
                    .put("proposal_digest", "proposal")
                    .put("base_revision", "1")
                State.Ready -> JSONObject().put("tag", "score_ready")
                State.Completed -> JSONObject().put("tag", "completed")
                State.Cancelled -> JSONObject().put("tag", "cancelled")
            }
            val delivered = setOf(State.Ready, State.Completed) +
                if (holeDelivers) setOf(State.Hole, State.AwaitingPatch) else emptySet()
            val delivery = if (state in delivered) {
                JSONObject()
                    .put("score", JSONObject().put("schema", "inku.score.v1").put("instructions", JSONArray()))
                    .put(
                        "compiler_options",
                        config.optJSONObject("compiler") ?: JSONObject()
                            .put("host", JSONObject().put("canvas_format_id", "square").put("resolved_catalog_id", "default"))
                            .put("composition_seed", JSONObject.NULL)
                            .put("error_policy", "omit_and_continue"),
                    )
                    .put("source_digest", "ddl-fixture")
                    .put("outcome", "complete")
                    .put("upstream_diagnostics", JSONArray()).put("downstream_diagnostics", JSONArray())
                    .put("resource_omissions", JSONArray()).put("relation_omissions", JSONArray())
            } else {
                null
            }
            return JSONObject()
                .put("protocol", "inku.pipeline")
                .put("version", "1.0.0")
                .put("execution_id", executionId)
                .put("variation_id", variationId)
                .put("sequence", sequence)
                .put("event_sequence", sequence)
                .put("action_ordinal", sequence)
                .put(
                    "authority",
                    JSONObject()
                        .put("protocol_version", "inku.variation-authority.v1")
                        .put("revision", revision)
                        .put("origin", if (direct) "user_authored_ddl" else "stage1_generated")
                        .put("authority", if (direct) "ddl_authoritative" else "description_authoritative"),
                )
                .put("config", JSONObject(config.toString()))
                .put("composition", if (config.has("composition")) JSONObject().put("state", "fixture") else JSONObject.NULL)
                .put("stage1_fallback_plan", if (state == State.Composition) JSONObject() else JSONObject.NULL)
                .put("document", document?.let(::visibleDocument) ?: JSONObject.NULL)
                .put("phase", phase)
                .put("action", action ?: JSONObject.NULL)
                .put("delivery", delivery ?: JSONObject.NULL)
                .put("snapshot_digest", "fixture")
                .put("origin_fixture", originFixture)
        }

        override fun canvasRegistry() = """{"digest":"registry-digest","registry":{"schema":"inku.canvas-format-registry.v1","formats":[{"id":"square","width_units":1,"height_units":1}]}}"""
        override fun resolvePalette(inputBytes: ByteArray) = "{}".encodeToByteArray()
        override fun resolveMacroCatalog(inputBytes: ByteArray) =
            """{"schema":"inku.macro-catalog-resolution.v1","entries":[],"locks":[],"diagnostics":[]}""".encodeToByteArray()
        override fun recompose(inputBytes: ByteArray): ByteArray {
            recompositionRequests += JSONObject(inputBytes.toString(Charsets.UTF_8))
            return recompositionResponse?.toString()?.encodeToByteArray() ?: super.recompose(inputBytes)
        }
        override fun renderSaved(inputBytes: ByteArray) = error("not used")

        private enum class State { Sketch, Stage1, Composition, FirstCommit, Hole, AwaitingPatch, SecondCommit, Ready, Completed, Cancelled }
    }

    private companion object {
        const val OWNER = "owner"
        const val EXECUTION_ID = "execution"
        val MODELS = PipelineModelSelection("stage1", "stage2")
        val CONFIG = JSONObject().put(
            "envelope_limits",
            JSONObject()
                .put("max_input_bytes", 100_000)
                .put("max_snapshot_bytes", 100_000)
                .put("max_output_bytes", 100_000),
        )
        fun providerAction(tag: String, id: String) = JSONObject()
            .put("tag", tag)
            .put("version", 1)
            .put(
                "identity",
                JSONObject().put("action_id", id).put("attempt", 1).put("request_digest", "digest-$id"),
            )
            .put("timeout_ms", "1000")
            .put("delay_ms", "0")
            .put(
                "payload",
                JSONObject().put(
                    "prompt",
                    JSONObject()
                        .put("action_name", tag)
                        .put("system", "system")
                        .put("message", "message")
                        .put("response_schema", JSONObject().put("type", "object").put("properties", JSONObject())),
                ),
            )

        fun commitAction(id: String, source: String, revision: String) = JSONObject()
            .put("tag", "commit_visible_normalized_ddl")
            .put("version", 1)
            .put(
                "identity",
                JSONObject().put("action_id", id).put("attempt", 1).put("request_digest", "digest-$id"),
            )
            .put("timeout_ms", "0")
            .put("delay_ms", "0")
            .put(
                "payload",
                JSONObject()
                    .put("ddl_digest", "ddl-$id")
                    .put("document", visibleDocument(source))
                    .put("reason", "fixture")
                    .put(
                        "authority",
                        JSONObject()
                            .put("expected_revision", revision)
                            .put(
                                "next_state",
                                JSONObject()
                                    .put("protocol_version", "inku.variation-authority.v1")
                                    .put("revision", (revision.toInt() + 1).toString())
                                    .put("origin", "stage1_generated")
                                    .put("authority", "description_authoritative"),
                            ),
                    ),
            )

        fun sha256(value: String): String = java.security.MessageDigest.getInstance("SHA-256")
            .digest(value.encodeToByteArray())
            .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }

        fun visibleDocument(source: String) = JSONObject()
            .put("source", source)
            .put("language", "en")
            .put("macro_locks", JSONArray())

        fun effectResult(action: JSONObject, tag: String, response: String) = JSONObject()
            .put("tag", tag)
            .put("identity", action.getJSONObject("identity"))
            .put("response", response)
            .put("elapsed_ms", "1")
            .toString()
    }
}
