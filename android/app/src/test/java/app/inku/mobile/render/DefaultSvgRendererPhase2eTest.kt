package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DefaultSvgRendererPhase2eTest {

    private fun readReferenceSvg(filename: String): String {
        val stream = javaClass.getResourceAsStream("/server_reference/$filename")
            ?: error("Resource /server_reference/$filename not found")
        return stream.bufferedReader().use { it.readText() }
    }

    private fun readReferenceIndex(): JSONObject {
        val stream = javaClass.getResourceAsStream("/server_reference/svg_index.json")
            ?: error("Resource /server_reference/svg_index.json not found")
        return JSONObject(stream.bufferedReader().use { it.readText() })
    }

    private fun renderSvgForReference(key: String): String {
        val indexJson = readReferenceIndex()
        val entry = indexJson.getJSONObject(key)
        val scoreObj = entry.getJSONObject("score")
        if (entry.has("render_seed") && !entry.isNull("render_seed")) {
            scoreObj.put("render_seed", entry.getLong("render_seed"))
        }

        val renderer = DefaultSvgRenderer()
        val result = renderer.render(
            RenderRequest(
                scoreJson = scoreObj.toString(),
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable"
            )
        )
        return result.svg
    }

    private fun extractContourPathD(svg: String): String {
        val groupIdx = svg.indexOf("contour-stroke-v1")
        if (groupIdx == -1) return ""
        val dIdx = svg.indexOf("d=\"", groupIdx)
        if (dIdx == -1) return ""
        val start = dIdx + 3
        val end = svg.indexOf("\"", start)
        return svg.substring(start, end)
    }

    private fun extractContourClassAttr(svg: String): String {
        val classIdx = svg.indexOf("class=\"contour-stroke-v1")
        if (classIdx == -1) return ""
        val start = classIdx + 7
        val end = svg.indexOf("\"", start)
        return svg.substring(start, end)
    }

    @Test
    fun test01CirclePenExactParity() {
        val expectedSvg = readReferenceSvg("01_circle_pen.svg")
        val actualSvg = renderSvgForReference("01_circle_pen")

        val expectedD = extractContourPathD(expectedSvg)
        val actualD = extractContourPathD(actualSvg)
        val expectedClass = extractContourClassAttr(expectedSvg)
        val actualClass = extractContourClassAttr(actualSvg)

        assertEquals("class attribute for 01_circle_pen.svg must match", expectedClass, actualClass)
        assertEquals("path d for 01_circle_pen.svg must match exactly", expectedD, actualD)
    }

    @Test
    fun test05CircleRotringNoContourStroke() {
        val actualSvg = renderSvgForReference("05_circle_rotring")

        assertFalse("rotring should not produce contour-stroke-v1 class", actualSvg.contains("contour-stroke-v1"))
        assertFalse("rotring should not produce <path> elements", actualSvg.contains("<path"))
        assertTrue("rotring should produce standard circle element", actualSvg.contains("<circle"))
    }

    @Test
    fun test07CircleWaveExactParity() {
        val expectedSvg = readReferenceSvg("07_circle_wave.svg")
        val actualSvg = renderSvgForReference("07_circle_wave")

        val expectedD = extractContourPathD(expectedSvg)
        val actualD = extractContourPathD(actualSvg)
        val expectedClass = extractContourClassAttr(expectedSvg)
        val actualClass = extractContourClassAttr(actualSvg)

        assertEquals("class attribute for 07_circle_wave.svg must match", expectedClass, actualClass)
        assertEquals("path d for 07_circle_wave.svg must match exactly", expectedD, actualD)
    }

    @Test
    fun test08CirclePerlinExactParity() {
        val expectedSvg = readReferenceSvg("08_circle_perlin.svg")
        val actualSvg = renderSvgForReference("08_circle_perlin")

        val expectedD = extractContourPathD(expectedSvg)
        val actualD = extractContourPathD(actualSvg)
        val expectedClass = extractContourClassAttr(expectedSvg)
        val actualClass = extractContourClassAttr(actualSvg)

        assertEquals("class attribute for 08_circle_perlin.svg must match", expectedClass, actualClass)
        assertEquals("path d for 08_circle_perlin.svg must match exactly", expectedD, actualD)
    }

    @Test
    fun test03SquareFilledContourClassMatch() {
        val expectedSvg = readReferenceSvg("03_square_filled.svg")
        val actualSvg = renderSvgForReference("03_square_filled")

        val expectedClass = extractContourClassAttr(expectedSvg)
        val actualClass = extractContourClassAttr(actualSvg)

        assertEquals("contour-stroke-v1 class for 03_square_filled.svg must match", expectedClass, actualClass)
    }

    @Test
    fun test06SurfaceHatchContourClassMatch() {
        val expectedSvg = readReferenceSvg("06_surface_hatch.svg")
        val actualSvg = renderSvgForReference("06_surface_hatch")

        val expectedClass = extractContourClassAttr(expectedSvg)
        val actualClass = extractContourClassAttr(actualSvg)

        assertEquals("contour-stroke-v1 class for 06_surface_hatch.svg must match", expectedClass, actualClass)
    }
}
