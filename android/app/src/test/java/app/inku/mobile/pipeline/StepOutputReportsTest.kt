package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class StepOutputReportsTest {
    @Test fun freshDescriptionRunUsesStepReportsWithoutSnapshotQueries() = runBlocking {
        var progressQueries = 0
        var attemptQueries = 0
        val binding = object : SharedPipelineBinding by NativePipelineBridge {
            override fun runProgress(snapshotBytes: ByteArray): ByteArray {
                progressQueries++
                return NativePipelineBridge.runProgress(snapshotBytes)
            }
            override fun providerAttempt(snapshotBytes: ByteArray): ByteArray {
                attemptQueries++
                return NativePipelineBridge.providerAttempt(snapshotBytes)
            }
        }
        val actions = mutableListOf<String>()
        val attempts = mutableListOf<ProviderAttempt>()
        val progress = mutableListOf<RunProgress>()
        val executions = mutableMapOf<String, ByteArray>()
        val pipeline = AndroidWorkPipeline(binding, object : ModelProvider {
            override val providerId = "fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse {
                actions += request.pipelineAction!!
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
                executions[executionId] = stateBytes.copyOf()
                return true
            }
            override suspend fun load(ownerId: String, executionId: String) = executions[executionId]?.copyOf()
        }, readHistory = { null }, onProviderAttempt = { _, attempt -> attempt?.let { attempts += it } },
            onRunProgress = { _, report -> report?.let { progress += it } })

        val result = pipeline.paint(PaintRequest(description = "円がひとつ浮かび、下に点が散らばる",
            originalText = "円がひとつ浮かび、下に点が散らばる", stage1Model = "fixture:model", stage2Model = "fixture:model",
            colorCatalogId = "default", canvasAspect = "square", renderSeed = 7L, autoRepair = true,
            instructionLang = "ja", uiLang = "ja", saveHistory = false))
        assertNotNull(result.normalizedDdl)
        assertNotNull(result.displaySvg)
        assertEquals(listOf("generate_normalized_ddl", "read_composition", "choose_laws", "choose_colors"), actions)
        assertEquals(actions, attempts.map { it.action })
        assertTrue(progress.any { it.current?.action == "generate_normalized_ddl" })
        assertTrue(progress.last().finished.any { it.action == "choose_laws" })
        assertNull(progress.last().current)
        assertEquals("legacy queries (runProgress, providerAttempt)", listOf(0, 0), listOf(progressQueries, attemptQueries))
    }

    companion object {
        private fun layer(action: String, shape: String, count: Int, position: String, size: String, color: String) =
            JSONObject().put("action", action).put("angle", "unspecified").put("bleeding", "unspecified").put("color", color)
                .put("continuity", "unspecified").put("count", count).put("handling", "dense").put("line_up_direction", "unspecified")
                .put("motion_amplitude", "unspecified").put("motion_quality", "unspecified").put("position", position)
                .put("proportion", "unspecified").put("shape", shape).put("size", size)
                .put("surface", if (shape == "point") "empty" else "flat").put("thinness", "unspecified").put("tool", "pen")
        private val PLAN = JSONObject().put("ground", "paper").put("background", "white").put("plugins", org.json.JSONArray())
            .put("layers", org.json.JSONArray().put(layer("fill", "square", 1, "unspecified", "large", "gray"))
                .put(layer("place", "circle", 1, "center", "small", "red"))
                .put(layer("scatter", "point", 12, "bottom", "very_small", "black"))).toString()
        private const val READING = """{"thesis":"ひとつの円が点の床の上に浮かぶ","roles":["field","focal","scattered"],"relations":[{"type":"above","layers":[1,2],"side":"unspecified","toward":"unspecified"}],"tension":{"motion":"still","focus":"unspecified","vertical":"unspecified","balance":"unspecified","symmetry":"unspecified","void":"unspecified"},"stated_places":[{"layer":2,"words":"下に","place":"bottom"}]}"""
        private const val LAWS = """{"main_law":"B1","description_counts":[{"layer":1,"words":"円がひとつ"}],"laws":{"B1":{"targets":[{"layer":1,"at":"point_ul"}]},"B21":{"targets":[{"layer":2,"hand":"still"}]}},"reason":"円を黄金分割の左上へ置く。"}"""
    }
}
