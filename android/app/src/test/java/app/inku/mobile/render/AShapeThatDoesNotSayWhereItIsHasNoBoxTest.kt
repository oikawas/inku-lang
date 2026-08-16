package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Whether a shape gets a surface is decided by whether it said where it is.
 *
 * The server's `_shape_bbox` takes a branch only when both of the fields that
 * place the shape are stated -- `center`+`radius` for a circle and a polygon,
 * `center`+`size` for an ellipse and a cloudform, `position`+`size` for a
 * square and a triangle -- and otherwise falls through to `return None`. The
 * port used to fill the missing half in with a default in four of those five
 * branches, so the one reader of the answer, `renderSurfaceVectors` with its
 * `?: return ""`, laid a surface on shapes the server leaves bare.
 *
 * None of this can be gated by the frozen corpus: of the 51 drawings only two
 * carry a surface at all (`06_surface_hatch` and `21_hatch_computer`), and both
 * are squares stating every field. So these are properties, and every expected
 * number below was read off `server/src/inku_server/renderer.py` -- `_shape_bbox`
 * at `:3432`, `_px` at `:5999`, `_size_px` at `:6004` -- rather than off the
 * port's own answer.
 *
 * The cloudform branch already agreed with the server and is not asked about
 * here; T-87 in `ThePortAnswersTheSameWayTheServerDoesTest` holds that one.
 */
class AShapeThatDoesNotSayWhereItIsHasNoBoxTest {

    private val seed = 12345L

    /** 1618x1000, so `unit` (1000) and `width` are different numbers. */
    private val goldenWidth = 1618.0
    private val goldenHeight = 1000.0
    private val goldenUnit = 1000.0

    private val squareSide = 1000.0

    private val surface =
        """"surface":{"texture":"hatch","direction":"diagonal_falling","density":0.5,"opacity":0.3}"""

    private fun instruction(vararg fields: String): JSONObject =
        JSONObject("{" + fields.joinToString(",") + ",\"weight\":\"pen\"," + surface + "}")

    private fun circle(): JSONObject =
        instruction(""""primitive":"circle"""", """"center":[0.5,0.5]""", """"radius":0.3""")

    private fun ellipse(): JSONObject =
        instruction(""""primitive":"ellipse"""", """"center":[0.5,0.5]""", """"size":[0.4,0.3]""")

    private fun corner(primitive: String): JSONObject =
        instruction(""""primitive":"$primitive"""", """"position":[0.25,0.25]""", """"size":[0.4,0.3]""")

    /**
     * Stated with `position` and `size` on top of `center` and `radius`, so that
     * dropping either half leaves something the old substitutions could have
     * built a box out of: the centre came from `position`+`size`, and the radius
     * from half of `size[0]`.
     */
    private fun polygon(): JSONObject = instruction(
        """"primitive":"polygon"""", """"center":[0.5,0.5]""", """"radius":0.3""",
        """"position":[0.25,0.25]""", """"size":[0.4,0.3]""", """"sides":5""",
    )

    private fun JSONObject.without(field: String): JSONObject =
        JSONObject(this.toString()).apply { remove(field) }

    /** The other spelling of "not stated": the key is there and its value is null. */
    private fun JSONObject.nulled(field: String): JSONObject =
        JSONObject(this.toString()).apply { put(field, JSONObject.NULL) }

    private fun boxOf(ins: JSONObject): DoubleArray? =
        ServerRendererGeometry.shapeBbox(ins, goldenWidth, goldenHeight, goldenUnit)

    private fun renderScore(instruction: JSONObject, aspect: String): String {
        val score = JSONObject().put("instructions", org.json.JSONArray().put(instruction))
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

    private fun surfaceRows(instruction: JSONObject): Int =
        renderScore(instruction, "golden").split("surface-stroke-v1").size - 1

    /**
     * Both halves missing, either half missing, and either half spelled as JSON
     * null -- against the control that states both, without which deleting the
     * branch altogether would leave the gate green.
     *
     * The last pair is the one that says the reading is "not stated" and not
     * "falsy": a shape sitting at the origin with a radius of zero has stated
     * both, and the server's `is not None` lets it through.
     */
    private fun assertTheGateIsTheServers(
        label: String,
        complete: JSONObject,
        first: String,
        second: String,
        atOrigin: JSONObject,
    ) {
        for (field in listOf(first, second)) {
            assertNull(
                "$label without a $field must have no bounding box",
                boxOf(complete.without(field)),
            )
            assertNull(
                "$label with a null $field must have no bounding box",
                boxOf(complete.nulled(field)),
            )
        }
        assertNull(
            "$label without either must have no bounding box",
            boxOf(complete.without(first).without(second)),
        )
        assertNotNull(
            "the control: $label stating both must have one",
            boxOf(complete),
        )
        assertNotNull(
            "$label at the origin with nothing to see has stated both, so it has a box",
            boxOf(atOrigin),
        )
    }

    /** T-182. A circle that never said where it is, or how big, has no box. */
    @Test
    fun testACircleMissingCentreOrRadiusHasNoBox() {
        assertTheGateIsTheServers(
            "a circle", circle(), "center", "radius",
            instruction(""""primitive":"circle"""", """"center":[0,0]""", """"radius":0"""),
        )
    }

    /** T-183. And so does an ellipse. */
    @Test
    fun testAnEllipseMissingCentreOrSizeHasNoBox() {
        assertTheGateIsTheServers(
            "an ellipse", ellipse(), "center", "size",
            instruction(""""primitive":"ellipse"""", """"center":[0,0]""", """"size":[0,0]"""),
        )
    }

    /** T-184. And a square and a triangle, which are placed by their corner. */
    @Test
    fun testASquareOrTriangleMissingPositionOrSizeHasNoBox() {
        for (primitive in listOf("square", "triangle")) {
            assertTheGateIsTheServers(
                "a $primitive", corner(primitive), "position", "size",
                instruction(""""primitive":"$primitive"""", """"position":[0,0]""", """"size":[0,0]"""),
            )
        }
    }

    /**
     * T-185. A polygon reads `center` and `radius` and nothing else.
     *
     * Both instructions below state `position` and `size`, which is what the two
     * substitutions the port used to make were built from -- a centre out of
     * `position` plus half of `size`, and a radius out of half of `size[0]`.
     * They are asked one at a time, so that a port that dropped one substitution
     * and kept the other cannot pass.
     */
    @Test
    fun testAPolygonMissingCentreOrRadiusHasNoBox() {
        assertNull(
            "a polygon stating position and size but no centre must have no box",
            boxOf(polygon().without("center")),
        )
        assertNull(
            "a polygon stating a size but no radius must have no box",
            boxOf(polygon().without("radius")),
        )
        assertTheGateIsTheServers(
            "a polygon", polygon(), "center", "radius",
            instruction(""""primitive":"polygon"""", """"center":[0,0]""", """"radius":0""", """"sides":5"""),
        )
    }

    /**
     * T-186. And the layer that reads the box draws nothing for a shape that has
     * none, which is what the null is for.
     *
     * Each shape is asked in a pair: once with a field taken away, and once with
     * it back. Without the second half, an implementation whose surface layer
     * never runs at all would pass this.
     *
     * The polygon is asked with BOTH `center` and `radius` taken away, so that
     * restoring either substitution on its own still leaves it boxless -- what
     * one substitution at a time does is T-185's question, not this one.
     */
    @Test
    fun testABoxlessShapeGetsNoSurface() {
        val pairs = listOf(
            Triple("a circle", circle().without("radius"), circle()),
            Triple("an ellipse", ellipse().without("size"), ellipse()),
            Triple("a square", corner("square").without("position"), corner("square")),
            Triple("a triangle", corner("triangle").without("size"), corner("triangle")),
            Triple("a polygon", polygon().without("center").without("radius"), polygon()),
        )
        for ((label, boxless, stated) in pairs) {
            assertEquals(
                "$label without its box must draw no surface rows",
                0,
                surfaceRows(boxless),
            )
            assertTrue(
                "the control: $label that states its box must draw some",
                surfaceRows(stated) >= 1,
            )
        }
    }

    /**
     * T-187. The shapes that do state their box keep the box they had.
     *
     * Tightening the gate must not move the arithmetic behind it: the surface
     * sits inside these four numbers, so a box a few percent wider slides every
     * row on the page. The numbers are written out here rather than read back
     * out of the product, and both papers are measured because a size goes
     * through `_size_px`, which puts a stated extent on the SHORT side -- on a
     * square canvas `unit` and `width` are the same number and a box built off
     * the width would pass, while on 1618x1000 it would answer 647.2 where the
     * server answers 400.
     */
    @Test
    fun testTheBoxOfAStatedShapeDidNotMove() {
        // cx = 0.5*1618 = 809, r = 0.3*1000 = 300.
        assertBox("a circle on golden", circle(), goldenWidth, 509.0, 200.0, 600.0, 600.0)
        assertBox("a circle on square", circle(), squareSide, 200.0, 200.0, 600.0, 600.0)

        // w, h = 0.4*1000, 0.3*1000 = 400, 300, hung on the centre.
        assertBox("an ellipse on golden", ellipse(), goldenWidth, 609.0, 350.0, 400.0, 300.0)
        assertBox("an ellipse on square", ellipse(), squareSide, 300.0, 350.0, 400.0, 300.0)

        // x = 0.25*1618 = 404.5; the corner is the box's corner.
        for (primitive in listOf("square", "triangle")) {
            assertBox("a $primitive on golden", corner(primitive), goldenWidth, 404.5, 250.0, 400.0, 300.0)
            assertBox("a $primitive on square", corner(primitive), squareSide, 250.0, 250.0, 400.0, 300.0)
        }

        // A polygon's box is its centre and radius, the same shape as a circle's.
        assertBox("a polygon on golden", polygon(), goldenWidth, 509.0, 200.0, 600.0, 600.0)
        assertBox("a polygon on square", polygon(), squareSide, 200.0, 200.0, 600.0, 600.0)
    }

    /** `width` picks the paper: 1618 is the golden one, 1000 the square. */
    private fun assertBox(
        label: String,
        ins: JSONObject,
        width: Double,
        x: Double,
        y: Double,
        w: Double,
        h: Double,
    ) {
        val box = ServerRendererGeometry.shapeBbox(ins, width, goldenHeight, goldenUnit)
        assertNotNull("$label must have a bounding box", box)
        assertEquals("$label: x", x, box!![0], 1e-9)
        assertEquals("$label: y", y, box[1], 1e-9)
        assertEquals("$label: width", w, box[2], 1e-9)
        assertEquals("$label: height", h, box[3], 1e-9)
    }
}
