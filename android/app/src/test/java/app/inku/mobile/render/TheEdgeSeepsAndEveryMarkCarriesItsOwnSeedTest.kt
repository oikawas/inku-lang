package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Locale

/**
 * The edge seeps, and every mark carries its own seed.
 *
 * Two claims, one function. `bleed` was the last surface word the port offered
 * the model and did not draw, and it is drawn from the outline outwards rather
 * than as an ellipse in the middle of a bounding box. And the surface layer now
 * makes its seed once, before the branches, so a mark's place in the score
 * reaches the texture the way it already reached the outline.
 *
 * Nothing here reads the frozen corpus: it holds no `bleed` case at all, and no
 * case where an `arrangement` and a surface are in force at the same time.
 */
class TheEdgeSeepsAndEveryMarkCarriesItsOwnSeedTest {

    private val renderSeed = 12345L

    /** `square` resolves to 1000x1000, so the stated ratios read straight as pixels. */
    private val canvasPx = 1000.0

    /** Written from the description, not from the code: 0.25 and 0.5 on 1000px. */
    private val squarePolygon = listOf(250.0 to 250.0, 750.0 to 250.0, 750.0 to 750.0, 250.0 to 750.0)
    private val trianglePolygon = listOf(500.0 to 250.0, 750.0 to 750.0, 250.0 to 750.0)
    private val shapes = mapOf("square" to squarePolygon, "triangle" to trianglePolygon)

    private fun surfaceJson(texture: String, bleed: Double, seed: Int?): String {
        val seedPart = if (seed == null) "" else ""","seed":$seed"""
        return """{"texture":"$texture","density":0.5,"scale":0.4,"opacity":0.36,"bleed":$bleed,""" +
            """"direction":"diagonal_rising","spacing_gradient":"none","tone_steps":3$seedPart}"""
    }

    private fun shape(
        primitive: String,
        texture: String,
        weight: String = "pen",
        bleed: Double = 0.6,
        seed: Int? = null,
    ): String =
        """{"primitive":"$primitive","position":[0.25,0.25],"size":[0.5,0.5],""" +
            """"weight":"$weight","filled":false,"surface":${surfaceJson(texture, bleed, seed)}}"""

    private fun renderSvg(vararg instructions: String, profile: String = "editable"): String =
        DefaultSvgRenderer().render(
            RenderRequest(
                scoreJson = """{"instructions":[${instructions.joinToString(",")}]}""",
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = profile,
                renderSeed = renderSeed,
            )
        ).svg

    // ---- reading the drawing back -------------------------------------------------

    private val surfaceElement = Regex("""<(?:path|line|circle)\b[^>]*class="surface-stroke-v1[^"]*"[^>]*/>""")
    private val ringElement = Regex("""<path\b[^>]*class="surface-stroke-v1 bleed-ring-(\d+)"[^>]*/>""")
    private val numberPair = Regex("""(-?\d+(?:\.\d+)?)[, ](-?\d+(?:\.\d+)?)""")

    private fun surfaceElements(svg: String): List<String> =
        surfaceElement.findAll(svg).map { it.value }.toList()

    /** Every ring the drawing wrote, as ring number to element. */
    private fun rings(svg: String): List<Pair<Int, String>> =
        ringElement.findAll(svg).map { it.groupValues[1].toInt() to it.value }.toList()

    private fun pointsOf(element: String): List<Pair<Double, Double>> {
        val body = Regex(""" d="([^"]*)"""").find(element)?.groupValues?.get(1)
            ?: Regex(""" points="([^"]*)"""").find(element)?.groupValues?.get(1)
        if (body != null) {
            return numberPair.findAll(body).map { it.groupValues[1].toDouble() to it.groupValues[2].toDouble() }.toList()
        }
        // The machine pole's hatch is a bare <line>; read its two ends.
        fun attr(name: String) = Regex(""" $name="([^"]*)"""").find(element)?.groupValues?.get(1)?.toDouble()
        val x1 = attr("x1")
        val y1 = attr("y1")
        val x2 = attr("x2")
        val y2 = attr("y2")
        return if (x1 != null && y1 != null && x2 != null && y2 != null) listOf(x1 to y1, x2 to y2) else emptyList()
    }

    private fun countOf(svg: String, tag: String): Int = Regex(Regex.escape(tag)).findAll(svg).count()

    /**
     * The pieces the `editable` face writes for one instruction.
     *
     * That face carries `id="instruction_NNN_..."` on each instruction's group,
     * and instructions are written one after another, so cutting the document
     * at every such id attributes each surface element to the instruction that
     * drew it. There is no per-mark id to cut at: an expanded mark's group is
     * written as a bare `<g>`.
     */
    private fun splitBy(svg: String, idPrefix: String): List<String> {
        val cuts = Regex("""id="$idPrefix""").findAll(svg).map { it.range.first }.toList()
        if (cuts.isEmpty()) return listOf(svg)
        return cuts.mapIndexed { i, start ->
            svg.substring(start, if (i + 1 < cuts.size) cuts[i + 1] else svg.length)
        }
    }

    /** The same elements with each one moved to its own bounding-box origin. */
    private fun placeless(elements: List<String>): List<String> = elements.map { element ->
        val points = pointsOf(element)
        if (points.isEmpty()) return@map element
        val minX = points.minOf { it.first }
        val minY = points.minOf { it.second }
        points.joinToString(" ") {
            "%.1f,%.1f".format(Locale.US, it.first - minX, it.second - minY)
        }
    }

    private fun inside(point: Pair<Double, Double>, polygon: List<Pair<Double, Double>>): Boolean {
        var result = false
        for (index in polygon.indices) {
            val (ax, ay) = polygon[index]
            val (bx, by) = polygon[(index + 1) % polygon.size]
            if ((ay > point.second) != (by > point.second)) {
                val t = (point.second - ay) / (by - ay)
                if (point.first < ax + (bx - ax) * t) result = !result
            }
        }
        return result
    }

    private fun distanceToEdge(point: Pair<Double, Double>, a: Pair<Double, Double>, b: Pair<Double, Double>): Double {
        val dx = b.first - a.first
        val dy = b.second - a.second
        val lengthSquared = dx * dx + dy * dy
        val t = if (lengthSquared <= 0.0) 0.0 else {
            (((point.first - a.first) * dx + (point.second - a.second) * dy) / lengthSquared).coerceIn(0.0, 1.0)
        }
        return Math.hypot(point.first - (a.first + dx * t), point.second - (a.second + dy * t))
    }

    /** How far outside the outline a point sits. Negative means inside it. */
    private fun signedDistance(point: Pair<Double, Double>, polygon: List<Pair<Double, Double>>): Double {
        val distance = polygon.indices.minOf { i ->
            distanceToEdge(point, polygon[i], polygon[(i + 1) % polygon.size])
        }
        return if (inside(point, polygon)) -distance else distance
    }

    // ---- T-167 --------------------------------------------------------------------

    /**
     * T-167. A bleed seeps past the edge, and not without limit.
     *
     * The two halves are one claim. Read on its own, "something is outside the
     * outline" passes on a renderer that throws the band anywhere, and "nothing
     * goes further than X" passes on one that draws nothing at all.
     *
     * The ceiling is the test's own arithmetic, written from the description of
     * what the band may do: the furthest a ring's centreline is pushed is the
     * blur times the largest waver, and the band's own width adds at most half
     * of the widest ring on top of that. It is not read back from the product.
     */
    @Test
    fun testBleedSeepsPastTheEdgeButNotWithoutLimit() {
        val bleed = 0.6
        val blur = Math.max(1.0, canvasPx * (0.010 + bleed * 0.030))
        val ceiling = blur * 1.45 + blur * 1.05 / 2.0
        for ((primitive, polygon) in shapes) {
            val points = rings(renderSvg(shape(primitive, "bleed", bleed = bleed)))
                .flatMap { pointsOf(it.second) }
            assertTrue("$primitive: the bleed must have drawn something to measure", points.size > 8)
            val furthest = points.maxOf { signedDistance(it, polygon) }
            assertTrue("$primitive: the bleed must reach outside the outline, got $furthest", furthest > 0.0)
            assertTrue(
                "$primitive: the bleed must stay within ${"%.1f".format(ceiling)}px of the outline, got $furthest",
                furthest <= ceiling,
            )
        }
    }

    // ---- T-168 --------------------------------------------------------------------

    /**
     * T-168. The bleed lays down three rings, and only three.
     *
     * Three is this test's own claim and is written here; the second assertion
     * is what ties it to the product's constant. Reading the count out of
     * `SURFACE_BLEED_RINGS` and then comparing it with itself would move with
     * the constant and assert nothing.
     */
    @Test
    fun testBleedLaysDownThreeRings() {
        for (primitive in shapes.keys) {
            val svg = renderSvg(shape(primitive, "bleed"))
            val byRing = rings(svg).groupBy({ it.first }, { it.second })
            assertEquals("$primitive: the rings written", listOf(1, 2, 3), byRing.keys.sorted())
            for (ring in listOf(1, 2, 3)) {
                assertEquals("$primitive: ring $ring is written once", 1, byRing.getValue(ring).size)
            }
            assertEquals("$primitive: there is no fourth ring", 0, countOf(svg, "bleed-ring-4"))
        }
        assertEquals("the product lays out the number this test asserts", 3, SURFACE_BLEED_RINGS)
    }

    // ---- T-169 --------------------------------------------------------------------

    /**
     * T-169. The innermost ring lies on the outline.
     *
     * A seep happens on both sides of an edge, so the first band rises from the
     * edge itself instead of floating at a distance from the shape; the bands
     * after it stand further and further out. Measured at 0.6 of bleed on a
     * 1000px canvas, the first ring's points average 2.5px outside the outline
     * while the third averages 24.5px, so a ceiling of 6px on the first is a
     * claim about lying on the edge rather than a copy of either number.
     */
    @Test
    fun testTheInnerRingLiesOnTheOutline() {
        for ((primitive, polygon) in shapes) {
            val means = rings(renderSvg(shape(primitive, "bleed"))).associate { (ring, element) ->
                ring to pointsOf(element).map { signedDistance(it, polygon) }.average()
            }
            assertEquals("$primitive: three rings to measure", 3, means.size)
            assertTrue(
                "$primitive: the inner ring must lie on the outline, its points average ${means.getValue(1)}px out",
                means.getValue(1) < 6.0,
            )
            for (ring in 2..3) {
                assertTrue(
                    "$primitive: ring $ring must stand further out than ring ${ring - 1}",
                    means.getValue(ring) > means.getValue(ring - 1),
                )
            }
        }
    }

    // ---- T-170 --------------------------------------------------------------------

    /**
     * T-170. How much it bleeds moves how far it seeps.
     *
     * The seed is stated in the score for both runs, so the only thing that
     * differs between them is the quantity under test: were it left out, the
     * amount would also be in the material the seed is made from and the two
     * drawings would differ for a second reason.
     */
    @Test
    fun testTheBleedAmountMovesHowFarItSeeps() {
        for ((primitive, polygon) in shapes) {
            fun furthest(bleed: Double): Double =
                rings(renderSvg(shape(primitive, "bleed", bleed = bleed, seed = 24680)))
                    .flatMap { pointsOf(it.second) }
                    .maxOf { signedDistance(it, polygon) }
            val dry = furthest(0.0)
            val wet = furthest(1.0)
            assertTrue(
                "$primitive: a full bleed must seep further than none at all, got $wet against $dry",
                wet > dry,
            )
        }
    }

    // ---- T-171 --------------------------------------------------------------------

    /**
     * T-171. Two roads, the way the server has two.
     *
     * The hand tool performs the band with the material engine and writes it as
     * a stroke; the machine pole gets the geometry and writes a bare polygon
     * with no class of its own. Counting polygons against the same shape drawn
     * with no surface at all is what keeps the shape's own body out of the
     * count.
     */
    @Test
    fun testBleedHasTwoRoads() {
        for (primitive in shapes.keys) {
            val byHand = renderSvg(shape(primitive, "bleed", weight = "pen"))
            val handControl = renderSvg(shape(primitive, "none", weight = "pen"))
            assertEquals("$primitive: a hand tool performs three bands", 3, rings(byHand).size)
            assertEquals(
                "$primitive: and adds no polygon of its own",
                countOf(handControl, "<polygon"),
                countOf(byHand, "<polygon"),
            )

            val byMachine = renderSvg(shape(primitive, "bleed", weight = "rotring"))
            val machineControl = renderSvg(shape(primitive, "none", weight = "rotring"))
            assertEquals(
                "$primitive: the machine pole draws its three bands as polygons",
                countOf(machineControl, "<polygon") + 3,
                countOf(byMachine, "<polygon"),
            )
            assertEquals(
                "$primitive: and performs no stroke",
                0,
                surfaceElements(byMachine).size,
            )
        }
    }

    // ---- T-172 --------------------------------------------------------------------

    /**
     * T-172. The bleed asks the profile for its filter, like the rest of the layer.
     *
     * Run on `pencil`, a tool the filter is defined for. `display` is the only
     * face that emits the defs, so a reference written on any other face points
     * at nothing.
     */
    @Test
    fun testBleedWritesItsFilterOnlyForDisplay() {
        for (primitive in shapes.keys) {
            val display = rings(renderSvg(shape(primitive, "bleed", weight = "pencil"), profile = "display"))
            assertEquals("$primitive: the display face draws three bands", 3, display.size)
            assertEquals(
                "$primitive: every band on the display face carries its texture filter",
                3,
                display.count { it.second.contains("""filter="url(#texture-pencil)"""") },
            )
            for (profile in listOf("editable", "compat")) {
                val plain = rings(renderSvg(shape(primitive, "bleed", weight = "pencil"), profile = profile))
                assertEquals("$primitive: $profile draws the same three bands", 3, plain.size)
                assertEquals(
                    "$primitive: $profile writes no filter the file cannot resolve",
                    0,
                    plain.count { it.second.contains("""filter="url(#texture-""") },
                )
            }
            // The machine pole declares no filter on any face.
            val machine = renderSvg(shape(primitive, "bleed", weight = "rotring"), profile = "display")
            val machineControl = renderSvg(shape(primitive, "none", weight = "rotring"), profile = "display")
            assertEquals(
                "$primitive: the machine pole's bands carry no filter",
                countOf(machineControl, """filter="url(#texture-"""),
                countOf(machine, """filter="url(#texture-"""),
            )
        }
    }

    // ---- T-173 / T-174 / T-175 ----------------------------------------------------

    /**
     * Three marks of one shape, spread across the sheet.
     *
     * Run on the machine pole. A hand tool quantises its samples onto a grid
     * anchored at the origin rather than at the shape, so two marks of the same
     * shape are never exact translations of one another even when they perform
     * the same texture -- and "the same texture" is precisely what the stated
     * seed is supposed to give, so the comparison has to be exact to say
     * anything. Measured on this instruction: the machine pole gives 24 wash
     * sweeps that fall into 8 distinct shapes when a seed is stated, while a
     * pen gives 24 that fall into 24.
     */
    private fun spread(texture: String, seed: Int? = null): String =
        """{"primitive":"circle","center":[0.5,0.5],"radius":0.09,"weight":"rotring","filled":false,""" +
            """"arrangement":{"count":3,"layout":"horizontal","margin":0.12},""" +
            """"surface":${surfaceJson(texture, 0.0, seed)}}"""

    private fun twin(texture: String, seed: Int? = null): String =
        """{"primitive":"circle","center":[0.5,0.5],"radius":0.14,"weight":"rotring","filled":false,""" +
            """"surface":${surfaceJson(texture, 0.0, seed)}}"""

    /** The surface each instruction drew, in the order the score states them. */
    private fun surfacePerInstruction(svg: String): List<List<String>> =
        splitBy(svg, "instruction_").map { surfaceElements(it) }

    /**
     * How many distinct textures the expanded marks wore.
     *
     * There is no per-mark id to cut the document at, so the marks are told
     * apart by their drawings instead: each element is moved to its own
     * bounding-box origin, and marks wearing one texture then write the very
     * same strings. Three marks wearing one texture give exactly a third as
     * many distinct strings as elements; anything more means they differ.
     */
    private fun distinctTexturesAcross(svg: String): Pair<Int, Int> {
        val normalized = placeless(surfaceElements(svg))
        return normalized.toSet().size to normalized.size
    }

    /**
     * Two marks that differ in nothing a score can state.
     *
     * The seed's material holds every stated field, so two marks an
     * `arrangement` expanded already differ through their own coordinates --
     * measured on this branch, and the reason the first half below passes
     * whether or not the mark index reaches the seed. What the mark's place in
     * the score adds on top of the coordinates is only readable where the
     * stated fields are identical, which is why the second half puts the same
     * instruction into the score twice: there the two differ by their index
     * alone.
     */
    private fun assertEveryMarkCarriesItsOwnTexture(texture: String) {
        val (distinct, total) = distinctTexturesAcross(renderSvg(spread(texture)))
        assertTrue("$texture: the three marks must each draw a surface", total >= 3)
        assertTrue(
            "$texture: the expanded marks must not all wear one texture, $distinct of $total",
            distinct > total / 3,
        )

        val twins = surfacePerInstruction(renderSvg(twin(texture), twin(texture))).filter { it.isNotEmpty() }
        assertEquals("$texture: two identical instructions must each draw a surface", 2, twins.size)
        assertNotEquals(
            "$texture: two instructions identical in every stated field must still differ",
            twins[0],
            twins[1],
        )
    }

    /** T-173. A wash is made once per mark, not once per instruction. */
    @Test
    fun testAWashSurfaceDiffersFromMarkToMark() {
        assertEveryMarkCarriesItsOwnTexture("wash")
    }

    /** T-174. And so is a hatch, and a crosshatch. */
    @Test
    fun testAHatchSurfaceDiffersFromMarkToMark() {
        assertEveryMarkCarriesItsOwnTexture("hatch")
        assertEveryMarkCarriesItsOwnTexture("crosshatch")
    }

    /**
     * T-175. The other direction: a stated seed makes every mark the same.
     *
     * Without this, an implementation that reaches for a fresh random number
     * per mark satisfies T-173 and T-174 as well as the right one does. The
     * stated seed is the one road that does not read where the mark sits.
     */
    @Test
    fun testAnExplicitSurfaceSeedMakesEveryMarkTheSame() {
        for (texture in listOf("wash", "hatch", "crosshatch")) {
            val (distinct, total) = distinctTexturesAcross(renderSvg(spread(texture, seed = 24680)))
            assertTrue("$texture: the three marks must each draw a surface", total >= 3)
            assertEquals("$texture: the three marks draw the same number of pieces", 0, total % 3)
            assertEquals(
                "$texture: a stated seed must give every expanded mark one texture, $distinct of $total",
                total / 3,
                distinct,
            )

            val twins = surfacePerInstruction(renderSvg(twin(texture, seed = 24680), twin(texture, seed = 24680)))
                .filter { it.isNotEmpty() }
            assertEquals("$texture: two identical instructions must each draw a surface", 2, twins.size)
            assertEquals(
                "$texture: and a stated seed must give both of them the same texture",
                twins[0],
                twins[1],
            )
        }
    }
}
