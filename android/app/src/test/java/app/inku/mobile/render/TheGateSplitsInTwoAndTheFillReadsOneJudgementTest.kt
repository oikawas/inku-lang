package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The variation gate splits in two, and the fill attribute reads one judgement
 * ([I-278], [I-298]).
 *
 * The server settles both of these once and lets the places that need them read
 * the answer. The port held copies: one folded gate that read all three axes from
 * every call site and excluded only `none`, and a `fill` decided out of "is this
 * primitive closed, or was `filled` written" that the seven `fill-opacity`
 * branches then read back.
 *
 * None of it is measurable against the frozen corpus. Of its 51 drawings only four
 * carry a `variation` at all; none of the four is `pink`, none is a line asked to
 * vary on `radius` alone, and none of the closed shapes is spelt with
 * `surface.texture="solid"`. So every gate here is stated as a property -- what
 * the server answers for the same instruction -- with the control that must not
 * move beside it.
 */
class TheGateSplitsInTwoAndTheFillReadsOneJudgementTest {

    private val seed = 12345L

    private fun render(instructions: String, profile: String = "editable"): String =
        DefaultSvgRenderer().render(
            RenderRequest(
                scoreJson = """{"instructions":[$instructions]}""",
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = profile,
                renderSeed = seed,
            )
        ).svg

    private fun variation(quality: String, vararg dims: String): String {
        val dimsJson = dims.joinToString(",") { "\"$it\"" }
        return """{"amplitude":"medium","frequency":"medium","quality":"$quality","dimensions":[$dimsJson]}"""
    }

    /** A line drawn by the machine pole: a `<line>` when it does not wobble, a `<polyline>` when it does. */
    private fun line(variation: String?, weight: String = "rotring"): String = buildString {
        append("""{"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"weight":"$weight","color":"black"""")
        if (variation != null) append(""","variation":$variation""")
        append("}")
    }

    /** A circle drawn by the machine pole: a `<circle>` when it does not wobble, a `<polygon>` when it does. */
    private fun circle(variation: String?, weight: String = "rotring", extra: String = ""): String = buildString {
        append("""{"primitive":"circle","center":[0.5,0.5],"radius":0.25,"weight":"$weight","color":"black"""")
        if (variation != null) append(""","variation":$variation""")
        append(extra)
        append("}")
    }

    /** The mark's own element, taken out of the ground and the grid around it. */
    private fun element(svg: String, tag: String): String {
        val m = Regex("""<$tag\b[^>]*>""").findAll(svg).lastOrNull()
        assertTrue("the drawing must hold a <$tag> element:\n$svg", m != null)
        return m!!.value
    }

    private fun wobbles(svg: String): Boolean = svg.contains("<polyline") || svg.contains("<polygon")

    // ---------------------------------------------------------------- the gate

    /**
     * T-224: `pink` is a bleed, and a bleed does not wobble.
     *
     * The server excludes `pink` from both gates and draws it with a blur instead
     * (`_needs_blur`). The port excluded only `none`, so a pink instruction came out
     * blurred AND wobbling -- two mechanisms for one word. Stated on both roads,
     * because the folded gate served both and a split that only fixed one would
     * still leave the other saying yes.
     *
     * `wave` is the control on the same score, same axes, same seed material: the
     * claim is about the quality word and nothing else.
     *
     * The line road is stated on the hand pole. It used to be stated on the machine
     * pole, where a wobble showed up as a `<polyline>` -- but that element was the
     * divergence [I-307] removed: the server answers a `rotring` line with
     * `dwg.line` and never reads the gate, so a machine-pole line is one straight
     * `<line>` whether it was asked to wobble or not, and both halves of the
     * contrast would now be vacuous there. The machine pole's own claim lives in
     * [TheMachinePoleLineDoesNotWaverTest]. On the hand pole the gate is live, and
     * the claim is read as "does the axis reach the stroke": `pink` is excluded
     * from the gate AND from the seed material's `dimensions`, so naming an axis
     * must change nothing at all. Byte equality, with the same quality word on
     * both sides, so what is measured is the axis and not the word.
     */
    @Test
    fun testPinkWobblesNothingOnEitherRoadWhileWaveDoes() {
        val pinkOnAnAxis = render(line(variation("pink", "position_y"), "pen"))
        val pinkOnNoAxis = render(line(variation("pink"), "pen"))
        // Byte equality is the whole reading on this road. `wobbles` cannot be
        // asked here: the hand pole clothes its stroke in `material-outline`
        // polylines, so it answers yes for every hand tool whether the stroke
        // wobbles or not. It stays the reading on the contour road below, where
        // the machine pole draws the mark itself.
        assertEquals(
            "a pink line must not read the axis it was given",
            pinkOnNoAxis,
            pinkOnAnAxis,
        )

        val waveOnAnAxis = render(line(variation("wave", "position_y"), "pen"))
        val waveOnNoAxis = render(line(variation("wave"), "pen"))
        assertNotEquals(
            "the control must read it: a wave line given position_y wobbles",
            waveOnNoAxis,
            waveOnAnAxis,
        )

        val pinkCircle = render(circle(variation("pink", "position_x", "position_y", "radius")))
        assertTrue("a pink circle stays the <circle> the server draws", pinkCircle.contains("<circle "))
        assertFalse(
            "a pink circle must not wobble on any axis it names:\n$pinkCircle",
            pinkCircle.contains("<polygon"),
        )

        val waveCircle = render(circle(variation("wave", "position_x", "position_y", "radius")))
        assertTrue("the control must wobble:\n$waveCircle", waveCircle.contains("<polygon"))
    }

    /**
     * T-225: and the bleed is still drawn.
     *
     * Kept apart from T-224 on purpose. Tightening the gate so that `pink` stops
     * wobbling would leave T-224 green even if the blur went with it, and the two
     * live in different layers -- the gate in `ServerRendererGeometry`, the bleed in
     * `ServerRendererStyle.blurFilterId`. The filter face is the display one, so
     * this is the one gate here that draws with `display`.
     */
    @Test
    fun testPinkComesOutAsABlurOnTheDisplayFace() {
        val pink = render(circle(variation("pink", "position_x")), profile = "display")
        assertTrue("a pink mark must carry a blur filter:\n$pink", pink.contains("""filter="url(#blur-"""))
        assertTrue("and the filter it names must be defined", pink.contains("""<filter id="blur-"""))
        assertTrue("the bleed is a gaussian blur", pink.contains("<feGaussianBlur"))

        val wave = render(circle(variation("wave", "position_x")), profile = "display")
        assertFalse("a wobble is not a bleed:\n$wave", wave.contains("blur-"))
    }

    /**
     * T-226: a line has no radius to vary along.
     *
     * `_needs_path_variation` reads `position_x` and `position_y`; `radius` is the
     * closed figure's own axis and reaches the line's gate nowhere. Stated as byte
     * equality with the same instruction carrying no `variation` at all, which is
     * the whole claim: not only does the line come out straight, it performs as the
     * line that was never asked to vary -- `variationJson` already drops a variation
     * the line's gate refuses, so the seed matches too.
     *
     * The hand pole, and only the hand pole. A line used to reach the gate twice --
     * the machine pole through the `"line"` branch as well -- and the machine half
     * of this walk was where the control lived: `position_y` moved a `rotring` line
     * because the port wobbled it. [I-307] took that branch out to match the
     * server, so on that road the unvaried line, the radius-only line and the
     * position_y line are now the same three bytes and the whole walk would be
     * true for the wrong reason. What the machine pole does instead is stated in
     * [TheMachinePoleLineDoesNotWaverTest]. The count is asserted so this cannot
     * quietly become a walk over nothing.
     */
    @Test
    fun testALineAskedToVaryOnRadiusAloneIsByteForByteTheUnvariedLine() {
        val roads = listOf("pen")
        var walked = 0
        for (weight in roads) {
            val radiusOnly = render(line(variation("wave", "radius"), weight))
            val noVariation = render(line(null, weight))
            assertEquals(
                "a $weight line asked to vary on radius alone must draw and perform as the unvaried line",
                noVariation,
                radiusOnly,
            )

            val positionY = render(line(variation("wave", "position_y"), weight))
            assertNotEquals(
                "the control must move: a $weight line asked to vary on position_y wobbles",
                noVariation,
                positionY,
            )
            walked++
        }
        assertEquals("every road that still holds the line's gate must be walked", roads.size, walked)
    }

    /**
     * T-227: and a contour does have one.
     *
     * The regression guard for the other half of the split. `_CONTOUR_VARIATION_DIMS`
     * holds `radius` for exactly these six, and a split that gave both gates the
     * line's two axes would answer T-226 correctly and take this away.
     */
    @Test
    fun testEveryContourStillVariesOnRadiusAlone() {
        val shapes = mapOf(
            "circle" to """"center":[0.5,0.5],"radius":0.25""",
            "ellipse" to """"center":[0.5,0.5],"size":[0.4,0.24]""",
            "square" to """"position":[0.3,0.3],"size":[0.4,0.4]""",
            "triangle" to """"position":[0.3,0.3],"size":[0.4,0.4]""",
            "polygon" to """"center":[0.5,0.5],"size":[0.4,0.4],"sides":5""",
            "arc" to """"center":[0.5,0.5],"radius":0.3,"angle_start":0,"angle_end":180""",
        )
        var compared = 0
        for ((primitive, geometry) in shapes) {
            val base = """{"primitive":"$primitive",$geometry,"weight":"rotring","color":"black"}"""
            val varied = base.dropLast(1) + ""","variation":${variation("wave", "radius")}}"""
            assertNotEquals(
                "$primitive must still vary on radius alone",
                render(base),
                render(varied),
            )
            compared++
        }
        assertEquals("all six contour primitives must be walked", shapes.size, compared)
    }

    /**
     * T-228: and the two answers are reached separately, in one drawing.
     *
     * A line and a circle given the identical `variation`. The circle wobbles, the
     * line does not, and the drawing is byte-for-byte the one where the line was
     * never given the variation at all. One folded gate cannot produce this: it
     * answers the same for both marks whichever way it is written.
     */
    @Test
    fun testTheLineAndTheContourAreJudgedApartInOneScore() {
        val radiusOnly = variation("wave", "radius")
        val both = render("${line(radiusOnly)},${circle(radiusOnly)}")
        val circleOnly = render("${line(null)},${circle(radiusOnly)}")
        val neither = render("${line(null)},${circle(null)}")

        assertEquals(
            "the line must be unmoved by a variation that names only radius",
            circleOnly,
            both,
        )
        assertNotEquals(
            "the circle in the same score must be moved by it",
            neither,
            both,
        )
    }

    // ---------------------------------------------------------------- the fill

    /**
     * T-229: a shape nobody asked to fill carries no fill-opacity either.
     *
     * The seven `fill-opacity` branches read `fill != "none"`, and `fill` was decided
     * out of the primitive's shape rather than the request -- so a haze hint put a
     * `fill-opacity` onto every closed shape, filled or not. The server reads
     * `do_fill` in all seven, the same value that decided `fill`.
     */
    @Test
    fun testAClosedShapeNobodyAskedToFillCarriesNoFillOpacity() {
        val hint = ""","color_hint":"haze over the water""""
        val bare = element(render(circle(null, extra = hint)), "circle")
        assertTrue("a circle nobody asked to fill is an outline: $bare", bare.contains("""fill="none""""))
        assertFalse("and an outline has no fill to make faint: $bare", bare.contains("fill-opacity"))

        val filled = element(render(circle(null, extra = """$hint,"filled":true""")), "circle")
        assertTrue("the control must be filled: $filled", filled.contains("""fill="#111111""""))
        assertTrue("and the haze must make that fill faint: $filled", filled.contains("""fill-opacity="0.12"""))
    }

    /**
     * T-230: one request, however it is spelt, writes one fill.
     *
     * `cloudform` is the mark that showed it. It is a closed shape -- `CLOSED_SHAPES`
     * has held it all along -- but the set `strokeAttrs` kept for itself did not, so
     * `filled=true` filled it and `surface.texture="solid"`, which says the same
     * thing, left it open.
     */
    @Test
    fun testTheTwoSpellingsOfAFillWriteTheSameFillValue() {
        fun cloudform(request: String): String {
            val svg = render(
                """{"primitive":"cloudform","center":[0.5,0.5],"size":[0.5,0.34],"weight":"rotring","color":"black",$request}"""
            )
            return element(svg, "path")
        }

        val asBoolean = cloudform(""""filled":true""")
        val asSurfaceWord = cloudform(""""surface":{"texture":"solid"}""")
        val fillOf = Regex("""fill="([^"]*)"""")
        assertEquals(
            "solid and filled=true must write the same fill onto the cloudform",
            fillOf.find(asBoolean)?.groupValues?.get(1),
            fillOf.find(asSurfaceWord)?.groupValues?.get(1),
        )
        assertEquals("and that fill is the mark's colour", "#111111", fillOf.find(asBoolean)?.groupValues?.get(1))

        val neither = cloudform(""""style":"solid"""")
        assertEquals(
            "a cloudform nobody asked to fill stays open",
            "none",
            fillOf.find(neither)?.groupValues?.get(1),
        )
    }

    /**
     * T-231: the two poles answer the same request the same way.
     *
     * They answer it in different elements -- the machine pole puts the fill on the
     * body, the hand pole draws the interior as marks in a `fill-*` group and leaves
     * the body open so the two do not stack, exactly as the server does with
     * `region_fill=False`. What has to agree is the answer, not the element, so each
     * road is read where its own answer lives.
     */
    @Test
    fun testTheMachineRoadAndTheHandRoadAgreeOnWhetherTheInteriorIsFilled() {
        val shapes = mapOf(
            "circle" to """"center":[0.5,0.5],"radius":0.25""",
            "ellipse" to """"center":[0.5,0.5],"size":[0.4,0.24]""",
            "square" to """"position":[0.3,0.3],"size":[0.4,0.4]""",
            "polygon" to """"center":[0.5,0.5],"size":[0.4,0.4],"sides":5""",
        )
        var compared = 0
        for ((primitive, geometry) in shapes) {
            for (asked in listOf(true, false)) {
                val request = if (asked) ""","filled":true""" else ""
                fun draw(weight: String) =
                    render("""{"primitive":"$primitive",$geometry,"weight":"$weight","color":"black"$request}""")

                val machine = draw("rotring")
                val machineFills = !Regex("""fill="none"""").containsMatchIn(machineBody(machine, primitive))
                val handFills = draw("pen").contains("""class="fill-""")

                assertEquals(
                    "the two poles must agree on whether $primitive is filled when asked=$asked",
                    machineFills,
                    handFills,
                )
                assertEquals(
                    "and the answer must be the request itself for $primitive",
                    asked,
                    machineFills,
                )
                compared++
            }
        }
        assertEquals("four primitives asked both ways", shapes.size * 2, compared)
    }

    /**
     * T-232: and each pole puts its answer in the place the server puts it.
     *
     * T-231 asks whether the two poles agree; this asks WHERE each one says it. The
     * machine pole has no mark group, so the body element carries the fill. The hand
     * pole draws the interior as marks and leaves the body open, because a flat fill
     * under them is the very thing engine 9 and 16 took out of filled shapes -- the
     * server states it in `_body_attrs_for_contour_stroke`, which drops `fill` and
     * `fill_opacity` whenever `_interior_fill` reports it drew the marks itself.
     *
     * Nothing measured this. `test03SquareFilledExactParity` compares the mark paths
     * and never reads the body, and the colour guard compares the SET of colours a
     * drawing holds -- `#111111` is already in the index's `fill_colors` for this
     * drawing, so a body newly filled with it changes no set. A flat fill could be
     * put back under every hand-drawn fill in the port and the suite stayed green.
     */
    @Test
    fun testTheHandPoleLeavesItsBodyOpenAndTheMachinePoleFillsIt() {
        val frozen = app.inku.mobile.ReferenceCorpus.text("03_square_filled.svg")
        val redrawn = ReferenceRendering.svg("03_square_filled")
        for ((who, svg) in listOf("the server" to frozen, "the port" to redrawn)) {
            val bodies = bodyRects(svg)
            assertEquals("$who draws one body rect for 03_square_filled", 1, bodies.size)
            assertTrue(
                "$who leaves the hand pole's body open: ${bodies[0]}",
                bodies[0].contains("""fill="none""""),
            )
            assertFalse(
                "$who writes no fill-opacity onto that open body: ${bodies[0]}",
                bodies[0].contains("fill-opacity"),
            )
            assertTrue("""$who draws the interior as marks instead""", svg.contains("""class="fill-"""))
        }

        // The frozen drawing carries no `color_hint`, so its `fill-opacity` is null
        // and the assertion above cannot tell an open body from one that simply had
        // no opacity to write. This one asks for the fill AND the haze, so the value
        // exists and the only reason it stays off the body is the judgement itself.
        val handWithAnOpacity = render(
            """{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"weight":"pen","color":"black","filled":true,"color_hint":"haze over the water"}"""
        )
        val handBody = bodyRects(handWithAnOpacity)
        assertEquals("the hand pole draws one body rect", 1, handBody.size)
        assertFalse(
            "an open body carries no fill-opacity even when the mark has one: ${handBody[0]}",
            handBody[0].contains("fill-opacity"),
        )
        assertTrue(
            "and the marks that do carry the interior are there",
            handWithAnOpacity.contains("""class="fill-"""),
        )

        val machine = render(
            """{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"weight":"rotring","color":"black","filled":true}"""
        )
        val machineBodies = bodyRects(machine)
        assertEquals("the machine pole draws one body rect", 1, machineBodies.size)
        assertTrue(
            "and that body IS the fill for the machine pole: ${machineBodies[0]}",
            machineBodies[0].contains("""fill="#111111""""),
        )
        assertFalse("the machine pole lays down no fill marks", machine.contains("""class="fill-"""))
    }

    /** Every `<rect>` a drawing holds except the ground, which is the one at the origin. */
    private fun bodyRects(svg: String): List<String> =
        Regex("""<rect\b[^>]*>""").findAll(svg)
            .map { it.value }
            .filterNot { it.contains("""x="0"""") && it.contains("""y="0"""") }
            .toList()

    private fun machineBody(svg: String, primitive: String): String = when (primitive) {
        "circle" -> element(svg, "circle")
        "ellipse" -> element(svg, "ellipse")
        "square" -> element(svg, "rect")
        else -> element(svg, "polygon")
    }
}
