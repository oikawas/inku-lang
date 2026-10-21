package app.inku.mobile.pipeline

import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.ManagedHistoryRead
import app.inku.mobile.data.refinement.SharedAutonomousRefinement
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Real host + JNI + fake provider: the two app moves reach the ordinary pipeline. */
class AutonomousMovesPipelineTest {
    private class Executions : PipelineExecutionStore {
        val bytes = mutableMapOf<String, ByteArray>()
        override suspend fun create(ownerId: String, executionId: String, variationId: String, sequence: String, stateBytes: ByteArray) {
            bytes[executionId] = stateBytes.copyOf()
        }
        override suspend fun compareAndSet(ownerId: String, executionId: String, expectedSequence: String,
            nextSequence: String, stateBytes: ByteArray): Boolean {
            bytes[executionId] = stateBytes.copyOf(); return true
        }
        override suspend fun load(ownerId: String, executionId: String) = bytes[executionId]?.copyOf()
    }

    private class Fixture(private val withColors: Boolean = true) {
        var saved: ManagedHistoryRead? = null
        var moved = false
        val requests = mutableListOf<ModelRequest>()
        val starts = mutableListOf<JSONObject>()
        val binding = object : SharedPipelineBinding by NativePipelineBridge {
            override fun stepSvgLimited(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray, maxSvgBytes: Long): NativeSvgOutput {
                val envelope = JSONObject(inputEnvelopeBytes.toString(Charsets.UTF_8))
                val payload = envelope.getJSONObject("payload")
                if (payload.optString("tag") == "start" && !withColors) payload.getJSONObject("config").remove("colors")
                if (payload.optString("tag") == "start") starts += payload
                return NativePipelineBridge.stepSvgLimited(snapshotBytes,
                    if (withColors) inputEnvelopeBytes else envelope.toString().encodeToByteArray(), maxSvgBytes)
            }
        }
        val provider = object : ModelProvider {
            override val providerId = "fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse {
                requests += request
                val answer = when (request.pipelineAction) {
                    "generate_normalized_ddl" -> PLAN
                    "read_composition" -> READING
                    "choose_laws" -> if (moved) MOVED else LAWS
                    "choose_colors" -> throw IllegalArgumentException("fixture declines recoloring")
                    else -> error("unexpected action ${request.pipelineAction}")
                }
                return ModelResponse(answer, request.modelId)
            }
        }
        val pipeline = AndroidWorkPipeline(binding, provider, object : PipelineCommitStore {
            override suspend fun commit(ownerId: String, actionJson: String, createIfMissing: Boolean, context: AuthoringContext): String {
                val action = JSONObject(actionJson)
                return JSONObject().put("tag", "visible_normalized_ddl_committed").put("identity", action.getJSONObject("identity"))
                    .put("ddl_digest", action.getJSONObject("payload").getString("ddl_digest"))
                    .put("revision", action.getJSONObject("payload").getJSONObject("authority").getJSONObject("next_state").get("revision"))
                    .put("authority_digest", action.getJSONObject("payload").getString("authority_digest")).toString()
            }
        }, Executions(), { saved })

        suspend fun parent(): PaintResult {
            val result = pipeline.paint(request())
            val link = result.managedHistoryLink!!
            val context = JSONObject(link.contextJson).put("config", JSONObject(link.snapshotJson).getJSONObject("config"))
            val item = HistoryItemEntity(id = "parent", createdAt = 1, updatedAt = 1, originalInput = DESCRIPTION,
                normalizedDdl = result.normalizedDdl, scoreJson = result.scoreJson, displaySvg = result.displaySvg,
                stage1Model = "fixture:parent", stage2Model = "fixture:parent", renderMetadataJson = result.renderMetadataJson,
                renderHash = result.renderHash, renderHashShort = result.renderHashShort, colorCatalogId = "default",
                canvasAspect = "square", starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null)
            saved = ManagedHistoryRead(item, "description_authoritative", variationId = link.variationId, forkContextJson = context.toString())
            requests.clear(); starts.clear()
            return result
        }
    }

    @Test
    fun aSavedLawsMoveWithAColorStageKeepsThatStageAndTheParentsConfigurationAndRecords() = checkSavedLaws(withColors = true)

    @Test
    fun aSavedLawsMoveWithoutAColorStageKeepsItAbsentAndTheParentsConfigurationAndRecords() = checkSavedLaws(withColors = false)

    private fun checkSavedLaws(withColors: Boolean) = runBlocking {
        val fixture = Fixture(withColors)
        val parent = fixture.parent()
        fixture.moved = true
        val direction = JSONObject("""{"exclude":["B1","B21"],"cards":"invite","note":"涼しげに"}""")
        val child = fixture.pipeline.savedLaws(request().copy(parentHistoryId = "parent", stage1Model = "fixture:run",
            stage2Model = "fixture:run"), parent.normalizedDdl!!, direction.toString())
        assertEquals(setOf("fixture:run"), fixture.requests.map { it.modelId }.toSet())
        val start = fixture.starts.single()
        val authoring = start.getJSONObject("authoring")
        assertEquals("saved_laws", authoring.getString("tag"))
        assertEquals(parent.normalizedDdl, authoring.getString("source"))
        assertEquals(DESCRIPTION, authoring.getString("description"))
        assertEquals("B1", authoring.getJSONObject("laws_basis").getString("main_law"))
        assertEquals("ddl_authoritative", start.getJSONObject("authority").getString("authority"))
        assertEquals(CoreIdentityJson.canonical(JSONObject(fixture.saved!!.forkContextJson!!).getJSONObject("config")),
            CoreIdentityJson.canonical(start.getJSONObject("config")))
        val basis = JSONObject(child.renderMetadataJson).getJSONObject("laws_basis")
        assertEquals("B3", basis.getString("main_law"))
        val laws = JSONObject().put("excluded", direction.getJSONArray("exclude")).put("cards", "invite")
        listOf("main_law", "main_layer", "laws", "reason").forEach { laws.put(it, basis.get(it)) }
        val record = record("laws", parent, child).put("laws", laws)
        assertEquals("laws", SharedAutonomousRefinement.call("record", record).getJSONObject("metadata").getJSONObject("ai_move").getString("kind"))
        // Neither saved configuration asks Stage 1 or the composition reader again.
        assertEquals(if (withColors) listOf("choose_laws", "choose_colors") else listOf("choose_laws"),
            fixture.requests.map { it.pipelineAction })
    }

    @Test
    fun aJuxtapositionDrawsItsJoinedDescriptionWithTheRunsOneModelAndKeepsBothRecords() = runBlocking {
        val fixture = Fixture(); val parent = fixture.parent()
        val joined = DESCRIPTION + "。廃駅のホームに時刻表だけが残る。"
        val child = fixture.pipeline.paint(request().copy(description = joined, originalText = joined,
            parentHistoryId = "parent", stage1Model = "fixture:run", stage2Model = "fixture:run"))
        assertEquals("description", fixture.starts.single().getJSONObject("authoring").getString("tag"))
        assertEquals(joined, fixture.starts.single().getJSONObject("authoring").getString("description"))
        assertEquals(setOf("fixture:run"), fixture.requests.map { it.modelId }.toSet())
        val juxtaposition = JSONObject().put("sentence", "廃駅のホームに時刻表だけが残る。")
            .put("history_ids", JSONArray(listOf("other"))).put("rank", 1).put("position", 0.5)
            .put("reason", "一文を足す").put("candidates", 4)
        val metadata = SharedAutonomousRefinement.call("record", record("juxtaposition", parent, child)
            .put("juxtaposition", juxtaposition)).getJSONObject("metadata")
        assertEquals("juxtaposition", metadata.getJSONObject("ai_move").getString("kind"))
        assertEquals(juxtaposition.getString("sentence"), metadata.getJSONObject("juxtaposition").getString("sentence"))
    }

    private fun record(kind: String, parent: PaintResult, child: PaintResult): JSONObject {
        val measured = SharedAutonomousRefinement.call("measure", JSONObject().put("before", parent.displaySvg).put("after", child.displaySvg))
        return JSONObject().put("run", "fixture-run").put("turn", 1).put("moves", 1).put("attempt", 1)
            .put("kind", kind).put("model", "fixture:run").put("outcome", if (measured.getBoolean("passes")) "kept" else "not_visible")
            .put("share", measured.get("share"))
    }

    companion object {
        private const val DESCRIPTION = "円がひとつ浮かび、下に点が散らばる"
        private fun request() = PaintRequest(description = DESCRIPTION, originalText = DESCRIPTION,
            stage1Model = "fixture:parent", stage2Model = "fixture:parent", colorCatalogId = "default", canvasAspect = "square",
            renderSeed = 7L, autoRepair = true, instructionLang = "ja", uiLang = "ja", saveHistory = false)
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
        private const val LAWS = """{"main_layer":1,"main_law":"B1","description_counts":[{"layer":1,"words":"円がひとつ"}],"laws":{"B1":{"targets":[{"layer":1,"at":"point_ul"}]},"B21":{"targets":[{"layer":2,"hand":"still"}]}},"reason":"円を黄金分割の左上へ置く。"}"""
        private const val MOVED = """{"main_layer":1,"main_law":"B3","description_counts":[{"layer":1,"words":"円がひとつ"}],"laws":{"B3":{"targets":[{"layer":1,"at":"point_lr"}]},"B15":{"layers":[2]}},"reason":"円を三分割の右下へ移し、点を遠くに置く。"}"""
    }
}
