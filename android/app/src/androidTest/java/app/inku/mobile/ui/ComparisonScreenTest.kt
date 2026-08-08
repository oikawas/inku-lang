package app.inku.mobile.ui

import android.app.Application
import androidx.activity.ComponentActivity
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
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
import app.inku.mobile.data.refinement.LanguageCombo
import app.inku.mobile.data.refinement.ModelCompareMode
import app.inku.mobile.data.refinement.PaintSeeds
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * T-11, T-12 and T-13 of 契約 android-compares-models-and-languages.
 *
 * The two inspections are driven here through the *shared* entry points --
 * `openRefinement` and `generateRefinementCandidates` -- and never through
 * anything of their own. That is what makes T-12 a check rather than a claim:
 * break either entry point and both halves of this class go red at once.
 */
@RunWith(AndroidJUnit4::class)
class ComparisonScreenTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository
    private lateinit var application: Application
    private var viewModel: InkuViewModel? = null
    private var store: ViewModelStore? = null

    private companion object {
        /** One stage call takes this long, so a run of four is still going. */
        const val STAGE_DELAY_MS = 3_000L
        /** Long enough that an uninterrupted run would have called again. */
        const val WATCH_AFTER_CHANGE_MS = 9_000L
    }

    /**
     * Slow enough that a run can be caught while it is still going, and it
     * counts: whether a run really stopped is a question about work, and a busy
     * flag can be lowered while the coroutine behind it keeps drawing.
     */
    private class SlowModel(private val delayMs: Long) : ModelProvider {
        override val providerId: String = "test-slow"
        @Volatile
        var calls: Int = 0

        override suspend fun generate(request: ModelRequest): ModelResponse {
            delay(delayMs)
            calls += 1
            return ModelResponse(text = "細い線を五本、中央付近に置く。", modelId = request.modelId)
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

    @After
    fun tearDown() = runBlocking {
        store?.let { withContext(Dispatchers.Main) { it.clear() } }
        repository.close()
        delay(300)
        database.close()
    }

    private fun vm(): InkuViewModel = requireNotNull(viewModel) { "showLineage() was not called" }

    private fun useSlowModel(delayMs: Long): SlowModel {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        runBlocking { repository.close() }
        val model = SlowModel(delayMs)
        repository = InkuRepository(context, database, modelProviderOverride = model)
        return model
    }

    private fun paintWork(description: String): HistoryItemEntity = runBlocking {
        repository.renderFromScore(
            description = description,
            scoreJson = score,
            catalogId = "ink_season",
            canvasAspect = "square",
            stage1ModelId = "target-s1",
            stage2ModelId = "target-s2",
            seeds = PaintSeeds(renderSeed = 4242L),
        )
    }

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

    private fun awaitState(what: String, condition: (InkuUiState) -> Boolean) {
        try {
            composeTestRule.waitUntil(30_000) { condition(vm().state.value) }
        } catch (timeout: Throwable) {
            val state = vm().state.value
            throw AssertionError(
                "timed out waiting for $what; open=${state.refinementOpen} view=${state.refinementSubview} " +
                    "busy=${state.refinementBusy} candidates=${state.refinementCandidates.size} " +
                    "status=${state.refinementStatus}",
                timeout,
            )
        }
    }

    private fun nodesWithTag(tag: String): Int {
        composeTestRule.mainClock.advanceTimeByFrame()
        composeTestRule.waitForIdle()
        return composeTestRule.onAllNodesWithTag(tag).fetchSemanticsNodes().size
    }

    // ── T-12: one skeleton, two comparisons ───────────────────

    /**
     * A model comparison, run through the refinement's own entry points. Nothing
     * in this test names a model-specific function.
     */
    @Test
    fun t12_aModelComparisonRunsThroughTheRefinementEntryPoints() {
        val work = paintWork("赤い線を引く")
        showLineage()
        composeTestRule.runOnIdle {
            vm().openRefinement(work, RefinementSubview.Model)
            vm().setModelCompareMode(ModelCompareMode.Common)
            vm().toggleModelCompareSelection("cmp-model")
            vm().generateRefinementCandidates()
        }
        awaitState("one model candidate") { it.refinementCandidates.size == 1 && !it.refinementBusy }

        val candidate = vm().state.value.refinementCandidates.first()
        assertEquals("model_comparison", candidate.plan.derivationKind)
        assertEquals("cmp-model", candidate.stage1Model)
        assertEquals("cmp-model", candidate.stage2Model)
    }

    /** The same entry points again, for the other comparison. */
    @Test
    fun t12_aLanguageComparisonRunsThroughTheSameEntryPoints() {
        val work = paintWork("夕暮れの水面に細い線を五本引く")
        showLineage()
        composeTestRule.runOnIdle {
            vm().openRefinement(work, RefinementSubview.Language)
            vm().toggleLanguageCombo(LanguageCombo("ja", "en").id)
            vm().generateRefinementCandidates()
        }
        awaitState("one language candidate") { it.refinementCandidates.size == 1 && !it.refinementBusy }

        val candidate = vm().state.value.refinementCandidates.first()
        assertEquals("language_comparison", candidate.plan.derivationKind)
        assertEquals("ja", candidate.plan.stage1Lang)
        assertEquals("en", candidate.plan.stage2Lang)
        assertEquals("en", candidate.instructionLangResolved)
    }

    /** 「比較対象はユーザーが明示的に選び、未選択モデルをfallback実行しない」. */
    @Test
    fun t12_anEmptyModelSelectionDrawsNothingAndSaysSo() {
        val work = paintWork("赤い線を引く")
        showLineage()
        composeTestRule.runOnIdle {
            vm().openRefinement(work, RefinementSubview.Model)
            vm().generateRefinementCandidates()
        }
        awaitState("the refusal") { it.refinementStatus == MODEL_SELECT_PROMPT }
        assertTrue("nothing was drawn", vm().state.value.refinementCandidates.isEmpty())
        assertFalse("and nothing is running", vm().state.value.refinementBusy)
    }

    /** 「1組も選ばずに実行すると案内文を出して止まる」(`state.svelte.ts:398-401`). */
    @Test
    fun t12_anEmptyLanguageSelectionDrawsNothingAndSaysSo() {
        val work = paintWork("夕暮れの水面")
        showLineage()
        composeTestRule.runOnIdle {
            vm().openRefinement(work, RefinementSubview.Language)
            vm().generateRefinementCandidates()
        }
        awaitState("the refusal") { it.refinementStatus == LANGUAGE_SELECT_PROMPT }
        assertTrue("nothing was drawn", vm().state.value.refinementCandidates.isEmpty())
    }

    /** The target's own pair cannot be selected, so it cannot be run. */
    @Test
    fun t12_theTargetsOwnLanguagePairCannotBeSelected() {
        val work = paintWork("夕暮れの水面")
        showLineage()
        composeTestRule.runOnIdle {
            vm().openRefinement(work, RefinementSubview.Language)
            vm().toggleLanguageCombo(LanguageCombo("ja", "ja").id)
        }
        awaitState("the refusal") { it.refinementStatus == LANGUAGE_COMBO_BLOCKED }
        assertTrue("nothing was selected", vm().state.value.languageCompareSelectedCombos.isEmpty())
    }

    // ── T-11: the target changes ──────────────────────────────

    /**
     * 「対象作品変更時は結果を破棄し、進行中の要求を中断する」(SPEC `:2143`).
     *
     * A comparison is started on one work and the target is moved to another
     * while it runs: the run stops and the candidates go with it.
     */
    @Test
    fun t11_changingTheTargetStopsTheRunAndDropsTheResults() {
        val first = paintWork("赤い線を引く")
        val model = useSlowModel(STAGE_DELAY_MS)
        val second = paintWork("青い円を置く")
        showLineage()
        composeTestRule.runOnIdle {
            vm().openRefinement(first, RefinementSubview.Model)
            vm().toggleModelCompareSelection("cmp-one")
            vm().toggleModelCompareSelection("cmp-two")
            vm().generateRefinementCandidates()
        }
        awaitState("the comparison to be running") { it.refinementBusy }
        // Two candidates, two stages each: the run is four calls long, and it is
        // caught after the first one.
        composeTestRule.waitUntil(30_000) { model.calls >= 1 }

        composeTestRule.runOnIdle { vm().openRefinement(second, RefinementSubview.Model) }
        val callsAtChange = model.calls

        // What is read is the work, not the flag: a run left to finish would
        // keep asking the model long after `refinementBusy` went down.
        Thread.sleep(WATCH_AFTER_CHANGE_MS)
        assertEquals(
            "the run kept drawing after the target changed; it was not interrupted",
            callsAtChange,
            model.calls,
        )

        val state = vm().state.value
        assertFalse("nothing is running", state.refinementBusy)
        assertEquals("the new target is the one on screen", second.id, state.refinementParent?.id)
        assertTrue("the old work's candidates are gone", state.refinementCandidates.isEmpty())
        assertTrue("and the old selection with them", state.modelCompareSelectedModels.isEmpty())
    }

    // ── T-13: the lineage card's menu ─────────────────────────

    /**
     * 「描画要素・記述・DDL・モデル・言語・…」(SPEC `:618`). Three of the seven are
     * built; they appear in that order, each opens its own sub-view with the
     * card's work as the target, and closing goes back to the lineage.
     */
    @Test
    fun t13_theCardMenuOpensEachSubViewAndComesBack() {
        val work = paintWork("赤い線を引く")
        showLineage()
        // The graph is read when the lineage tab is opened on a picked work,
        // the way `openLineageOn` in LineageScreenTest opens it.
        composeTestRule.runOnIdle { vm().selectHistory(work) }
        awaitState("the pick to reach the shared state") { it.selectedHistory?.id == work.id }
        composeTestRule.runOnIdle { vm().setTab(AppTab.Lineage) }
        awaitState("the lineage to be drawn") { it.lineageGraph != null }

        assertEquals("描画要素 is on the card", 1, nodesWithTag(REFINE_ENTRY_TAG))
        assertEquals("モデル is on the card", 1, nodesWithTag(MODEL_ENTRY_TAG))
        assertEquals("言語 is on the card", 1, nodesWithTag(LANGUAGE_ENTRY_TAG))

        composeTestRule.onAllNodesWithTag(MODEL_ENTRY_TAG)[0].performClick()
        awaitState("the model sub-view") {
            it.refinementOpen && it.refinementSubview == RefinementSubview.Model
        }
        assertEquals("with the card's work as the target", work.id, vm().state.value.refinementParent?.id)

        composeTestRule.runOnIdle { vm().closeRefinement() }
        awaitState("the lineage again") { !it.refinementOpen }
        assertEquals("still on the lineage screen", AppTab.Lineage, vm().state.value.tab)
        assertEquals("and the card is back", 1, nodesWithTag(LANGUAGE_ENTRY_TAG))

        composeTestRule.onAllNodesWithTag(LANGUAGE_ENTRY_TAG)[0].performClick()
        awaitState("the language sub-view") {
            it.refinementOpen && it.refinementSubview == RefinementSubview.Language
        }
        assertEquals("with the card's work as the target", work.id, vm().state.value.refinementParent?.id)

        composeTestRule.runOnIdle { vm().closeRefinement() }
        awaitState("the lineage again") { !it.refinementOpen }
        composeTestRule.onAllNodesWithTag(REFINE_ENTRY_TAG)[0].performClick()
        awaitState("the adjust sub-view") {
            it.refinementOpen && it.refinementSubview == RefinementSubview.Adjust
        }
    }

    /** The sub-view chips switch the same panel rather than opening another one. */
    @Test
    fun t13_theSubViewChipsSwitchOnePanel() {
        val work = paintWork("赤い線を引く")
        showLineage()
        composeTestRule.runOnIdle { vm().openRefinement(work, RefinementSubview.Adjust) }
        awaitState("the panel") { it.refinementOpen }

        RefinementSubview.entries.forEach { subview ->
            assertEquals("the ${subview.id} chip is there", 1, nodesWithTag(refinementSubviewTag(subview)))
        }

        composeTestRule.onAllNodesWithTag(refinementSubviewTag(RefinementSubview.Language))[0].performClick()
        awaitState("the language sub-view") { it.refinementSubview == RefinementSubview.Language }
        assertEquals("the target did not change", work.id, vm().state.value.refinementParent?.id)
    }
}
