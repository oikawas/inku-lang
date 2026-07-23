package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DefaultSvgRendererPhase2fTest {

    private fun readReferenceResource(filename: String): String {
        val stream = javaClass.getResourceAsStream("/server_reference/$filename")
            ?: error("Resource /server_reference/$filename not found")
        return stream.bufferedReader().use { it.readText() }
    }

    private fun readReferenceIndex(): JSONObject {
        return JSONObject(readReferenceResource("svg_index.json"))
    }

    private fun readFillAndArcReference(): JSONObject {
        return JSONObject(readReferenceResource("renderer_fill_and_arc.json"))
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
                colorCatalogId = "sumi",
                canvasAspect = "square",
                svgProfile = "editable"
            )
        )
        return result.svg
    }

    private fun extractGroupPathDList(svg: String, groupClassPrefix: String): List<String> {
        val result = mutableListOf<String>()
        var searchIdx = 0
        while (true) {
            val groupIdx = svg.indexOf("class=\"$groupClassPrefix", searchIdx)
            if (groupIdx == -1) break
            val groupEndIdx = svg.indexOf("</g>", groupIdx)
            val searchRegion = if (groupEndIdx != -1) svg.substring(groupIdx, groupEndIdx) else svg.substring(groupIdx)
            
            var dIdx = 0
            while (true) {
                val match = searchRegion.indexOf(" d=\"", dIdx)
                if (match == -1) break
                val start = match + 4
                val end = searchRegion.indexOf("\"", start)
                result.add(searchRegion.substring(start, end))
                dIdx = end + 1
            }
            searchIdx = if (groupEndIdx != -1) groupEndIdx + 4 else svg.length
        }
        return result
    }

    private fun extractClassAttrs(svg: String): List<String> {
        val classes = mutableListOf<String>()
        var idx = 0
        while (true) {
            val match = svg.indexOf("class=\"", idx)
            if (match == -1) break
            val start = match + 7
            val end = svg.indexOf("\"", start)
            classes.add(svg.substring(start, end))
            idx = end + 1
        }
        return classes
    }

    private fun countElements(svg: String): Map<String, Int> {
        val counts = mutableMapOf<String, Int>()
        val tags = listOf("path", "circle", "rect", "polygon", "polyline", "line")
        for (tag in tags) {
            val openCount = svg.split("<$tag ").size - 1 + svg.split("<$tag>").size - 1
            if (openCount > 0) counts[tag] = openCount
        }
        return counts
    }

    @Test
    fun testFillAndArcConstantsAndSeeds() {
        val ref = readFillAndArcReference()
        val seedsRef = ref.getJSONArray("fill_stroke_seed")
        for (i in 0 until seedsRef.length()) {
            val item = seedsRef.getJSONObject(i)
            val seedInput = item.get("seed")
            val index = item.getInt("index")
            val expectedSeedStr = item.optLong("value").toULong().toString()
            val actualSeedLong = ServerRendererGeometry.fillStrokeSeed(seedInput, index)
            val actualSeedStr = actualSeedLong.toULong().toString()
            assertEquals("fill_stroke_seed for seed=$seedInput index=$index must match", expectedSeedStr, actualSeedStr)
        }
    }

    @Test
    fun testScanlineSegmentsReferenceParity() {
        val ref = readFillAndArcReference()
        val scanlinesRef = ref.getJSONArray("scanline_segments")
        for (i in 0 until scanlinesRef.length()) {
            val item = scanlinesRef.getJSONObject(i)
            val contourArr = item.getJSONArray("contour_points")
            val contour = (0 until contourArr.length()).map { idx ->
                val pt = contourArr.getJSONArray(idx)
                pt.getDouble(0) to pt.getDouble(1)
            }
            val angle = item.getDouble("angle")
            val spacing = item.getDouble("spacing")
            val seedInput = item.get("seed")

            val expectedSegs = item.getJSONArray("segments")
            val actualSegs = ServerRendererGeometry.scanlineSegments(contour, angle, spacing, seedInput)

            assertEquals("Segment count for item $i must match", expectedSegs.length(), actualSegs.size)
            for (j in 0 until expectedSegs.length()) {
                val expSeg = expectedSegs.getJSONObject(j)
                val actSeg = actualSegs[j]
                assertEquals("Index for seg $j item $i must match", expSeg.getInt("index"), actSeg.first)
                
                val expP0 = expSeg.getJSONArray("start")
                val expP1 = expSeg.getJSONArray("end")
                assertEquals("p0.x for seg $j item $i", expP0.getDouble(0), actSeg.second.first, 1e-5)
                assertEquals("p0.y for seg $j item $i", expP0.getDouble(1), actSeg.second.second, 1e-5)
                assertEquals("p1.x for seg $j item $i", expP1.getDouble(0), actSeg.third.first, 1e-5)
                assertEquals("p1.y for seg $j item $i", expP1.getDouble(1), actSeg.third.second, 1e-5)
            }
        }
    }

    @Test
    fun test03SquareFilledExactParity() {
        val expectedSvg = readReferenceResource("03_square_filled.svg")
        val actualSvg = renderSvgForReference("03_square_filled")

        val expectedFillPaths = extractGroupPathDList(expectedSvg, "fill-stroke-v1")
        val actualFillPaths = extractGroupPathDList(actualSvg, "fill-stroke-v1")

        assertEquals("fill-stroke-v1 path count for 03_square_filled.svg must match", expectedFillPaths.size, actualFillPaths.size)
        for (i in expectedFillPaths.indices) {
            assertEquals("fill-stroke-v1 path d #$i for 03_square_filled.svg must match", expectedFillPaths[i], actualFillPaths[i])
        }
    }

    @Test
    fun test04ArcCrayonExactParity() {
        val expectedSvg = readReferenceResource("04_arc_crayon.svg")
        val actualSvg = renderSvgForReference("04_arc_crayon")

        val expectedArcPaths = extractGroupPathDList(expectedSvg, "arc-stroke-v1")
        val actualArcPaths = extractGroupPathDList(actualSvg, "arc-stroke-v1")

        assertEquals("arc-stroke-v1 path count for 04_arc_crayon.svg must match", expectedArcPaths.size, actualArcPaths.size)
        for (i in expectedArcPaths.indices) {
            assertEquals("arc-stroke-v1 path d #$i for 04_arc_crayon.svg must match", expectedArcPaths[i], actualArcPaths[i])
        }
    }

    @Test
    fun test06SurfaceHatchExactParity() {
        val expectedSvg = readReferenceResource("06_surface_hatch.svg")
        val actualSvg = renderSvgForReference("06_surface_hatch")

        val expectedHatchPaths = extractGroupPathDList(expectedSvg, "surface-stroke-v1")
        val actualHatchPaths = extractGroupPathDList(actualSvg, "surface-stroke-v1")

        assertEquals("surface-stroke-v1 path count for 06_surface_hatch.svg must match", expectedHatchPaths.size, actualHatchPaths.size)
        for (i in expectedHatchPaths.indices) {
            assertEquals("surface-stroke-v1 path d #$i for 06_surface_hatch.svg must match", expectedHatchPaths[i], actualHatchPaths[i])
        }
    }

    @Test
    fun test10ArcWaveExactParity() {
        val expectedSvg = readReferenceResource("10_arc_wave.svg")
        val actualSvg = renderSvgForReference("10_arc_wave")

        val expectedArcPaths = extractGroupPathDList(expectedSvg, "arc-stroke-v1")
        val actualArcPaths = extractGroupPathDList(actualSvg, "arc-stroke-v1")

        assertEquals("arc-stroke-v1 path count for 10_arc_wave.svg must match", expectedArcPaths.size, actualArcPaths.size)
        for (i in expectedArcPaths.indices) {
            assertEquals("arc-stroke-v1 path d #$i for 10_arc_wave.svg must match", expectedArcPaths[i], actualArcPaths[i])
        }
    }

    @Test
    fun test05CircleRotringNoStrokeBands() {
        val actualSvg = renderSvgForReference("05_circle_rotring")

        assertFalse("rotring should not produce fill-stroke-v1", actualSvg.contains("fill-stroke-v1"))
        assertFalse("rotring should not produce arc-stroke-v1", actualSvg.contains("arc-stroke-v1"))
        assertFalse("rotring should not produce contour-stroke-v1", actualSvg.contains("contour-stroke-v1"))
    }

    @Test
    fun testArcIntentElementCount() {
        val svg04 = renderSvgForReference("04_arc_crayon")
        val svg10 = renderSvgForReference("10_arc_wave")

        val intent04Count = svg04.split("fill=\"none\" stroke=\"none\"").size - 1 + svg04.split("stroke=\"none\" fill=\"none\"").size - 1
        val intent10Count = svg10.split("fill=\"none\" stroke=\"none\"").size - 1 + svg10.split("stroke=\"none\" fill=\"none\"").size - 1

        assertEquals("04_arc_crayon must have exactly 1 intent element", 1, intent04Count)
        assertEquals("10_arc_wave must have exactly 1 intent element", 1, intent10Count)
    }

    @Test
    fun testAllReferenceSvgStructureParity() {
        val keys = listOf(
            "01_circle_pen", "02_line_brush", "03_square_filled", "04_arc_crayon",
            "05_circle_rotring", "06_surface_hatch", "07_circle_wave", "08_circle_perlin",
            "09_line_white", "10_arc_wave"
        )
        for (key in keys) {
            val expectedSvg = readReferenceResource("$key.svg")
            val actualSvg = renderSvgForReference(key)

            val expectedClasses = extractClassAttrs(expectedSvg)
            val actualClasses = extractClassAttrs(actualSvg)
            assertEquals("Class attributes list for $key.svg must match", expectedClasses, actualClasses)

            val expectedElements = countElements(expectedSvg)
            val actualElements = countElements(actualSvg)
            assertEquals("Element counts map for $key.svg must match", expectedElements, actualElements)
        }
    }
}
