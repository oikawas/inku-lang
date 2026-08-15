package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import kotlin.math.abs
import kotlin.math.hypot
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The four rulers render engines 27-30 moved, asserted as properties.
 *
 * The frozen corpus already says "this version's output is this"; it cannot say why, and
 * it cannot say anything about a canvas or a tool it does not hold. These are the claims
 * that survive a rebake.
 */
class TheMarkIsMeasuredTheWayTheServerMeasuresItTest {

    private val renderer = DefaultSvgRenderer()

    private fun render(
        instruction: JSONObject,
        aspect: String = "square",
        seed: Long? = 12345L,
    ): String = renderer.render(
        RenderRequest(
            scoreJson = JSONObject().put("instructions", JSONArray().put(instruction)).toString(),
            colorCatalogId = "default",
            canvasAspect = aspect,
            svgProfile = "editable",
            renderSeed = seed,
        )
    ).svg

    private fun circle(weight: String, radius: Double = 0.25): JSONObject = JSONObject()
        .put("primitive", "circle")
        .put("center", JSONArray(listOf(0.5, 0.5)))
        .put("radius", radius)
        .put("weight", weight)
        .put("color", "black")

    // T-5 ------------------------------------------------------------------

    /**
     * The material layer stopped being a dotted line, and `style` did not.
     *
     * Both halves in one test on purpose: an implementation that simply deleted every
     * dasharray would pass the first claim perfectly, and `style: dashed` is a thing the
     * description asked for rather than a tool losing the paper.
     */
    @Test
    fun testTheMaterialLayerNeverDashesAndTheStatedStyleStillDoes() {
        for (weight in listOf("pencil", "chalk", "brush_thin", "brush_thick", "crayon", "pen")) {
            val svg = render(circle(weight))
            val strata = Regex("""<[a-z]+\b[^>]*class="material-outline[^"]*"[^>]*>""").findAll(svg).toList()
            assertTrue("$weight must wear a material layer at all", strata.isNotEmpty())
            for (element in strata) {
                assertFalse(
                    "no material stratum may carry a dasharray ($weight): ${element.value.take(160)}",
                    element.value.contains("stroke-dasharray"),
                )
            }
        }

        // The stated styles are a different mechanism and keep their patterns. rotring owns
        // no material layer, so nothing here is confused with a stratum.
        // The patterns are px constants mapped onto the canvas unit, so the document
        // carries them at the renderer's six decimals rather than as written in the table.
        val stated = mapOf(
            "dashed" to "12.000000,8.000000",
            "dotted" to "2.000000,6.000000",
            "dash_dot" to "12.000000,6.000000,2.000000,6.000000",
        )
        for ((style, pattern) in stated) {
            val line = JSONObject()
                .put("primitive", "line")
                .put("from", JSONArray(listOf(0.1, 0.5)))
                .put("to", JSONArray(listOf(0.9, 0.5)))
                .put("weight", "rotring")
                .put("style", style)
                .put("color", "black")
            val svg = render(line)
            assertTrue(
                "style $style must still write stroke-dasharray=\"$pattern\"",
                svg.contains("""stroke-dasharray="$pattern""""),
            )
        }
    }

    // T-6 ------------------------------------------------------------------

    /**
     * The wander is read against the mark, not against the figure.
     *
     * The claim is not "the ratio is a constant" -- the sampling of a wave lands where it
     * lands, so it is not -- but "the ratio does not follow the radius". Under the ruler
     * this replaced, a wander of 8% of the representative size made the ratio grow
     * linearly with the radius, so the correlation is what separates the two rulers.
     *
     * 48 combinations, the way the server measured it: four tools spanning 1.5px to 8px,
     * three thinnesses, four radii spanning 8x.
     */
    @Test
    fun testTheWanderFollowsTheStrokeWidthAndNotTheRadius() {
        val unit = 1000.0
        val radii = listOf(0.05, 0.12, 0.25, 0.40)
        val rows = mutableListOf<Triple<Double, Double, String>>()
        for (weight in listOf("pencil", "pen", "crayon", "brush_thick")) {
            for (thinness in listOf(null, "fine", "extra_fine")) {
                for (radius in radii) {
                    val variation = JSONObject()
                        .put("quality", "wave")
                        .put("amplitude", "medium")
                        .put("frequency", "medium")
                        .put("dimensions", JSONArray(listOf("radius")))
                    val ins = circle(weight, radius).put("variation", variation)
                    if (thinness != null) ins.put("thinness", thinness)
                    val radiusPx = radius * unit
                    val points = ServerRendererGeometry.variedCirclePoints(
                        500.0, 500.0, radiusPx, radiusPx, variation, 12345L, ins, unit, unit, unit
                    )
                    // The wander is read back as the root-mean-square of the radial
                    // offset times root two, not as its largest sample. A sine's peak is
                    // only reached if a sample happens to land on the crest, and how many
                    // samples there are follows the path length -- so the peak estimator
                    // would report the SAMPLING as a function of the radius and hide the
                    // quantity being measured. The samples cover whole periods uniformly,
                    // so the RMS estimator is exact for every count.
                    val offsets = points.map { hypot(it.first - 500.0, it.second - 500.0) - radiusPx }
                    val deviation = Math.sqrt(offsets.sumOf { it * it } / offsets.size) * Math.sqrt(2.0)
                    val width = ServerRendererStyle.strokeWidth(weight, unit, thinness)
                    rows.add(Triple(radius, deviation / width, "$weight/$thinness/r=$radius"))
                }
            }
        }
        assertEquals("48 combinations, as the server measured", 48, rows.size)

        val ratios = rows.map { it.second }
        val minRatio = ratios.min()
        val maxRatio = ratios.max()
        assertTrue(
            "every combination must wander six tenths of its own width (saw $minRatio..$maxRatio)",
            minRatio > 0.599 && maxRatio < 0.601,
        )

        // The claim that separates the two rulers, stated as an effect size rather than
        // as a correlation coefficient. A correlation is scale-free, so it reports the
        // 0.1% residual left by the sample count as loudly as it would report the thing
        // being tested; across these radii the ruler this replaced spreads the ratio by
        // the radius ratio itself, which is 8.0.
        for ((group, groupRows) in rows.groupBy { it.third.substringBeforeLast("/r=") }) {
            val spread = groupRows.maxOf { it.second } / groupRows.minOf { it.second }
            assertTrue(
                "$group: the ratio must not follow the radius -- an 8x change in radius " +
                    "moved it by ${(spread - 1.0) * 100}%, where the figure-size ruler would move it 8x",
                spread < 1.01,
            )
        }
    }

    // T-7 ------------------------------------------------------------------

    /**
     * Two rules narrow the tone, and they read different widths.
     *
     * The cap reads the tool's NOMINAL stroke -- paper tooth and powder do not get finer
     * because the line was drawn finer -- and the floor that keeps a stratum outside the
     * mark reads the ACTUAL one. An implementation that read the same width in both places
     * passes every corpus case where no thinness is stated, so the cases below are chosen
     * where the two widths differ.
     */
    @Test
    fun testTheCapReadsTheNominalWidthAndTheFloorReadsTheActualOne() {
        val unit = 1000.0

        // brush_thin, extra_fine. Nominal 3.0 -> cap 0.99. Actual max(3.0*0.35, 0.5) = 1.05,
        // which would cap at 0.3465 -- a third of the value the server states.
        val thinned = ServerRendererMaterial.materialOutlineProfile("brush_thin", unit, "extra_fine")
        assertEquals("brush_thin states two strata", 2, thinned.size)
        assertEquals("the cap is 0.33 of the NOMINAL 3.0px stroke", 0.99, thinned[1].width, 1e-12)
        assertNotEquals(
            "reading the thinned width here would give a third of that",
            0.33 * ServerRendererStyle.strokeWidth("brush_thin", unit, "extra_fine"),
            thinned[1].width,
            1e-6,
        )
        assertEquals(
            "and the cap does not move when the line is thinned",
            ServerRendererMaterial.materialOutlineProfile("brush_thin", unit, null)[1].width,
            thinned[1].width,
            1e-12,
        )

        // crayon. Actual 4.0 -> half 2.0, so the table's -1.5 is pushed out to -2.0. Thinned
        // to extra_fine the mark is 1.4 -> half 0.7, and -1.5 is already outside it. Reading
        // the nominal width in the floor would push both to -2.0.
        val crayonNominal = ServerRendererMaterial.materialOutlineProfile("crayon", unit, null)
        val crayonThin = ServerRendererMaterial.materialOutlineProfile("crayon", unit, "extra_fine")
        assertEquals("the floor is half of the ACTUAL 4.0px mark", -2.0, crayonNominal[1].offset, 1e-12)
        assertEquals("thinned, the mark is narrower and the table's own -1.5 already clears it",
            -1.5, crayonThin[1].offset, 1e-12)

        // And the two rules hold for every tool and every thinness, not only the two above.
        for (weight in listOf("pencil", "chalk", "brush_thin", "brush_thick", "crayon", "pen")) {
            for (thinness in listOf(null, "fine", "extra_fine")) {
                val nominal = ServerRendererStyle.strokeWidth(weight, unit)
                val actual = ServerRendererStyle.strokeWidth(weight, unit, thinness)
                for (layer in ServerRendererMaterial.materialOutlineProfile(weight, unit, thinness)) {
                    assertTrue(
                        "$weight/$thinness: a stratum may not be wider than 0.33 of the nominal mark",
                        layer.width <= nominal * ServerRendererMaterial.MATERIAL_OUTLINE_MAX_WIDTH_RATIO + 1e-12,
                    )
                    assertTrue(
                        "$weight/$thinness: a stratum may not sit inside the actual mark",
                        abs(layer.offset) >= actual / 2.0 - 1e-12,
                    )
                }
            }
        }
    }

    // T-8 ------------------------------------------------------------------

    /**
     * The contact decision counts on the SVG's own six-decimal lattice.
     *
     * Asserted where it is consumed, not only on the helper: a probe nothing reads is
     * true of any implementation. The pair of walks below is built so that the lattice is
     * the only thing that decides how many samples come out -- a step of 2.0000004 rounds
     * down to 2.0 and reaches the end of a 10px line exactly, while the unrounded value
     * overshoots it and loses the last sample.
     */
    @Test
    fun testTheContactLengthsSitOnTheSixDecimalLattice() {
        val line = listOf(0.0 to 0.0, 10.0 to 0.0)

        // The step. 2.0000004 -> 2.0 (5 steps land on 10.0 exactly, so 6 points).
        assertEquals(
            "an off-lattice step must be counted as its rounded self",
            6,
            ServerRendererMaterial.resampleByLength(line, 2.0000004, false).size,
        )
        // The same input one lattice place further does change the answer, so the check
        // above is not blind: 2.0000006 -> 2.000001, which overshoots 10.0.
        assertEquals(
            "a step that rounds to a different lattice point must give a different walk",
            5,
            ServerRendererMaterial.resampleByLength(line, 2.0000006, false).size,
        )

        // The segment length. 9.9999996 -> 10.0, so the fifth step still lands on it.
        val shortLine = listOf(0.0 to 0.0, 9.9999996 to 0.0)
        assertEquals(
            "an off-lattice segment must be counted as its rounded self",
            6,
            ServerRendererMaterial.resampleByLength(shortLine, 2.0, false).size,
        )
        val shorterLine = listOf(0.0 to 0.0, 9.9999994 to 0.0)
        assertEquals(
            "a segment that rounds down does lose the sample",
            5,
            ServerRendererMaterial.resampleByLength(shorterLine, 2.0, false).size,
        )

        // The lattice itself, over the magnitudes the five quantities span: a segment of a
        // fraction of a px, a fragment near the 0.6px floor, a grain of a few px, a step,
        // and a closed contour's total arc length.
        val magnitudes = listOf(
            0.12345678901, 0.5999999123, 2.66674486741, 8.0000004999, 1600.6469204482155
        )
        for (value in magnitudes) {
            val quantised = ServerRendererMaterial.quantiseContactLength(value)
            val scaled = quantised * 1e6
            assertEquals(
                "$value must land on the six-decimal lattice, saw $quantised",
                Math.rint(scaled),
                scaled,
                0.0,
            )
            assertTrue("$value must not move by more than half a lattice step", abs(quantised - value) <= 5e-7)
        }
    }

    // T-9 ------------------------------------------------------------------

    /**
     * On a square canvas the short-edge mouth is the identity, bit for bit.
     *
     * This alone would pass without stage 4 ever being written, which is why it is stated
     * beside T-10 rather than on its own: together they say the mouth changed the tall
     * canvases and left the square one exactly where it was.
     */
    @Test
    fun testASquareCanvasCannotTellTheNewArithmeticFromTheOld() {
        val width = 1000.0
        val height = 1000.0
        val unit = 1000.0
        for (w in listOf(0.4, 0.2, 0.0, 1.0, 0.123456789)) {
            for (h in listOf(0.4, 0.2, 0.0, 1.0, 0.987654321)) {
                val (newW, newH) = ServerRendererGeometry.sizePx(w, h, width, height, unit)
                assertEquals("width extent, square canvas", w * width, newW, 0.0)
                assertEquals("height extent, square canvas", h * height, newH, 0.0)
            }
        }
    }

    // T-10 -----------------------------------------------------------------

    /**
     * On a canvas that is not square, a mark keeps the proportion the description gave it.
     *
     * Both directions, in one test: a wide ellipse must stay wide and a tall one must stay
     * tall. One direction alone would pass an implementation that had simply swapped the
     * two extents. rotring is the tool because it draws the analytic `<ellipse>`, so rx
     * and ry can be read straight off the document.
     */
    @Test
    fun testATallCanvasDoesNotTurnAWideEllipseOnItsSide() {
        fun radii(sizeW: Double, sizeH: Double, aspect: String): Pair<Double, Double> {
            val ins = JSONObject()
                .put("primitive", "ellipse")
                .put("center", JSONArray(listOf(0.5, 0.5)))
                .put("size", JSONArray(listOf(sizeW, sizeH)))
                .put("weight", "rotring")
                .put("color", "black")
            val svg = render(ins, aspect = aspect)
            val match = Regex("""<ellipse[^>]*\brx="([^"]+)"[^>]*\bry="([^"]+)"""").find(svg)
                ?: error("no analytic ellipse in $aspect: ${svg.take(400)}")
            return match.groupValues[1].toDouble() to match.groupValues[2].toDouble()
        }

        // pillar is 200 x 1000. Stretching the extents separately made 0.4 x 0.2 come out
        // 40 x 100 -- taller than it is wide, the opposite of what was written.
        val (wideRx, wideRy) = radii(0.4, 0.2, "pillar")
        assertTrue("a wide ellipse must stay wide on a pillar (rx=$wideRx ry=$wideRy)", wideRx > wideRy)
        assertEquals("and the ratio must be the one the description gave", 2.0, wideRx / wideRy, 1e-9)

        val (tallRx, tallRy) = radii(0.2, 0.4, "pillar")
        assertTrue("a tall ellipse must stay tall on a pillar (rx=$tallRx ry=$tallRy)", tallRy > tallRx)
        assertEquals("and the ratio must be the one the description gave", 2.0, tallRy / tallRx, 1e-9)

        // The same on a canvas that is wider than it is tall, so the claim is not about
        // which of the two edges happens to be short.
        val (cinemaRx, cinemaRy) = radii(0.4, 0.2, "wide")
        assertEquals("a 2:1 ellipse is 2:1 on a cinema canvas too", 2.0, cinemaRx / cinemaRy, 1e-9)

        // A square stays square on every canvas, which is the whole ruling in one line.
        for (aspect in listOf("square", "pillar", "wide", "vertical", "oban")) {
            val (rx, ry) = radii(0.3, 0.3, aspect)
            assertEquals("a square mark stays square on $aspect", rx, ry, 0.0)
        }
    }
}
