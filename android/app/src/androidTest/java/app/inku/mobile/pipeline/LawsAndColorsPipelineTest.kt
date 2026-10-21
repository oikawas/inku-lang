package app.inku.mobile.pipeline

import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.refinement.PaintSeeds
import app.inku.mobile.data.refinement.RefinementParent
import app.inku.mobile.data.refinement.RefinementPlan
import app.inku.mobile.data.refinement.RefinementRoute
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The laws and color stages (SPEC §12.6.4-5) on the real JNI core, with the
 * answers of the server's `test_a_run_asked_for_its_colors_prints_the_colors_a_reader_chose.py`
 * and `test_a_composed_description_takes_the_laws_a_reader_chose.py`: a
 * composed description is asked for its laws and its colors with Stage 1's
 * model, keeps what each stage was sent, and saves the laws records.
 */
@RunWith(AndroidJUnit4::class)
class LawsAndColorsPipelineTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private var database: InkuDatabase? = null
    private var repository: InkuRepository? = null

    @After
    fun tearDown(): Unit = runBlocking {
        repository?.close()
        database?.close()
    }

    @Test
    fun aComposedDescriptionIsPrintedWithTheColorsItsReaderChose() = runBlocking {
        val provider = ReaderProvider(refuseColors = false)
        val repo = repository(provider)

        val work = paint(repo)

        assertEquals(listOf("generate_normalized_ddl", "read_composition", "choose_laws", "choose_colors"),
            provider.requests.map { it.pipelineAction })
        assertEquals(setOf(MODEL), provider.requests.map { it.modelId }.toSet())
        val colors = provider.requests[3]
        assertTrue(colors.prompt.contains(DESCRIPTION))
        // The color table names the paint each of the nine colors draws.
        assertTrue(colors.prompt, colors.prompt.contains("\"name\":\"black\",\"paint\":\"黒\""))
        // The circle the laws placed is printed in the blue.
        assertTrue(work.normalizedDdl, work.normalizedDdl.orEmpty().lines().contains(BLUE_CIRCLE))

        val metadata = JSONObject(work.renderMetadataJson)
        assertEquals(STAGES, metadata.getJSONArray("sent_system_prompt_stages").strings())
        val sent = metadata.getJSONObject("sent_system_prompts")
        assertEquals(provider.requests[2].prompt, sent.getJSONObject("laws").getString("message"))
        assertEquals(provider.requests[2].systemInstruction, sent.getJSONObject("laws").getString("system"))
        assertEquals(colors.prompt, sent.getJSONObject("colors").getString("message"))
        assertEquals(colors.systemInstruction, sent.getJSONObject("colors").getString("system"))
        assertNotNull(metadata.optJSONObject("laws_layers"))
        assertNotNull(metadata.optJSONObject("laws_basis"))

        // The estimate draws with the work's seed.
        val managed = repo.readManagedHistory(AndroidWorkPipeline.OWNER_ID, work.id)!!
        val config = JSONObject(managed.forkContextJson!!).getJSONObject("config")
        assertEquals("7", config.getJSONObject("colors").getString("render_seed"))
        assertEquals(0, config.getJSONObject("laws").length())
    }

    @Test
    fun aRefusedColorStageCommitsTheDocumentTheLawsPrinted() = runBlocking {
        val provider = ReaderProvider(refuseColors = true)
        val repo = repository(provider)

        val work = paint(repo)

        assertEquals(listOf("generate_normalized_ddl", "read_composition", "choose_laws", "choose_colors"),
            provider.requests.map { it.pipelineAction })
        // The circle stands at the crossing the laws chose, in the color Stage 1 gave it.
        assertTrue(work.normalizedDdl, work.normalizedDdl.orEmpty().lines().contains(RED_CIRCLE))
        val metadata = JSONObject(work.renderMetadataJson)
        assertNotNull(metadata.optJSONObject("laws_basis"))
        // The color stage was asked; it answered nothing to keep but what it was sent.
        assertTrue(metadata.getJSONObject("sent_system_prompts").getJSONObject("colors").has("message"))
    }

    @Test
    fun aChildDrawnWithoutARunKeepsItsParentsLawsRecords() = runBlocking {
        val provider = ReaderProvider(refuseColors = false)
        val repo = repository(provider)
        val parent = paint(repo)
        val asked = provider.requests.size

        val saved = RefinementParent.of(parent, parent.originalInput)
        val child = repo.renderRefinementCandidate(saved, RefinementPlan(
            element = null,
            route = RefinementRoute.RenderFromScore,
            catalogId = saved.catalogId,
            canvasAspect = saved.canvasAspect,
            seeds = saved.seeds,
            derivationKind = "variation_replay",
            derivationMetadata = emptyMap(),
        ))

        assertEquals(asked, provider.requests.size)
        val parentRecords = JSONObject(parent.renderMetadataJson)
        val childRecords = JSONObject(child.renderMetadataJson)
        for (key in listOf("laws_layers", "laws_basis")) {
            assertEquals(parentRecords.getJSONObject(key).toString(), childRecords.getJSONObject(key).toString())
        }
    }

    private fun repository(provider: ModelProvider): InkuRepository {
        val db = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .build().also { database = it }
        return InkuRepository(context, db, modelProviderOverride = provider).also { repository = it }
    }

    private suspend fun paint(repo: InkuRepository) = repo.paint(
        description = DESCRIPTION,
        catalogId = "default", canvasAspect = "square",
        stage1ModelId = MODEL, stage2ModelId = MODEL,
        seeds = PaintSeeds(renderSeed = 7L),
        instructionLang = "ja", uiLang = "ja",
    )

    private fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }

    /** Stage 1, the reader, the laws and the colors each answering once. */
    private class ReaderProvider(private val refuseColors: Boolean) : ModelProvider {
        override val providerId = "fixture"
        val requests = mutableListOf<ModelRequest>()

        override suspend fun generate(request: ModelRequest): ModelResponse {
            requests += request
            val answer = when (request.pipelineAction) {
                "generate_normalized_ddl" -> PLAN
                "read_composition" -> READING
                "choose_laws" -> LAWS
                "choose_colors" -> if (refuseColors) throw IllegalArgumentException("refused") else COLORS
                else -> error("unexpected action ${request.pipelineAction}")
            }
            return ModelResponse(answer, request.modelId)
        }
    }

    private companion object {
        const val MODEL = "fixture:model"
        // No color words, so the reader may recolor every layer.
        const val DESCRIPTION = "円がひとつ浮かび、下に点が散らばる"
        val STAGES = listOf("sketch", "stage1", "composition", "laws", "colors", "stage2")
        const val RED_CIRCLE = "画面の横0.381966、縦0.381966の位置に、赤のペンの濃い塗りの小さな円を1個置く。"
        const val BLUE_CIRCLE = "画面の横0.381966、縦0.381966の位置に、青のペンの濃い塗りの小さな円を1個置く。"

        private fun layer(action: String, shape: String, count: Int, position: String, size: String, color: String) =
            JSONObject()
                .put("action", action).put("angle", "unspecified").put("bleeding", "unspecified").put("color", color)
                .put("continuity", "unspecified").put("count", count).put("handling", "dense")
                .put("line_up_direction", "unspecified").put("motion_amplitude", "unspecified")
                .put("motion_quality", "unspecified").put("position", position).put("proportion", "unspecified")
                .put("shape", shape).put("size", size).put("surface", if (shape == "point") "empty" else "flat")
                .put("thinness", "unspecified").put("tool", "pen")

        val PLAN: String = JSONObject()
            .put("ground", "paper").put("background", "white").put("plugins", JSONArray())
            .put("layers", JSONArray()
                .put(layer("fill", "square", 1, "unspecified", "large", "gray"))
                .put(layer("place", "circle", 1, "center", "small", "red"))
                .put(layer("scatter", "point", 12, "bottom", "very_small", "black")))
            .toString()

        const val READING = """{"thesis":"ひとつの円が点の床の上に浮かぶ","roles":["field","focal","scattered"],"relations":[{"type":"above","layers":[1,2],"side":"unspecified","toward":"unspecified"}],"tension":{"motion":"still","focus":"unspecified","vertical":"unspecified","balance":"unspecified","symmetry":"unspecified","void":"unspecified"},"stated_places":[{"layer":2,"words":"下に","place":"bottom"}]}"""

        // The circle goes to the golden section's upper left crossing.
        const val LAWS = """{"main_layer":1,"main_law":"B1","description_counts":[{"layer":1,"words":"円がひとつ"}],"laws":{"B1":{"targets":[{"layer":1,"at":"point_ul"}]},"B21":{"targets":[{"layer":2,"hand":"still"}]}},"reason":"円を黄金分割の左上の交点に置く。"}"""

        // The circle, the laws' main layer, takes the blue.
        const val COLORS = """{"main_law":"D5","laws":{"D5":{"hue":"blue"}},"reason":"青を軸に近い色でまとめる。"}"""
    }
}
