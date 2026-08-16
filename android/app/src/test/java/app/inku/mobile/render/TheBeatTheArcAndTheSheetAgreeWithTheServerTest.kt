package app.inku.mobile.render

import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONArray
import org.json.JSONObject
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
    private fun countOccurrences(haystack: String, needle: String): Int =
        haystack.split(needle).size - 1

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

    // ---- [I-274] the varied arc ------------------------------------------

    /**
     * The arc the whole of stage 2 is measured on: 280 degrees on a 1000x1000
     * sheet at r = 300 px, which the server measures at 1466.0766 px and cuts
     * into 147 segments -- 148 points.
     */
    private fun arc(weight: String, varied: Boolean): JSONObject {
        val ins = JSONObject(
            """
            {"primitive":"arc","center":[0.5,0.5],"radius":0.3,
             "angle_start":20,"angle_end":300,"weight":"$weight"}
            """.trimIndent()
        )
        if (varied) {
            ins.put(
                "variation",
                JSONObject("""{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_y"]}"""),
            )
        }
        return ins
    }

    private fun renderScore(instruction: JSONObject, aspect: String = "square"): String {
        val score = JSONObject().put("instructions", JSONArray().put(instruction))
        return DefaultSvgRenderer().render(
            RenderRequest(
                scoreJson = score.toString(),
                colorCatalogId = "default",
                canvasAspect = aspect,
                svgProfile = "editable",
                renderSeed = seed,
            )
        ).svg
    }

    /**
     * The arc's points, whichever element carries them.
     *
     * A `<polyline points>` is read straight; a `<path d>` of `M` and `L` is
     * read the same way. Which element the port writes is T-126's question
     * alone -- if this helper only knew about the polyline, replacing it with a
     * path would redden T-127 through T-129 as well, and three gates that all
     * fail for one reason cannot say which quantity moved.
     */
    private fun arcPointsOf(svg: String): List<String> {
        Regex(" points=\"([^\"]*)\"").find(svg)?.let { return it.groupValues[1].split(" ") }
        val d = Regex(" d=\"([^\"]*)\"").findAll(svg).map { it.groupValues[1] }
            .firstOrNull { it.contains(" L ") } ?: return emptyList()
        return d.removePrefix("M ").split(" L ").map { it.trim().replace(" ", ",") }
    }

    /** The two ends of the arc command the port writes when nothing wobbles:
     * `M x y A rx ry rot large sweep x y`. */
    private fun plainArcEnds(svg: String): Pair<String, String> {
        val d = Regex(" d=\"([^\"]*)\"").find(svg)!!.groupValues[1]
        val n = Regex("-?\\d+\\.\\d+").findAll(d).map { it.value }.toList()
        return "${n[0]},${n[1]}" to "${n[n.size - 2]},${n[n.size - 1]}"
    }

    /**
     * T-126: a wobbling geometric arc is a `<polyline>`, and one that does not
     * wobble is still a `<path>`.
     *
     * The server keeps both branches (`_render_instruction`: `dwg.polyline` when
     * the contour varies, `_arc_path_d` otherwise) and the port wrote a `<path>`
     * for both -- an `M`/`L` run inside a `d`, which draws the same ink but is
     * not the same document. The second half is the control: emitting a polyline
     * unconditionally would answer the first half and be just as wrong.
     */
    @Test
    fun testAWobblingGeometricArcIsAPolylineAndAPlainOneIsAPath() {
        val varied = renderScore(arc("rotring", varied = true))
        assertEquals("one polyline", 1, countOccurrences(varied, "<polyline"))
        assertEquals("and no path", 0, countOccurrences(varied, "<path"))

        val plain = renderScore(arc("rotring", varied = false))
        assertEquals("one path", 1, countOccurrences(plain, "<path"))
        assertEquals("and no polyline", 0, countOccurrences(plain, "<polyline"))
        assertTrue("still an arc command", plain.contains(" A 300.000000 300.000000 "))
    }

    /**
     * T-127: it is sampled 148 times -- `segmentCount` plus one.
     *
     * The server puts a point on both ends of every segment; the port put one
     * per segment and so drew the arc one point short, which moves every sample
     * after the first because the phase is measured against the count.
     */
    @Test
    fun testTheArcIsSampledOnePointMoreThanItHasSegments() {
        assertEquals(
            "the server samples this arc 148 times",
            148,
            arcPointsOf(renderScore(arc("rotring", varied = true))).size,
        )
    }

    /**
     * T-128: the two ends do not wobble.
     *
     * They are the `touching` contract: a second arc asked to meet this one
     * meets it at the coordinates the geometry says, so those two points are
     * placed unwobbled and everything between them is not. Both halves are
     * measured -- if the middle did not move either, the wobble would not be
     * running at all and the fixed ends would prove nothing.
     */
    @Test
    fun testTheArcsTwoEndsDoNotWobble() {
        val points = arcPointsOf(renderScore(arc("rotring", varied = true)))
        val (plainFirst, plainLast) = plainArcEnds(renderScore(arc("rotring", varied = false)))
        assertEquals("the first point is where the plain arc starts", plainFirst, points.first())
        assertEquals("the last point is where the plain arc ends", plainLast, points.last())
        // The unwobbled point 74 on the server, against the wobbled one below.
        assertNotEquals("but the middle of the arc did move", "216.425700,402.093839", points[74])
    }

    /**
     * T-129: and the phase is `i / last`, not `i / count`.
     *
     * Both readings agree at the two ends, so only a point in the middle can
     * tell them apart: at i = 74 the server's phase is 0.503401 and puts the
     * point at y = 402.192664, where `i / count` gives 0.5 and 402.217861. The
     * coordinate is the server's own.
     */
    @Test
    fun testTheWobbleIsSampledAtTheServersPhase() {
        val points = arcPointsOf(renderScore(arc("rotring", varied = true)))
        assertEquals("point 74 is the server's", "216.425700,402.192664", points[74])
    }

    /**
     * T-130: the hand-stroke arc did not move.
     *
     * The control for the whole of stage 2. `arcPointsWithVariation` is the
     * other copy of the same idea and it already agreed with the server, down to
     * writing the arc's length as `2*pi*r*|end-start|/360` -- so it is pinned
     * here at both of the server's counts, with and without a wobble, and its
     * powder with it.
     */
    @Test
    fun testTheHandStrokeArcDidNotMove() {
        val varied = renderScore(arc("pencil", varied = true))
        assertTrue(
            "the varied centreline keeps the server's 148 samples",
            varied.contains("arc-stroke-v1 controls-148 events-1"),
        )
        assertEquals("and its 55 specks", 55, Regex("<circle[ />]").findAll(varied).count())

        val plain = renderScore(arc("pencil", varied = false))
        assertTrue(
            "the plain centreline keeps the server's 72 samples",
            plain.contains("arc-stroke-v1 controls-72 events-0"),
        )
        assertEquals("and its 55 specks", 55, Regex("<circle[ />]").findAll(plain).count())
    }
}
