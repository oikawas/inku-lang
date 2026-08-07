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
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The screens declare where a drawing came from ([I-138]).
 *
 * `LineageWiringTest` next door drives `InkuRepository` directly, so it is
 * green whether or not any screen ever fills the declaration in -- and until
 * this contract, none did: seven call sites, none passing `lineage`, so every
 * node was written and no edge ever was. What is under test here is the wiring
 * from the view model down, which is why it runs on the device against a real
 * repository rather than as a truth table on the JVM.
 *
 * `SubmitDerivationKindTest` on the JVM covers the rule itself. It cannot stand
 * in for this: a rule nothing calls still passes its own table.
 *
 * Every kind is read back out of `lineage_edges`, never off the screen.
 */
@RunWith(AndroidJUnit4::class)
class LineageDeclarationWiringTest {

    /** Echoes the request, so that two descriptions stay two pictures. */
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

    /**
     * Started by each test rather than by `setUp`, because the startup restore
     * this contract has to see only happens when history already holds a row --
     * so the rows have to be in place before the view model exists.
     */
    private fun startViewModel() {
        // Held in a store: the view model starts work of its own that outlives a
        // test method, and only `clear()` cancels it. Left running, it goes on
        // reading a database the next test has already closed.
        val created = ViewModelStore()
        store = created
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                InkuViewModel(application, repositoryOverride = repository) as T
        }
        viewModel = ViewModelProvider(created, factory)[InkuViewModel::class.java]
        // `state` is shared with `WhileSubscribed`, and every drawing path reads
        // `state.value`. Without a collector it would stay at the initial
        // `InkuUiState()` and nothing set below would be seen.
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
        // `onCleared` closes the repository on the application scope; the
        // database goes last so that nothing is still reading it.
        delay(SETTLE_AFTER_CLEAR_MS)
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

    /** Read at failure time, so a timeout says which half of a condition was false. */
    private fun stateReport(): String {
        val state = viewModel?.state?.value ?: return "no view model"
        return "selectedHistory=${state.selectedHistory?.id} lineageDetached=${state.lineageDetached} " +
            "prompt=\"${state.prompt.take(24)}\" isDrawing=${state.isDrawing} message=\"${state.message}\""
    }

    private suspend fun useModel() {
        vm().setSelectedModel(STAGE_MODEL)
        settle("the model to reach the shared state") { vm().state.value.selectedModelId == STAGE_MODEL }
    }

    /** A setter's value arrives a hop later, because `state` is combined and shared. */
    private suspend fun promptFor(text: String) {
        vm().setPrompt(text)
        settle("the prompt to reach the shared state") { vm().state.value.prompt == text }
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

    /** Rows come back newest first (`created_at DESC`). */
    private suspend fun awaitNewestAfter(previous: Int): HistoryItemEntity =
        awaitSavedRuns(previous + 1).first()

    private suspend fun edgeOf(item: HistoryItemEntity): LineageEdgeEntity? =
        database.lineageDao().getEdgeByChildId(requireNotNull(item.lineageNodeId))

    private suspend fun countEdges(items: List<HistoryItemEntity>): Int =
        items.count { edgeOf(it) != null }

    /**
     * Puts a finished work in history without drawing it, so that a test can
     * start from a parent whose description, canvas ratio and render hash it
     * chose. Drawing the parent instead would tie the child's description to it:
     * `render_hash` is unique, so a second run that reached the same score is
     * refused, and `replay` -- the case where nothing changed -- could never be
     * reached at all.
     */
    private suspend fun seedParent(
        description: String = PARENT_DESCRIPTION,
        canvasAspect: String = PARENT_CANVAS,
    ): HistoryItemEntity {
        val now = System.currentTimeMillis()
        val nodeId = "seed-node-$now"
        val item = HistoryItemEntity(
            id = "seed-history-$now",
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
            renderHash = "seed-render-hash-$now",
            renderHashShort = "seedhash",
            colorCatalogId = "default",
            canvasAspect = canvasAspect,
            starred = false,
            trashed = false,
            elapsedMs = 0L,
            tokenMetadataJson = null,
            lineageNodeId = nodeId,
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

    private suspend fun awaitStartupRestore(seeded: HistoryItemEntity) {
        settle("the startup restore to put the seeded work on screen") {
            vm().state.value.selectedHistory?.id == seeded.id
        }
    }

    /** What web's `loadIterationItem` does: an explicit pick, which becomes a parent. */
    private suspend fun chooseFromHistory(item: HistoryItemEntity) {
        vm().selectHistory(item)
        settle("the pick to reach the shared state") {
            vm().state.value.selectedHistory?.id == item.id && !vm().state.value.lineageDetached
        }
    }

    // --- T-2: the wiring is real ---

    @Test
    fun t2_asecondDrawingIsSavedAsTheChildOfTheFirst() = runBlocking {
        startViewModel()
        useModel()
        promptFor(FIRST_DRAWING)
        vm().draw()
        val first = awaitSavedRuns(1).first()
        settle("the first run to finish") { !vm().state.value.isDrawing }

        promptFor(SECOND_DRAWING)
        vm().draw()
        val second = awaitNewestAfter(1)

        assertNull("the first drawing had nothing to descend from", edgeOf(first))
        val edge = edgeOf(second)
        assertNotNull("the second drawing was saved with no lineage edge at all", edge)
        assertEquals(first.lineageNodeId, edge!!.parentNodeId)
        assertEquals(second.lineageNodeId, edge.childNodeId)
    }

    // --- T-3: all four kinds this contract reaches ---

    @Test
    fun t3a_anEditedDescriptionWritesDescriptionEdit() = runBlocking {
        val parent = seedParent()
        startViewModel()
        useModel()
        awaitStartupRestore(parent)
        chooseFromHistory(parent)
        promptFor("記述を変えて描く 一")
        vm().draw()

        val child = awaitNewestAfter(1)

        assertEquals("description_edit", edgeOf(child)?.derivationKind)
    }

    @Test
    fun t3b_anEditedDdlWritesDdlEdit() = runBlocking {
        val parent = seedParent()
        startViewModel()
        useModel()
        awaitStartupRestore(parent)
        chooseFromHistory(parent)
        vm().setDdl("黒い太筆の線を3本、斜めに置く")
        settle("the edited DDL to reach the shared state") {
            vm().state.value.ddlEditedAfterGeneration && vm().state.value.ddl.isNotBlank()
        }
        vm().drawFromDdl()

        val child = awaitNewestAfter(1)

        assertEquals("ddl_edit", edgeOf(child)?.derivationKind)
    }

    @Test
    fun t3c_aChangedCanvasRatioWritesCanvasAspectChange() = runBlocking {
        val parent = seedParent()
        startViewModel()
        useModel()
        awaitStartupRestore(parent)
        chooseFromHistory(parent)
        // The description moves too. One edge, one cause: the ratio wins.
        promptFor("キャンバスを変えて描く 一")
        vm().setCanvasAspect(CHILD_CANVAS)
        settle("the canvas ratio to reach the shared state") {
            vm().state.value.selectedCanvasAspect == CHILD_CANVAS
        }
        vm().draw()

        val child = awaitNewestAfter(1)

        assertEquals("canvas_aspect_change", edgeOf(child)?.derivationKind)
    }

    @Test
    fun t3d_anUnchangedRedrawWritesReplay() = runBlocking {
        val parent = seedParent()
        startViewModel()
        useModel()
        awaitStartupRestore(parent)
        chooseFromHistory(parent)
        // Nothing is touched: the pick already put the parent's description and
        // canvas ratio in the state.
        settle("the parent's description to be the one on screen") {
            vm().state.value.prompt == parent.originalInput &&
                vm().state.value.selectedCanvasAspect == parent.canvasAspect
        }
        vm().draw()

        val child = awaitNewestAfter(1)

        assertEquals("replay", edgeOf(child)?.derivationKind)
    }

    // --- T-4: the paths that declare nothing ---

    @Test
    fun t4a_theBatchWritesNoEdges() = runBlocking {
        // Paired with T-2 on purpose: an implementation that always declares a
        // parent passes T-2 and fails here, one that never does passes here and
        // fails T-2.
        startViewModel()
        useModel()
        vm().setBatchText("赤い円を5個、横に並べる\n黒い太筆の線を3本、斜めに置く")
        settle("the batch text to reach the shared state") {
            vm().state.value.batchText.lines().size == 2
        }
        vm().runBatch()

        val saved = awaitSavedRuns(2)

        assertEquals("every batch line is a root of its own", 0, countEdges(saved))
    }

    @Test
    fun t4b_theDemoWritesNoEdges() = runBlocking {
        startViewModel()
        useModel()
        // A drawing first, so that there is a work on screen for the demo to
        // descend from. Without one the demo could declare a parent and this
        // would still be green, because there would be no parent to declare.
        promptFor(FIRST_DRAWING)
        vm().draw()
        awaitSavedRuns(1)
        settle("the first run to finish") { !vm().state.value.isDrawing }
        settle("the drawn work to be the one on screen") {
            vm().state.value.selectedHistory != null && !vm().state.value.lineageDetached
        }

        vm().startDemo()
        val saved = awaitSavedRuns(2)
        vm().stopDrawing()

        assertEquals("every demo cycle is a root of its own", 0, countEdges(saved))
    }

    // --- T-5: the startup restore is for display, not for descent ---

    @Test
    fun t5_theRestoredWorkIsNotAParentButAnExplicitPickIs() = runBlocking {
        val parent = seedParent()
        startViewModel()
        useModel()
        awaitStartupRestore(parent)

        promptFor(FIRST_DRAWING)
        vm().draw()
        val afterRestore = awaitNewestAfter(1)
        settle("the first run to finish") { !vm().state.value.isDrawing }

        assertNull(
            "opening the app and drawing must not descend from what was restored for display",
            edgeOf(afterRestore),
        )

        // The same work, this time chosen on purpose.
        chooseFromHistory(parent)
        promptFor(SECOND_DRAWING)
        vm().draw()
        val afterPick = awaitNewestAfter(2)

        assertEquals(parent.lineageNodeId, edgeOf(afterPick)?.parentNodeId)
    }

    // --- T-6: 「新しい起点にする」 ---

    @Test
    fun t6_detachingMakesTheNextSaveARootAndNotDetachingMakesItAChild() = runBlocking {
        val parent = seedParent()
        startViewModel()
        useModel()
        awaitStartupRestore(parent)

        chooseFromHistory(parent)
        vm().detachLineage()
        settle("the detach to reach the shared state") { vm().state.value.lineageDetached }
        promptFor(FIRST_DRAWING)
        vm().draw()
        val root = awaitNewestAfter(1)
        settle("the first run to finish") { !vm().state.value.isDrawing }

        assertNull("a detached run must write no edge", edgeOf(root))
        val rootNode = database.lineageDao().getNodeById(requireNotNull(root.lineageNodeId))
        assertEquals("a root is its own root", root.lineageNodeId, rootNode?.rootNodeId)

        // The other direction, in the same test: without detaching it descends.
        chooseFromHistory(parent)
        promptFor(SECOND_DRAWING)
        vm().draw()
        val child = awaitNewestAfter(2)

        assertNotNull("without detaching, the next save descends", edgeOf(child))
        val childNode = database.lineageDao().getNodeById(requireNotNull(child.lineageNodeId))
        assertEquals("the child inherits the parent's root", parent.lineageNodeId, childNode?.rootNodeId)
    }

    // --- T-7: the metadata a canvas change carries ---

    @Test
    fun t7_aCanvasChangeCarriesBothRatiosInCanonicalJson() = runBlocking {
        val parent = seedParent()
        startViewModel()
        useModel()
        awaitStartupRestore(parent)
        chooseFromHistory(parent)
        promptFor("キャンバスの記録 一")
        vm().setCanvasAspect(CHILD_CANVAS)
        settle("the canvas ratio to reach the shared state") {
            vm().state.value.selectedCanvasAspect == CHILD_CANVAS
        }
        vm().draw()

        val child = awaitNewestAfter(1)
        val edge = edgeOf(child)

        assertEquals("canvas_aspect_change", edge?.derivationKind)
        // Sorted keys, no separators: `LineagePlanner.canonicalJson`, which is
        // the server's `_canonical_json`.
        assertEquals(
            "{\"from_canvas_aspect\":\"$PARENT_CANVAS\",\"to_canvas_aspect\":\"$CHILD_CANVAS\"}",
            edge?.metadataJson,
        )
    }

    @Test
    fun t7b_aRunThatChangedNoRatioCarriesAnEmptyObject() = runBlocking {
        val parent = seedParent()
        startViewModel()
        useModel()
        awaitStartupRestore(parent)
        chooseFromHistory(parent)
        promptFor("記述だけ変えて描く 一")
        vm().draw()

        val child = awaitNewestAfter(1)
        val edge = edgeOf(child)

        assertEquals("description_edit", edge?.derivationKind)
        assertTrue(
            "a run that moved no ratio must record no ratios, got ${edge?.metadataJson}",
            edge?.metadataJson == "{}",
        )
    }

    private companion object {
        /** Not provider-qualified, so Stage 1 and Stage 2 may fall back locally. */
        const val STAGE_MODEL = "test-stage-model"
        const val PARENT_DESCRIPTION = "親となる作品 青い鉛筆の線を12本、波打つ軌跡に沿って散らす"

        // Two drawings inside one test have to be two pictures. `upsert` is
        // `@Insert(onConflict = REPLACE)` over a unique `render_hash`, so a
        // second run that reached the same score replaces the first row instead
        // of adding one, and a test waiting for two rows waits forever while
        // every run reports success. Prose carrying no drawing vocabulary all
        // lands on the same score, so these two name shapes, counts and colours.
        const val FIRST_DRAWING = "赤い円を5個、横に並べる"
        const val SECOND_DRAWING = "黒い太筆の線を3本、斜めに置く"
        const val PARENT_CANVAS = "square"
        const val CHILD_CANVAS = "pixel9_landscape_safe"
        const val TIMEOUT_MS = 120_000L
        const val POLL_MS = 200L
        const val SETTLE_AFTER_CLEAR_MS = 500L
    }
}
