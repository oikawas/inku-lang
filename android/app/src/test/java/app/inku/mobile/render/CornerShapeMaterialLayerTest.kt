package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * engine 15 gave the corner shapes the material layer square already had.
 *
 * The frozen reference corpus cannot see this: not one of its 25 cases is a triangle or a
 * polygon. Deleting the call outright leaves the whole suite green, which is the failure
 * this file exists to close - a correct function that nothing ever calls.
 *
 * The expected values were measured from the server (v2.9.0, render engine 15) at
 * render_seed 12345, not from this port. With them in place the port's output is
 * element-for-element identical to the server's for all three cases, down to the 48
 * powder specks; the only remaining difference in the document is the background rect's
 * `id`, which the port has never emitted.
 */
class CornerShapeMaterialLayerTest {

    private val renderer = DefaultSvgRenderer()

    private fun render(instruction: JSONObject): String {
        val score = JSONObject()
            .put("canvas", "square")
            .put("background", "white")
            .put("render_seed", 12345L)
            .put("instructions", JSONArray().put(instruction))
        return renderer.render(
            RenderRequest(
                scoreJson = score.toString(),
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable"
            )
        ).svg
    }

    private fun classes(svg: String): List<String> =
        Regex("""class="([^"]+)"""").findAll(svg).map { it.groupValues[1] }.toList()

    /** Points of every polygon carrying class="material-outline", attribute order aside. */
    private fun outlinePoints(svg: String): List<String> =
        Regex("""<polygon\b([^>]*)/?>""").findAll(svg).mapNotNull { match ->
            val attrs = Regex("""([\w-]+)="([^"]*)"""").findAll(match.groupValues[1])
                .associate { it.groupValues[1] to it.groupValues[2] }
            if (attrs["class"] == "material-outline") attrs["points"] else null
        }.toList()

    private fun sha256(text: String): String =
        MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }

    private fun speckCount(svg: String): Int =
        Regex("""<circle[^>]*stroke="none"""").findAll(svg).count()

    private fun triangle(weight: String): JSONObject = JSONObject()
        .put("primitive", "triangle")
        .put("position", JSONArray(listOf(0.3, 0.3)))
        .put("size", JSONArray(listOf(0.4, 0.4)))
        .put("weight", weight)
        .put("color", "black")

    private fun hexagon(weight: String): JSONObject = JSONObject()
        .put("primitive", "polygon")
        .put("center", JSONArray(listOf(0.5, 0.5)))
        .put("radius", 0.25)
        .put("sides", 6)
        .put("weight", weight)
        .put("color", "black")

    @Test
    fun testATrianglePencilCarriesTheServersMaterialLayer() {
        val svg = render(triangle("pencil"))
        assertEquals(
            listOf("contour-stroke-v1 controls-64 events-0", "material-outline", "material-outline"),
            classes(svg),
        )
        val points = outlinePoints(svg)
        assertEquals("two strata, as the pencil table says", 2, points.size)
        assertEquals(
            "the strata must ride the performed centreline exactly as the server draws them",
            "c9e24c029a9bb1128b4677dff5a8efd740a0fd53c915d4a4a0ba0eb486e9e47a",
            sha256(points.joinToString("|")),
        )
        assertEquals("pencil powder, spread by the intensity ladder's 1.8", 48, speckCount(svg))
    }

    @Test
    fun testAPolygonBrushThinCarriesTheServersMaterialLayer() {
        val svg = render(hexagon("brush_thin"))
        assertEquals(
            listOf("contour-stroke-v1 controls-102 events-0", "material-outline", "material-outline"),
            classes(svg),
        )
        val points = outlinePoints(svg)
        assertEquals(2, points.size)
        assertEquals(
            "02fca4c7c951d6b72dbcceeb9332ed6722475b648aa32d9a133f4630ef811144",
            sha256(points.joinToString("|")),
        )
        assertEquals("brush_thin is given no powder", 0, speckCount(svg))
    }

    @Test
    fun testTheMachinePoleStaysBare() {
        // rotring owns no material mechanism at all, so widening the corner shapes must
        // not have handed it one.
        val svg = render(triangle("rotring"))
        assertEquals(emptyList<String>(), classes(svg))
        assertEquals(0, outlinePoints(svg).size)
        assertEquals(0, speckCount(svg))
    }

    @Test
    fun testTheStrataDoNotSitOnTheGeometry() {
        // Drawn from the performed centreline, not from the corners: if they were taken
        // from the geometry they would be three-sided like the shape itself.
        val svg = render(triangle("pencil"))
        val points = outlinePoints(svg)
        assertTrue("a stratum must be sampled, not a bare triangle", points.all { it.split(" ").size > 8 })
    }
}
