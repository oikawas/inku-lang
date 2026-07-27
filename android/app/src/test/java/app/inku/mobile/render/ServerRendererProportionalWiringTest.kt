package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max

class ServerRendererProportionalWiringTest {

    private val renderer = DefaultSvgRenderer()

    @Test
    fun testStrokeWidthProportionalWiring() {
        val weights = mapOf(
            "hair" to Pair(0.5, 0.1),
            "rotring" to Pair(1.0, 0.2),
            "pencil" to Pair(1.5, 0.3),
            "pen" to Pair(2.0, 0.4),
            "drypoint" to Pair(2.6, 0.52),
            "chalk" to Pair(3.0, 0.6),
            "brush_thin" to Pair(3.0, 0.6),
            "burin" to Pair(3.2, 0.64),
            "crayon" to Pair(4.0, 0.8),
            "brush_thick" to Pair(8.0, 1.6)
        )

        for ((weight, expected) in weights) {
            val scoreJson = JSONObject()
                .put("canvas", "square")
                .put("background", "white")
                .put("instructions", JSONArray().put(
                    JSONObject()
                        .put("primitive", "line")
                        .put("weight", weight)
                        .put("color", "black")
                        .put("from", JSONArray(listOf(0.1, 0.5)))
                        .put("to", JSONArray(listOf(0.9, 0.5)))
                )).toString()

            val resSquare = renderer.render(RenderRequest(scoreJson = scoreJson, colorCatalogId = "default", canvasAspect = "square", svgProfile = "editable"))
            val resPillar = renderer.render(RenderRequest(scoreJson = scoreJson, colorCatalogId = "default", canvasAspect = "pillar", svgProfile = "editable"))

            if (weight == "rotring") {
                val widthSquare = extractStrokeWidth(resSquare.svg)
                assertEquals("Square stroke-width for $weight", expected.first, widthSquare, 1e-9)

                val widthPillar = extractStrokeWidth(resPillar.svg)
                assertEquals("Pillar stroke-width for $weight", expected.second, widthPillar, 1e-9)
            } else {
                assertTrue("Non-rotring line ($weight) should produce stroke-engine-v1 band in square", resSquare.svg.contains("stroke-engine-v1"))
                assertTrue("Non-rotring line ($weight) should produce stroke-engine-v1 band in pillar", resPillar.svg.contains("stroke-engine-v1"))
            }
        }
    }

    @Test
    fun testAmplitudeProportionalWiring() {
        val scoreJson = JSONObject()
            .put("canvas", "square")
            .put("background", "white")
            .put("instructions", JSONArray().put(
                JSONObject()
                    .put("primitive", "circle")
                    .put("weight", "pen")
                    .put("color", "black")
                    .put("center", JSONArray(listOf(0.5, 0.5)))
                    .put("radius", 0.20)
                    .put("variation", JSONObject()
                        .put("quality", "wave")
                        .put("amplitude", "medium")
                        .put("frequency", "medium")
                        .put("dimensions", JSONArray(listOf("radius")))
                    )
            )).toString()

        val resSquare = renderer.render(RenderRequest(scoreJson = scoreJson, colorCatalogId = "default", canvasAspect = "square", svgProfile = "editable"))
        val resPillar = renderer.render(RenderRequest(scoreJson = scoreJson, colorCatalogId = "default", canvasAspect = "pillar", svgProfile = "editable"))

        val devSquare = maxRadiusDeviation(resSquare.svg, 500.0, 500.0, 200.0)
        val devPillar = maxRadiusDeviation(resPillar.svg, 100.0, 500.0, 40.0)

        assertTrue("Square amplitude deviation $devSquare should not exceed 16.0", devSquare <= 16.0 + 1e-6)
        assertTrue("Pillar amplitude deviation $devPillar should not exceed 3.2", devPillar <= 3.2 + 1e-6)

        val ratio = devSquare / devPillar
        assertEquals("Deviation ratio between square (unit 1000) and pillar (unit 200)", 5.0, ratio, 0.25)
    }

    @Test
    fun testBlurProportionalWiring() {
        val scoreJson = JSONObject()
            .put("canvas", "square")
            .put("background", "white")
            .put("instructions", JSONArray().put(
                JSONObject()
                    .put("primitive", "circle")
                    .put("weight", "pen")
                    .put("color", "black")
                    .put("center", JSONArray(listOf(0.5, 0.5)))
                    .put("radius", 0.20)
                    .put("variation", JSONObject()
                        .put("quality", "pink")
                        .put("amplitude", "medium")
                        .put("frequency", "medium")
                    )
            )).toString()

        val resSquare = renderer.render(RenderRequest(scoreJson = scoreJson, colorCatalogId = "default", canvasAspect = "square", svgProfile = "editable"))
        val resPillar = renderer.render(RenderRequest(scoreJson = scoreJson, colorCatalogId = "default", canvasAspect = "pillar", svgProfile = "editable"))

        val stdSquare = extractGaussianBlurStd(resSquare.svg)
        val stdPillar = extractGaussianBlurStd(resPillar.svg)

        assertEquals("Square blur stdDeviation", 6.0, stdSquare, 1e-9)
        assertEquals("Pillar blur stdDeviation", 1.2, stdPillar, 1e-9)
    }

    @Test
    fun testMaterialProportionalWiring() {
        val scoreJson = JSONObject()
            .put("canvas", "square")
            .put("background", "white")
            .put("instructions", JSONArray().put(
                JSONObject()
                    .put("primitive", "circle")
                    .put("weight", "crayon")
                    .put("color", "black")
                    .put("center", JSONArray(listOf(0.5, 0.5)))
                    .put("radius", 0.20)
            )).toString()

        val resPillar = renderer.render(RenderRequest(scoreJson = scoreJson, colorCatalogId = "default", canvasAspect = "pillar", svgProfile = "editable"))


        // Check speck count in pillar (perim = 2*PI*40 = 251.327, anchorPerim = 200*1.2566... = 251.327 -> ratio = 1.0 -> 28 * 2.6 = 72.8 -> 73 specks)
        val speckMatches = Regex("""<circle cx="[^"]+" cy="[^"]+" r="[^"]+" fill="[^"]+" stroke="none" opacity="[^"]+"/>""").findAll(resPillar.svg).toList()
        assertEquals("Speck count in pillar for crayon circle", 73, speckMatches.size)

        // engine 15 took the offset gain back to 1.0 and dropped the floor to 0.0, so the
        // strata land where the table always said. In pillar (unit = 200, scale = 0.2) the
        // crayon offset -1.5 * 0.2 = -0.3 -> r = 40.0 - 0.3 = 39.700000. Under engine 14
        // the 2.8x gain and the 0.7px floor put it at 39.160000.
        assertTrue("Contains outline circle at the table's own offset r=39.700000", resPillar.svg.contains("""r="39.700000""""))
        assertFalse("The engine 14 floored offset r=39.160000 must be gone", resPillar.svg.contains("""r="39.160000""""))
    }

    private fun extractStrokeWidth(svg: String): Double {
        val match = Regex("""stroke-width="([^"]+)"""").find(svg) ?: throw IllegalArgumentException("No stroke-width found")
        return match.groupValues[1].toDouble()
    }

    private fun extractGaussianBlurStd(svg: String): Double {
        val match = Regex("""stdDeviation="([^"]+)"""").find(svg) ?: throw IllegalArgumentException("No stdDeviation found")
        return match.groupValues[1].toDouble()
    }

    private fun maxRadiusDeviation(svg: String, cx: Double, cy: Double, baseR: Double): Double {
        val match = Regex("""<polygon points="([^"]+)"""").find(svg) ?: throw IllegalArgumentException("No polygon points found")
        val pointsStr = match.groupValues[1]
        var maxDev = 0.0
        pointsStr.split(" ").forEach { pt ->
            val coords = pt.split(",")
            if (coords.size == 2) {
                val x = coords[0].toDouble()
                val y = coords[1].toDouble()
                val dist = hypot(x - cx, y - cy)
                val dev = abs(dist - baseR)
                if (dev > maxDev) maxDev = dev
            }
        }
        return maxDev
    }
}
