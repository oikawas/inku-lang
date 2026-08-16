package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import app.inku.mobile.pipeline.ServerScoreSchemaJson
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A surface belongs to the shape that carries it (engine 35).
 *
 * The two hatch cases in the frozen corpus are both unrotated squares, whose
 * contour happens to be their own bounding box, so the corpus alone cannot say
 * whether the rows are cut at the shape or merely at a rectangle. These gates
 * are the triangle the corpus does not hold, plus the one that says every
 * surface word the schema offers the model is a word this layer draws.
 */
class ASurfaceKeepsToItsShapeTest {

    /** `square` resolves to 1000x1000, so the stated ratios read straight as pixels. */
    private val canvasPx = 1000.0

    private fun renderSvg(instruction: String): String =
        DefaultSvgRenderer().render(
            RenderRequest(
                scoreJson = """{"instructions":[$instruction]}""",
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable",
                renderSeed = 12345L,
            )
        ).svg

    private fun surfacePoints(svg: String): List<Pair<Double, Double>> {
        val points = mutableListOf<Pair<Double, Double>>()
        val number = Regex("""(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)""")
        val group = Regex("""<(?:path|line)\b[^>]*class="surface-stroke-v1[^"]*"[^>]*>""")
        for (element in group.findAll(svg)) {
            val d = Regex(""" d="([^"]*)"""").find(element.value)?.groupValues?.get(1)
            if (d != null) {
                number.findAll(d).forEach { points.add(it.groupValues[1].toDouble() to it.groupValues[2].toDouble()) }
                continue
            }
            // The non-hand branch draws a bare <line>; read its two ends.
            fun attr(name: String) = Regex(""" $name="([^"]*)"""").find(element.value)?.groupValues?.get(1)?.toDouble()
            val x1 = attr("x1"); val y1 = attr("y1"); val x2 = attr("x2"); val y2 = attr("y2")
            if (x1 != null && y1 != null && x2 != null && y2 != null) {
                points.add(x1 to y1)
                points.add(x2 to y2)
            }
        }
        return points
    }

    private fun insidePolygon(point: Pair<Double, Double>, polygon: List<Pair<Double, Double>>): Boolean {
        var inside = false
        for (index in polygon.indices) {
            val (ax, ay) = polygon[index]
            val (bx, by) = polygon[(index + 1) % polygon.size]
            if ((ay > point.second) != (by > point.second)) {
                val t = (point.second - ay) / (by - ay)
                if (point.first < ax + (bx - ax) * t) inside = !inside
            }
        }
        return inside
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

    /** How far the furthest drawn point sits outside the shape, in pixels. */
    private fun overshootPx(svg: String, polygon: List<Pair<Double, Double>>): Double {
        val points = surfacePoints(svg)
        assertTrue("the surface must have drawn something to measure", points.size > 50)
        return points.filterNot { insidePolygon(it, polygon) }.maxOfOrNull { point ->
            polygon.indices.minOf { i -> distanceToEdge(point, polygon[i], polygon[(i + 1) % polygon.size]) }
        } ?: 0.0
    }

    /**
     * The two shapes, written from the description rather than from the code:
     * position 0.25 and size 0.5 on a 1000px square is a 500px box at (250, 250).
     */
    private val squarePolygon = listOf(250.0 to 250.0, 750.0 to 250.0, 750.0 to 750.0, 250.0 to 750.0)
    private val trianglePolygon = listOf(500.0 to 250.0, 750.0 to 750.0, 250.0 to 750.0)

    private fun shape(primitive: String, texture: String) =
        """{"primitive":"$primitive","position":[0.25,0.25],"size":[0.5,0.5],"weight":"pen",
            "surface":{"texture":"$texture","density":0.5,"direction":"diagonal_rising"}}"""

    /** T-77: hatch rows do not leave the shape. */
    @Test
    fun testHatchRowsStayInsideTheContour() {
        assertTrue(
            "hatch on a square must stay within 20px of it",
            overshootPx(renderSvg(shape("square", "hatch")), squarePolygon) <= 20.0,
        )
        assertTrue(
            "hatch on a triangle must stay within 20px of it",
            overshootPx(renderSvg(shape("triangle", "hatch")), trianglePolygon) <= 20.0,
        )
    }

    /** T-77: and neither does the second layer a crosshatch adds. */
    @Test
    fun testCrosshatchRowsStayInsideTheContour() {
        assertTrue(
            "crosshatch on a square must stay within 20px of it",
            overshootPx(renderSvg(shape("square", "crosshatch")), squarePolygon) <= 20.0,
        )
        assertTrue(
            "crosshatch on a triangle must stay within 20px of it",
            overshootPx(renderSvg(shape("triangle", "crosshatch")), trianglePolygon) <= 20.0,
        )
    }

    /**
     * The words the schema offers the model for `surface.texture`, read from the
     * schema itself rather than copied here. A copy would go stale the day the
     * schema moved, and this gate is about the two lists agreeing.
     */
    private fun offeredSurfaceWords(): List<String> {
        val schema = JSONObject(ServerScoreSchemaJson.parameters)
        val surface = schema.getJSONObject("properties")
            .getJSONObject("instructions")
            .getJSONObject("items")
            .getJSONObject("properties")
            .getJSONObject("surface")
            .getJSONArray("anyOf")
            .getJSONObject(0)
        val words = surface.getJSONObject("properties").getJSONObject("texture").getJSONArray("enum")
        return (0 until words.length()).map { words.getString(it) }
    }

    /**
     * T-166: every surface word the schema offers is a word the port draws.
     *
     * This replaces the T-78 control, which asserted that `bleed` drew nothing.
     * That claim was true and is what this round went to change, and it could
     * not simply lose its one entry: an empty list makes the loop run zero times
     * and the check assert nothing at all. So the claim is turned over instead,
     * which also makes it the guard for the other side of ledger I-008 -- the
     * port must not offer the model a texture it cannot draw. The count of words
     * that draw went 8 to 3 to 1 to 0 over ten rounds; `bleed` was the last.
     *
     * `none` and `solid` are not drawn by this layer on either side: `none` is
     * the absence of one, and a `solid` is laid down by the fill layer.
     *
     * The elements are counted against the same shape carrying no surface, so
     * that the shape's own body never counts as a texture.
     */
    @Test
    fun testEverySurfaceWordTheSchemaOffersIsDrawn() {
        val offered = offeredSurfaceWords()
        assertTrue("the schema must offer `none`", offered.contains("none"))
        assertTrue("the schema must offer `solid`", offered.contains("solid"))
        val drawable = offered.filterNot { it == "none" || it == "solid" }
        assertEquals("the words this layer is asked to draw", 8, drawable.size)

        fun pieces(svg: String) = Triple(
            Regex("surface-stroke-v1").findAll(svg).count(),
            Regex("<circle").findAll(svg).count(),
            Regex("<polygon").findAll(svg).count(),
        )
        val bare = pieces(renderSvg(shape("square", "none")))
        for (texture in drawable) {
            val drawn = pieces(renderSvg(shape("square", texture)))
            val added = (drawn.first - bare.first) + (drawn.second - bare.second) + (drawn.third - bare.third)
            assertTrue("$texture is offered to the model, so it must draw something", added > 0)
        }
    }
}
