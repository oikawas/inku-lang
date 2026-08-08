package app.inku.mobile.ui

import android.app.Application
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.LineageEdgeEntity
import app.inku.mobile.data.db.LineageNodeEntity
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.pipeline.SketchMode
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The 写生 (Stage 0.5) grain writes its own lineage edge, from the screen down.
 *
 * `SubmitDerivationKindTest` on the JVM covers the rule; it is green whether or
 * not any screen ever passes `grainChanged` in. What is under test here is that
 * wiring, which is why it runs on the device against a real repository, and why
 * every kind is read back out of `lineage_edges` rather than off the screen.
 *
 * The harness is `LineageDeclarationWiringTest`'s, for the same reasons stated
 * there.
 */
@RunWith(AndroidJUnit4::class)
class SketchLineageWiringTest {

    /** Echoes the request, so that two runs stay two pictures. */
    private object EchoModel : ModelProvider {
        override val providerId: String = "test"

        override suspend fun generate(request: ModelRequest): ModelResponse =
            ModelResponse(text = request.prompt, modelId = request.modelId)
    }

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository
    private lateinit var application: Application
    private var viewModel: InkuViewModel? = null
    private var store: ViewModelStore? = null
    private var scope: CoroutineScope? = null
    private var collection: Job? = null

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        application = context.applicationContext as Application
        database = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        repository = InkuRepository(context, database, modelProviderOverride = EchoModel)
    }

    private fun startViewModel() {
        val created = ViewModelStore()
        store = created
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                InkuViewModel(application, repositoryOverride = repository) as T
        }
        viewModel = ViewModelProvider(created, factory)[InkuViewModel::class.java]
        val collector = CoroutineScope(Dispatchers.Main)
        scope = collector
        collection = collector.launch { vm().state.collect { } }
    }

    private fun vm(): InkuViewModel = requireNotNull(viewModel) { "startViewModel() was not called" }

    @After
    fun tearDown() = runBlocking {
        viewModel?.stopDrawing()
        collection?.cancel()
        scope?.cancel()
        store?.let { withContext(Dispatchers.Main) { it.clear() } }
        delay(SETTLE_AFTER_CLEAR_MS)
        // Closing it here as well is what makes the wait above a belt rather
        // than the guarantee: this one blocks until the scheduled thumbnail
        // write is on disk, so the close below cannot land on top of it.
        repository.close()
        database.close()
    }

    // --- helpers ---

    private suspend fun settle(what: String, condition: () -> Boolean) {
        try {
            withTimeout(TIMEOUT_MS) {
                while (!condition()) {
                    delay(POLL_MS)
                }
            }
        } catch (timeout: Exception) {
            throw AssertionError("timed out waiting for $what; ${stateReport()}", timeout)
        }
    }

    private fun stateReport(): String {
        val state = viewModel?.state?.value ?: return "no view model"
        return "selectedHistory=${state.selectedHistory?.id} sketchMode=${state.sketchMode} " +
            "prompt=\"${state.prompt.take(24)}\" isDrawing=${state.isDrawing} message=\"${state.message}\""
    }

    private suspend fun useModel() {
        vm().setSelectedModel(STAGE_MODEL)
        settle("the model to reach the shared state") { vm().state.value.selectedModelId == STAGE_MODEL }
    }

    private suspend fun promptFor(text: String) {
        vm().setPrompt(text)
        settle("the prompt to reach the shared state") { vm().state.value.prompt == text }
    }

    private suspend fun useSketchMode(mode: SketchMode) {
        vm().setSketchMode(mode)
        settle("the 写生 control to reach the shared state") { vm().state.value.sketchMode == mode }
    }

    private suspend fun savedRows(): List<HistoryItemEntity> =
        database.historyDao().listActive(20, 0).first()

    private suspend fun awaitSavedRuns(count: Int): List<HistoryItemEntity> {
        var rows: List<HistoryItemEntity> = emptyList()
        settle("$count drawing(s) to be saved") {
            rows = runBlocking { savedRows() }
            rows.size >= count
        }
        return rows
    }

    private suspend fun awaitNewestAfter(previous: Int): HistoryItemEntity =
        awaitSavedRuns(previous + 1).first()

    private suspend fun edgeOf(item: HistoryItemEntity): LineageEdgeEntity? =
        database.lineageDao().getEdgeByChildId(requireNotNull(item.lineageNodeId))

    /** As in `LineageDeclarationWiringTest`: a finished work put in place, not drawn. */
    private suspend fun seedParent(
        description: String,
        sketchGrain: String?,
        suffix: String,
    ): HistoryItemEntity {
        val now = System.currentTimeMillis()
        val nodeId = "seed-node-$suffix"
        val item = HistoryItemEntity(
            id = "seed-history-$suffix",
            createdAt = now,
            updatedAt = now,
            originalInput = description,
            normalizedDdl = description,
            expandedDdl = null,
            scoreJson = "{}",
            displaySvg = "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
            stage1Model = STAGE_MODEL,
            stage2Model = STAGE_MODEL,
            renderMetadataJson = "{}",
            renderHash = "seed-render-hash-$suffix",
            renderHashShort = "seed$suffix".takeLast(8),
            colorCatalogId = "default",
            canvasAspect = PARENT_CANVAS,
            starred = false,
            trashed = false,
            elapsedMs = 0L,
            tokenMetadataJson = null,
            lineageNodeId = nodeId,
            sketchText = sketchGrain?.let { PARENT_PROSE },
            sketchGrain = sketchGrain,
            sketchState = sketchGrain ?: "off",
        )
        database.historyDao().upsert(item)
        database.lineageDao().insertNode(
            LineageNodeEntity(
                id = nodeId,
                historyId = item.id,
                state = "active",
                descriptionHash = null,
                renderHash = item.renderHash,
                at = now,
                rootNodeId = nodeId,
            ),
        )
        return item
    }

    private suspend fun chooseFromHistory(item: HistoryItemEntity) {
        vm().selectHistory(item)
        settle("the pick to reach the shared state") {
            vm().state.value.selectedHistory?.id == item.id && !vm().state.value.lineageDetached
        }
    }

    // --- T-8 -------------------------------------------------------------

    /**
     * Both halves in one test, because either alone is passed by a broken
     * implementation: "a moved grain writes its own edge" is passed by one that
     * writes `sketch_grain_change` for every redraw, and "an unchanged grain is
     * a replay" is passed by one that never writes the new edge at all.
     */
    @Test
    fun t8_amovedGrainWritesItsOwnEdgeAndAnUnchangedOneIsAReplay() = runBlocking {
        val parent = seedParent(PARENT_DESCRIPTION, sketchGrain = "fine", suffix = "t8")
        startViewModel()
        useModel()
        useSketchMode(SketchMode.Fine)
        chooseFromHistory(parent)
        settle("the parent's description to be the one on screen") {
            vm().state.value.prompt == parent.originalInput
        }

        // Same description, same canvas, same grain: nothing moved.
        vm().draw()
        val replayed = awaitNewestAfter(1)
        assertEquals("replay", edgeOf(replayed)?.derivationKind)

        // The same parent again, and only the grain moves.
        chooseFromHistory(parent)
        settle("the parent's description to be back on screen") {
            vm().state.value.prompt == parent.originalInput
        }
        useSketchMode(SketchMode.Coarse)
        vm().draw()
        val recut = awaitNewestAfter(2)

        val edge = edgeOf(recut)
        assertNotNull("the redraw at a new grain was saved with no lineage edge at all", edge)
        assertEquals("sketch_grain_change", edge!!.derivationKind)
        assertEquals(parent.lineageNodeId, edge.parentNodeId)
        assertEquals("and the new grain is on the row", "coarse", recut.sketchGrain)
    }

    /**
     * A work with no grain recorded was not drawn at the default: it was drawn
     * before there was a grain to record. Redrawing it with the layer on is
     * therefore a grain change, and redrawing it with the layer off is not --
     * `off` carries no grain either, so absence compares equal to absence.
     *
     * This is the pair that fails if the recorded grain is read with the
     * request-side normalizer, which would round the absent value up to `fine`
     * and give both answers backwards.
     */
    @Test
    fun t8b_aworkWithNoGrainRecordedIsNotAWorkDrawnAtTheDefault() = runBlocking {
        val parent = seedParent(OLD_DESCRIPTION, sketchGrain = null, suffix = "t8b")
        startViewModel()
        useModel()
        useSketchMode(SketchMode.Off)
        chooseFromHistory(parent)
        settle("the parent's description to be the one on screen") {
            vm().state.value.prompt == parent.originalInput
        }

        vm().draw()
        val withLayerOff = awaitNewestAfter(1)
        assertEquals(
            "redrawing a work that predates the column with the layer off moved nothing",
            "replay",
            edgeOf(withLayerOff)?.derivationKind,
        )

        chooseFromHistory(parent)
        settle("the parent's description to be back on screen") {
            vm().state.value.prompt == parent.originalInput
        }
        useSketchMode(SketchMode.Fine)
        vm().draw()
        val withLayerOn = awaitNewestAfter(2)
        assertEquals(
            "and turning the layer on is a grain change",
            "sketch_grain_change",
            edgeOf(withLayerOn)?.derivationKind,
        )
    }

    // --- T-9 -------------------------------------------------------------

    /**
     * One edge, one cause (SPEC.ja.md:614). The description and the grain moved
     * together, and the edge is the description's: the grain branch is read
     * after it, and this is the gate that keeps it there.
     */
    @Test
    fun t9_adescriptionAndAGrainMovingTogetherIsADescriptionEdit() = runBlocking {
        val parent = seedParent(PARENT_DESCRIPTION, sketchGrain = "fine", suffix = "t9")
        startViewModel()
        useModel()
        useSketchMode(SketchMode.Fine)
        chooseFromHistory(parent)
        settle("the parent's description to be the one on screen") {
            vm().state.value.prompt == parent.originalInput
        }

        promptFor(CHILD_DESCRIPTION)
        useSketchMode(SketchMode.Coarse)
        vm().draw()
        val child = awaitNewestAfter(1)

        assertEquals("description_edit", edgeOf(child)?.derivationKind)
    }

    private companion object {
        const val STAGE_MODEL = "test-stage-model"
        const val PARENT_DESCRIPTION = "親となる作品 青い鉛筆の線を12本、波打つ軌跡に沿って散らす"
        const val OLD_DESCRIPTION = "写生より前に描かれた作品 緑の四角を12個、散らす"
        const val CHILD_DESCRIPTION = "赤い円を5個、横に並べる"
        const val PARENT_PROSE = "線がある。線は青い。線は波打つ。"
        const val PARENT_CANVAS = "square"
        const val TIMEOUT_MS = 120_000L
        const val POLL_MS = 200L
        const val SETTLE_AFTER_CLEAR_MS = 500L
    }
}
