package app.inku.mobile.data

import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.pipeline.SketchInput
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * 写生 (Stage 0.5) really runs, and what it did is really written down.
 *
 * The whole run is real except the language model, and what the run used is
 * read back out of what was saved -- the same shape `DescriptionPassthroughTest`
 * next door uses, and for the same reason: the layer's job is to change what
 * Stage 1 reads, and only the recorded Stage 1 prompt can say whether it did.
 *
 * `SketchTest` on the JVM covers the values, the prompt and the states. It
 * cannot stand in for this: a layer nothing calls still passes its own table.
 */
@RunWith(AndroidJUnit4::class)
class SketchLayerTest {

    /**
     * Answers the 0.5 call and the Stage calls differently, so the two are
     * distinguishable in what comes out.
     *
     * A 0.5 call is the one carrying the layer's system prompt. Echoing
     * everything else keeps two descriptions two pictures, which the unique
     * render hash requires.
     */
    private class SketchAwareModel(private val failSketch: Boolean = false) : ModelProvider {
        override val providerId: String = "test"

        val requests = mutableListOf<ModelRequest>()

        override suspend fun generate(request: ModelRequest): ModelResponse {
            requests += request
            if (!isSketchCall(request)) {
                return ModelResponse(text = request.prompt, modelId = request.modelId)
            }
            if (failSketch) error("the provider refused the 0.5 call")
            return ModelResponse(text = SKETCH_PREFIX + request.prompt, modelId = request.modelId)
        }

        fun sketchCalls(): List<ModelRequest> = requests.filter(::isSketchCall)

        /** The layer is the only caller that sends a system prompt naming it. */
        private fun isSketchCall(request: ModelRequest): Boolean =
            request.systemInstruction?.startsWith(SKETCH_PROMPT_OPENING) == true
    }

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository
    private lateinit var model: SketchAwareModel

    @Before
    fun setUp() {
        model = SketchAwareModel()
        repository = openWith(model)
    }

    private fun openWith(provider: ModelProvider): InkuRepository {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        database = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        return InkuRepository(context, database, modelProviderOverride = provider)
    }

    @After
    fun tearDown() = runBlocking {
        repository.close()
        database.close()
    }

    private suspend fun savedRows(): List<HistoryItemEntity> =
        database.historyDao().listActive(20, 0).first()

    /** Stage 1 is the first call that is not the 0.5 one. */
    private fun stage1Prompt(): String {
        val stage = model.requests.firstOrNull { it.systemInstruction?.startsWith(SKETCH_PROMPT_OPENING) != true }
        return requireNotNull(stage) { "no stage was reached at all" }.prompt
    }

    private suspend fun paint(description: String, sketch: SketchInput) = repository.paint(
        description = description,
        catalogId = CATALOG,
        canvasAspect = ASPECT,
        stage1ModelId = STAGE_MODEL,
        stage2ModelId = STAGE_MODEL,
        sketch = sketch,
    )

    // --- T-5: the layer really runs -------------------------------------

    /**
     * With the control off, the layer is never called and Stage 1 reads the
     * description itself -- exactly what `DescriptionPassthroughTest` pins for
     * the plain path.
     */
    @Test
    fun t5a_offSendsTheDescriptionStraightToStageOne() = runBlocking {
        val description = "T-5a 夕暮れに鳥が二羽"

        paint(description, SketchInput(requested = false))

        assertTrue("the layer was called with the control off", model.sketchCalls().isEmpty())
        assertEquals(
            "Stage 1 read the description itself, with nothing in front of it",
            description,
            stage1Prompt(),
        )
    }

    /**
     * With the control on, the layer is called once with the description, and
     * Stage 1 reads what came back -- not the description.
     *
     * Both halves are asserted. "The layer was called" alone is passed by an
     * implementation that runs 0.5 and then throws its answer away, which is the
     * failure the whole layer would be invisible under.
     */
    @Test
    fun t5b_fineSendsTheSketchToStageOne() = runBlocking {
        val description = "T-5b 雨のあとの石畳がひかる"

        paint(description, SketchInput(requested = true, grain = "fine"))

        val sketchCalls = model.sketchCalls()
        assertEquals("the layer was called exactly once", 1, sketchCalls.size)
        assertEquals("the layer read the description", description, sketchCalls.single().prompt)
        assertEquals(
            "Stage 1 read what the layer produced, not the description",
            SKETCH_PREFIX + description,
            stage1Prompt(),
        )
        assertNotEquals("and those two are not the same string", description, stage1Prompt())
    }

    /**
     * A prose that came with the request is used as it stands and the layer is
     * not called again. This is what a redraw at the same grain does, and it has
     * to hold: the layer is not deterministic, so asking it a second time would
     * not be a replay.
     */
    @Test
    fun t5c_acarriedProseIsUsedWithoutCallingTheLayer() = runBlocking {
        val description = "T-5c 楠の影が石段にかかる"
        val prose = "石段がある。影が石段にかかる。影は濃い。"

        paint(description, SketchInput(requested = true, text = prose, grain = "fine"))

        assertTrue("the layer was called for a prose already in hand", model.sketchCalls().isEmpty())
        assertEquals("Stage 1 read the carried prose", prose, stage1Prompt())
    }

    // --- T-6: the three columns -----------------------------------------

    @Test
    fun t6a_theThreeColumnsAreSavedAndReadBack() = runBlocking {
        val description = "T-6a 白い花びらが散る"

        paint(description, SketchInput(requested = true, grain = "coarse"))

        val row = savedRows().single()
        assertEquals("the prose is stored", SKETCH_PREFIX + description, row.sketchText)
        assertEquals("the grain it was cut at is stored", "coarse", row.sketchGrain)
        assertEquals("and what the layer did is stored", "coarse", row.sketchState)
        assertEquals(
            "the author's description is untouched by the layer",
            description,
            row.originalInput,
        )
    }

    /**
     * With the control off the row still says so, and it says `off` rather than
     * nothing at all: an empty column means the work predates the columns, and
     * this work did not.
     */
    @Test
    fun t6b_theControlOffIsRecordedAsAChoice() = runBlocking {
        val description = "T-6b 黒い太筆の線を3本、斜めに置く"

        paint(description, SketchInput(requested = false))

        val row = savedRows().single()
        assertNull("nothing was produced, so there is no prose", row.sketchText)
        assertNull("and no grain", row.sketchGrain)
        assertEquals("but the choice is on the record", "off", row.sketchState)
    }

    /**
     * The layer was asked for and the provider refused.
     *
     * The picture is still made -- a broken 0.5 can never stop a painting -- and
     * the row says `fallback`. The prose and the grain columns stay empty,
     * because what a fallback carries is the description itself, and writing
     * that into the prose column would make a work that never went through the
     * layer indistinguishable from one that did (`render.py:1917-1922`).
     *
     * Production holds no `fallback` row at all, so this condition is made here
     * rather than found.
     */
    @Test
    fun t6c_afailedLayerIsRecordedAsFallbackAndStillDraws() = runBlocking {
        repository.close()
        database.close()
        val failing = SketchAwareModel(failSketch = true)
        repository = openWith(failing)
        val description = "T-6c 石走る垂水の上のさわらび"

        val saved = repository.paint(
            description = description,
            catalogId = CATALOG,
            canvasAspect = ASPECT,
            stage1ModelId = STAGE_MODEL,
            stage2ModelId = STAGE_MODEL,
            sketch = SketchInput(requested = true, grain = "fine"),
        )

        assertEquals("the layer was tried", 1, failing.sketchCalls().size)
        val row = savedRows().single()
        assertEquals(saved.id, row.id)
        assertEquals("the failure is on the record", "fallback", row.sketchState)
        assertNull("a fallback carries no prose of its own", row.sketchText)
        assertNull("and no grain", row.sketchGrain)
        assertFalse("the picture was still made", row.displaySvg.isEmpty())
        assertEquals(
            "and it was made from the description, untouched",
            description,
            row.originalInput,
        )
    }

    /**
     * The other direction, and the one the state column exists for: a failure is
     * not written down as `off`. Without this, an implementation that rounded
     * every unusable result to "the author chose not to" would pass T-6b and
     * T-6c's "it still draws" half.
     */
    @Test
    fun t6d_afailureIsNotRecordedAsAChoice() = runBlocking {
        repository.close()
        database.close()
        val failing = SketchAwareModel(failSketch = true)
        repository = openWith(failing)

        repository.paint(
            description = "T-6d 濡れた岩は黒い",
            catalogId = CATALOG,
            canvasAspect = ASPECT,
            stage1ModelId = STAGE_MODEL,
            stage2ModelId = STAGE_MODEL,
            sketch = SketchInput(requested = true, grain = "fine"),
        )

        val row = savedRows().single()
        assertNotEquals("a wiring failure is not a choice the author made", "off", row.sketchState)
        assertNotEquals("nor a success", "fine", row.sketchState)
        assertEquals("fallback", row.sketchState)
    }

    private companion object {
        /** Not provider-qualified, so Stage 1 and Stage 2 may fall back locally. */
        const val STAGE_MODEL = "test-stage-model"
        const val CATALOG = "sumi"
        const val ASPECT = "1:1"

        /** Marks what the layer produced, so Stage 1's input is identifiable. */
        const val SKETCH_PREFIX = "［写生］"

        /**
         * The first line of the Japanese 0.5 system prompt. Written out rather
         * than read from the product, so that a run which sent some other prompt
         * is not quietly accepted as a 0.5 call. `SketchTest` pins the prompt
         * itself against the server's material.
         */
        const val SKETCH_PROMPT_OPENING = "あなたは inku の写生層である。"
    }
}
