package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * T-8 of 契約 description-propagation-cut.
 *
 * The rule-based fallback used to hand the coercer `"$ddl\n$originalText"` twice
 * -- once for the single instruction it composes and once, through
 * `normalizeServerScore`, for all thirty branches and the background governor.
 * Those branches could then author a mark from a word only the description
 * carried, and nothing in the DDL explained it. They read the DDL alone now.
 *
 * `context` inside `scoreFromWebRules` still carries the description: that is
 * this fallback's Stage 2, not its coerce, and the contract cuts coerce.
 */
class DescriptionPropagationCutTest {

    private val pipeline = LocalFallbackPipeline()

    private fun backgroundOf(ddl: String, originalText: String): String {
        return pipeline.scoreFromWebRules(ddl, originalText, "square").optString("background")
    }

    private fun instructionsOf(score: JSONObject): List<JSONObject> {
        val array = score.optJSONArray("instructions") ?: JSONArray()
        return (0 until array.length()).map { array.getJSONObject(it) }
    }

    /**
     * The description says night and the DDL does not. The dark background the
     * description produced is the fallback's Stage 2 talking, and it is the
     * governor -- a coerce-side branch -- that decides whether it survives.
     * While the governor read the concatenation it saw 夜 and kept the black;
     * reading the DDL alone it finds neither a background clause nor a surface
     * word, and washes it. That difference is the cut, seen from its far end.
     */
    @Test
    fun `the governor no longer reads a night the ddl never wrote`() {
        val ddl = "白い細い弧を三百本、上から下へ散らす。境界が滲む。透明な膜を重ねる。"
        val background = backgroundOf(ddl, "夜である。静かな気配がある。")

        assertEquals("white", background)
    }

    /**
     * Control. The same governor, with the same prose, and a DDL that does say
     * what it wants: the colour survives. Without this the case above passes on
     * an implementation that washes every background.
     */
    @Test
    fun `a background the ddl asks for survives`() {
        val ddl = "背景を黒で塗りつぶす。白い細い弧を三百本、上から下へ散らす。境界が滲む。透明な膜を重ねる。"
        val background = backgroundOf(ddl, "夜である。静かな気配がある。")

        assertEquals("black", background)
    }

    /**
     * The removed guard, from the far end. This DDL is a single line of five
     * clauses opening with 背景を and mentioning 気配 -- every condition the
     * guard tested, and the ordinary shape of a production DDL. While the
     * context was `ddl\nprose` the guard never saw this shape, because the
     * newline alone made it stand down. The cut handed it exactly this, and it
     * washed the background the DDL had asked for.
     */
    @Test
    fun `a production shaped plan is not mistaken for a pasted one`() {
        val ddl = "背景を青で塗りつぶす。画面全体に白い細い縦線を三百本散らす。" +
            "黒い細い余白線を存在の重心として右上の焦点へ二本引く。透明な膜を重ねる。境界が滲む。"
        val background = backgroundOf(ddl, "静かな水面がある。")

        assertEquals("blue", background)
    }

    /**
     * A background clause on the second line is read. The whole-context read
     * replaces a first-line read that existed only because the first line used
     * to be the description.
     */
    @Test
    fun `a surface word below the first line is read`() {
        val ddl = "地: 生成りの紙、細かい紙目。\n夜空に白い細い弧を静かに散らす。"
        val background = backgroundOf(ddl, "夜である。静かな気配がある。")

        assertEquals("black", background)
    }

    /** Control for the case above: the same two lines without the surface word. */
    @Test
    fun `a second line with no surface word is still governed`() {
        val ddl = "地: 生成りの紙、細かい紙目。\n静かに白い細い弧を散らす。"
        val background = backgroundOf(ddl, "夜である。静かな気配がある。")

        assertEquals("white", background)
    }

    /**
     * Not only the governor. `coerceInstruction` and every list pass below it
     * take the same string, so a colour named only in the description must not
     * appear in the Score through them.
     */
    @Test
    fun `no branch delivers a colour only the description named`() {
        val ddl = "黒い線を一本引く。"
        val score = pipeline.scoreFromWebRules(ddl, "紫の菫が咲いている。")
            .let { it }
        val colors = instructionsOf(score).mapNotNull { instruction ->
            instruction.optString("color").takeIf { it.isNotBlank() }
        }.toSet()
        val cycles = instructionsOf(score).flatMap { instruction ->
            val cycle = instruction.optJSONObject("arrangement")?.optJSONArray("color_cycle") ?: JSONArray()
            (0 until cycle.length()).map { cycle.getString(it) }
        }.toSet()

        assertTrue("purple reached the Score: $colors / $cycles", "purple" !in colors + cycles)
    }

    private fun LocalFallbackPipeline.scoreFromWebRules(ddl: String, originalText: String): JSONObject =
        scoreFromWebRules(ddl, originalText, "square")
}
