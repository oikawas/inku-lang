package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/**
 * A grain is one touch, and a band is made of them (render engine 36's surface
 * layer, ported).
 *
 * Four words arrive together because they share one mechanism: `stipple`,
 * `grain` and `paper_grain` scatter positions inside the outline and set the
 * tool down once at each, and `aquatint` scatters the same way and then lets
 * the band a grain fell into decide how dark it is.
 *
 * None of this can be gated by the frozen corpus. Of the 51 drawings only two
 * carry a surface at all and both say `hatch`, all 51 are `editable`, and not
 * one of them holds a `filter="` -- so these are properties, measured on what
 * the port itself draws. The claims are the server's own `test_s8_stipple_*`
 * and `test_s8_aquatint_*`, put again rather than copied.
 */
class AGrainIsOneTouchTest {

    /** `square` resolves to 1000x1000, so a stated ratio reads straight as pixels. */
    private val unit = 1000.0
    private val canvasPx = 1000.0
    private val renderSeed = 12345L

    /** The server's two shapes, to the digit. */
    private val shapes = listOf("square", "triangle")

    private val grainWords = listOf("stipple", "grain", "paper_grain")

    /**
     * The tools these run on, and why they are not `pencil`.
     *
     * The surface layer's own grains are `<circle>` elements without a class
     * when the tool is a machine pole, which is exactly what the material layer
     * draws for `pencil` as well (`ServerRendererMaterial`, 66 of them on this
     * square). Nothing in the markup tells the two apart, so a count taken with
     * `pencil` would be counting the shape's own grain along with the surface's.
     * `pen` is a hand tool that draws no circle anywhere, and `rotring` is the
     * machine pole whose every circle is a grain -- between them the two roads
     * through `surfaceDab` are readable without ambiguity.
     *
     * The filter gates below are the exception: no filter is defined for `pen`
     * or `rotring` at all, so T-164 and T-165 have to run on `pencil` and read
     * the paths, where the class does tell them apart.
     */
    private val handTool = "pen"
    private val machinePole = "rotring"

    private fun surfaceJson(texture: String, density: Double, toneSteps: Int): String =
        """{"texture":"$texture","density":$density,"scale":0.4,"opacity":0.36,"bleed":0.25,""" +
            """"direction":"diagonal_rising","spacing_gradient":"none","tone_steps":$toneSteps,"seed":24680}"""

    private fun instructionJson(
        primitive: String,
        texture: String,
        weight: String,
        density: Double,
        toneSteps: Int,
    ): String =
        """{"primitive":"$primitive","position":[0.28,0.28],"size":[0.44,0.44],""" +
            """"weight":"$weight","filled":false,"surface":${surfaceJson(texture, density, toneSteps)}}"""

    private fun renderSvg(
        primitive: String,
        texture: String,
        weight: String = "pen",
        profile: String = "editable",
        density: Double = 0.55,
        toneSteps: Int = 3,
    ): String = DefaultSvgRenderer().render(
        RenderRequest(
            scoreJson = """{"instructions":[${instructionJson(primitive, texture, weight, density, toneSteps)}]}""",
            colorCatalogId = "default",
            canvasAspect = "square",
            svgProfile = profile,
            renderSeed = renderSeed,
        )
    ).svg

    private fun contourOf(primitive: String, texture: String, weight: String): List<Pair<Double, Double>> {
        val ins = JSONObject(instructionJson(primitive, texture, weight, 0.55, 3))
        return DefaultSvgRenderer().surfaceContour(ins, canvasPx, canvasPx, unit, renderSeed, 0, 0)!!
    }

    // ---- reading the grains out of the drawing -------------------------------

    private class Grain(
        val element: String,
        val classes: String,
        val centre: Pair<Double, Double>,
        val opacity: Double,
    ) {
        val carriesFilter = element.contains("""filter="url(#texture-""")
        val step: Int? = Regex("""aquatint-step-(\d+)""").find(classes)?.groupValues?.get(1)?.toInt()
    }

    /** Every `<path>` the surface layer laid down, whatever else the drawing holds. */
    private fun surfaceStrokes(svg: String): List<Grain> =
        Regex("""<path\b[^>]*class="surface-stroke-v1[^"]*"[^>]*/>""").findAll(svg).map { match ->
            val element = match.value
            val d = Regex(""" d="([^"]*)"""").find(element)?.groupValues?.get(1).orEmpty()
            val points = Regex("""(-?[0-9.]+) (-?[0-9.]+)""").findAll(d)
                .map { it.groupValues[1].toDouble() to it.groupValues[2].toDouble() }.toList()
            // A dab is one short stroke laid along its own centre line, and
            // `contourStrokePath` writes the two banks into one ring, so the
            // mean of the vertices is where the tool was set down.
            val centre = if (points.isEmpty()) {
                0.0 to 0.0
            } else {
                points.sumOf { it.first } / points.size to points.sumOf { it.second } / points.size
            }
            Grain(
                element = element,
                classes = Regex("""\bclass="([^"]*)"""").find(element)?.groupValues?.get(1).orEmpty(),
                centre = centre,
                opacity = Regex("""fill-opacity="([0-9.]+)"""").find(element)?.groupValues?.get(1)?.toDouble() ?: 1.0,
            )
        }.toList()

    /**
     * Every `<circle>` in the drawing.
     *
     * Only ever read for [machinePole] and [handTool], where the shape itself
     * contributes none -- see the note on those two.
     */
    private fun circles(svg: String): List<Grain> =
        Regex("""<circle\b[^>]*/>""").findAll(svg).map { match ->
            val element = match.value
            Grain(
                element = element,
                classes = Regex("""\bclass="([^"]*)"""").find(element)?.groupValues?.get(1).orEmpty(),
                centre = (Regex("""\bcx="(-?[0-9.]+)"""").find(element)?.groupValues?.get(1)?.toDouble() ?: 0.0) to
                    (Regex("""\bcy="(-?[0-9.]+)"""").find(element)?.groupValues?.get(1)?.toDouble() ?: 0.0),
                opacity = Regex("""\bopacity="([0-9.]+)"""").find(element)?.groupValues?.get(1)?.toDouble() ?: 1.0,
            )
        }.toList()

    /** Whichever of the two roads the tool takes, the grains it laid. */
    private fun grainsOf(svg: String, weight: String): List<Grain> =
        if (weight == machinePole) circles(svg) else surfaceStrokes(svg)

    private fun pointInPolygon(x: Double, y: Double, polygon: List<Pair<Double, Double>>): Boolean {
        var inside = false
        for (index in polygon.indices) {
            val (ax, ay) = polygon[index]
            val (bx, by) = polygon[(index + 1) % polygon.size]
            if ((ay > y) != (by > y)) {
                val t = (y - ay) / (by - ay)
                if (x < ax + (bx - ax) * t) inside = !inside
            }
        }
        return inside
    }

    /** The distance out to the contour when the point is outside it, else 0. */
    private fun distanceOutside(point: Pair<Double, Double>, contour: List<Pair<Double, Double>>): Double {
        if (pointInPolygon(point.first, point.second, contour)) return 0.0
        var best = Double.MAX_VALUE
        for (index in contour.indices) {
            val (ax, ay) = contour[index]
            val (bx, by) = contour[(index + 1) % contour.size]
            val dx = bx - ax
            val dy = by - ay
            val lengthSq = dx * dx + dy * dy
            var t = if (lengthSq == 0.0) 0.0 else ((point.first - ax) * dx + (point.second - ay) * dy) / lengthSq
            t = max(0.0, min(1.0, t))
            best = min(best, hypot(point.first - (ax + dx * t), point.second - (ay + dy * t)))
        }
        return best
    }

    /**
     * The ceiling this suite claims, written here and not read from the product.
     *
     * ⚠ Comparing the drawing against the constant that produced it says
     * nothing: raise [SURFACE_MARK_MAX] and an expectation read from it rises
     * with the drawing, which is how the first version of T-154 sat green
     * through exactly that perturbation. So the number is stated here, the
     * drawing is measured against it, and the product's constant is compared
     * against it separately.
     */
    private val statedMarkCeiling = 90

    /**
     * T-157. A grain is put inside the shape it belongs to.
     *
     * The centre of every grain, on both roads through `surfaceDab`. On the
     * machine pole the centre is the scattered point to the digit; on the hand
     * road it is the mean of the stroke's vertices, and the material engine's
     * wander does not move it out -- measured 0.00px of excursion on all 358
     * grains the four cases draw.
     */
    @Test
    fun testAGrainPutsItsMarksInsideTheShape() {
        for (primitive in shapes) {
            for (texture in grainWords) {
                for (weight in listOf(handTool, machinePole)) {
                    val grains = grainsOf(renderSvg(primitive, texture, weight = weight), weight)
                    assertTrue("$primitive/$texture/$weight: the surface must put down grains", grains.isNotEmpty())
                    val contour = contourOf(primitive, texture, weight)
                    for (grain in grains) {
                        assertEquals(
                            "$primitive/$texture/$weight: a grain sits at ${grain.centre}, outside the contour",
                            0.0,
                            distanceOutside(grain.centre, contour),
                            0.0,
                        )
                    }
                }
            }
        }
    }

    /**
     * T-158. The scatter answers the density, and stops at the ceiling.
     *
     * Two claims in one place because either alone is weak: a count that
     * ignores the density passes a ceiling test, and a ceiling that never binds
     * passes a density test. The realised count runs a mark or two under the
     * asked-for one -- `surfaceScatter` hands each scan segment its whole share
     * and rounds the remainder by a hash -- so the ceiling is read as a band of
     * three around the stated number rather than as an equality.
     */
    @Test
    fun testTheScatterStopsAtTheMarkCeiling() {
        assertEquals("the product's ceiling is the one this test states", statedMarkCeiling, SURFACE_MARK_MAX)

        for (primitive in shapes) {
            val sparse = grainsOf(renderSvg(primitive, "stipple", density = 0.05), handTool).size
            val dense = grainsOf(renderSvg(primitive, "stipple", density = 1.0), handTool).size
            assertTrue(
                "$primitive: a thin surface must stay well under the ceiling, drew $sparse",
                sparse in 1 until statedMarkCeiling - 20,
            )
            assertTrue("$primitive: density must reach the count, $sparse to $dense", sparse < dense)
            assertTrue(
                "$primitive: a dense surface must stop at the ceiling of $statedMarkCeiling, drew $dense",
                dense >= statedMarkCeiling - 2 && dense <= statedMarkCeiling + 1,
            )
        }
    }

    /**
     * T-159. The three words are three names for one act.
     *
     * The server holds them in one set, and this is that claim: at the same
     * seed the surface layer writes the same elements for all three, byte for
     * byte. Only the surface layer -- the whole drawing differs, because the
     * instruction's own seed is a hash of the instruction and the texture word
     * is in it, so the shape's outline is performed differently. That is the
     * server's behaviour too.
     */
    @Test
    fun testTheThreeGrainWordsDrawTheSameThing() {
        for (primitive in shapes) {
            val drawn = grainWords.map { texture ->
                surfaceStrokes(renderSvg(primitive, texture)).map { it.element }
            }
            assertTrue("$primitive: the first word must draw something", drawn.first().isNotEmpty())
            for ((index, word) in grainWords.withIndex()) {
                assertEquals("$primitive: $word must draw what stipple draws", drawn.first(), drawn[index])
            }
        }
    }

    /**
     * T-160. A grain is not a circle.
     *
     * It is the mark a tool leaves where it was set down once, so the hand road
     * lays one of the material engine's strokes and only the machine pole gets
     * the geometry. Both directions are read: were the hand road removed the
     * first assertion fails, and were the machine's branch ignored the second
     * does.
     */
    @Test
    fun testAGrainIsNotACircleForAHandTool() {
        for (primitive in shapes) {
            val byHand = renderSvg(primitive, "stipple", weight = handTool)
            assertTrue("$primitive: a hand tool draws its grains as strokes", surfaceStrokes(byHand).isNotEmpty())
            assertEquals("$primitive: and draws no circle at all", 0, circles(byHand).size)

            val byMachine = renderSvg(primitive, "stipple", weight = machinePole)
            assertTrue("$primitive: the machine pole draws its grains as circles", circles(byMachine).isNotEmpty())
            assertEquals("$primitive: and performs no stroke", 0, surfaceStrokes(byMachine).size)
        }
    }

    /**
     * T-161. An aquatint puts out one step per band.
     *
     * The number of bands is the one the surface asked for, stated in the score
     * and read back from the class names -- never from a product constant. Run
     * at 2, 3 and 4 because the band count is the quantity under test.
     */
    @Test
    fun testAquatintPutsOutOneStepPerBand() {
        for (primitive in shapes) {
            for (steps in listOf(2, 3, 4)) {
                val grains = surfaceStrokes(renderSvg(primitive, "aquatint", toneSteps = steps))
                assertTrue("$primitive/$steps: an aquatint must put down grains", grains.isNotEmpty())
                assertEquals(
                    "$primitive/$steps: every grain names the band it fell in",
                    emptyList<Grain>(),
                    grains.filter { it.step == null },
                )
                assertEquals(
                    "$primitive/$steps: the bands present must be 1..$steps",
                    (1..steps).toList(),
                    grains.mapNotNull { it.step }.distinct().sorted(),
                )
            }
        }
    }

    /**
     * T-162. The nudge at a band's border does not put a grain outside.
     *
     * The border is moved once per band so a step reads as a tone rather than
     * as a ruled edge, and a nudge that lands outside the outline is given
     * back. It has teeth: measured on these six cases, the nudge would carry 1
     * grain out of the square and 2 to 4 out of the triangle if it were not.
     * Read on the machine pole as well as the hand road, because there the
     * centre is the nudged point itself and no averaging can hide a pixel of
     * excursion.
     */
    @Test
    fun testAquatintKeepsItsGrainsInsideTheContour() {
        for (primitive in shapes) {
            for (steps in listOf(2, 3, 4)) {
                for (weight in listOf(handTool, machinePole)) {
                    val grains = grainsOf(renderSvg(primitive, "aquatint", weight = weight, toneSteps = steps), weight)
                    assertTrue("$primitive/$steps/$weight: an aquatint must put down grains", grains.isNotEmpty())
                    val contour = contourOf(primitive, "aquatint", weight)
                    for (grain in grains) {
                        assertEquals(
                            "$primitive/$steps/$weight: a grain sits at ${grain.centre}, outside the contour",
                            0.0,
                            distanceOutside(grain.centre, contour),
                            0.0,
                        )
                    }
                }
            }
        }
    }

    /**
     * T-163. The bands darken, one step at a time.
     *
     * Every grain in a band carries that band's ink exactly, so the reading is
     * an equality per band and a strict order across them. A band whose ink
     * repeats its neighbour's is not a step.
     */
    @Test
    fun testAquatintDarkensBandByBand() {
        for (primitive in shapes) {
            for (steps in listOf(2, 3, 4)) {
                val byStep = surfaceStrokes(renderSvg(primitive, "aquatint", toneSteps = steps))
                    .groupBy { it.step }
                assertEquals("$primitive/$steps: every band must be drawn", steps, byStep.size)
                val inks = (1..steps).map { step ->
                    val band = byStep.getValue(step)
                    val ink = band.first().opacity
                    for (grain in band) {
                        assertEquals("$primitive/$steps: band $step must carry one ink", ink, grain.opacity, 0.0)
                    }
                    ink
                }
                for (step in 1 until steps) {
                    assertTrue(
                        "$primitive/$steps: band ${step + 1} must be darker than band $step, was $inks",
                        inks[step] > inks[step - 1],
                    )
                }
            }
        }
    }

    /**
     * T-164. The surface layer writes its texture filter for `display` only.
     *
     * The defs a filter points at are emitted for `display` and for nothing
     * else, so a reference written into an editable file resolves to nothing.
     * The server has read `use_filters` in `_surface_dab` all along; the port
     * could not, because the surface layer was never given the profile.
     *
     * Run on `pencil`, the tool the filter is defined for. Both directions are
     * read: that the display face writes it on every grain, and that the other
     * two faces write it on none while still drawing the same grains.
     */
    @Test
    fun testTheSurfaceLayerWritesItsFiltersOnlyForDisplay() {
        for (primitive in shapes) {
            for (texture in grainWords + "aquatint") {
                val display = surfaceStrokes(renderSvg(primitive, texture, weight = "pencil", profile = "display"))
                assertTrue("$primitive/$texture: the display face must draw grains", display.isNotEmpty())
                assertEquals(
                    "$primitive/$texture: every grain on the display face carries its texture filter",
                    display.size,
                    display.count { it.carriesFilter },
                )
                for (profile in listOf("editable", "compat")) {
                    val plain = surfaceStrokes(renderSvg(primitive, texture, weight = "pencil", profile = profile))
                    assertEquals("$primitive/$texture: $profile draws the same grains", display.size, plain.size)
                    assertEquals(
                        "$primitive/$texture: $profile writes no filter the file cannot resolve",
                        0,
                        plain.count { it.carriesFilter },
                    )
                }
            }
        }
    }

    /**
     * T-165. And so does the wash, which until now wrote its filter always.
     *
     * The sweep was written unconditionally on the grounds that no frozen case
     * pinned it either way. Nothing measured it either: [AWashIsAFieldTest]
     * runs on `pen`, and no filter is defined for `pen`, so the line never put
     * out a byte. On `pencil` it does.
     */
    @Test
    fun testAWashWritesItsFilterOnlyForDisplay() {
        for (primitive in shapes) {
            val display = surfaceStrokes(renderSvg(primitive, "wash", weight = "pencil", profile = "display"))
            assertTrue("$primitive: the display face must draw sweeps", display.isNotEmpty())
            assertEquals(
                "$primitive: every sweep on the display face carries its texture filter",
                display.size,
                display.count { it.carriesFilter },
            )
            for (profile in listOf("editable", "compat")) {
                val plain = surfaceStrokes(renderSvg(primitive, "wash", weight = "pencil", profile = profile))
                assertEquals("$primitive: $profile draws the same sweeps", display.size, plain.size)
                assertEquals(
                    "$primitive: $profile writes no filter the file cannot resolve",
                    0,
                    plain.count { it.carriesFilter },
                )
            }
        }
    }
}
