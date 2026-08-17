package app.inku.mobile.data

import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The repository hands the author's description to the pipeline unchanged
 * (ledger I-134).
 *
 * Android used to concatenate an `emotionHint` of its own onto `description`
 * itself, which the server never did; I-114 removed it. The acceptance that
 * came with the removal drives `pipeline.paint()` directly, so it never passes
 * through `InkuRepository` -- putting the concatenation back was measured to
 * turn 0 of 136 JVM tests red. No JVM test constructs an `InkuRepository` at
 * all, because doing so needs a context and a database, which is why this gate
 * lives here on the device.
 *
 * This follows the server, whose description gates "run through the routes,
 * not through the predicates" (`test_description_is_the_origin.py`): the whole
 * run is real except the language model, and what the run used is read back
 * out of what was saved.
 *
 * **Where the description is observable.** `description` and `originalText`
 * leave the repository as two fields of one `PaintRequest`, and they surface in
 * different places:
 *
 * - `description` becomes the Stage 1 prompt verbatim -- `prompt =
 *   request.description` in `LocalFallbackPipeline`, with no template around
 *   it. So the recorded prompt is the observation, and it is exact.
 * - `originalText` becomes `PaintResult.originalInput`, which `saveResult`
 *   stores as `history_items.originalInput`.
 *
 * **`composeFromDdl` is deliberately not gated on `description`.** That entry
 * point takes the DDL as its own argument and reads `request.description`
 * nowhere, so an assertion about it would be green whatever the repository did
 * -- the same shape as I-142. Its `originalText` is observable and is gated
 * (T-4).
 */
@RunWith(AndroidJUnit4::class)
class DescriptionPassthroughTest {

    /**
     * Answers with the text it was given and keeps every prompt it saw.
     *
     * Echoing matters for the same reason it does in
     * `CatalogSelectionWiringTest`: a model that answered with one fixed
     * sentence would make two descriptions render one picture, and a test that
     * reads the description back could not tell which run wrote the row.
     *
     * Not an `object`: the recorded prompts must not survive into the next test.
     */
    private class RecordingModel : ModelProvider {
        override val providerId: String = "test"

        val prompts = mutableListOf<String>()

        override suspend fun generate(request: ModelRequest): ModelResponse {
            prompts += request.prompt
            return ModelResponse(text = request.prompt, modelId = request.modelId)
        }
    }

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository
    private lateinit var model: RecordingModel

    private val score =
        """{"version":"0.1.0","canvas":"square","background":"white","instructions":[]}"""

    private val ddl = "円 中央 半径0.2"

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        database = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        model = RecordingModel()
        repository = InkuRepository(context, database, modelProviderOverride = model)
    }

    @After
    fun tearDown() = runBlocking {
        // Cancels the thumbnail coroutine before the database goes away.
        repository.close()
        database.close()
    }

    /**
     * Stage 1 runs before Stage 2, so the first prompt recorded is the one the
     * description was supposed to become.
     */
    private fun firstPrompt(): String {
        assertTrue("the model was reached at all", model.prompts.isNotEmpty())
        return model.prompts.first()
    }

    /** Read back out of the store, not off the return value the call handed us. */
    private suspend fun savedRows(): List<HistoryItemEntity> =
        database.historyDao().listActive(20, 0).first()

    private suspend fun paint(description: String) = repository.paint(
        description = description,
        catalogId = CATALOG,
        canvasAspect = ASPECT,
        stage1ModelId = STAGE_MODEL,
        stage2ModelId = STAGE_MODEL,
    )

    @Test
    fun t1_paintGivesStage1TheDescriptionVerbatim() = runBlocking {
        val description = "T-1 ゆっくりと墨がにじむ朝の庭"

        paint(description)

        assertEquals(
            "the Stage 1 prompt is the description itself, with nothing added",
            description,
            firstPrompt(),
        )
    }

    @Test
    fun t2_interpretGivesStage1TheDescriptionVerbatim() = runBlocking {
        val description = "T-2 雨のあとの石畳がひかる"

        val result = repository.interpret(
            description = description,
            catalogId = CATALOG,
            canvasAspect = ASPECT,
            stage1ModelId = STAGE_MODEL,
            stage2ModelId = STAGE_MODEL,
        )

        assertEquals(
            "the Stage 1 prompt is the description itself, with nothing added",
            description,
            firstPrompt(),
        )
        // This path saves nothing, so its `originalText` is observable only in
        // what it returns. Without this the field would be ungated here while
        // the other three entry points have it covered -- and it is not inert:
        // it becomes the expander's context text.
        assertEquals(
            "the returned originalInput is the description itself, with nothing added",
            description,
            result.originalInput,
        )
    }

    @Test
    fun t3_paintStoresTheDescriptionAsTheOriginalInput() = runBlocking {
        val description = "T-3 夕暮れに鳥が二羽"

        paint(description)

        val rows = savedRows()
        assertEquals("exactly one run was saved", 1, rows.size)
        assertEquals(
            "originalInput is the description itself, with nothing added",
            description,
            rows.single().originalInput,
        )
    }

    @Test
    fun t4_composeFromDdlStoresTheDescriptionAsTheOriginalInput() = runBlocking {
        val description = "T-4 指示書から起こした一枚"

        repository.composeFromDdl(
            description = description,
            ddl = ddl,
            catalogId = CATALOG,
            canvasAspect = ASPECT,
            stage1ModelId = STAGE_MODEL,
            stage2ModelId = STAGE_MODEL,
        )

        val rows = savedRows()
        assertEquals("exactly one run was saved", 1, rows.size)
        assertEquals(
            "originalInput is the description itself, with nothing added",
            description,
            rows.single().originalInput,
        )
    }

    @Test
    fun t5_renderFromScoreStoresTheDescriptionUnchangedInBothPlaces() = runBlocking {
        val description = "T-5 楽譜から直に描く"

        repository.renderFromScore(
            description = description,
            scoreJson = score,
            catalogId = CATALOG,
            canvasAspect = ASPECT,
            stage1ModelId = STAGE_MODEL,
            stage2ModelId = STAGE_MODEL,
        )

        val row = savedRows().single()
        assertEquals(
            "originalInput is the description itself, with nothing added",
            description,
            row.originalInput,
        )
        // This path carries `description` through as the DDL, so the same text
        // has to arrive there too -- an addition made to only one of the two
        // fields would otherwise pass T-3 to T-5.
        assertEquals(
            "normalizedDdl is the description itself, with nothing added",
            description,
            row.normalizedDdl,
        )
    }

    /**
     * The other way round, so that an implementation which ignored its argument
     * and returned a constant could not pass: two descriptions must reach the
     * model, and the store, as two different texts.
     */
    @Test
    fun t6_twoDescriptionsStayTwoTexts() = runBlocking {
        val first = "T-6 一つ目の記述"
        val second = "T-6 二つ目の記述"

        paint(first)
        val firstSeen = firstPrompt()
        // Cleared between the runs: a paint reaches the model twice (Stage 1
        // then Stage 2), so "the last prompt" is not the second description.
        model.prompts.clear()
        paint(second)
        val secondSeen = firstPrompt()

        assertNotEquals("the two runs did not collapse into one prompt", firstSeen, secondSeen)
        assertEquals(first, firstSeen)
        assertEquals(second, secondSeen)

        val stored = savedRows().map { it.originalInput }.toSet()
        assertEquals("both descriptions were stored, unchanged", setOf(first, second), stored)
    }

    private companion object {
        /** Not provider-qualified, so Stage 1 and Stage 2 may fall back locally. */
        const val STAGE_MODEL = "test-stage-model"
        const val CATALOG = "sumi"
        const val ASPECT = "1:1"
    }
}
