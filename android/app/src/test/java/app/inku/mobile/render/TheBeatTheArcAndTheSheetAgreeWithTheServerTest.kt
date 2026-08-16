package app.inku.mobile.render

import app.inku.mobile.data.model.CanvasAspects
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Three more places where the port answered something else than the server, and
 * none of them is reachable from the frozen corpus: the beat a repeated
 * arrangement is laid on, the sampling of a varied arc that does not go through
 * the hand-stroke engine, and the pixel size a paper ratio turns into.
 *
 * The corpus was counted before these gates were written. Its thirteen
 * arrangements are all `rhythm_spacing: "none"`; its six arcs hold exactly one
 * with a `variation`, and that one is `pen`, which takes the hand path; and its
 * fifty-one drawings are 1000x1000 fifty times and 2350x1000 once, so no paper
 * whose ratio needs rounding is drawn at all. Nothing frozen moves, which is
 * why every expected number below was read off
 * `server/src/inku_server/renderer.py` and
 * `plugins/system/canvas_aspect/__init__.py` rather than off the port's own
 * previous answer -- "it changed" would be true of a wrong implementation too.
 */
class TheBeatTheArcAndTheSheetAgreeWithTheServerTest {

    private val seed = 12345L
    private val seedText = "12345"
    private val squareSide = 1000.0

    // ---- [I-273] the beat ------------------------------------------------

    /** `DefaultSvgRenderer.rhythmT`, the function the five placement sites read. */
    private fun rhythmT(i: Int, count: Int, spacing: String, seedArg: String = seedText): Double {
        val method = DefaultSvgRenderer::class.java.getDeclaredMethod(
            "rhythmT",
            Int::class.javaPrimitiveType,
            Int::class.javaPrimitiveType,
            String::class.java,
            String::class.java,
        )
        method.isAccessible = true
        return method.invoke(DefaultSvgRenderer(), i, count, seedArg, spacing) as Double
    }

    /**
     * T-121: a group of one starts where the server starts it.
     *
     * The server answers 0.0 and the port answered 0.5, which is the middle of
     * whatever the beat is spread across -- a lone member drawn half a span away
     * from where the server draws it. The pair of two is the control: it says
     * the guard was narrowed to `n <= 1` and not replaced by a constant.
     */
    @Test
    fun testALoneMemberSitsWhereTheServerPutsIt() {
        assertEquals("a group of one", 0.0, rhythmT(0, 1, "none"), 1e-12)
        assertEquals("a group of none", 0.0, rhythmT(0, 0, "none"), 1e-12)
        assertEquals("first of two", 0.0, rhythmT(0, 2, "none"), 1e-12)
        assertEquals("second of two", 1.0, rhythmT(1, 2, "none"), 1e-12)
    }

    /**
     * T-122: `accelerando` is `base ** 1.35`.
     *
     * The five values are the server's own at n = 5. The exponent is what is
     * measured: the port squared its base, which puts member 1 at 0.0625 where
     * the server puts it at 0.1539 -- and squaring passes any gate that only
     * asks for "a curve that starts slow and ends at 1".
     */
    @Test
    fun testAccelerandoRaisesTheBaseToTheServersExponent() {
        val expected = listOf(
            0.0,
            0.1538930516681145,
            0.3922920489483753,
            0.678160836085047,
            1.0,
        )
        for (i in expected.indices) {
            assertEquals("accelerando i=$i", expected[i], rhythmT(i, 5, "accelerando"), 1e-12)
        }
    }

    /**
     * T-123: the `loose` jitter is a flat 0.16, and does not know how many
     * members there are.
     *
     * The port divided it by `max(n/8, 1)`, so the same seed drew a beat 2.5
     * times smaller at twenty members than at eight. Both counts are measured
     * because the divisor is 1 at eight -- reading only the small group would
     * leave the division invisible. And the displacement itself is pinned to the
     * server's value, because "the two counts agree" is also true of a jitter
     * that is flat but the wrong size.
     */
    @Test
    fun testTheLooseJitterDoesNotKnowHowManyMembersThereAre() {
        val atEight = rhythmT(3, 8, "loose") - 3.0 / 7.0
        val atTwenty = rhythmT(3, 20, "loose") - 3.0 / 19.0
        assertEquals("the server's displacement at n=8", 0.025164154196429, atEight, 1e-12)
        assertEquals("the server's displacement at n=20", 0.025164154196429, atTwenty, 1e-12)
    }

    /**
     * T-124: `syncopated` beats the server's two constants on the server's
     * parity.
     *
     * The port beat -0.055 on the even index and 0.085 on the odd one; the
     * server beats 0.09 on the odd index and -0.045 on the even one. Both the
     * sizes and which index gets which are read here: member 2 lands on
     * `base - 0.045 * sin(pi/2)` = 0.455, which no swap of the parity produces.
     */
    @Test
    fun testSyncopatedBeatsTheServersConstantsOnTheServersParity() {
        val expected = listOf(
            0.0,
            0.3136396103067893,
            0.455,
            0.8136396103067893,
            1.0,
        )
        for (i in expected.indices) {
            assertEquals("syncopated i=$i", expected[i], rhythmT(i, 5, "syncopated"), 1e-12)
        }
    }

    /**
     * T-125: and the even spacing did not move.
     *
     * The control for the three above. Every arrangement the frozen corpus holds
     * is `none`, so this is the branch that must not be touched while the other
     * three are being corrected.
     */
    @Test
    fun testTheEvenSpacingDidNotMove() {
        val expected = listOf(0.0, 0.25, 0.5, 0.75, 1.0)
        for (i in expected.indices) {
            assertEquals("none i=$i", expected[i], rhythmT(i, 5, "none"), 1e-12)
        }
    }
}
