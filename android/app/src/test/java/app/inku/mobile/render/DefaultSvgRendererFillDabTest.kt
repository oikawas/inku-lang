package app.inku.mobile.render

import app.inku.mobile.ReferenceCorpus
import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DefaultSvgRendererFillDabTest {
    private val renderer = DefaultSvgRenderer()
    private val attrs = SvgAttrs(
        stroke = "#111111",
        strokeWidth = 2.0,
        strokeLinecap = "round",
        strokeOpacity = 1.0,
        fill = "#111111",
    )

    private fun resource(name: String): String = ReferenceCorpus.text(name)

    private fun fixture(): JSONObject = JSONObject(resource("renderer_fill_and_arc.json"))

    private fun contour(item: JSONObject): List<Pair<Double, Double>> {
        val values = item.getJSONArray("contour")
        return (0 until values.length()).map { index ->
            val point = values.getJSONArray(index)
            point.getDouble(0) to point.getDouble(1)
        }
    }

    private fun instruction(item: JSONObject): JSONObject = JSONObject()
        .put("primitive", "circle")
        .put("filled", true)
        .put("weight", item.getString("weight"))
        .also {
            if (!item.isNull("thinness")) it.put("thinness", item.getString("thinness"))
        }

    private fun groupClass(group: String?): String? =
        group?.let { Regex("""<g class="([^"]+)"""").find(it)?.groupValues?.get(1) }

    private fun pathD(group: String?): List<String> =
        if (group == null) emptyList()
        else Regex("""<path\b[^>]*\bd="([^"]+)"""").findAll(group).map { it.groupValues[1] }.toList()

    private fun assertPathNear(message: String, expected: String, actual: String) {
        val number = Regex("""-?\d+(?:\.\d+)?""")
        val expectedNumbers = number.findAll(expected).map { it.value.toDouble() }.toList()
        val actualNumbers = number.findAll(actual).map { it.value.toDouble() }.toList()
        assertEquals("$message coordinate count", expectedNumbers.size, actualNumbers.size)
        expectedNumbers.indices.forEach { index ->
            assertEquals("$message coordinate $index", expectedNumbers[index], actualNumbers[index], 1e-5)
        }
        assertEquals(
            "$message path commands",
            expected.replace(number, "#"),
            actual.replace(number, "#"),
        )
    }

    private fun renderReference(key: String): String {
        val index = JSONObject(resource("svg_index.json"))
        val entry = index.getJSONObject(key)
        val score = JSONObject(entry.getJSONObject("score").toString())
        // The corpus keeps the seed beside the Score; so does the server.
        val renderSeed = if (entry.isNull("render_seed")) null else entry.getLong("render_seed")
        if (entry.has("wild") && !entry.isNull("wild")) {
            score.put("render_wild", entry.getBoolean("wild"))
        }
        val canvas = when (val value = score.opt("canvas")) {
            is String -> value
            is JSONObject -> value.optString("aspect", "square")
            else -> "square"
        }
        return renderer.render(
            RenderRequest(
                scoreJson = score.toString(),
                colorCatalogId = ReferenceRendering.catalogId(entry),
                canvasAspect = entry.optString("canvas_aspect", canvas),
                svgProfile = "editable",
                renderSeed = renderSeed,
            )
        ).svg
    }

    @Test
    fun testFillDabConstantsAndAllTenPathsMatchTheServer() {
        val root = fixture()
        val constants = root.getJSONObject("constants")
        assertEquals(constants.getInt("FILL_DAB_SAMPLES"), FILL_DAB_SAMPLES)
        assertEquals(constants.getDouble("FILL_DAB_MIN_TRAVEL"), FILL_DAB_MIN_TRAVEL, 1e-12)

        val cases = root.getJSONArray("fill_dab_group")
        for (index in 0 until cases.length()) {
            val item = cases.getJSONObject(index)
            val group = renderer.renderFillDab(
                ins = instruction(item),
                attrs = attrs,
                contour = contour(item),
                unit = 1000.0,
                instructionSeed = item.get("seed"),
            )
            assertEquals("${item.getString("case")} dab class", item.getString("dab_class"), groupClass(group))
            val expectedPaths = item.getJSONArray("dab_path_d")
            assertEquals("${item.getString("case")} must be one placed path", item.getInt("dab_path_count"), pathD(group).size)
            val actualPaths = pathD(group)
            for (pathIndex in 0 until expectedPaths.length()) {
                // The fixture serializes its input contour at 6 decimals after deriving the
                // expected path from the server's full-precision contour. Replaying those
                // serialized points can therefore differ by one final grid digit.
                assertPathNear(
                    "${item.getString("case")} dab path d",
                    expectedPaths.getString(pathIndex),
                    actualPaths[pathIndex],
                )
            }
        }
    }

    @Test
    fun testInteriorBranchMatchesAllTenServerCases() {
        val cases = fixture().getJSONArray("fill_dab_group")
        val actualByName = mutableMapOf<String, Pair<String?, Boolean>>()
        for (index in 0 until cases.length()) {
            val item = cases.getJSONObject(index)
            val actual = renderer.interiorFill(
                ins = instruction(item),
                attrs = attrs,
                contour = contour(item),
                unit = 1000.0,
                instructionSeed = item.get("seed"),
            )
            val name = item.getString("case")
            actualByName[name] = groupClass(actual.first) to actual.second
            val expectedClass = if (item.isNull("interior_class")) null else item.getString("interior_class")
            assertEquals("$name interior class", expectedClass, groupClass(actual.first))
            assertEquals("$name region-fill branch", item.getBoolean("interior_region_fill"), actual.second)
        }

        // Either side of the boundary engine 16 measured go opposite ways, and
        // since engine 22 the scanned side is an underlay with marks on it
        // rather than the marks alone: `fill-v2` wraps the field and whichever
        // branch the coverage chose. A dab has no underlay -- it is one touch
        // of the tool, and giving it one would put back the flat region fill
        // engine 16 took out of tiny shapes.
        assertEquals("fill-dab-v1", actualByName.getValue("boundary_below_pen").first)
        assertEquals("fill-v2", actualByName.getValue("boundary_above_pen").first)
        assertEquals(null, actualByName.getValue("tiny_circle_rotring").first)
        assertTrue(actualByName.getValue("tiny_circle_rotring").second)
        assertEquals("fill-v2", actualByName.getValue("large_circle_pen").first)
    }

    @Test
    fun testLargeFillReferencesRemainExact() {
        for (key in listOf("03_square_filled", "30_square_filled_pencil_fine")) {
            val expected = resource("$key.svg")
            val actual = renderReference(key)
            assertEquals(
                "$key path list",
                Regex(""" d="([^"]*)"""").findAll(expected).map { it.groupValues[1] }.toList(),
                Regex(""" d="([^"]*)"""").findAll(actual).map { it.groupValues[1] }.toList(),
            )
            assertFalse("$key must stay on scanline fill", actual.contains("fill-dab-v1"))
        }
    }

    @Test
    fun testTinyFillReferenceUsesOneDabEndToEnd() {
        val actual = renderReference("26_tinyfill_circle_pen")
        val start = actual.indexOf("""class="fill-dab-v1"""")
        assertTrue(start >= 0)
        val end = actual.indexOf("</g>", start)
        assertEquals(1, pathD(actual.substring(start, end)).size)
    }
}
