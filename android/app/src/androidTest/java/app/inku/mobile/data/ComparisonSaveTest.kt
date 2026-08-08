package app.inku.mobile.data

import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.refinement.ComparisonPlanner
import app.inku.mobile.data.refinement.LanguageCombo
import app.inku.mobile.data.refinement.ModelCompareMode
import app.inku.mobile.data.refinement.RefinementParent
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.pipeline.WebDdlSpec
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * T-6, T-7, T-8, T-9 and T-10 of 契約 android-compares-models-and-languages.
 *
 * A real Room database on the device: the three new columns and the two new
 * lineage edges only exist as rows, and what each stage was handed is only
 * visible from where the model would have stood.
 */
@RunWith(AndroidJUnit4::class)
class ComparisonSaveTest {

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository
    private lateinit var provider: CapturingProvider

    /** Remembers which model each stage asked, and in which language. */
    private class CapturingProvider : ModelProvider {
        override val providerId: String = "test"
        val stage1Models = mutableListOf<String>()
        val stage2Models = mutableListOf<String>()
        val stage1Prompts = mutableListOf<String>()
        val stage2Prompts = mutableListOf<String>()

        override suspend fun generate(request: ModelRequest): ModelResponse {
            // Stage 2 is the call that carries the score tool; Stage 1 does not.
            if (request.tool == null) {
                stage1Models += request.modelId
                stage1Prompts += request.systemInstruction.orEmpty()
                return ModelResponse(text = "細い線を五本、中央付近に置く。", modelId = request.modelId)
            }
            stage2Models += request.modelId
            stage2Prompts += request.systemInstruction.orEmpty()
            return ModelResponse(text = "", modelId = request.modelId)
        }
    }

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        database = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        provider = CapturingProvider()
        repository = InkuRepository(context, database, modelProviderOverride = provider)
    }

    @After
    fun tearDown() = runBlocking {
        repository.close()
        // The thumbnail scope may already be inside a transaction when it is
        // cancelled; closing the database out from under it takes the whole
        // instrumentation process down, and every test after it with it.
        delay(300)
        database.close()
    }

    private fun rowOf(id: String): HistoryItemEntity = runBlocking { requireNotNull(repository.getHistoryById(id)) }

    private fun descriptionHashOf(nodeId: String?): String? {
        database.openHelper.readableDatabase
            .query("SELECT description_hash FROM lineage_nodes WHERE id = ?", arrayOf(nodeId))
            .use { cursor ->
                if (!cursor.moveToFirst()) return null
                return cursor.getString(0)
            }
    }

    private fun edges(): List<Pair<String, JSONObject>> {
        val found = mutableListOf<Pair<String, JSONObject>>()
        database.openHelper.readableDatabase
            .query("SELECT derivation_kind, metadata_json FROM lineage_edges")
            .use { cursor ->
                while (cursor.moveToNext()) {
                    found += cursor.getString(0) to JSONObject(cursor.getString(1))
                }
            }
        return found
    }

    private fun paint(
        description: String,
        instructionLang: String? = null,
        historyInput: String? = null,
        sourceText: String? = null,
    ): HistoryItemEntity = runBlocking {
        repository.paint(
            description = description,
            catalogId = "ink_season",
            canvasAspect = "square",
            stage1ModelId = "target-s1",
            stage2ModelId = "target-s2",
            historyInput = historyInput,
            instructionLang = instructionLang,
            sourceText = sourceText,
        )
    }

    // ── T-6: the two language columns ─────────────────────────

    /**
     * 「要求と解決は別の量」. `auto` is what was asked for and stays `auto` in its
     * own column; what it resolved to lands in the other. An implementation that
     * writes one value twice fails on the first assertion pair.
     */
    @Test
    fun t6_requestedAndResolvedAreTwoColumns() {
        val item = paint("a quiet river at dusk", instructionLang = "auto")
        val row = rowOf(item.id)

        assertEquals("auto", row.instructionLangRequested)
        assertEquals("en", row.instructionLangResolved)
        assertNotEquals(row.instructionLangRequested, row.instructionLangResolved)
    }

    /** The same two columns for a work that named its language outright. */
    @Test
    fun t6_anExplicitLanguageIsRecordedInBothColumns() {
        val japanese = rowOf(paint("夕暮れの水面", instructionLang = "ja").id)
        assertEquals("ja", japanese.instructionLangRequested)
        assertEquals("ja", japanese.instructionLangResolved)

        val english = rowOf(paint("dusk on the water", instructionLang = "en").id)
        assertEquals("en", english.instructionLangRequested)
        assertEquals("en", english.instructionLangResolved)
    }

    /** `auto` on Japanese prose resolves the other way; without this the pair above proves nothing. */
    @Test
    fun t6_autoResolvesJapaneseToo() {
        val row = rowOf(paint("夕暮れの水面に細い線を五本引く", instructionLang = "auto").id)

        assertEquals("auto", row.instructionLangRequested)
        assertEquals("ja", row.instructionLangResolved)
    }

    // ── T-7: source_text ──────────────────────────────────────

    /**
     * 「`source_text` if there is one, `input` if there is not, and the hash is
     * taken from whichever it was」(`db.py:2049-2051`, `:1835`).
     *
     * Two rows: one written by a batch line, which keeps its numbering in
     * `original_input` and the prose in `source_text`, and one written plainly,
     * which has no `source_text` at all. Their description hashes agree, which is
     * only possible if the read falls back to `original_input` for the second.
     */
    @Test
    fun t7_sourceTextIsStoredAndTheHashFollowsIt() {
        val batched = paint("赤い線を引く", historyInput = "#3 赤い線を引く", sourceText = "赤い線を引く")
        val plain = paint("赤い線を引く")

        val batchedRow = rowOf(batched.id)
        assertEquals("#3 赤い線を引く", batchedRow.originalInput)
        assertEquals("赤い線を引く", batchedRow.sourceText)

        val plainRow = rowOf(plain.id)
        assertEquals("赤い線を引く", plainRow.originalInput)
        assertNull("a row with no separate prose leaves the column empty", plainRow.sourceText)

        assertEquals(
            "the same prose hashes the same whether or not a line number precedes it",
            descriptionHashOf(plainRow.lineageNodeId),
            descriptionHashOf(batchedRow.lineageNodeId),
        )
    }

    /**
     * The control for the case above: two different proses hash differently, so
     * the agreement there is not an implementation that hashes a constant.
     */
    @Test
    fun t7_differentProseStillHashesDifferently() {
        val one = rowOf(paint("赤い線を引く", historyInput = "#1 赤い線を引く", sourceText = "赤い線を引く").id)
        val two = rowOf(paint("青い円を置く", historyInput = "#2 青い円を置く", sourceText = "青い円を置く").id)

        assertNotEquals(descriptionHashOf(one.lineageNodeId), descriptionHashOf(two.lineageNodeId))
    }

    // ── T-8: the three model comparison modes ─────────────────

    private fun parentFor(item: HistoryItemEntity) = RefinementParent.of(item, item.originalInput)

    private fun runModelComparison(mode: ModelCompareMode, fixed: String, model: String): Pair<String, String> {
        val parentItem = paint("赤い線を引く")
        provider.stage1Models.clear()
        provider.stage2Models.clear()
        val parent = parentFor(parentItem)
        val plan = ComparisonPlanner.modelPlan(mode, fixed, model, parent)
        runBlocking { repository.renderRefinementCandidate(parent, plan) }
        return provider.stage1Models.first() to provider.stage2Models.first()
    }

    /**
     * All three modes in one test, each read as the pair of models that actually
     * reached the two stages. A test of one mode alone passes an implementation
     * that swapped the two fixed ones.
     */
    @Test
    fun t8_eachModeSendsTheRightModelToEachStage() {
        assertEquals(
            "common sends the chosen model to both",
            "cmp-model" to "cmp-model",
            runModelComparison(ModelCompareMode.Common, fixed = "", model = "cmp-model"),
        )
        assertEquals(
            "stage1_fixed holds Stage 1 and compares Stage 2",
            "fix-model" to "cmp-model",
            runModelComparison(ModelCompareMode.Stage1Fixed, fixed = "fix-model", model = "cmp-model"),
        )
        assertEquals(
            "stage2_fixed compares Stage 1 and holds Stage 2",
            "cmp-model" to "fix-model",
            runModelComparison(ModelCompareMode.Stage2Fixed, fixed = "fix-model", model = "cmp-model"),
        )
    }

    /** 「対象作品と同一のStage 1/2組み合わせだけを禁止し」-- and nothing else. */
    @Test
    fun t8_onlyTheTargetsOwnPairIsBlocked() {
        val blocked = ComparisonPlanner.isModelChoiceBlocked(
            mode = ModelCompareMode.Common, fixedModel = "",
            model = "target-s1", targetStage1Model = "target-s1", targetStage2Model = "target-s2",
        )
        assertTrue("the target's own model is not a comparison", blocked)

        val stillSelectable = ComparisonPlanner.isModelChoiceBlocked(
            mode = ModelCompareMode.Stage1Fixed, fixedModel = "other",
            model = "target-s2", targetStage1Model = "target-s1", targetStage2Model = "target-s2",
        )
        assertEquals(
            "a model the target used is selectable when the pair differs",
            false,
            stillSelectable,
        )
    }

    // ── T-9: a language per stage ─────────────────────────────

    /**
     * The `ja:en` pair: Stage 1 is asked in Japanese and Stage 2 in English, in
     * one candidate. Passing Stage 1's language to Stage 2 makes the second
     * assertion fail while the first still holds.
     */
    @Test
    fun t9_thePairSendsADifferentLanguageToEachStage() {
        val parentItem = paint("夕暮れの水面に細い線を五本引く")
        provider.stage1Prompts.clear()
        provider.stage2Prompts.clear()
        val parent = parentFor(parentItem)
        val plan = ComparisonPlanner.languagePlan(LanguageCombo("ja", "en"), parent)

        runBlocking { repository.renderRefinementCandidate(parent, plan) }

        assertEquals(
            WebDdlSpec.buildStage1SystemPrompt(parent.description, "ja"),
            provider.stage1Prompts.first(),
        )
        assertEquals(WebDdlSpec.STAGE2_SYSTEM_PROMPT_EN, provider.stage2Prompts.first())
    }

    /** The mirror pair, so neither language is a constant. */
    @Test
    fun t9_theOtherPairIsTheOtherWayRound() {
        val parentItem = paint("夕暮れの水面に細い線を五本引く")
        provider.stage1Prompts.clear()
        provider.stage2Prompts.clear()
        val parent = parentFor(parentItem)
        val plan = ComparisonPlanner.languagePlan(LanguageCombo("en", "ja"), parent)

        runBlocking { repository.renderRefinementCandidate(parent, plan) }

        assertEquals(
            WebDdlSpec.buildStage1SystemPrompt(parent.description, "en"),
            provider.stage1Prompts.first(),
        )
        assertEquals(WebDdlSpec.STAGE2_SYSTEM_PROMPT_JA, provider.stage2Prompts.first())
    }

    /** 「対象作品と同じ言語構成だけを禁止する」. */
    @Test
    fun t9_theTargetsOwnPairCannotBeChosen() {
        assertTrue(ComparisonPlanner.isLanguageComboBlocked(LanguageCombo("ja", "ja"), "ja"))
        assertEquals(false, ComparisonPlanner.isLanguageComboBlocked(LanguageCombo("ja", "en"), "ja"))
        assertEquals(false, ComparisonPlanner.isLanguageComboBlocked(LanguageCombo("en", "ja"), "ja"))
        assertEquals(false, ComparisonPlanner.isLanguageComboBlocked(LanguageCombo("ja", "ja"), "en"))
    }

    // ── T-10: the two lineage edges ───────────────────────────

    /**
     * Both kinds in one test: an implementation whose branch fell to a constant
     * writes one of them twice, and a test that only saved one comparison would
     * not see it.
     */
    @Test
    fun t10_theTwoComparisonsWriteTheirOwnEdges() {
        val parentItem = paint("夕暮れの水面に細い線を五本引く")
        val parent = parentFor(parentItem)

        val modelPlan = ComparisonPlanner.modelPlan(ModelCompareMode.Common, "", "cmp-model", parent)
        val languagePlan = ComparisonPlanner.languagePlan(LanguageCombo("ja", "en"), parent)
        runBlocking {
            val modelResult = repository.renderRefinementCandidate(parent, modelPlan)
            repository.saveRefinementCandidate(
                result = modelResult, plan = modelPlan, parentNodeId = parentItem.lineageNodeId,
                elapsedMs = 1L, stage1ModelId = "cmp-model", stage2ModelId = "cmp-model",
            )
            val languageResult = repository.renderRefinementCandidate(parent, languagePlan)
            repository.saveRefinementCandidate(
                result = languageResult, plan = languagePlan, parentNodeId = parentItem.lineageNodeId,
                elapsedMs = 1L, stage1ModelId = "target-s1", stage2ModelId = "target-s2",
            )
        }

        val written = edges().toMap()
        assertEquals("one edge each", 2, edges().size)

        val model = requireNotNull(written["model_comparison"]) { "no model_comparison edge: ${edges()}" }
        assertEquals("common", model.getString("comparison_mode"))
        assertEquals("cmp-model", model.getString("compared_model"))
        assertEquals("cmp-model", model.getString("stage1_model"))
        assertEquals("cmp-model", model.getString("stage2_model"))

        val language = requireNotNull(written["language_comparison"]) { "no language_comparison edge: ${edges()}" }
        assertEquals("common", language.getString("comparison_mode"))
        assertEquals("ja", language.getString("stage1_language"))
        assertEquals("en", language.getString("stage2_language"))
    }
}
