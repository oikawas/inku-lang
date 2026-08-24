package app.inku.mobile.pipeline

import java.io.InputStreamReader
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * 写生 (Stage 0.5) against the server's own measurements.
 *
 * The expectations are not re-derived here. They were measured on the server's
 * product functions at `ea5035a3` and handed over as material
 * (`cli/out2/861-v2.11.5-sketch-expectations/`): `expectations.json` plus the
 * four system prompts in full. Those five files are copied verbatim into
 * `src/test/resources/sketch/` and are read below. Measuring the port against
 * itself would only prove it agrees with itself.
 *
 * They are deliberately outside the historical Server renderer corpus because
 * putting prompts there would tie this test to drawing-quality work.
 */
class SketchTest {

    private fun material(name: String): String {
        val path = "/sketch/$name"
        val stream = SketchTest::class.java.getResourceAsStream(path)
            ?: error("Sketch expectation material $path not found")
        return InputStreamReader(stream, Charsets.UTF_8).use { it.readText() }
    }

    private val expectations: JSONObject by lazy { JSONObject(material("expectations.json")) }

    // --- T-1 -------------------------------------------------------------

    /**
     * `normalize_sketch_grain` resolves a *requested* grain, and anything that
     * is not one of the two words falls to the default. The null and the
     * unknown word are the cases that matter: an implementation that just
     * lower-cased its argument would pass on `"fine"` and `"COARSE"` alone.
     */
    @Test
    fun t1_normalizeGrainReproducesTheServersTable() {
        val table = expectations.getJSONObject("normalize_sketch_grain")
        val inputs = mapOf(
            "None" to null,
            "''" to "",
            "'fine'" to "fine",
            "'coarse'" to "coarse",
            "'COARSE'" to "COARSE",
            "'  fine  '" to "  fine  ",
            "'medium'" to "medium",
            "'off'" to "off",
            "'0'" to "0",
        )
        assertEquals("every case the server measured is read", table.length(), inputs.size)
        inputs.forEach { (label, input) ->
            assertEquals(
                "normalizeGrain($label)",
                table.getString(label),
                Sketches.normalizeGrain(input).wire,
            )
        }
        // Stated on its own because it is the surprising one: `off` is a state
        // of the control, not a grain, and it never reaches this function. That
        // is why SketchMode and SketchGrain are two types.
        assertEquals("fine", Sketches.normalizeGrain("off").wire)
    }

    /**
     * The other normalizer, on the same axis and with the opposite rule: a
     * state a caller claims is either one of the five or nothing at all. It is
     * never rounded to a default, because a default state is a claim nobody
     * made.
     */
    @Test
    fun t1_normalizeStateReproducesTheServersTable() {
        val table = expectations.getJSONObject("normalize_sketch_state")
        val inputs = mapOf(
            "None" to null,
            "''" to "",
            "'fine'" to "fine",
            "'coarse'" to "coarse",
            "'fallback'" to "fallback",
            "'off'" to "off",
            "'not_applicable'" to "not_applicable",
            "'FINE'" to "FINE",
            "'unknown'" to "unknown",
        )
        assertEquals("every case the server measured is read", table.length(), inputs.size)
        inputs.forEach { (label, input) ->
            val expected = if (table.isNull(label)) null else table.getString(label)
            assertEquals(
                "normalizeState($label)",
                expected,
                Sketches.normalizeState(input)?.wire,
            )
        }
    }

    // --- T-2 -------------------------------------------------------------

    /**
     * The system prompt, in full, for all four combinations.
     *
     * Compared whole rather than by length or opening line: a prompt that
     * agrees on its first sixty characters and diverges in the middle is a
     * different prompt, and length is not a stand-in for content. The digest is
     * asserted too, because that is what the record carries -- if the two ever
     * disagree, the record would name a prompt nobody sent.
     */
    @Test
    fun t2_theSystemPromptIsTheServersDownToTheByte() {
        val table = expectations.getJSONObject("build_system_prompt")
        val cases = listOf(
            Triple("ja", SketchGrain.Fine, "system-prompt-ja-fine.txt"),
            Triple("ja", SketchGrain.Coarse, "system-prompt-ja-coarse.txt"),
            Triple("en", SketchGrain.Fine, "system-prompt-en-fine.txt"),
            Triple("en", SketchGrain.Coarse, "system-prompt-en-coarse.txt"),
        )
        assertEquals("every combination the server measured is read", table.length(), cases.size)
        cases.forEach { (lang, grain, file) ->
            val key = "$lang/${grain.wire}"
            val expected = material(file)
            val actual = SketchFromLife.systemPrompt(lang, grain)
            assertEquals("the $key prompt is the server's, whole", expected, actual)
            val row = table.getJSONObject(key)
            assertEquals("$key characters", row.getInt("chars"), actual.length)
            assertEquals(
                "$key bytes",
                row.getInt("bytes"),
                actual.toByteArray(Charsets.UTF_8).size,
            )
            assertEquals("$key digest", row.getString("digest"), SketchFromLife.promptDigest(actual))
        }
    }

    /**
     * The four prompts are four, not two: an implementation that ignored the
     * grain and always built the `fine` text would satisfy every "is it the
     * server's prompt" check above for two of the four rows, so the four
     * digests are asserted to be four distinct values as well.
     */
    @Test
    fun t2_theFourPromptsAreFourDistinctPrompts() {
        val digests = listOf("ja" to SketchGrain.Fine, "ja" to SketchGrain.Coarse, "en" to SketchGrain.Fine, "en" to SketchGrain.Coarse)
            .map { (lang, grain) -> SketchFromLife.promptDigest(SketchFromLife.systemPrompt(lang, grain)) }
        assertEquals("no two of the four prompts are the same", 4, digests.toSet().size)
    }

    /** The digest is SHA-256's first 16 hex digits, and the empty string proves it. */
    @Test
    fun t2_thePromptDigestIsTheServersDigest() {
        assertEquals("e3b0c44298fc1c14", SketchFromLife.promptDigest(""))
        assertEquals(16, SketchFromLife.promptDigest("anything").length)
    }

    // --- T-3 -------------------------------------------------------------

    /**
     * All five states, from the seven input combinations the server measured.
     *
     * `fallback` and `not_applicable` are both in the table on purpose. With
     * only one of them present, an implementation that answered `fine` for
     * everything with a detail and `off` for everything without one would pass.
     */
    @Test
    fun t3_stateOfReturnsAllFiveStates() {
        val rows = expectations.getJSONArray("sketch_state_of")
        val seen = mutableSetOf<String>()
        for (index in 0 until rows.length()) {
            val row = rows.getJSONObject(index)
            val detail = if (row.isNull("detail")) {
                null
            } else {
                val d = row.getJSONObject("detail")
                SketchFromLife.Detail(
                    text = "写生文",
                    grain = Sketches.normalizeGrain(d.getString("grain")),
                    fallbackUsed = d.getBoolean("fallback_used"),
                )
            }
            val expected = row.getString("state")
            assertEquals(
                row.getString("case"),
                expected,
                SketchFromLife.stateOf(
                    detail,
                    requested = row.getBoolean("requested"),
                    hasDescription = row.getBoolean("has_description"),
                ).wire,
            )
            seen += expected
        }
        assertEquals(
            "the seven cases between them name all five states",
            setOf("fine", "coarse", "fallback", "off", "not_applicable"),
            seen,
        )
    }

    /**
     * The single row this layer exists to protect: the layer was asked for and
     * nothing came back. That is `not_applicable`, not `off` -- a wiring
     * regression must not be written down as a choice the author made.
     */
    @Test
    fun t3_askedForAndAbsentIsNotApplicableNotOff() {
        assertEquals(
            SketchState.NotApplicable,
            SketchFromLife.stateOf(null, requested = true, hasDescription = true),
        )
        assertEquals(
            "and the author choosing not to run it is what `off` means",
            SketchState.Off,
            SketchFromLife.stateOf(null, requested = false, hasDescription = true),
        )
    }

    // --- T-4 -------------------------------------------------------------

    /**
     * The sixth state: no value at all. It is not `off`.
     *
     * `off` is a choice the author made; a work drawn before the column existed
     * made no such choice, and every reader has to be able to tell them apart.
     * This is the only gate on that distinction, so it is asserted on both
     * functions that can lose it and on the type that carries it.
     */
    @Test
    fun t4_absenceIsNotOff() {
        assertNull("an absent state is nothing at all", Sketches.normalizeState(null))
        assertEquals("and `off` is a state", SketchState.Off, Sketches.normalizeState("off"))
        assertNotEquals(Sketches.normalizeState(null), Sketches.normalizeState("off"))

        // The recorded grain, read off a saved work, keeps the same distinction:
        // a row that predates the column has no grain, and rounding it up to the
        // default would say it was drawn at `fine`.
        assertNull("a work with no grain recorded has none", Sketches.recordedGrainOf(null))
        assertNull("`off` is not a grain either", Sketches.recordedGrainOf("off"))
        assertEquals(SketchGrain.Fine, Sketches.recordedGrainOf("fine"))
        assertEquals(SketchGrain.Coarse, Sketches.recordedGrainOf("coarse"))

        // And the two normalizers do not agree, which is the point of having
        // both: one resolves a request, the other reads a record.
        assertEquals(SketchGrain.Fine, Sketches.normalizeGrain(null))
        assertNotEquals(
            "the requested-grain normalizer must not be used to read a record",
            Sketches.recordedGrainOf(null),
            Sketches.normalizeGrain(null),
        )
    }

    /** The mode `off` carries no grain, and a work with no grain reads as off. */
    @Test
    fun t4_offAndAbsenceAreTheSameGrainAndDifferentStates() {
        assertNull(Sketches.grainOf(SketchMode.Off))
        assertEquals(SketchGrain.Fine, Sketches.grainOf(SketchMode.Fine))
        assertEquals(SketchGrain.Coarse, Sketches.grainOf(SketchMode.Coarse))
        assertEquals(SketchMode.Off, Sketches.modeOf(null))
        assertEquals(SketchMode.Fine, Sketches.modeOf("fine"))
        assertEquals(SketchMode.Coarse, Sketches.modeOf("coarse"))
        assertEquals("the author's default is that the layer runs", SketchMode.Fine, Sketches.DEFAULT_MODE)
    }

    /**
     * A state a caller claims wins over one derived from the row, and an
     * unknown claim does not (`history.py:255`). Without the first half, a run
     * whose layer fell back would be saved as `off`, because a fallback leaves
     * no prose for the derivation to read.
     */
    @Test
    fun t3_aClaimedStateWinsOverTheDerivedOne() {
        assertEquals(
            SketchState.Fallback,
            SketchFromLife.claimedOrDerivedState(
                claimed = "fallback",
                prose = null,
                grain = null,
                hasDescription = true,
            ),
        )
        assertEquals(
            "an unknown claim is not honoured; the row decides",
            SketchState.Off,
            SketchFromLife.claimedOrDerivedState(
                claimed = "unknown",
                prose = null,
                grain = null,
                hasDescription = true,
            ),
        )
        assertEquals(
            "and a carried prose names its own grain",
            SketchState.Coarse,
            SketchFromLife.claimedOrDerivedState(
                claimed = null,
                prose = "岩の面を水が速く流れ落ちる。",
                grain = "coarse",
                hasDescription = true,
            ),
        )
    }

    /** Fenced prose is unwrapped the same way Stage 1's DDL is. */
    @Test
    fun t2_fencedProseIsUnwrapped() {
        assertEquals("水は白い。", SketchFromLife.cleanText("```\n水は白い。\n```"))
        assertEquals("水は白い。", SketchFromLife.cleanText("  水は白い。  "))
        assertEquals("", SketchFromLife.cleanText(null))
    }
}
