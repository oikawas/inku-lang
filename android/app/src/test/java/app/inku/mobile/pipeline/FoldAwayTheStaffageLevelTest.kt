package app.inku.mobile.pipeline

import app.inku.mobile.ReferenceCorpus
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import java.io.File
import org.junit.Test

/**
 * Acceptance for the contract android-folds-away-the-staffage-level (2026-08-05, [I-139]).
 *
 * The staffage level (tenkei) was an axis for "how much may the machine invent".
 * v2.11.0 folded it away on the server; this port writes the same judgement in
 * Kotlin. The gates below are numbered as in the contract's section 4.
 *
 * The nine sites of the contract's section 2.2 are asserted ONE BY ONE, not as a
 * set: restoring any single one of them turns exactly the matching test red.
 */
class FoldAwayTheStaffageLevelTest {

    private fun source(relative: String): String {
        var file = File("src/$relative")
        if (!file.exists()) {
            file = File("app/src/$relative")
        }
        assertTrue("source not found (searched in ./src and ./app/src): $relative", file.exists())
        return file.readText()
    }

    private fun projectFile(name: String): File {
        var file = File(name)
        if (!file.exists()) {
            file = File("../$name")
        }
        return file
    }

    private val expanderSource: String
        get() = source("main/java/app/inku/mobile/pipeline/WebDdlExpander.kt")

    private fun readReferenceCorpus(): JSONObject = ReferenceCorpus.json("ddl_expand.json")

    private fun corpusCases(): List<JSONObject> {
        val cases = readReferenceCorpus().getJSONArray("cases")
        return (0 until cases.length()).map { cases.getJSONObject(it) }
    }

    private fun runCase(caseObj: JSONObject): String {
        val input = caseObj.getJSONObject("input")
        fun optString(key: String): String? =
            if (!input.has(key) || input.isNull(key)) null else input.getString(key)
        fun optLong(key: String): Long? =
            if (!input.has(key) || input.isNull(key)) null else input.getLong(key)
        return WebDdlExpander.expandIntermediateDdl(
            ddl = input.getString("ddl"),
            lang = optString("lang") ?: "ja",
            contextText = optString("context_text"),
            // manifest key renamed in v2.8.0; the expander parameter stays frozen.
            varySeed = optLong("composition_seed"),
            enablePlugins = input.optBoolean("enable_plugins", true),
            pluginInstructionsPresent = input.optBoolean("plugin_instructions_present", false),
            focus = optString("focus"),
            variationAmplitude = optString("variation_amplitude"),
            variationSeed = optLong("variation_seed"),
        )
    }

    // ── T-1: the axis is gone from the expander, not merely defaulted ──────────

    /** Site 1 of section 2.2: the parameter itself (`tenkei: String = "auto",`). */
    @Test
    fun t1a_theEntryPointHasNoStaffageParameter() {
        val signature = expanderSource
            .substringAfter("fun expandIntermediateDdl(")
            .substringBefore("): String {")
        assertFalse(
            "expandIntermediateDdl still declares a staffage parameter",
            signature.contains("tenkei"),
        )
    }

    /** Site 2: the Japanese expander returned the reframe only when the level was "none". */
    @Test
    fun t1b_theJapaneseExpanderReturnsTheReframeUnconditionally() {
        val tail = expanderSource
            .substringAfter("val reframed = reframeStaticCenterJa(ddl, focusId)")
            .substringBefore("return reframed")
        assertFalse("_expand_ja still branches before returning the reframe", tail.contains("if ("))
    }

    /** Site 3: same for the English expander. */
    @Test
    fun t1c_theEnglishExpanderReturnsTheReframeUnconditionally() {
        val tail = expanderSource
            .substringAfter("val reframed = reframeStaticCenterEn(ddl, focusId)")
            .substringBefore("return reframed")
        assertFalse("_expand_en still branches before returning the reframe", tail.contains("if ("))
    }

    /** Site 4: the ranked axis list collapsed to focus. */
    @Test
    fun t1d_theRankedAxisListIsGone() {
        assertFalse("variationRankedAxes still exists", expanderSource.contains("variationRankedAxes"))
        for (axis in listOf("type_swap", "\"count\"", "\"touch\"", "\"color\"", "\"composition\"", "type_family")) {
            assertFalse("a variation axis other than focus survives: $axis", expanderSource.contains(axis))
        }
    }

    /** Site 5: the amplitude no longer decides how many axes move. */
    @Test
    fun t1e_theAmplitudeAxisRangeIsGone() {
        assertFalse(
            "AMPLITUDE_AXIS_RANGE still exists",
            expanderSource.contains("AMPLITUDE_AXIS_RANGE"),
        )
    }

    /** Sites 6 and 7: recapAfterVariation, including its sparse arm. */
    @Test
    fun t1f_theRecapAfterVariationIsGone() {
        assertFalse(
            "recapAfterVariation still exists",
            expanderSource.contains("recapAfterVariation"),
        )
    }

    /** Sites 8 and 9: capCategoryPlan, including its sparse arm. */
    @Test
    fun t1g_theCategoryCapIsGone() {
        assertFalse("capCategoryPlan still exists", expanderSource.contains("capCategoryPlan"))
        assertFalse("categoryPlan still exists", expanderSource.contains("categoryPlan"))
    }

    /** Both sparse arms, asserted on the string the contract names. */
    @Test
    fun t1h_neitherSparseArmSurvives() {
        assertFalse("the sparse arm survives", expanderSource.contains("sparse"))
    }

    /** The word itself is gone from the expander -- not defaulted somewhere else. */
    @Test
    fun t1i_theStaffageLevelIsNotNamedInTheExpander() {
        assertFalse("the expander still names the staffage level", expanderSource.contains("tenkei"))
    }

    /** Behavioural form of T-1: only the focus axis can move, at any amplitude. */
    @Test
    fun t1j_onlyTheFocusAxisEverMoves() {
        for (amplitude in listOf("small", "medium", "large")) {
            val report = mutableMapOf<String, Any>()
            WebDdlExpander.expandIntermediateDdl(
                ddl = "中心に黒い四角を置く。白い横線を三本引く。",
                variationAmplitude = amplitude,
                variationSeed = 12345L,
                variationReport = report,
            )
            @Suppress("UNCHECKED_CAST")
            val moved = report["moved_axes"] as List<Map<String, String>>
            assertTrue("more than one axis moved at $amplitude: $moved", moved.size <= 1)
            for (entry in moved) {
                assertEquals("an axis other than focus moved at $amplitude", "focus", entry["axis"])
            }
        }
    }

    // ── T-2: the control -- focus still authors the output ─────────────────────

    /**
     * Without this control, "delete the axis" would pass T-1 by returning a constant.
     * Measured 2026-08-05: five B-focus-* cases, FOUR distinct outputs, all five
     * differing from A-base-ja. (B-focus-not-a-focus is not a focus id, so the
     * variation shifts the hashed default -- it lands on the same output as
     * B-focus-lower_right. That is the defined behaviour, not a regression.)
     */
    @Test
    fun t2_focusStillAuthorsTheOutput() {
        val cases = corpusCases().associateBy { it.getString("case") }
        val base = runCase(cases.getValue("A-base-ja"))
        val focusCases = cases.keys.filter { it.startsWith("B-focus-") }.sorted()
        assertEquals("the corpus no longer holds five focus cases", 5, focusCases.size)

        val produced = linkedMapOf<String, String>()
        for (name in focusCases) {
            val output = runCase(cases.getValue(name))
            assertNotEquals("$name produces the same output as A-base-ja", base, output)
            produced[name] = output
        }
        assertEquals(
            "the five focus cases no longer resolve to four distinct outputs: $produced",
            4,
            produced.values.toSet().size,
        )
        // Case by case, so a collapse of any single one is named.
        assertEquals("右下の焦点に黒い四角を置く。白い横線を三本引く。", produced["B-focus-lower_right"])
        assertEquals("右半分の焦点に黒い四角を置く。白い横線を三本引く。", produced["B-focus-right_half"])
        assertEquals("上端寄りの焦点に黒い四角を置く。白い横線を三本引く。", produced["B-focus-upper_edge"])
        assertEquals("左上の焦点に黒い四角を置く。白い横線を三本引く。", produced["B-focus-upper_left"])
    }

    // ── T-3: no pipeline or repository entry point carries the level ───────────

    @Test
    fun t3_noPipelineOrRepositoryEntryPointCarriesTheLevel() {
        val fields = PaintRequest::class.java.declaredFields.map { it.name }
        assertFalse("PaintRequest still carries the staffage level: $fields", fields.any { it.contains("tenkei", ignoreCase = true) })

        for (relative in listOf(
            "main/java/app/inku/mobile/pipeline/InkuPipeline.kt",
            "main/java/app/inku/mobile/pipeline/LocalFallbackPipeline.kt",
            "main/java/app/inku/mobile/data/InkuRepository.kt",
        )) {
            assertFalse(
                "$relative still names the staffage level",
                source(relative).contains("tenkei", ignoreCase = true),
            )
        }
    }

    // ── T-4: the picker is gone from the UI ───────────────────────────────────

    @Test
    fun t4_thePickerIsGoneFromTheUi() {
        val model = projectFile("app/src/main/java/app/inku/mobile/data/model/Tenkei.kt")
        val modelInModuleDir = projectFile("src/main/java/app/inku/mobile/data/model/Tenkei.kt")
        assertFalse("data/model/Tenkei.kt still exists", model.exists() || modelInModuleDir.exists())

        val app = source("main/java/app/inku/mobile/ui/InkuApp.kt")
        for (marker in listOf("TenkeiSelect", "tenkei_select_row", "tenkei_chip_", "添景選択")) {
            assertFalse("the staffage picker survives in InkuApp.kt: $marker", app.contains(marker))
        }
        assertFalse(
            "InkuViewModel still holds the staffage state",
            source("main/java/app/inku/mobile/ui/InkuViewModel.kt").contains("Tenkei"),
        )
    }

    // ── T-5: the reference parity holds ───────────────────────────────────────

    /**
     * *** This is a REGENERATED RECORD, not a property test. *** The re-bake left
     * only 14 distinct outputs among the 30 cases, so a port that ignored its input
     * would still go green on 16 of them. It does not stand alone -- t2 above is
     * what carries the discrimination.
     */
    @Test
    fun t5_everyReferenceCaseMatchesExactly() {
        val cases = corpusCases()
        assertTrue("the reference corpus shrank below 30 cases: ${cases.size}", cases.size >= 30)
        for (caseObj in cases) {
            val name = caseObj.getString("case")
            assertEquals("output mismatch for case: $name", caseObj.getString("output"), runCase(caseObj))
        }
    }

    // ── T-6: the re-pointed tests are still there ─────────────────────────────

    /**
     * The six tests of the contract's section 1.3 were re-pointed, not deleted.
     * Each name states a property that is true after the fold and false before it;
     * this gate keeps a later edit from quietly dropping one.
     */
    @Test
    fun t6_theRePointedTestsSurvive() {
        val phase3a = source("test/java/app/inku/mobile/pipeline/WebDdlExpanderPhase3aTest.kt")
        for (name in listOf(
            "testContextTextNoLongerMovesTheOutputButFocusDoes",
            "testVarySeedNoLongerModifiesTheOutputButFocusDoes",
        )) {
            assertTrue("re-pointed test missing: $name", phase3a.contains("fun $name("))
        }

        val expanderTest = source("test/java/app/inku/mobile/pipeline/WebDdlExpanderTest.kt")
        for (name in listOf(
            "addsNoSentenceBeyondTheReframe",
            "variesByFocusAndReframesCenter",
            "atmosphericAndSensoryContextNoLongerAddSentences",
            "presenceContextNoLongerAddsBodySymbols",
        )) {
            assertTrue("re-pointed test missing: $name", expanderTest.contains("fun $name("))
        }
    }

    // ── T-7: the specification followed ───────────────────────────────────────

    @Test
    fun t7_neitherSpecificationDescribesTheStaffageLevelAsALiveFeature() {
        val ja = projectFile("ANDROID_SPEC.ja.md")
        val en = projectFile("ANDROID_SPEC.md")
        assertTrue("ANDROID_SPEC.ja.md must exist", ja.exists())
        assertTrue("ANDROID_SPEC.md must exist", en.exists())

        val jaText = ja.readText()
        val enText = en.readText()

        // The dated history sections keep their record of what was ported in 2026-07;
        // what must be gone is the staffage level named as something still standing.
        assertFalse(
            "ANDROID_SPEC.ja.md still lists the staffage level among the features to follow",
            jaText.contains("プラグイン、系譜、添景"),
        )
        assertFalse(
            "ANDROID_SPEC.md still lists the staffage level among the features to follow",
            enText.contains("lineage, tenkei"),
        )

        // Both languages record the fold, so the pair stays in step.
        assertTrue("ANDROID_SPEC.ja.md does not record the fold", jaText.contains("2026-08-05 添景水準"))
        assertTrue("ANDROID_SPEC.md does not record the fold", enText.contains("2026-08-05 The staffage level"))
    }
}
