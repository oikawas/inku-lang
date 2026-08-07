package app.inku.mobile.render

import app.inku.mobile.ReferenceCorpus
import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DefaultSvgRendererPhase2dTest {

    private fun readResourceText(name: String): String = ReferenceCorpus.text(name)

    private fun extractPathD(svg: String): String {
        val regex = """<path [^>]*d="([^"]+)"[^\/>]*\/>""".toRegex()
        val match = regex.find(svg)
        assertNotNull("path element should be present in SVG", match)
        return match!!.groupValues[1]
    }

    private fun extractClassAttr(svg: String): String {
        val regex = """<g [^>]*class="([^"]+)"[^\/>]*>""".toRegex()
        val match = regex.find(svg)
        assertNotNull("group element with class should be present in SVG", match)
        return match!!.groupValues[1]
    }

    @Test
    fun testLineBrushParity() {
        val refSvg = readResourceText("02_line_brush.svg")
        val expectedD = extractPathD(refSvg)
        val expectedClass = extractClassAttr(refSvg)

        val scoreJson = JSONObject().apply {
            put("render_seed", 12345)
            put("instructions", JSONArray().apply {
                put(JSONObject().apply {
                    put("primitive", "line")
                    put("from", JSONArray().apply { put(0.1); put(0.5) })
                    put("to", JSONArray().apply { put(0.9); put(0.5) })
                    put("weight", "brush_thick")
                })
            })
        }.toString()

        val renderer = DefaultSvgRenderer()
        val actualResult = renderer.render(
            RenderRequest(
                scoreJson = scoreJson,
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable"
            )
        )
        val actualSvg = actualResult.svg

        val actualD = extractPathD(actualSvg)
        val actualClass = extractClassAttr(actualSvg)

        assertEquals("class attribute must match reference SVG", expectedClass, actualClass)
        assertEquals("path d attribute must match reference SVG exactly", expectedD, actualD)
    }

    @Test
    fun testRotringLineDoesNotCreateStrokeEngineBand() {
        val scoreJson = JSONObject().apply {
            put("render_seed", 12345)
            put("instructions", JSONArray().apply {
                put(JSONObject().apply {
                    put("primitive", "line")
                    put("from", JSONArray().apply { put(0.1); put(0.5) })
                    put("to", JSONArray().apply { put(0.9); put(0.5) })
                    put("weight", "rotring")
                })
            })
        }.toString()

        val renderer = DefaultSvgRenderer()
        val actualResult = renderer.render(
            RenderRequest(
                scoreJson = scoreJson,
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable"
            )
        )
        val actualSvg = actualResult.svg

        assertFalse("rotring line should not create stroke-engine-v1 group", actualSvg.contains("stroke-engine-v1"))
        assertTrue("rotring line should contain geometric <line>", actualSvg.contains("<line "))
    }

    @Test
    fun testLineWhiteVariationParity() {
        val refSvg = readResourceText("09_line_white.svg")
        val expectedD = extractPathD(refSvg)
        val expectedClass = extractClassAttr(refSvg)

        val scoreJson = JSONObject().apply {
            put("render_seed", 12345)
            put("instructions", JSONArray().apply {
                put(JSONObject().apply {
                    put("primitive", "line")
                    put("from", JSONArray().apply { put(0.1); put(0.5) })
                    put("to", JSONArray().apply { put(0.9); put(0.5) })
                    put("weight", "pencil")
                    put("variation", JSONObject().apply {
                        put("amplitude", "medium")
                        put("frequency", "medium")
                        put("quality", "white")
                        put("dimensions", JSONArray().apply { put("position_y") })
                    })
                })
            })
        }.toString()

        val renderer = DefaultSvgRenderer()
        val actualResult = renderer.render(
            RenderRequest(
                scoreJson = scoreJson,
                colorCatalogId = "default",
                canvasAspect = "square",
                svgProfile = "editable"
            )
        )
        val actualSvg = actualResult.svg

        val actualD = extractPathD(actualSvg)
        val actualClass = extractClassAttr(actualSvg)

        assertEquals("class attribute must match reference SVG", expectedClass, actualClass)
        assertEquals("path d attribute must match reference SVG exactly", expectedD, actualD)
    }
}
