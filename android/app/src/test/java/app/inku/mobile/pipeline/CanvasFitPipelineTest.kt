package app.inku.mobile.pipeline

import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.ManagedHistoryRead
import app.inku.mobile.data.lineage.LineagePlanner
import app.inku.mobile.data.refinement.CanvasFit
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Production Android entry points and native core; no provider or device is involved. */
class CanvasFitPipelineTest {
    private class Fixture {
        var parent: ManagedHistoryRead? = null
        val starts = mutableListOf<JSONObject>()
        var commits = 0
        val binding = object : SharedPipelineBinding by NativePipelineBridge {
            override fun stepSvgLimited(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray, maxSvgBytes: Long): NativeSvgOutput {
                val payload = JSONObject(inputEnvelopeBytes.decodeToString()).getJSONObject("payload")
                if (payload.optString("tag") == "start") starts += payload
                return NativePipelineBridge.stepSvgLimited(snapshotBytes, inputEnvelopeBytes, maxSvgBytes)
            }
        }
        private val executions = mutableMapOf<String, ByteArray>()
        val pipeline = AndroidWorkPipeline(binding, object : ModelProvider {
            override val providerId = "fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse = error("Fitting must not call a model")
        }, object : PipelineCommitStore {
            override suspend fun commit(ownerId: String, actionJson: String, createIfMissing: Boolean, context: AuthoringContext): String {
                commits++
                val action = JSONObject(actionJson)
                val payload = action.getJSONObject("payload")
                return JSONObject().put("tag", "visible_normalized_ddl_committed").put("identity", action.getJSONObject("identity"))
                    .put("ddl_digest", payload.getString("ddl_digest"))
                    .put("revision", payload.getJSONObject("authority").getJSONObject("next_state").get("revision"))
                    .put("authority_digest", payload.getString("authority_digest")).toString()
            }
        }, object : PipelineExecutionStore {
            override suspend fun create(ownerId: String, executionId: String, variationId: String, sequence: String, stateBytes: ByteArray) {
                executions[executionId] = stateBytes.copyOf()
            }
            override suspend fun compareAndSet(ownerId: String, executionId: String, expectedSequence: String, nextSequence: String, stateBytes: ByteArray): Boolean {
                executions[executionId] = stateBytes.copyOf(); return true
            }
            override suspend fun load(ownerId: String, executionId: String) = executions[executionId]?.copyOf()
        }, { parent }, bundledPluginsEnabled = { false })

        suspend fun saveParent(): PaintResult {
            val result = pipeline.composeFromDdl(DDL, request())
            val link = requireNotNull(result.managedHistoryLink)
            val context = JSONObject(link.contextJson).put("config", JSONObject(link.snapshotJson).getJSONObject("config"))
                .put("pipeline_diagnostics", JSONObject(link.pipelineDiagnosticsJson))
            parent = ManagedHistoryRead(item(result), "ddl_authoritative", variationId = link.variationId,
                forkContextJson = context.toString())
            starts.clear()
            return result
        }
    }

    @Test
    fun newDirectDdlDeclaresItsPaperWhileAnEditKeepsItsSourceAndTheChosenFitReachesAFork() = runBlocking {
        val fixture = Fixture()
        val root = fixture.saveParent()
        assertTrue(root.normalizedDdl!!, root.normalizedDdl.startsWith("画面比1:1。"))
        val edited = fixture.pipeline.composeFromDdl(DDL, request().copy(parentHistoryId = "parent"))
        assertFalse(fixture.starts.last().getJSONObject("authoring").getBoolean("declare_canvas"))
        assertFalse(edited.normalizedDdl!!, edited.normalizedDdl.contains("画面比"))
        val fitted = fixture.pipeline.composeFromDdl(root.normalizedDdl, request().copy(parentHistoryId = "parent",
            executionId = edited.pipelineView!!.executionId, canvasAspect = "vertical", canvasFit = "contain"))
        val start = fixture.starts.last()
        assertFalse(start.getJSONObject("authoring").getBoolean("declare_canvas"))
        assertEquals("contain", start.getJSONObject("config").getJSONObject("compiler").getJSONObject("host").getString("canvas_fit"))
        assertEquals("contain", JSONObject(fitted.scoreJson).getJSONObject("canvas").getString("fit"))
        val stretched = fixture.pipeline.composeFromDdl(root.normalizedDdl, request().copy(parentHistoryId = "parent",
            executionId = fitted.pipelineView!!.executionId, canvasAspect = "vertical"))
        assertFalse(fixture.starts.last().getJSONObject("config").getJSONObject("compiler").getJSONObject("host").has("canvas_fit"))
        assertFalse(JSONObject(stretched.scoreJson).getJSONObject("canvas").has("fit"))
    }

    @Test
    fun fittingAnUntouchedWorkKeepsItsScoreVersionDdlAuthorityAndRenderingEvidence() = runBlocking {
        val fixture = Fixture()
        val root = fixture.saveParent()
        val committed = fixture.commits
        val (fitted, metadata) = fixture.pipeline.renderCanvasFit(root.scoreJson,
            request().copy(parentHistoryId = "parent", canvasAspect = "vertical"))
        assertEquals(committed, fixture.commits)
        assertTrue("No authoring start may re-read a saved work", fixture.starts.isEmpty())
        assertEquals(root.normalizedDdl, fitted.normalizedDdl)
        assertNull(fitted.managedHistoryLink)
        assertNull(fitted.managedHistoryReplay)
        val replay = requireNotNull(fitted.managedCanvasFit?.replay)
        assertEquals("parent", replay.sourceHistoryId)
        assertEquals("vertical", JSONObject(replay.hostOptionsJson).getString("canvas_aspect"))
        val original = JSONObject(root.scoreJson)
        val changed = JSONObject(fitted.scoreJson)
        assertEquals(original.getString("version"), changed.getString("version"))
        assertEquals(CoreIdentityJson.canonical(original.getJSONArray("instructions")), CoreIdentityJson.canonical(changed.getJSONArray("instructions")))
        assertEquals("contain", changed.getJSONObject("canvas").getString("fit"))
        assertEquals(7L, fitted.renderSeed)
        assertEquals(11L, fitted.compositionSeed)
        assertTrue(fitted.displaySvg.startsWith("<svg"))
        val parentMetadata = JSONObject(root.renderMetadataJson)
        val childMetadata = JSONObject(fitted.renderMetadataJson)
        assertEquals(CoreIdentityJson.canonical(parentMetadata.getJSONObject("render_color_map")),
            CoreIdentityJson.canonical(childMetadata.getJSONObject("render_color_map")))
        val child = item(fitted).copy(id = "child", canvasAspect = "vertical")
        val edgeMetadata = LineagePlanner.canonicalJson(metadata)
        CanvasFit.verify(fixture.parent!!.history, child, edgeMetadata)
        assertTrue(runCatching { CanvasFit.verify(fixture.parent!!.history, child.copy(scoreJson = root.scoreJson), edgeMetadata) }.isFailure)
        assertTrue(runCatching { CanvasFit.verify(fixture.parent!!.history, child.copy(normalizedDdl = DDL), edgeMetadata) }.isFailure)
    }

    @Test
    fun aSavedFitUsesTheFrozenSeedOrRefusesRatherThanAllocatingAnother() = runBlocking {
        val fixture = Fixture()
        val root = fixture.saveParent()
        val parent = requireNotNull(fixture.parent)
        fixture.parent = parent.copy(history = parent.history.copy(renderSeed = null))
        val (fitted, _) = fixture.pipeline.renderCanvasFit(root.scoreJson,
            request().copy(parentHistoryId = "parent", canvasAspect = "vertical", renderSeed = null))
        assertEquals(7L, fitted.renderSeed)
        fixture.parent = ManagedHistoryRead(parent.history.copy(renderSeed = null, renderMetadataJson = "{}"), "legacy_unknown")
        val failure = runCatching { fixture.pipeline.renderCanvasFit(root.scoreJson,
            request().copy(parentHistoryId = "parent", canvasAspect = "vertical", renderSeed = null)) }.exceptionOrNull()
        assertEquals("saved_render_seed_missing", failure?.message)
    }

    @Test
    fun fitRefusalsAndTheRecordedPaperCrossTheNativeBoundaryWithoutGuessing() {
        val score = """{"version":"0.22","canvas":"square","instructions":[]}"""
        val fitted = CanvasFit.render(score, "square", "vertical")
        assertEquals("square", fitted.derivationMetadata["from_canvas_aspect"])
        assertEquals(1, JSONObject(fitted.scoreJson).getJSONObject("canvas").getJSONObject("declared_ratio").getInt("width_units"))
        for ((drawnOn, paper, reason) in listOf(Triple("square", "square", "same_ratio"), Triple(null, "vertical", "no_recorded_ratio"))) {
            var answer: JSONObject? = null
            val binding = object : SharedPipelineBinding by NativePipelineBridge {
                override fun savedVariants(inputBytes: ByteArray): ByteArray = NativePipelineBridge.savedVariants(inputBytes).also {
                    answer = JSONObject(it.decodeToString())
                }
            }
            assertTrue(runCatching { CanvasFit.render(score, drawnOn, paper, binding) }.isFailure)
            assertEquals(reason, answer!!.getString("reason"))
        }
    }

    companion object {
        private const val DDL = "青の円を1個置く。"
        private fun request() = PaintRequest("", stage1Model = "fixture:model", stage2Model = "fixture:model",
            colorCatalogId = "default", canvasAspect = "square", autoRepair = false, renderSeed = 7L, compositionSeed = 11L)
        private fun item(result: PaintResult) = HistoryItemEntity(id = "parent", createdAt = 1, updatedAt = 1, originalInput = "",
            normalizedDdl = result.normalizedDdl, scoreJson = result.scoreJson, displaySvg = result.displaySvg,
            stage1Model = "fixture:model", stage2Model = "fixture:model", renderMetadataJson = result.renderMetadataJson,
            renderHash = result.renderHash, renderHashShort = result.renderHashShort, colorCatalogId = "default", canvasAspect = "square",
            starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null, lineageNodeId = "parent-node",
            renderSeed = "7", compositionSeed = "11")
    }
}
