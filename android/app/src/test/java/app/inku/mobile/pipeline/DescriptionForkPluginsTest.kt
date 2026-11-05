package app.inku.mobile.pipeline

import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.ManagedHistoryRead
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Exercises the Android host and real core with an in-memory saved parent. */
class DescriptionForkPluginsTest {
    private class Fixture {
        var enabled = true
        var saved: ManagedHistoryRead? = null
        val starts = mutableListOf<JSONObject>()
        val requests = mutableListOf<ModelRequest>()
        private val executions = mutableMapOf<String, ByteArray>()
        private val binding = object : SharedPipelineBinding by NativePipelineBridge {
            override fun stepSvgLimited(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray, maxSvgBytes: Long): NativeSvgOutput {
                val payload = JSONObject(inputEnvelopeBytes.decodeToString()).getJSONObject("payload")
                if (payload.optString("tag") == "start") starts += payload
                return NativePipelineBridge.stepSvgLimited(snapshotBytes, inputEnvelopeBytes, maxSvgBytes)
            }
        }
        val pipeline = AndroidWorkPipeline(binding, object : ModelProvider {
            override val providerId = "fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse {
                requests += request
                val answer = when (request.pipelineAction) {
                    "generate_normalized_ddl" -> PLAN
                    "read_composition" -> READING
                    "choose_laws" -> LAWS
                    "choose_colors" -> throw IllegalArgumentException("fixture declines recoloring")
                    else -> error("unexpected action ${request.pipelineAction}")
                }
                return ModelResponse(answer, request.modelId)
            }
        }, object : PipelineCommitStore {
            override suspend fun commit(ownerId: String, actionJson: String, createIfMissing: Boolean, context: AuthoringContext): String {
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
        }, { saved }, bundledPluginsEnabled = { enabled })

        suspend fun parent(): PaintResult {
            val result = pipeline.paint(request())
            val link = requireNotNull(result.managedHistoryLink)
            val context = JSONObject(link.contextJson).put("config", JSONObject(link.snapshotJson).getJSONObject("config"))
            val item = HistoryItemEntity(id = "parent", createdAt = 1, updatedAt = 1, originalInput = DESCRIPTION,
                normalizedDdl = result.normalizedDdl, scoreJson = result.scoreJson, displaySvg = result.displaySvg,
                stage1Model = "fixture:model", stage2Model = "fixture:model", renderMetadataJson = result.renderMetadataJson,
                renderHash = result.renderHash, renderHashShort = result.renderHashShort, colorCatalogId = "default",
                canvasAspect = "square", starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null)
            saved = ManagedHistoryRead(item, "description_authoritative", variationId = link.variationId, forkContextJson = context.toString())
            return result
        }
        fun clear() { starts.clear(); requests.clear() }
        fun config() = starts.single().getJSONObject("config")
    }

    @Test
    fun descriptionForkWithDisabledPluginsMatchesANewDisabledWork() = runBlocking {
        val f = Fixture()
        val parent = f.parent()
        val parentContext = JSONObject(f.saved!!.forkContextJson!!)
        val parentConfig = parentContext.getJSONObject("config")
        assertTrue("parent must have bundled definitions", parentConfig.getJSONArray("definitions").length() > 0)
        val parentLocks = parentContext.getJSONObject("macro_catalog").getJSONArray("definition_locks")
        assertTrue("parent must have bundled locks", parentLocks.length() > 0)
        f.enabled = false
        f.clear()
        val fresh = f.pipeline.paint(request())
        val freshConfig = f.config()
        val freshLocks = JSONObject(fresh.managedHistoryLink!!.contextJson).getJSONObject("macro_catalog").getJSONArray("definition_locks")
        f.clear()
        val child = f.pipeline.paint(request().copy(parentHistoryId = "parent"))
        val childConfig = f.config()
        assertEquals("disabled description fork definitions must match a new disabled work",
            freshConfig.getJSONArray("definitions").toString(), childConfig.getJSONArray("definitions").toString())
        assertEquals("disabled description fork summaries must match a new disabled work",
            freshConfig.getJSONArray("macro_summaries").toString(), childConfig.getJSONArray("macro_summaries").toString())
        assertEquals("disabled description fork locks must match a new disabled work", freshLocks.toString(),
            JSONObject(child.managedHistoryLink!!.contextJson).getJSONObject("macro_catalog").getJSONArray("definition_locks").toString())
        assertNotNull(parent.normalizedDdl)
    }

    @Test
    fun savedDdlKeepsParentDefinitionsWhenDisabled() = runBlocking {
        val f = Fixture()
        val parent = f.parent()
        val parentContext = JSONObject(f.saved!!.forkContextJson!!)
        val parentConfig = parentContext.getJSONObject("config")
        val locks = parentContext.getJSONObject("macro_catalog").getJSONArray("definition_locks").toString()
        f.enabled = false
        f.clear()
        val ddl = f.pipeline.composeFromDdl(parent.normalizedDdl!!, request().copy(parentHistoryId = "parent", canvasAspect = "vertical"))
        for (key in listOf("definitions", "macro_summaries")) assertEquals(parentConfig.getJSONArray(key).toString(), f.config().getJSONArray(key).toString())
        assertEquals(locks, JSONObject(ddl.managedHistoryLink!!.contextJson).getJSONObject("macro_catalog").getJSONArray("definition_locks").toString())
    }

    companion object {
        private const val DESCRIPTION = "円がひとつ浮かび、下に点が散らばる"
        private fun request() = PaintRequest(description = DESCRIPTION, originalText = DESCRIPTION, stage1Model = "fixture:model", stage2Model = "fixture:model",
            colorCatalogId = "default", canvasAspect = "square", renderSeed = 7L, autoRepair = true, instructionLang = "ja", uiLang = "ja", saveHistory = false)
        private fun layer(action: String, shape: String, count: Int, position: String, size: String, color: String) =
            JSONObject().put("action", action).put("angle", "unspecified").put("bleeding", "unspecified").put("color", color)
                .put("continuity", "unspecified").put("count", count).put("handling", "dense").put("line_up_direction", "unspecified")
                .put("motion_amplitude", "unspecified").put("motion_quality", "unspecified").put("position", position)
                .put("proportion", "unspecified").put("shape", shape).put("size", size)
                .put("surface", if (shape == "point") "empty" else "flat").put("thinness", "unspecified").put("tool", "pen")
        private val PLAN = JSONObject().put("ground", "paper").put("background", "white").put("plugins", JSONArray())
            .put("layers", JSONArray().put(layer("fill", "square", 1, "unspecified", "large", "gray"))
                .put(layer("place", "circle", 1, "center", "small", "red"))
                .put(layer("scatter", "point", 12, "bottom", "very_small", "black"))).toString()
        private const val READING = """{"thesis":"ひとつの円が点の床の上に浮かぶ","roles":["field","focal","scattered"],"relations":[{"type":"above","layers":[1,2],"side":"unspecified","toward":"unspecified"}],"tension":{"motion":"still","focus":"unspecified","vertical":"unspecified","balance":"unspecified","symmetry":"unspecified","void":"unspecified"},"stated_places":[{"layer":2,"words":"下に","place":"bottom"}]}"""
        private const val LAWS = """{"main_law":"B1","description_counts":[{"layer":1,"words":"円がひとつ"}],"laws":{"B1":{"targets":[{"layer":1,"at":"point_ul"}]},"B21":{"targets":[{"layer":2,"hand":"still"}]}},"reason":"円を黄金分割の左上へ置く。"}"""
    }
}
