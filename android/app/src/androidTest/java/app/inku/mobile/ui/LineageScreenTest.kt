package app.inku.mobile.ui

import app.inku.mobile.ui.i18n.InkuStringsJa
import android.app.Application
import androidx.activity.ComponentActivity
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
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
import app.inku.mobile.data.model.DerivationKindRegistry
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import java.io.File
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The lineage screen shows the real graph and reaches the view model.
 *
 * `LineageGraphReferenceTest` on the JVM covers the graph function against the
 * baked server output; it says nothing about whether any screen draws it. What
 * is under test here is everything below that: the DAO queries this contract
 * added, the gathering in `InkuRepository.loadLineage`, and the two things the
 * screen sends back -- opening a node and starting a new root.
 *
 * The labels are read off the screen and compared with
 * [InkuStrings.derivationLabel], so a screen that wrote its own wording is
 * red here even when it wrote the same words the registry holds today.
 *
 * Nothing here runs inside `runBlocking` except the database calls. Wrapping a
 * whole test in it looks harmless and is not: the composition then never
 * recomposes, every assertion reads the screen as it was at `setContent`, and a
 * screen showing "保存すると、ここに系譜が表示されます。" passes any test that only
 * looks at the view model. `waitUntil` drives the clock instead.
 */
@RunWith(AndroidJUnit4::class)
class LineageScreenTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

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
    private val generatedThumbnailHashes = mutableSetOf<String>()

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        application = context.applicationContext as Application
        database = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        repository = InkuRepository(context, database, modelProviderOverride = EchoModel)
    }

    @After
    fun tearDown() = runBlocking {
        viewModel?.stopDrawing()
        // Held in a store: the view model starts work of its own that outlives a
        // test method, and only `clear()` cancels it. Left running, it goes on
        // reading a database the next test has already closed.
        store?.let { withContext(Dispatchers.Main) { it.clear() } }
        delay(SETTLE_AFTER_CLEAR_MS)
        // Closing it here as well is what makes the wait above a belt rather
        // than the guarantee: this one blocks until the scheduled thumbnail
        // write is on disk, so the close below cannot land on top of it.
        repository.close()
        generatedThumbnailHashes.forEach { renderHash ->
            File(application.filesDir, "thumbnails/$renderHash.webp").delete()
        }
        generatedThumbnailHashes.clear()
        database.close()
    }

    private fun vm(): InkuViewModel = requireNotNull(viewModel) { "showLineage() was not called" }

    /**
     * Builds the view model and puts the real screen on it.
     *
     * Composing is what subscribes to `state`, which is shared with
     * `WhileSubscribed`: without a collector it would stay at the initial
     * `InkuUiState()` and nothing set below would be seen.
     */
    private fun showLineage() {
        val created = ViewModelStore()
        store = created
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                InkuViewModel(application, repositoryOverride = repository) as T
        }
        viewModel = ViewModelProvider(created, factory)[InkuViewModel::class.java]
        composeTestRule.setContent {
            val state by vm().state.collectAsState()
            LineageScreen(state, vm())
        }
    }

    // --- helpers ---

    /** A setter's value arrives a hop later, because `state` is combined and shared. */
    private fun awaitState(what: String, condition: (InkuUiState) -> Boolean) {
        try {
            composeTestRule.waitUntil(TIMEOUT_MS) { condition(vm().state.value) }
        } catch (timeout: Throwable) {
            val state = vm().state.value
            throw AssertionError(
                "timed out waiting for $what; selected=${state.selectedHistory?.id} " +
                    "detached=${state.lineageDetached} loading=${state.lineageLoading} " +
                    "nodes=${state.lineageGraph?.nodes?.size} tab=${state.tab}",
                timeout,
            )
        }
    }

    private fun savedRows(): List<HistoryItemEntity> =
        runBlocking { database.historyDao().listActive(20, 0).first() }

    /** Rows come back newest first (`created_at DESC`). */
    private fun awaitNewestAfter(previous: Int): HistoryItemEntity {
        try {
            composeTestRule.waitUntil(TIMEOUT_MS) { savedRows().size > previous }
        } catch (timeout: Throwable) {
            throw AssertionError("timed out waiting for a drawing to be saved", timeout)
        }
        return savedRows().first()
    }

    private fun edgeOf(item: HistoryItemEntity): LineageEdgeEntity? = runBlocking {
        database.lineageDao().getEdgeByChildId(requireNotNull(item.lineageNodeId))
    }

    /** One row of history plus its lineage node, with no drawing to produce it. */
    private suspend fun seedWork(
        suffix: String,
        at: Long,
        description: String,
        parentNodeId: String? = null,
        derivationKind: String? = null,
    ): HistoryItemEntity {
        val nodeId = "node-$suffix"
        val item = HistoryItemEntity(
            id = "history-$suffix",
            createdAt = at,
            updatedAt = at,
            originalInput = description,
            normalizedDdl = description,
            expandedDdl = null,
            scoreJson = "{}",
            displaySvg = "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
            stage1Model = STAGE_MODEL,
            stage2Model = STAGE_MODEL,
            renderMetadataJson = "{}",
            renderHash = "render-hash-$suffix",
            renderHashShort = suffix.takeLast(4),
            colorCatalogId = "default",
            canvasAspect = "square",
            starred = false,
            trashed = false,
            elapsedMs = 0L,
            tokenMetadataJson = null,
            lineageNodeId = nodeId,
        )
        database.historyDao().insert(item)
        database.lineageDao().insertNode(
            LineageNodeEntity(
                id = nodeId,
                historyId = item.id,
                state = "active",
                descriptionHash = "dh1:$suffix",
                renderHash = item.renderHash,
                at = at,
                rootNodeId = if (parentNodeId == null) nodeId else "node-root",
            ),
        )
        if (parentNodeId != null && derivationKind != null) {
            database.lineageDao().insertEdge(
                LineageEdgeEntity(
                    id = "edge-$suffix",
                    parentNodeId = parentNodeId,
                    childNodeId = nodeId,
                    derivationKind = derivationKind,
                    metadataJson = "{}",
                    at = at,
                ),
            )
        }
        return item
    }

    /** Root -> child -> grandchild, two edges of two different kinds. */
    private fun seedThreeGenerations(): Triple<HistoryItemEntity, HistoryItemEntity, HistoryItemEntity> =
        runBlocking {
            val root = seedWork("root", 1_000L, ROOT_DESCRIPTION)
            val child = seedWork("child", 2_000L, CHILD_DESCRIPTION, "node-root", FIRST_KIND)
            val grand = seedWork("grand", 3_000L, GRAND_DESCRIPTION, "node-child", SECOND_KIND)
            Triple(root, child, grand)
        }

    /**
     * Waits for the screen, not for the view model.
     *
     * `waitUntil` re-checks after each frame it drives, so a condition that is
     * already true when it is called drives no frames at all. Waiting on
     * `state.value` therefore returns before the composition has read the new
     * state, and every assertion after it looks at the screen as it was.
     */
    private fun awaitCards(count: Int) {
        try {
            composeTestRule.waitUntil(TIMEOUT_MS) {
                composeTestRule.onAllNodesWithTag(LINEAGE_NODE_TAG).fetchSemanticsNodes().size == count
            }
        } catch (timeout: Throwable) {
            val shown = composeTestRule.onAllNodesWithTag(LINEAGE_NODE_TAG).fetchSemanticsNodes().size
            throw AssertionError(
                "timed out waiting for $count cards on screen; showing $shown, " +
                    "state holds ${vm().state.value.lineageGraph?.nodes?.size} nodes",
                timeout,
            )
        }
    }

    private fun openLineageOn(item: HistoryItemEntity, cards: Int) {
        vm().selectHistory(item)
        awaitState("the pick to reach the shared state") { it.selectedHistory?.id == item.id }
        vm().setTab(AppTab.Lineage)
        awaitState("the graph to be read") { it.lineageGraph != null }
        awaitCards(cards)
    }

    private fun useModelAndPrompt(text: String) {
        vm().setSelectedModel(STAGE_MODEL)
        awaitState("the model to reach the shared state") { it.selectedModelId == STAGE_MODEL }
        vm().setPrompt(text)
        awaitState("the prompt to reach the shared state") { it.prompt == text }
    }

    // --- T-5: the screen is real ---

    @Test
    fun t5_threeGenerationsAppearWithTheRegistrysLabels() {
        val (_, _, grand) = seedThreeGenerations()
        showLineage()
        openLineageOn(grand, cards = 3)

        val graph = requireNotNull(vm().state.value.lineageGraph)
        assertEquals("three nodes were read", 3, graph.nodes.size)
        assertEquals("two edges were read", 2, graph.edges.size)

        // And three cards are on screen, not merely three rows in the state.
        composeTestRule.onAllNodesWithTag(LINEAGE_NODE_TAG).assertCountEquals(3)

        // The two edges, named on the cards they point at. Compared with the
        // registry rather than with a literal: a screen that invented its own
        // wording fails even if it happens to agree today.
        composeTestRule.onNodeWithText(InkuStringsJa.derivationLabel(FIRST_KIND)).assertIsDisplayed()
        composeTestRule.onNodeWithText(InkuStringsJa.derivationLabel(SECOND_KIND)).assertIsDisplayed()
        // And the node no edge points at, which the registry answers for too.
        composeTestRule.onNodeWithText(InkuStringsJa.derivationOrigin).assertIsDisplayed()

        // The generation is the depth from the root, and it is on the cards.
        composeTestRule.onNodeWithText("第1世代").assertIsDisplayed()
        composeTestRule.onNodeWithText("第3世代").assertIsDisplayed()
    }

    // --- T-6: picking a node opens the work and drops the detach ---

    @Test
    fun t6_pickingANodeOpensThatWorkAndTheNextSaveDescendsFromIt() {
        val (root, _, grand) = seedThreeGenerations()
        showLineage()

        // Started from the state the app really opens in: the newest work is
        // restored for display with the detach raised (InkuViewModel.kt:240).
        // That is the only state holding a graph and a raised detach at once --
        // `detachLineage` drops the work, and web drops the graph with it.
        awaitState("the startup restore to put the newest work on screen") {
            it.selectedHistory?.id == grand.id
        }
        assertTrue("the restore raises the detach", vm().state.value.lineageDetached)

        vm().setTab(AppTab.Lineage)
        awaitState("the graph to be read") { it.lineageGraph != null }
        awaitCards(3)

        // The root card names itself: it is the one node no edge points at.
        composeTestRule.onNodeWithText(InkuStringsJa.derivationOrigin).performClick()
        awaitState("the tap to open the root") { it.selectedHistory?.id == root.id }

        assertFalse("picking a node drops the detach", vm().state.value.lineageDetached)
        assertEquals("the reader is still looking at the lineage", AppTab.Lineage, vm().state.value.tab)
        awaitState("the graph to re-centre, the way web's openLineageNode refetches") {
            it.lineageGraph?.focusNodeId == root.lineageNodeId
        }

        // The next save descends from what was tapped. Read out of
        // `lineage_edges`, never off the screen.
        useModelAndPrompt(FIRST_DRAWING)
        vm().draw()
        val saved = awaitNewestAfter(3)

        val edge = edgeOf(saved)
        assertNotNull("the save after a pick must write an edge", edge)
        assertEquals(root.lineageNodeId, edge?.parentNodeId)
    }

    // --- T-7: 「新しい起点にする」 reaches the view model from this screen ---

    @Test
    fun t7_startingANewRootReachesTheViewModelFromTheScreen() {
        val (_, _, grand) = seedThreeGenerations()
        showLineage()
        openLineageOn(grand, cards = 3)

        assertFalse("the pick left it attached", vm().state.value.lineageDetached)
        assertNotNull("the work is on screen", vm().state.value.selectedHistory)
        composeTestRule.onAllNodesWithTag(LINEAGE_NODE_TAG).assertCountEquals(3)

        composeTestRule.onNodeWithText(DETACH_LABEL).performClick()
        awaitState("the detach to reach the shared state") { it.lineageDetached }

        assertNull("web's detachLineage drops the work too", vm().state.value.selectedHistory)
        assertNull("and the graph with it", vm().state.value.lineageGraph)

        // The next save is a root: read out of `lineage_edges`, never off screen.
        useModelAndPrompt(FIRST_DRAWING)
        vm().draw()
        val saved = awaitNewestAfter(3)
        assertNull("a detached run must write no edge", edgeOf(saved))
    }

    // --- T-8: a lineage card edits its saved DDL and returns on the child ---

    @Test
    fun t8_ddlActionEditsTheCardAndRefocusesTheSavedChild() {
        val (root, _, grand) = seedThreeGenerations()
        showLineage()
        openLineageOn(grand, cards = 3)
        useModelAndPrompt(grand.originalInput)

        val ddlActions = composeTestRule.onAllNodesWithTag(DDL_ENTRY_TAG)
        ddlActions.assertCountEquals(3)
        ddlActions[0].performClick()
        awaitState("the card DDL action to open the saved work") {
            it.ddlEditorOpen && it.selectedHistory?.id == root.id
        }
        assertEquals(root.normalizedDdl, vm().state.value.ddl)
        assertEquals(AppTab.Lineage, vm().state.value.tab)

        vm().setDdl(EDITED_DDL)
        awaitState("the edited DDL to reach shared state") {
            it.ddl == EDITED_DDL && it.ddlEditedAfterGeneration
        }
        vm().closeDdlEditor()
        vm().drawFromDdl()
        val saved = awaitNewestAfter(3)
        generatedThumbnailHashes += saved.renderHash

        assertEquals(root.lineageNodeId, edgeOf(saved)?.parentNodeId)
        assertEquals("ddl_edit", edgeOf(saved)?.derivationKind)
        awaitState("the saved child to become the selected work") {
            it.selectedHistory?.id == saved.id && it.tab == AppTab.Lineage
        }
        awaitState("the lineage to refocus on the saved child") {
            it.lineageGraph?.let { graph ->
                graph.focusNodeId == saved.lineageNodeId &&
                    graph.nodes.any { node -> node.id == saved.lineageNodeId } &&
                    graph.nodes.any { node -> node.id == root.lineageNodeId }
            } == true
        }
    }

    private companion object {
        const val STAGE_MODEL = "gpt-4o-mini"
        const val ROOT_DESCRIPTION = "赤い円を5個、横に並べる"
        const val CHILD_DESCRIPTION = "黒い太筆の線を3本、斜めに置く"
        const val GRAND_DESCRIPTION = "青い三角を2つ、上に重ねる"
        const val FIRST_DRAWING = "緑の四角を4つ、下に敷く"
        const val EDITED_DDL = "紫の線を2本、中央に並べる"
        const val FIRST_KIND = "description_edit"
        const val SECOND_KIND = "ddl_edit"
        const val DETACH_LABEL = "新しい起点にする"
        const val TIMEOUT_MS = 120_000L
        const val SETTLE_AFTER_CLEAR_MS = 500L
    }
}
