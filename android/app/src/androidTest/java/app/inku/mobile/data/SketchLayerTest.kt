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
import app.inku.mobile.testing.pipelineFixtureResponse
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * 写生 (Stage 0.5) through the shared pipeline: when it is not asked, when its
 * prose is already in hand, and when it fails -- and what the row records.
 *
 * A layer asked for and answered is `AndroidSharedPipelineTest`'s
 * `sketchOnUsesPackagedPipelineAndSavesGeneratedProse`. This class kept the
 * pre-pipeline contract until 2026-09-26 -- Stage 1 reading the prose as its
 * whole prompt, fine and coarse grains, a catalog and paper that no longer
 * exist -- and was rewritten to the cases no other device test covers.
 */
@RunWith(AndroidJUnit4::class)
class SketchLayerTest {

    /** Answers the pipeline in its own shape, and can refuse the 0.5 call. */
    private class SketchAwareModel(private val failSketch: Boolean = false) : ModelProvider {
        override val providerId: String = "test"

        val requests = mutableListOf<ModelRequest>()

        override suspend fun generate(request: ModelRequest): ModelResponse {
            requests += request
            if (isSketchCall(request) && failSketch) error("the provider refused the 0.5 call")
            return pipelineFixtureResponse(request)
        }

        fun sketchCalls(): List<ModelRequest> = requests.filter(::isSketchCall)

        /** The 0.5 call is the one whose answer is a `sketch`. */
        private fun isSketchCall(request: ModelRequest): Boolean =
            request.tool?.parametersJson?.contains("\"sketch\"") == true
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

    private suspend fun paint(description: String, sketch: SketchInput) = repository.paint(
        description = description,
        catalogId = CATALOG,
        canvasAspect = ASPECT,
        stage1ModelId = STAGE_MODEL,
        stage2ModelId = STAGE_MODEL,
        sketch = sketch,
    )

    /**
     * With the control off the layer is never called, and the row says `off`
     * rather than nothing: an empty column means a work older than the column.
     */
    @Test
    fun offSkipsTheLayerAndRecordsTheChoice() = runBlocking {
        paint("夕暮れに鳥が二羽", SketchInput(requested = false))

        assertTrue("the layer was called with the control off", model.sketchCalls().isEmpty())
        val row = savedRows().single()
        assertNull("nothing was produced, so there is no prose", row.sketchText)
        assertEquals("but the choice is on the record", "off", row.sketchState)
    }

    /**
     * A prose that came with the request is used as it stands and the layer is
     * not asked again: the layer is not deterministic, so a second call would
     * not be a replay. This is what a redraw of a work with 写生 carries.
     */
    @Test
    fun aCarriedProseIsUsedWithoutCallingTheLayer() = runBlocking {
        val prose = "石段がある。影が石段にかかる。影は濃い。"

        paint("楠の影が石段にかかる", SketchInput(requested = true, text = prose))

        assertTrue("the layer was called for a prose already in hand", model.sketchCalls().isEmpty())
        val row = savedRows().single()
        assertEquals("the carried prose is the one on the record", prose, row.sketchText)
        assertEquals("supplemented", row.sketchState)
    }

    /**
     * The layer was asked for and the provider refused. The picture is still
     * made -- a broken 0.5 never stops a painting -- and the row says
     * `fallback`, not `off`: a failure is not a choice the author made. No
     * prose is recorded, so the work cannot pass for one that went through
     * the layer.
     */
    @Test
    fun aFailedLayerIsRecordedAsFallbackAndStillDraws() = runBlocking {
        repository.close()
        database.close()
        val failing = SketchAwareModel(failSketch = true)
        repository = openWith(failing)
        val description = "石走る垂水の上のさわらび"

        val saved = paint(description, SketchInput(requested = true))

        // The pipeline asks a failing layer again before it falls back (four
        // calls on the Pixel 9); what matters is that it was asked at all.
        assertTrue("the layer was tried", failing.sketchCalls().isNotEmpty())
        val row = savedRows().single()
        assertEquals(saved.id, row.id)
        assertEquals("the failure is on the record", "fallback", row.sketchState)
        assertNull("a fallback carries no prose of its own", row.sketchText)
        assertFalse("the picture was still made", row.displaySvg.isEmpty())
        assertEquals("from the description, untouched", description, row.originalInput)
    }

    private companion object {
        const val STAGE_MODEL = "test-stage-model"
        const val CATALOG = "default"
        const val ASPECT = "square"
    }
}
