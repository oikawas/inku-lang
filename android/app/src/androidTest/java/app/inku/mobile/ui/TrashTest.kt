package app.inku.mobile.ui

import android.app.Application
import androidx.activity.ComponentActivity
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
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
import app.inku.mobile.data.refinement.PaintSeeds
import app.inku.mobile.ui.i18n.InkuStringsJa
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The trash (D-2), as web and the server keep it: a work moved there leaves the
 * works and keeps its lineage node, comes back with 復元, and only a work in the
 * trash can be deleted for good, which leaves a tombstone.
 */
@RunWith(AndroidJUnit4::class)
class TrashTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository
    private lateinit var application: Application
    private var viewModel: InkuViewModel? = null
    private var store: ViewModelStore? = null

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

    @After
    fun tearDown() = runBlocking {
        store?.let { withContext(Dispatchers.Main) { it.clear() } }
        repository.close()
        delay(300)
        database.close()
    }

    private fun paintWork(description: String): HistoryItemEntity = runBlocking {
        repository.renderFromScore(
            description = description,
            scoreJson = score,
            catalogId = "ink_season",
            canvasAspect = "square",
            stage1ModelId = "s1",
            stage2ModelId = "s2",
            seeds = PaintSeeds(renderSeed = 4242L),
        )
    }

    private fun vm(): InkuViewModel = requireNotNull(viewModel) { "showLineage() was not called" }

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

    private fun await(what: String, condition: () -> Boolean) {
        try {
            composeTestRule.waitUntil(30_000) { condition() }
        } catch (timeout: Throwable) {
            throw AssertionError("timed out waiting for $what", timeout)
        }
    }

    private fun listed(id: String) = vm().historyItems.value.any { it.id == id }
    private fun inTrash(id: String) = vm().trashedItems.value.any { it.id == id }

    /** Trash and restore move the flag only: the node stays `active` throughout. */
    @Test
    fun aTrashedWorkLeavesTheWorksKeepsItsNodeAndComesBack() {
        val work = paintWork("赤い線を引く")
        showLineage()
        await("the work to be listed") { listed(work.id) }

        composeTestRule.runOnIdle { vm().trashWork(work) }
        await("the work to be in the trash") { !listed(work.id) && inTrash(work.id) }
        val node = runBlocking { database.lineageDao().getNodeById(requireNotNull(work.lineageNodeId)) }
        assertEquals("the lineage keeps the node", "active", node?.state)
        assertEquals(InkuStringsJa.workTrashed, vm().state.value.workNotice)

        composeTestRule.runOnIdle { vm().restoreWork(work.id) }
        await("the work to be back") { listed(work.id) && !inTrash(work.id) }
    }

    /** web limits 完全削除 to the trash (`require_trashed`); a listed work is not touched. */
    @Test
    fun onlyAWorkInTheTrashIsDeletedForGood() {
        val work = paintWork("青い円を置く")
        showLineage()
        await("the work to be listed") { listed(work.id) }

        composeTestRule.runOnIdle { vm().deleteWorkForGood(work.id) }
        Thread.sleep(1_000)
        assertNotNull("a work outside the trash is kept", runBlocking { repository.getHistoryById(work.id) })

        composeTestRule.runOnIdle { vm().trashWork(work) }
        await("the work to be in the trash") { inTrash(work.id) }
        composeTestRule.runOnIdle { vm().deleteWorkForGood(work.id) }
        await("the work to be gone") { runBlocking { repository.getHistoryById(work.id) } == null }
        val node = runBlocking { database.lineageDao().getNodeById(requireNotNull(work.lineageNodeId)) }
        assertEquals("the lineage keeps a tombstone in its place", "tombstone", node?.state)
    }

    /** The card's entry asks first, and the card then says where the work is. */
    @Test
    fun theLineageCardAsksThenMarksTheWork() {
        val work = paintWork("白い花びらが散る")
        showLineage()
        composeTestRule.runOnIdle { vm().selectHistory(work) }
        await("the pick") { vm().state.value.selectedHistory?.id == work.id }
        composeTestRule.runOnIdle { vm().setTab(AppTab.Lineage) }
        // Waited for on the tree, not on the state: the graph can be in the
        // state a frame before its cards are on the screen.
        await("the card's trash entry") {
            composeTestRule.onAllNodesWithTag(TRASH_ENTRY_TAG).fetchSemanticsNodes().isNotEmpty()
        }

        composeTestRule.onAllNodesWithTag(TRASH_ENTRY_TAG)[0].performClick()
        await("the question") {
            composeTestRule.onAllNodesWithText(InkuStringsJa.confirmTrash(1)).fetchSemanticsNodes().isNotEmpty()
        }
        composeTestRule.onNodeWithText(InkuStringsJa.confirmRun).performClick()

        // The mark is a text inside the card, which merges what it holds;
        // the unmerged tree is where its own tag is kept.
        await("the card to be marked") {
            composeTestRule.onAllNodesWithTag(LINEAGE_TRASHED_TAG, useUnmergedTree = true).fetchSemanticsNodes().size == 1
        }
        assertTrue("and it offers nothing to edit", composeTestRule.onAllNodesWithTag(TRASH_ENTRY_TAG).fetchSemanticsNodes().isEmpty())
        assertEquals("the work on screen is marked, not dropped", true, vm().state.value.selectedHistory?.trashed)
    }
}
