package app.inku.mobile.ui

import app.inku.mobile.pipeline.SaijikiGenerated
import app.inku.mobile.ui.i18n.UiLanguage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import java.io.File
import org.junit.Test

/**
 * Acceptance for stage 1 of the-interface-speaks-both-languages (2026-08-09, [I-065]).
 *
 * The point of this file is the THOROUGHFARE, not the generated snapshot. That a
 * correct `SaijikiGenerated.kt` exists is checked on the server side
 * (`test_saijiki_kt_is_current.py`); a screen still reading a hand-copied list
 * passes every one of those assertions while showing the old words. So the gates
 * below call the function the screen calls, and read the screen's own source.
 *
 * The hand-copy is not a hypothetical failure. It was written on 2026-07-26 with
 * the ten touch words of that day, the server returned the silverpoint to the
 * vocabulary on 2026-07-27 (a2d1d100), and the client displayed ten against
 * eleven until this contract.
 */
class SaijikiIsGeneratedTest {

    private fun source(relative: String): String {
        var file = File("src/$relative")
        if (!file.exists()) {
            file = File("app/src/$relative")
        }
        assertTrue("source not found (searched in ./src and ./app/src): $relative", file.exists())
        return file.readText()
    }

    /** T1: what the screen builds, in either language, is the server's table. */
    @Test
    fun testScreenShowsTwelveCategoriesAndNinetyOneWordsInBothLanguages() {
        for (lang in UiLanguage.entries) {
            val groups = saijikiGroups(lang)
            assertEquals("$lang: display categories", 12, groups.size)
            assertEquals("$lang: display words", 91, groups.sumOf { it.words.size })
        }
    }

    /**
     * T2: the eleven words and the category the hand-copy was missing.
     *
     * Named one by one rather than counted, so that a snapshot which gained
     * eleven OTHER words would not satisfy the count above and pass.
     */
    @Test
    fun testTheWordsTheHandCopyCouldNotReachAreOnTheScreen() {
        val ja = saijikiGroups(UiLanguage.Ja)
        val words = ja.flatMap { it.words }
        for (word in listOf("雲形", "銀筆", "黄", "橙", "紫", "敷き詰める")) {
            assertTrue("missing from the screen: $word", word in words)
        }
        val aida = ja.firstOrNull { it.key == "aida" }
        assertTrue("the aida category is absent from the screen", aida != null)
        assertEquals(
            "aida words",
            listOf("沿う", "触れない", "切る", "間に", "触れる"),
            aida!!.words,
        )
    }

    /**
     * T3: the touch words, in the server's order, including the silverpoint.
     *
     * This replaces `WebDdlSpecTest.testStage5dDisplayVocabulary10TermsExactOrder`,
     * which asserted the ten words of 2026-07-26 and so held the drift in place
     * rather than reporting it.
     */
    @Test
    fun testTouchWordsMatchTheServerOrderIncludingTheSilverpoint() {
        val touch = saijikiGroups(UiLanguage.Ja).first { it.key == "tezawari" }
        assertEquals(
            listOf("銀筆", "鉛筆", "ペン", "ロットリング", "クレヨン", "チョーク", "細筆", "太筆", "ビュラン", "ドライポイント", "コンピュータ"),
            touch.words,
        )
        val touchEn = saijikiGroups(UiLanguage.En).first { it.key == "tezawari" }
        assertEquals(
            listOf("silverpoint", "pencil", "pen", "rotring", "crayon", "chalk", "fine-brush", "thick-brush", "burin", "drypoint", "computer"),
            touchEn.words,
        )
    }

    /**
     * T4: the words come from the generated file and nowhere else.
     *
     * T1--T3 are satisfied by a hand-written list that happens to be correct
     * today, which is exactly the state this contract found. This one reads the
     * screen's source: no vocabulary may be spelled out in the ui package.
     */
    @Test
    fun testTheUiPackageSpellsOutNoVocabularyOfItsOwn() {
        val uiSources = listOf(
            "main/java/app/inku/mobile/ui/InkuApp.kt",
            "main/java/app/inku/mobile/ui/InkuViewModel.kt",
        )
        for (relative in uiSources) {
            val text = source(relative)
            assertFalse(
                "$relative constructs a SaijikiGroup from literals; the words must come from SaijikiGenerated",
                Regex("""SaijikiGroup\(\s*"""").containsMatchIn(text),
            )
            for (word in listOf("ロットリング", "ドライポイント", "一点鎖線", "三日月")) {
                assertFalse("$relative spells out the vocabulary word $word", text.contains("\"$word\""))
            }
        }
        val display = source("main/java/app/inku/mobile/ui/InkuApp.kt")
        assertTrue(
            "the display groups must be built from SaijikiGenerated.CATEGORIES",
            Regex("""fun saijikiGroups\([^)]*\)[^=]*=\s*SaijikiGenerated\.CATEGORIES""").containsMatchIn(display),
        )
    }

    /**
     * T5: recognising a word in the DDL is a different question from which words
     * to offer.
     *
     * `highlight.ts:41-42` matches against the Japanese AND the English lists
     * whatever the interface language is, because a work's language is chosen
     * separately from the reader's. A client that matched only the displayed
     * language would stop highlighting a Japanese DDL the moment the reader
     * switched to English -- the same input, a different judgement.
     */
    @Test
    fun testDetectionMatchesBothLanguagesWhicheverOneIsDisplayed() {
        for (lang in UiLanguage.entries) {
            val words = saijikiDetectionWords(lang).map { it.first }.toSet()
            assertTrue("$lang: does not recognise the Japanese 円", "円" in words)
            assertTrue("$lang: does not recognise the English circle", "circle" in words)
            assertEquals("$lang: detection surfaces", 182, words.size)
        }
    }

    /**
     * T6: every category has a colour of its own.
     *
     * The pill colour is looked up as `[index % size]`, so a list one short does
     * not fail -- the tenth category quietly takes the first one's colour. The
     * hand-copy had nine categories and nine colours, and adding the tenth is
     * the kind of change that leaves the list behind.
     */
    @Test
    fun testEveryCategoryHasItsOwnColour() {
        val colors = SaijikiGenerated.CATEGORIES.indices.map { saijikiGroupColorAt(it) }
        assertEquals("one colour per category", SaijikiGenerated.CATEGORIES.size, colors.toSet().size)
    }
}
