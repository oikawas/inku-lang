package app.inku.mobile.render

import app.inku.mobile.ReferenceCorpus
import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * engine 16 gives the corner shapes the material layer square already had.
 *
 * The expected values are the server's, and they are read from the frozen corpus rather
 * than copied into this file. They used to be sha256 literals measured once at engine 16;
 * a hand-copied expectation freezes whatever the server said on the day it was copied, and
 * engine 28 -- which broke each stratum into contact fragments and renamed its class --
 * turned all four of them into stale copies at once. `31_triangle_pencil` and
 * `32_polygon_brush_thin` hold exactly these two cases, at the same seed, keyed by engine
 * version, so reading them means the check follows the server instead of outliving it.
 *
 * What is asserted here and nowhere else is the material layer *per tool*: the corpus-wide
 * parity tests compare every drawing on every attribute, but they do not say which tool is
 * supposed to come out clothed and which bare.
 */
class CornerShapeMaterialLayerTest {

    private val renderer = DefaultSvgRenderer()

    private fun renderFromCorpus(key: String): Pair<String, String> {
        val entry = ReferenceCorpus.json("svg_index.json").getJSONObject(key)
        val renderSeed = if (entry.isNull("render_seed")) null else entry.getLong("render_seed")
        val svg = renderer.render(
            RenderRequest(
                scoreJson = entry.getJSONObject("score").toString(),
                colorCatalogId = ReferenceRendering.catalogId(entry),
                canvasAspect = "square",
                svgProfile = "editable",
                renderSeed = renderSeed,
            )
        ).svg
        return Pair(ReferenceCorpus.text("$key.svg"), svg)
    }

    private fun render(instruction: JSONObject): String {
        val score = JSONObject()
            .put("canvas", "square")
            .put("background", "white")
            .put("instructions", JSONArray().put(instruction))
        return renderer.render(
            RenderRequest(
                scoreJson = score.toString(),
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable",
                renderSeed = 12345L,
            )
        ).svg
    }

    private fun classes(svg: String): List<String> =
        Regex("""class="([^"]+)"""").findAll(svg).map { it.groupValues[1] }.toList()

    /** Points of every element carrying a material-outline class, attribute order aside. */
    private fun outlinePoints(svg: String): List<String> =
        Regex("""<(?:polyline|polygon)\b([^>]*)/?>""").findAll(svg).mapNotNull { match ->
            val attrs = Regex("""([\w-]+)="([^"]*)"""").findAll(match.groupValues[1])
                .associate { it.groupValues[1] to it.groupValues[2] }
            if (attrs["class"]?.startsWith("material-outline") == true) attrs["points"] else null
        }.toList()

    /**
     * Where each grain of powder landed, not merely how many there are. A count alone
     * survives a wrong spread: halving the intensity ladder's speck gain moves all 48 and
     * changes none of them away.
     */
    private fun speckPositions(svg: String): List<String> =
        Regex("""<circle\b([^>]*)/?>""").findAll(svg).mapNotNull { match ->
            val attrs = Regex("""([\w-]+)="([^"]*)"""").findAll(match.groupValues[1])
                .associate { it.groupValues[1] to it.groupValues[2] }
            if (attrs["stroke"] == "none" && attrs.containsKey("cx")) {
                "${attrs["cx"]},${attrs["cy"]},${attrs["r"]}"
            } else {
                null
            }
        }.toList()

    private fun triangle(weight: String): JSONObject = JSONObject()
        .put("primitive", "triangle")
        .put("position", JSONArray(listOf(0.3, 0.3)))
        .put("size", JSONArray(listOf(0.4, 0.4)))
        .put("weight", weight)
        .put("color", "black")

    @Test
    fun testATrianglePencilCarriesTheServersMaterialLayer() {
        val (expected, actual) = renderFromCorpus("31_triangle_pencil")
        assertEquals("the class list must be the server's", classes(expected), classes(actual))
        assertEquals(
            "the strata must ride the performed centreline exactly as the server draws them",
            outlinePoints(expected),
            outlinePoints(actual),
        )
        assertEquals(
            "every grain must land where the server puts it, spread by the ladder's 1.8",
            speckPositions(expected),
            speckPositions(actual),
        )
        // The claim the corpus cannot make on its own: the pencil is one of the tools that
        // owns both mechanisms, so it must come out with strata AND with powder.
        assertTrue("the pencil wears two strata", classes(actual).any { it == "material-outline stratum-1" })
        assertTrue("the pencil leaves powder", speckPositions(actual).isNotEmpty())
    }

    @Test
    fun testAPolygonBrushThinCarriesTheServersMaterialLayer() {
        val (expected, actual) = renderFromCorpus("32_polygon_brush_thin")
        assertEquals("the class list must be the server's", classes(expected), classes(actual))
        assertEquals(outlinePoints(expected), outlinePoints(actual))
        assertTrue("brush_thin wears two strata", classes(actual).any { it == "material-outline stratum-1" })
        assertEquals("brush_thin is given no powder", emptyList<String>(), speckPositions(actual))
    }

    @Test
    fun testTheMachinePoleStaysBare() {
        // rotring owns no material mechanism at all, so widening the corner shapes must
        // not have handed it one.
        val svg = render(triangle("rotring"))
        assertEquals(emptyList<String>(), classes(svg))
        assertEquals(0, outlinePoints(svg).size)
        assertEquals(emptyList<String>(), speckPositions(svg))
    }

    @Test
    fun testTheStrataDoNotSitOnTheGeometry() {
        // Drawn from the performed centreline, not from the corners: taken from the
        // geometry they would follow three straight edges, so the vertices of a stratum
        // would number the shape's corners rather than the band's samples. Counted over
        // all fragments of one stratum, because engine 28 breaks a stratum where the tool
        // lost the paper.
        val svg = render(triangle("pencil"))
        val stratumZeroVertices = Regex("""<polyline\b([^>]*)/?>""").findAll(svg).sumOf { match ->
            val attrs = Regex("""([\w-]+)="([^"]*)"""").findAll(match.groupValues[1])
                .associate { it.groupValues[1] to it.groupValues[2] }
            if (attrs["class"] == "material-outline stratum-0") {
                attrs["points"]!!.trim().split(" ").size
            } else {
                0
            }
        }
        assertTrue("a stratum must be sampled, not a bare triangle", stratumZeroVertices > 8)
    }
}
