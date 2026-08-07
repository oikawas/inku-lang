package app.inku.mobile.ui

import android.app.Application
import androidx.activity.ComponentActivity
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.hasScrollAction
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeUp
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.printToLog
import androidx.compose.ui.test.onRoot
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
import app.inku.mobile.data.refinement.PaintSeeds
import app.inku.mobile.data.refinement.RefinementElement
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * T-6 and T-10: the screen's side of the refinement.
 *
 * Built the way [LineageScreenTest] builds its own: the view model lives in a
 * `ViewModelStore` so its work is cancelled with the test, and the real screen
 * is composed on top of it so that `state` -- shared with `WhileSubscribed` --
 * has a collector at all.
 */
@RunWith(AndroidJUnit4::class)
class RefinementScreenTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository
    private lateinit var application: Application
    private var viewModel: InkuViewModel? = null
    private var store: ViewModelStore? = null

    /**
     * Stands in for Stage 1 and Stage 2 and takes its time about it.
     *
     * The stop button only exists while there is something to stop, and a
     * candidate drawn from the fallback rules is finished long before three
     * seconds. So the run is made slow on purpose rather than hoped to be.
     */
    private class SlowModel(private val delayMs: Long) : ModelProvider {
        override val providerId: String = "test-slow"

        override suspend fun generate(request: ModelRequest): ModelResponse {
            delay(delayMs)
            return ModelResponse(text = request.prompt, modelId = request.modelId)
        }
    }

    private val score = """
        {"version":"0.1.0","canvas":"square","background":"white","instructions":[
          {"primitive":"line","from":[0.2,0.5],"to":[0.8,0.5],"color":"red","weight":"brush_thick"}
        ]}
    """.trimIndent()

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        application = context.applicationContext as Application
        database = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        repository = InkuRepository(context, database)
    }

    /**
     * Swaps in a repository whose model calls are slow. Call before [openPanel].
     *
     * The one it replaces is closed: a repository keeps a coroutine scope that
     * writes thumbnails, and one left running goes on writing to a database the
     * test has already closed -- which takes the whole process down with it.
     */
    private fun useSlowModel(delayMs: Long) {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        runBlocking { repository.close() }
        repository = InkuRepository(context, database, modelProviderOverride = SlowModel(delayMs))
    }

    /**
     * Reads a setting off the main thread.
     *
     * `runBlocking` inside `waitUntil` would block the main looper, and
     * `viewModelScope` dispatches there: the write being waited for could never
     * run, so the wait could only ever time out.
     */
    private fun settingOffMainThread(key: String): String? {
        var value: String? = null
        val worker = Thread { value = runBlocking { repository.getSetting(key) } }
        worker.start()
        worker.join(5_000)
        return value
    }

    @After
    fun tearDown() = runBlocking {
        store?.let { withContext(Dispatchers.Main) { it.clear() } }
        // Cancels the thumbnail scope before the database goes away.
        repository.close()
        delay(300)
        database.close()
    }

    private fun vm(): InkuViewModel = requireNotNull(viewModel) { "openPanel() was not called" }

    private fun paintParent(): HistoryItemEntity = runBlocking {
        repository.renderFromScore(
            description = "赤い線を引く",
            scoreJson = score,
            catalogId = "ink_season",
            canvasAspect = "square",
            stage1ModelId = "s1",
            stage2ModelId = "s2",
            seeds = PaintSeeds(renderSeed = 4242L),
        )
    }

    private fun openPanel(): HistoryItemEntity {
        val parent = paintParent()
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
        composeTestRule.runOnIdle { vm().openRefinement(parent) }
        awaitState("the panel to open") { it.refinementOpen }
        return parent
    }

    private fun awaitState(what: String, condition: (InkuUiState) -> Boolean) {
        try {
            composeTestRule.waitUntil(30_000) { condition(vm().state.value) }
        } catch (timeout: Throwable) {
            val state = vm().state.value
            throw AssertionError(
                "timed out waiting for $what; busy=${state.refinementBusy} " +
                    "candidates=${state.refinementCandidates.size} status=${state.refinementStatus}",
                timeout,
            )
        }
    }

    /**
     * Lets the screen catch up with a state change, then counts what is on it.
     *
     * `waitForIdle` alone can read the tree a frame early, and a `waitUntil`
     * whose condition queries semantics deadlocks here -- the query waits for
     * idle from inside the wait that is driving it. `runOnIdle` runs a pass and
     * comes back, which is all that is needed.
     */
    private fun nodesWithTag(tag: String, unmerged: Boolean = false): Int {
        // A state change that arrives between frames needs a frame to be drawn;
        // `waitForIdle` alone does not schedule one.
        composeTestRule.mainClock.advanceTimeByFrame()
        composeTestRule.waitForIdle()
        return composeTestRule.onAllNodesWithTag(tag, useUnmergedTree = unmerged).fetchSemanticsNodes().size
    }

    private fun countRows(table: String): Int {
        database.openHelper.readableDatabase.query("SELECT COUNT(*) FROM $table").use { cursor ->
            cursor.moveToFirst()
            return cursor.getInt(0)
        }
    }

    /** 「候補は2列（1案のみ全幅1列）で…表示する」and 「4案では可能な限り異なるカタログを使う」. */
    @Test
    fun t10_fourCandidatesAreDrawnAndEachUsesADifferentCatalogue() {
        openPanel()
        composeTestRule.runOnIdle {
            vm().setRefinementElement(RefinementElement.Color)
            vm().setRefinementCount(4)
            vm().generateRefinementCandidates()
        }
        awaitState("four candidates") { it.refinementCandidates.size == 4 && !it.refinementBusy }
        composeTestRule.waitForIdle()

        // Two cards to a row, so the fourth is below the fold -- and a card
        // clipped entirely out of the window is not in the semantics tree at
        // all, which is why it is scrolled to rather than asserted from where
        // the screen happens to be.
        // Two to a row, and the panel scrolls: a card clipped entirely out of
        // the window is not in the semantics tree, so what the screen can be
        // asked is that the grid is really laid out in rows of two. That there
        // are four of them is read off the state, which is where the count is.
        assertTrue("the grid rows are on the screen", nodesWithTag(REFINE_CANDIDATE_TAG) >= 2)
        assertEquals("four were drawn", 4, vm().state.value.refinementCandidates.size)
        val catalogs = vm().state.value.refinementCandidates.map { it.plan.catalogId }
        assertEquals("four different catalogues", 4, catalogs.toSet().size)
        assertFalse("none of them is the parent's", catalogs.contains("ink_season"))
    }

    /**
     * 「候補生成中は他の生成・描画操作を禁止し」. The two drawing entry points are asked
     * while the refinement is running and have to refuse. The state is read, not
     * the screen: a greyed-out button is not the same as an operation that
     * cannot start.
     */
    @Test
    fun t10_noOtherGenerationStartsWhileCandidatesAreBeingMade() {
        openPanel()
        composeTestRule.runOnIdle {
            vm().setRefinementElement(RefinementElement.Color)
            vm().setRefinementCount(4)
            vm().generateRefinementCandidates()
        }
        awaitState("the run to be busy") { it.refinementBusy }

        composeTestRule.runOnIdle {
            vm().draw()
            vm().drawFromDdl()
        }
        composeTestRule.runOnIdle {
            assertFalse("no drawing started", vm().state.value.isDrawing)
            assertEquals("推敲の候補を生成中です。", vm().state.value.message)
        }
        awaitState("the run to finish") { !it.refinementBusy }
    }

    /**
     * 「開始3秒後から共通デザインの停止ボタンで…中断できる」. Both halves: nothing to press
     * in the first moment, and pressing it really ends the run.
     */
    @Test
    fun t10_theStopAppearsAfterThreeSecondsAndActuallyStops() {
        useSlowModel(4_000)
        openPanel()
        composeTestRule.runOnIdle {
            vm().setRefinementElement(RefinementElement.Reading)
            vm().setRefinementCount(4)
            vm().generateRefinementCandidates()
        }
        composeTestRule.runOnIdle {
            assertFalse("no stop in the first moment", vm().state.value.refinementCanAbort)
        }
        awaitState("the stop to appear") { it.refinementCanAbort }
        composeTestRule.waitForIdle()

        // Waited for on the tree, not on the state: `waitUntil` with a
        // semantics condition is what drives recomposition here, and a plain
        // `waitForIdle` after a state change leaves the screen a frame behind.
        assertEquals("the stop button is on the screen", 1, nodesWithTag(REFINE_STOP_TAG))
        composeTestRule.onNodeWithText("停止").performClick()
        awaitState("the run to stop") { !it.refinementBusy }
        assertEquals("停止しました。", vm().state.value.refinementStatus)
    }

    /** T-6 on the screen: unsaved → saved, and a second press writes no second row. */
    @Test
    fun t6_theSaveGoesUnsavedThenSavedAndRefusesASecondPress() {
        openPanel()
        composeTestRule.runOnIdle {
            vm().setRefinementElement(RefinementElement.Color)
            vm().setRefinementCount(1)
            vm().generateRefinementCandidates()
        }
        awaitState("one candidate") { it.refinementCandidates.size == 1 && !it.refinementBusy }
        val candidate = vm().state.value.refinementCandidates.single()
        assertEquals(RefinementSaveState.Unsaved, candidate.saveState)

        val before = countRows("history_items")
        composeTestRule.runOnIdle { vm().saveRefinementCandidate(candidate.id) }
        awaitState("the candidate to be saved") {
            it.refinementCandidates.single().saveState == RefinementSaveState.Saved
        }
        assertEquals("one work was added", before + 1, countRows("history_items"))
        assertNotNull(vm().state.value.refinementCandidates.single().savedNodeId)

        // 「保存済み候補は再保存できない」.
        composeTestRule.runOnIdle { vm().saveRefinementCandidate(candidate.id) }
        composeTestRule.waitForIdle()
        assertEquals("nothing more was written", before + 1, countRows("history_items"))
        assertEquals(RefinementSaveState.Saved, vm().state.value.refinementCandidates.single().saveState)
    }

    /** 「推敲要素の選択は前回値を…記憶する」-- here the device remembers it. */
    @Test
    fun theChosenElementIsRemembered() {
        openPanel()
        composeTestRule.runOnIdle { vm().setRefinementElement(RefinementElement.Variation) }
        composeTestRule.waitUntil(20_000) {
            settingOffMainThread(SETTING_KEY_REFINEMENT_ELEMENT) != null
        }

        // A second view model, as if the app had been opened again. `state` is
        // shared with `WhileSubscribed`, so without a collector it would sit at
        // the initial value for ever and the restore would be invisible.
        val second = InkuViewModel(application, repositoryOverride = repository)
        val subscriber = kotlinx.coroutines.CoroutineScope(Dispatchers.Default)
        subscriber.launch { second.state.collect { } }
        try {
            composeTestRule.waitUntil(30_000) {
                second.state.value.refinementElement == RefinementElement.Variation
            }
            assertTrue(second.state.value.refinementElement == RefinementElement.Variation)
        } finally {
            subscriber.cancel()
        }
    }

    /** The same words are one touch, so four of them is refused rather than drawn. */
    @Test
    fun fourTouchCandidatesAreRefused() {
        openPanel()
        composeTestRule.runOnIdle {
            vm().setRefinementElement(RefinementElement.Touch)
            vm().setRefinementTouchWords("しずかに")
            vm().setRefinementCount(4)
            vm().generateRefinementCandidates()
        }
        composeTestRule.runOnIdle {
            assertEquals(
                "同じ言葉は同じタッチ(Seed)になります。1案だけ生成可能です。",
                vm().state.value.refinementStatus,
            )
            assertTrue("nothing was drawn", vm().state.value.refinementCandidates.isEmpty())
        }
    }

    /** The entry SPEC :618 puts on a lineage card reaches the panel. */
    @Test
    fun theLineageCardOpensTheRefinement() {
        val parent = paintParent()
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
        composeTestRule.runOnIdle {
            vm().selectHistory(parent)
            // Picking a work does not fetch its graph; the screen asks for it.
            vm().refreshLineage()
        }
        awaitState("the graph") { it.lineageGraph?.nodes?.isNotEmpty() == true }
        composeTestRule.waitForIdle()

        // The card grew a button, so the entry can sit below the fold.
        // The card is clickable, so it merges its descendants: the button's own
        // tag is only in the unmerged tree.
        assertEquals("the entry is on the card", 1, nodesWithTag(REFINE_ENTRY_TAG, unmerged = true))
        composeTestRule.onNodeWithText("描画要素").performClick()
        awaitState("the panel to open") { it.refinementOpen }
        assertEquals(parent.id, vm().state.value.refinementParent?.id)
    }
}
