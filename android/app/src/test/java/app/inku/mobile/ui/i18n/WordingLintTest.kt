package app.inku.mobile.ui.i18n

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import java.io.File
import org.junit.Test

/**
 * Acceptance for stage 2 of the-interface-speaks-both-languages (2026-08-09, [I-065]).
 *
 * This is the Kotlin counterpart of `web/scripts/i18n-lint.mjs`, and the
 * contract says it is what defines "how many strings there are": no count was
 * handed down, because a floor measured with one regex is not the same quantity
 * as what a lint decides to look at.
 *
 * What it counts: every Japanese string literal in the ten files that hold
 * interface wording. What it does not count is listed in [EXCLUDED] one line at
 * a time -- the exclusions are the dangerous part of this contract, so they are
 * named individually rather than by a pattern that could quietly widen.
 *
 * Measured on the branch point (bdfec13e): 452 Japanese literals in the ten
 * files, of which this reports 446 -- the other six are [EXCLUDED]. It reports 0
 * now. Both numbers matter: a lint that can only ever say 0 is not a lint, so
 * [testTheLintCanSeeWording] proves it still sees wording when wording is there,
 * and [testTheLintIsCalibrated] holds the two settings that could empty it.
 *
 * (452 rather than the contract's 453 because this skips comments, and one of
 * the ten files carries a Japanese comment.)
 */
class WordingLintTest {

    private companion object {
        /**
         * The files that hold interface wording (contract §0.0).
         *
         * The sixteen files NOT here hold Stage 1/2 prompts and the DDL
         * vocabulary. Translating those would make this client judge the same
         * description differently from the server (conventions §2-4), so they
         * are outside the lint by intent, not by oversight.
         */
        val SCANNED = listOf(
            "ui/InkuApp.kt",
            "ui/InkuViewModel.kt",
            "data/model/DerivationKind.kt",
            "data/refinement/RefinementPlan.kt",
            "data/InkuRepository.kt",
            "llm/RoutingModelProvider.kt",
            "llm/LocalLiteRtLmProvider.kt",
            "data/refinement/ComparisonPlan.kt",
            "data/model/ModelRecommendations.kt",
            "llm/ProviderUrlValidator.kt",
        )

        /**
         * Japanese that is NOT interface wording, named one literal at a time.
         *
         * Two kinds live here, and the difference is worth stating:
         *
         * - **A prompt sent to a model.** Its words are the model's input. The
         *   contract names `DefaultDemoSeedPhrase` and the two in `InkuRepository`.
         * - **Content the author starts from and overwrites.** The web keeps one
         *   Japanese `DEFAULT_INPUT` under both languages (`+page.svelte:324`),
         *   so translating these would be a behaviour web does not have. The
         *   contract did not name these two; they were found by measuring web.
         *
         * `languageLabel` is neither: it already answers in both languages, the
         * way each pack names itself in itself.
         */
        val EXCLUDED = setOf(
            "世界の人と動物、自然と都市を主題として96文字の短文を作って。感情豊かに、季節や、人生と人のつながり、人生、世代、神。色々な観点から。",
            "青い鉛筆の線を12本、波打つ軌跡に沿って散らす",
            "赤い円を5個、横に並べる\n黒い太筆の線を3本、斜めに置く\n緑の四角を12個、散らす",
            "日本語",
            // The other two the contract names, in `InkuRepository` (:464, :471
            // at the branch point): the seed sentence the demo asks a model for,
            // and the system instruction that asks it.
            "96文字以内の短い描画指示文を1つ作って。",
            "あなたはinkuのデモ用短文を作る。回答は日本語の短文1つだけ。前置き、箇条書き、番号、引用符、説明、Markdownを出さない。",
        )

        val JAPANESE = Regex("[\\u3040-\\u30ff\\u3400-\\u9fff]")

        /**
         * Every string literal in [text], comments excluded.
         *
         * Written as a scan rather than a regex: the obvious pattern for a
         * literal-with-escapes backtracks, and `WebDdlSpec.kt` carries prompts
         * long enough to turn that into a StackOverflowError rather than a slow
         * test. Comments are skipped because several of them quote the wording
         * they explain, and a comment is not something the reader sees.
         */
        fun literalsIn(text: String): List<String> {
            val out = mutableListOf<String>()
            var i = 0
            while (i < text.length) {
                val c = text[i]
                when {
                    c == '/' && i + 1 < text.length && text[i + 1] == '/' -> {
                        while (i < text.length && text[i] != '\n') i++
                    }
                    c == '/' && i + 1 < text.length && text[i + 1] == '*' -> {
                        i += 2
                        while (i + 1 < text.length && !(text[i] == '*' && text[i + 1] == '/')) i++
                        i += 2
                    }
                    text.startsWith("\"\"\"", i) -> {
                        val end = text.indexOf("\"\"\"", i + 3)
                        val stop = if (end < 0) text.length else end
                        out += text.substring(i + 3, stop)
                        i = stop + 3
                    }
                    // A char literal can hold a quote. `.trim('"', '\u201c', …)`
                    // in InkuRepository is exactly that, and reading its `"` as
                    // the start of a string swallowed the next 40 lines whole.
                    c == '\'' -> {
                        i++
                        while (i < text.length && text[i] != '\'') {
                            i += if (text[i] == '\\') 2 else 1
                        }
                        i++
                    }
                    c == '"' -> {
                        val sb = StringBuilder()
                        i++
                        while (i < text.length && text[i] != '"') {
                            if (text[i] == '\\' && i + 1 < text.length) {
                                sb.append(text[i]).append(text[i + 1]); i += 2
                            } else {
                                sb.append(text[i]); i++
                            }
                        }
                        i++
                        out += sb.toString()
                    }
                    else -> i++
                }
            }
            return out
        }
    }

    private fun sourceRoot(): File {
        var root = File("src/main/java/app/inku/mobile")
        if (!root.isDirectory) root = File("app/src/main/java/app/inku/mobile")
        assertTrue("source root not found (searched ./src and ./app/src)", root.isDirectory)
        return root
    }

    /** Every Japanese literal in [relative] that the lint holds against the file. */
    private fun offenders(relative: String): List<String> {
        val file = File(sourceRoot(), relative)
        assertTrue("scanned file is missing: $relative", file.isFile)
        return literalsIn(file.readText())
            .filter { JAPANESE.containsMatchIn(it) }
            .map { it.replace("\\n", "\n") }
            .filterNot { it in EXCLUDED }
            .toList()
    }

    /** T1: no wording is written into the sources any more. */
    @Test
    fun testNoJapaneseWordingIsLeftInTheScannedFiles() {
        val found = SCANNED.flatMap { relative -> offenders(relative).map { "$relative: $it" } }
        assertEquals("wording still written into the sources:\n" + found.joinToString("\n"), 0, found.size)
    }

    /**
     * T2: the lint has discriminating power.
     *
     * A lint that reports 0 because it looks at nothing reports 0 after the
     * change too. This puts a sentence back, in the same shape the sources used,
     * and requires it to be seen.
     */
    @Test
    fun testTheLintCanSeeWording() {
        val text = """Text("描画する")"""
        val seen = literalsIn(text).filter { JAPANESE.containsMatchIn(it) }
        assertEquals(listOf("描画する"), seen)
    }

    /**
     * T3: the file list and the exclusion list are themselves gated.
     *
     * Emptying [SCANNED] makes T1 pass while nothing is checked, and widening
     * [EXCLUDED] does the same one string at a time. Both are settings, and a
     * gate on a setting is the only thing that notices when the setting moves.
     */
    @Test
    fun testTheLintIsCalibrated() {
        assertEquals("the ten files of contract §0.0", 10, SCANNED.size)
        SCANNED.forEach { relative ->
            assertTrue("$relative is not a file", File(sourceRoot(), relative).isFile)
        }
        assertEquals(
            "exclusions are named one at a time; adding one is a decision, not a tweak",
            6,
            EXCLUDED.size,
        )
        // The sixteen untouchable files must still hold their Japanese: this
        // contract translating a prompt would be the worst outcome, so it is
        // checked from the same place rather than left to review.
        val prompts = File(sourceRoot(), "pipeline/WebDdlSpec.kt").readText()
        assertTrue("the Stage 1 prompt has lost its Japanese", JAPANESE.containsMatchIn(prompts))
        assertTrue("the Stage 1 prompt has lost its touch words", prompts.contains("銀筆"))
    }

    /** T4: the two packs answer the same set of keys. */
    @Test
    fun testBothPacksDeclareTheSameKeys() {
        fun keys(name: String): List<String> {
            var file = File("src/main/java/app/inku/mobile/ui/i18n/$name")
            if (!file.isFile) file = File("app/src/main/java/app/inku/mobile/ui/i18n/$name")
            assertTrue("pack not found: $name", file.isFile)
            return Regex("""override val (\w+)""").findAll(file.readText())
                .map { it.groupValues[1] }
                .toList()
        }
        val ja = keys("InkuStringsJa.kt")
        val en = keys("InkuStringsEn.kt")
        assertEquals("a key is declared twice in ja", ja.size, ja.toSet().size)
        assertEquals("a key is declared twice in en", en.size, en.toSet().size)
        assertEquals("ja has keys en does not", emptySet<String>(), ja.toSet() - en.toSet())
        assertEquals("en has keys ja does not", emptySet<String>(), en.toSet() - ja.toSet())
        assertTrue("the packs look too small to be the real ones", ja.size > 200)
    }

    /**
     * T5: the English is English.
     *
     * The interface type already forces both packs to answer every key. It does
     * not stop `InkuStringsEn` from answering with the Japanese, which is
     * exactly what a half-finished translation looks like.
     */
    @Test
    fun testTheEnglishPackHoldsNoJapanese() {
        var file = File("src/main/java/app/inku/mobile/ui/i18n/InkuStringsEn.kt")
        if (!file.isFile) file = File("app/src/main/java/app/inku/mobile/ui/i18n/InkuStringsEn.kt")
        val japanese = literalsIn(file.readText()).filter { JAPANESE.containsMatchIn(it) }
        assertEquals("the English pack answers in Japanese: $japanese", 0, japanese.size)
    }

    /**
     * T6: the words the glossary forbids.
     *
     * `GLOSSARY.md` §5 rules out generate / create / prompt / image / AI-powered
     * as inku's English, and §2 rules out palette, artwork, fluctuation and
     * jitter. `npm run lint:i18n` enforces this for web and cannot see Kotlin.
     */
    @Test
    fun testTheEnglishPackFollowsTheGlossary() {
        var file = File("src/main/java/app/inku/mobile/ui/i18n/InkuStringsEn.kt")
        if (!file.isFile) file = File("app/src/main/java/app/inku/mobile/ui/i18n/InkuStringsEn.kt")
        val strings = literalsIn(file.readText())
        val forbidden = listOf(
            "palette", "artwork", "fluctuation", "jitter",
            "AI-powered", "AI powered", "magic",
        )
        for (word in forbidden) {
            val hits = strings.filter { it.contains(word, ignoreCase = true) }
            assertEquals("GLOSSARY forbids \"$word\": $hits", emptyList<String>(), hits)
        }
    }
}
