package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A surface belongs to the shape that carries it (engine 35).
 *
 * The two hatch cases in the frozen corpus are both unrotated squares, whose
 * contour happens to be their own bounding box, so the corpus alone cannot say
 * whether the rows are cut at the shape or merely at a rectangle. These gates
 * are the triangle the corpus does not hold, plus the control that says the
 * other surface words were not touched.
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
     * T-78, the control: the other surface words were not touched.
     *
     * The contract states this as "wash and stipple overshoot by the same amount
     * before and after". This port drew neither -- renderSurfaceVectors answered
     * `hatch` and `crosshatch` and returned "" for every other texture -- so the
     * same claim was put the only way it could be measured here: they still draw
     * nothing. Widening the cut to take them in is what P-14 does, and it fails
     * here.
     *
     * `wash` left this list first, and `stipple` and `aquatint` have now
     * followed it. All three are drawn: the wash by render engine 36's surface
     * layer and the grains and the bands by the port of `_surface_dab`, whose
     * gates live in [AWashIsAFieldTest] and [AGrainIsOneTouchTest]. One word is
     * still offered to the model and still draws nothing -- `bleed`, which
     * shares none of that mechanism and has its own 66 lines on the server -- so
     * the control keeps its force for it.
     */
    @Test
    fun testTheOtherSurfaceWordsAreUntouched() {
        for (texture in listOf("bleed")) {
            val svg = renderSvg(shape("square", texture))
            assertEquals(
                "$texture must still contribute no surface stroke",
                0,
                Regex("surface-stroke-v1").findAll(svg).count(),
            )
        }
        // And the one that does draw is not caught by the same net, or the check
        // above would pass on a renderer that drew nothing at all.
        assertTrue(
            "hatch must still draw, or the control above proves nothing",
            Regex("surface-stroke-v1").findAll(renderSvg(shape("square", "hatch"))).count() > 20,
        )
    }
}
