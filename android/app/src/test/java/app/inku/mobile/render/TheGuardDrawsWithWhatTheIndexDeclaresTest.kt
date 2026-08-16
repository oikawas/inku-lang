package app.inku.mobile.render

import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The colour half of the reference comparison.
 *
 * `svg_index.json` states three things about every drawing that nothing read:
 * the catalog the server drew it with, and the `fill` and `stroke` colours the
 * finished picture holds. Everything the suite compared -- `d`, `points`,
 * element counts, class attributes, dasharrays -- carries no colour, so a port
 * that painted an interior the server left open was green, and stayed green from
 * the day the corpus was baked.
 *
 * The declarations are usable as a yardstick without rebaking anything: measured
 * over all 51 drawings, the colours the index declares and the colours the frozen
 * reference SVGs actually hold agree on every one of them.
 */
class TheGuardDrawsWithWhatTheIndexDeclaresTest {

    /** The drawings the index attributes to a catalog other than `default`. */
    private val declaredCatalogs = mapOf(
        "33_circle_pen_dye_earth_purple" to "dye_earth",
        "34_circle_pen_cool_material_black" to "cool_material",
        "35_square_filled_sea_stone_blue" to "sea_stone",
        "37_circle_pen_ink_season_brown_hint" to "ink_season",
        "38_line_pen_ink_porcelain_background" to "ink_porcelain",
    )

    /**
     * The colours one attribute of a drawing holds.
     *
     * Only values that are colours, which is the same counting the index does:
     * `fill="none"` states the absence of a fill rather than a colour, and it is
     * in neither the index's lists nor these sets. The leading space keeps
     * `fill-opacity` and `stroke-width` out of it.
     */
    private fun colours(svg: String, attribute: String): Set<String> =
        Regex(""" $attribute="(#[0-9a-fA-F]+)"""").findAll(svg).map { it.groupValues[1] }.toSet()

    private fun declared(entry: JSONObject, field: String): Set<String> {
        val arr = entry.getJSONArray(field)
        return (0 until arr.length()).map { arr.getString(it) }.toSet()
    }

    private class Walk {
        var compared = 0
        var drewAFill = 0
        var drewAStroke = 0
        val fillDisagreements = mutableListOf<String>()
        val strokeDisagreements = mutableListOf<String>()
    }

    /**
     * Every drawing in the index, redrawn and compared against its declaration.
     *
     * The counting happens beside the comparison and not instead of it: a guard
     * that only compares two extractions is green when both come back empty, so
     * how many drawings were reached and how many of them actually carried a
     * colour are asserted separately in [testTheColourGuardSaysHowManyItCompared].
     */
    private fun walk(): Walk {
        val index = ReferenceRendering.index()
        val walk = Walk()
        for (key in index.keys()) {
            val entry = index.getJSONObject(key)
            val svg = ReferenceRendering.svg(entry)

            val drawnFill = colours(svg, "fill")
            val drawnStroke = colours(svg, "stroke")
            val declaredFill = declared(entry, "fill_colors")
            val declaredStroke = declared(entry, "stroke_colors")

            if (drawnFill != declaredFill) {
                walk.fillDisagreements +=
                    "$key: the index declares ${declaredFill.sorted()}, the port drew ${drawnFill.sorted()}"
            }
            if (drawnStroke != declaredStroke) {
                walk.strokeDisagreements +=
                    "$key: the index declares ${declaredStroke.sorted()}, the port drew ${drawnStroke.sorted()}"
            }
            if (drawnFill.isNotEmpty()) walk.drewAFill++
            if (drawnStroke.isNotEmpty()) walk.drewAStroke++
            walk.compared++
        }
        return walk
    }

    /**
     * T-176: the guard hands the renderer the catalog the index declares.
     *
     * This measures the guard's own road and nothing downstream of it. What the
     * renderer then does with the id is a different layer, measured by T-177 and
     * T-178: were this stated as "the drawing comes out in the declared colours",
     * a renderer that ignored the id and a guard that never passed it would be
     * indistinguishable, and the two perturbations aimed at those two layers
     * would redden the same tests.
     */
    @Test
    fun testTheGuardHandsOverTheCatalogTheIndexDeclares() {
        val index = ReferenceRendering.index()
        var checked = 0
        var awayFromDefault = 0
        for (key in index.keys()) {
            val entry = index.getJSONObject(key)
            val declaration = entry.getString("color_catalog_id")
            assertEquals(
                "the request for $key must carry the catalog its index entry declares",
                declaration,
                ReferenceRendering.request(entry).colorCatalogId,
            )
            if (declaration != "default") awayFromDefault++
            checked++
        }
        assertEquals("every drawing in the index must be walked", index.length(), checked)

        // Named, because these five are the whole reason the hard-coded "default"
        // mattered: the other 46 draw the same either way.
        for ((key, catalog) in declaredCatalogs) {
            assertEquals(
                "$key is drawn with $catalog",
                catalog,
                ReferenceRendering.request(ReferenceRendering.entry(key)).colorCatalogId,
            )
        }
        assertEquals(
            "engine ${CompatibilityConstants.renderEngineVersion}'s corpus attributes five drawings to another catalog",
            declaredCatalogs.size,
            awayFromDefault,
        )
    }

    /** T-177: the `fill` colours the port draws are the ones the index declares. */
    @Test
    fun testEveryDrawingsFillColoursAgreeWithTheIndex() {
        val disagreements = walk().fillDisagreements
        assertEquals(
            "the port must fill with the colours the index declares:\n" + disagreements.joinToString("\n"),
            emptyList<String>(),
            disagreements,
        )
    }

    /** T-178: and so are the `stroke` colours. */
    @Test
    fun testEveryDrawingsStrokeColoursAgreeWithTheIndex() {
        val disagreements = walk().strokeDisagreements
        assertEquals(
            "the port must stroke with the colours the index declares:\n" + disagreements.joinToString("\n"),
            emptyList<String>(),
            disagreements,
        )
    }

    /**
     * T-179: the colour guard says how many drawings it compared, and how many of
     * them held a colour to compare.
     *
     * Two extractions compared against each other are green when both come back
     * empty. So the walk is measured on the side that can actually go quiet -- the
     * colours the port drew -- rather than on the declarations, which would still
     * count 51 if the port drew nothing at all.
     *
     * The three numbers are tied to the engine whose corpus they were measured on.
     * They have to be measured again in the cycle that raises `renderEngineVersion`.
     */
    @Test
    fun testTheColourGuardSaysHowManyItCompared() {
        val index = ReferenceRendering.index()
        assertEquals(
            "engine ${CompatibilityConstants.renderEngineVersion}'s corpus holds 51 drawings",
            51,
            index.length(),
        )

        val walk = walk()
        assertEquals("the colour guard must reach every drawing in the index", index.length(), walk.compared)
        assertEquals("the port draws at least one fill colour in every drawing", 51, walk.drewAFill)
        assertEquals(
            "the port draws at least one stroke colour in 44 of them -- the seven that hold none " +
                "are the machine poles and the extra-fine silverpoint, which stroke nothing the index counts",
            44,
            walk.drewAStroke,
        )
    }

    private fun renderCircle(weight: String, filled: Boolean?): String {
        val instruction = JSONObject()
            .put("primitive", "circle")
            .put("center", JSONArray(listOf(0.5, 0.5)))
            .put("radius", 0.2)
            .put("weight", weight)
        if (filled != null) instruction.put("filled", filled)
        val score = JSONObject()
            .put("canvas", "square")
            .put("background", "white")
            .put("instructions", JSONArray().put(instruction))
        return DefaultSvgRenderer().render(
            RenderRequest(
                scoreJson = score.toString(),
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable",
                renderSeed = 12345L,
            )
        ).svg
    }

    /** The body element's fill -- the first `<circle>`, which both roads write first. */
    private fun circleFill(svg: String): String =
        Regex("""<circle[^>]*\sfill="([^"]+)"""").find(svg)!!.groupValues[1]

    /**
     * T-180: a machine pole does not fill an interior nobody asked to have filled.
     *
     * The server settles this once, in `_stroke_attrs`: `"fill": color if do_fill
     * else "none"`, with `do_fill = _fills_interior(ins)`. The port's hand road
     * reached the same answer inside `renderBodyShape`, and the geometric road --
     * which never calls it -- wrote the colour unconditionally, because
     * `ServerRendererStyle.fill` only knows whether the primitive has an inside.
     *
     * Stated as a pair on purpose. "The rotring circle is not filled" alone is
     * satisfied by a port that fills nothing at all, so the other direction is
     * here too. The two poles answer the same request in different elements: the
     * machine pole has no fill layer, so its interior is the body element's own
     * `fill`, while the hand pole draws the interior as marks in a `fill-*` group
     * and deliberately leaves the body open so the two do not stack.
     */
    @Test
    fun testTheMachinePoleDoesNotFillWhatWasNotAskedToBeFilled() {
        assertEquals(
            "a rotring circle nobody asked to fill must come out as an outline",
            "none",
            circleFill(renderCircle("rotring", filled = null)),
        )
        assertEquals(
            "a rotring circle that was asked to be filled must be filled",
            "#111111",
            circleFill(renderCircle("rotring", filled = true)),
        )

        val handBare = renderCircle("pen", filled = null)
        val handFilled = renderCircle("pen", filled = true)
        assertEquals(
            "the hand pole reads the same request the same way",
            "none",
            circleFill(handBare),
        )
        assertTrue(
            "a pen circle nobody asked to fill must hold no fill layer either",
            !handBare.contains("""class="fill-"""),
        )
        assertTrue(
            "a pen circle that was asked to be filled draws its interior as marks",
            handFilled.contains("""class="fill-"""),
        )

        // The one drawing in the corpus this divergence reached, against the
        // server's own frozen answer for it.
        val frozen = app.inku.mobile.ReferenceCorpus.text("05_circle_rotring.svg")
        assertEquals("the server draws 05_circle_rotring as an outline", "none", circleFill(frozen))
        assertEquals(
            "so must the port",
            "none",
            circleFill(ReferenceRendering.svg("05_circle_rotring")),
        )
    }

    /**
     * T-181: the declaration is what decides, not a constant that happens to
     * agree with it.
     *
     * 46 of the 51 drawings declare `default`, so a road that ignored the
     * declaration entirely would still satisfy T-177 and T-178 on all but five.
     * This swaps the declaration on a drawing that does say `default` and asks
     * the same road to draw it again.
     *
     * The swap is made on the entry this test parsed for itself. The frozen index
     * on disk is not touched, and the assertion at the end says so.
     */
    @Test
    fun testSwappingTheDeclaredCatalogChangesTheColoursDrawn() {
        val entry = ReferenceRendering.entry("01_circle_pen")
        assertEquals("01_circle_pen is a drawing the index attributes to default", "default", entry.getString("color_catalog_id"))

        val asDeclared = colours(ReferenceRendering.svg(entry), "stroke") + colours(ReferenceRendering.svg(entry), "fill")

        entry.put("color_catalog_id", "dye_earth")
        val svgSwapped = ReferenceRendering.svg(entry)
        val asSwapped = colours(svgSwapped, "stroke") + colours(svgSwapped, "fill")

        assertNotEquals("swapping the declared catalog must change the colours drawn", asDeclared, asSwapped)

        val swappedPalette = ColorCatalogs.get("dye_earth").renderMap.values.toSet()
        val defaultPalette = ColorCatalogs.get("default").renderMap.values.toSet()
        assertTrue(
            "the swapped drawing must hold a colour that belongs to dye_earth and not to default, drew $asSwapped",
            asSwapped.any { it in swappedPalette && it !in defaultPalette },
        )

        assertEquals(
            "the frozen index must be untouched by this test",
            "default",
            ReferenceRendering.entry("01_circle_pen").getString("color_catalog_id"),
        )
    }
}
