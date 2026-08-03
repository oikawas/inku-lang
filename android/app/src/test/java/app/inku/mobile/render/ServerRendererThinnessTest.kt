package app.inku.mobile.render

import app.inku.mobile.pipeline.ServerScoreCoercer
import app.inku.mobile.pipeline.ServerScoreSchemaJson
import app.inku.mobile.pipeline.ServerScoreSemantics
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerRendererThinnessTest {
    private fun fixture(): JSONObject {
        val stream = javaClass.getResourceAsStream("/server_reference/renderer_proportional.json")
            ?: error("renderer_proportional.json not found")
        return JSONObject(stream.bufferedReader().use { it.readText() })
    }

    private fun nullableString(item: JSONObject, key: String): String? =
        if (!item.has(key) || item.isNull(key)) null else item.getString(key)

    @Test
    fun testStrokeWidthsAndConstantsMatchTheServer() {
        val root = fixture()
        val constants = root.getJSONObject("constants")
        val expectedScales = constants.getJSONObject("THINNESS_TO_WIDTH_SCALE")
        assertEquals(expectedScales.getDouble("null"), ServerRendererStyle.thinnessToWidthScale.getValue(null), 1e-12)
        assertEquals(expectedScales.getDouble("fine"), ServerRendererStyle.thinnessToWidthScale.getValue("fine"), 1e-12)
        assertEquals(expectedScales.getDouble("extra_fine"), ServerRendererStyle.thinnessToWidthScale.getValue("extra_fine"), 1e-12)

        val minimum = ServerRendererStyle.weightToStrokeWidth.values.minOrNull()
            ?: error("stroke width table is empty")
        assertEquals(constants.getDouble("MIN_STROKE_WIDTH"), minimum, 1e-12)

        val canvases = root.getJSONObject("canvases")
        val cases = root.getJSONArray("stroke_width_thinness_px")
        for (index in 0 until cases.length()) {
            val item = cases.getJSONObject(index)
            val aspect = item.getString("aspect")
            val weight = item.getString("weight")
            val thinness = nullableString(item, "thinness")
            val unit = canvases.getJSONObject(aspect).getDouble("unit")
            val actual = ServerRendererStyle.strokeWidth(weight, unit, thinness)
            assertEquals("stroke width mismatch for $aspect/$weight/$thinness", item.getDouble("value"), actual, 1e-9)
            assertTrue("no tool may draw below the silverpoint floor", actual >= minimum * (unit / 1000.0))
        }

        assertEquals(setOf(null, "fine", "extra_fine"), ServerRendererStyle.thinnessToWidthScale.keys)
        assertTrue("thinness has no thick side", ServerRendererStyle.thinnessToWidthScale.values.all { it <= 1.0 })
        listOf(null, "fine", "extra_fine").forEach { thinness ->
            assertEquals(0.5, ServerRendererStyle.strokeWidth("silverpoint", 1000.0, thinness), 1e-12)
        }
    }

    @Test
    fun testMaterialOutlinesMatchTheServer() {
        val root = fixture()
        val canvases = root.getJSONObject("canvases")
        val cases = root.getJSONArray("material_outline_thinness")
        for (index in 0 until cases.length()) {
            val item = cases.getJSONObject(index)
            val aspect = item.getString("aspect")
            val weight = item.getString("weight")
            val thinness = nullableString(item, "thinness")
            val unit = canvases.getJSONObject(aspect).getDouble("unit")
            val expected = item.getJSONArray("layers")
            val actual = ServerRendererMaterial.materialOutlineProfile(weight, unit, thinness)
            assertEquals("layer count mismatch for $aspect/$weight/$thinness", expected.length(), actual.size)
            actual.forEachIndexed { layerIndex, layer ->
                val expectedLayer = expected.getJSONObject(layerIndex)
                assertEquals(expectedLayer.getDouble("offset"), layer.offset, 1e-9)
                assertEquals(expectedLayer.getDouble("width"), layer.width, 1e-9)
                assertEquals(expectedLayer.getDouble("opacity"), layer.opacity, 1e-9)
                assertEquals(expectedLayer.optString("dash").takeIf { it.isNotEmpty() }, layer.dash)
            }
        }
    }

    @Test
    fun testSchemaDeclaresThinnessImmediatelyBeforeSurface() {
        // Optional fields fill in more often the further back they are declared, and
        // the last slot belongs to `surface`: while `thinness` held it, surface's
        // carry fell 92% -> 42% and Stage 2's whole output halved (server contract
        // stage2-score-shrinkage, 2026-08-03). That `surface` is genuinely last is
        // held by ServerScoreVocabularyTest against the server-generated fixture;
        // what this pins is that nothing gets wedged between the two.
        val schema = ServerScoreSchemaJson.parameters
        val thinness = schema.indexOf("\"thinness\":{")
        val surface = schema.indexOf("\"surface\":{")
        assertTrue("both fields must exist", thinness >= 0 && surface >= 0)
        assertTrue("thinness must be declared before surface", thinness < surface)
        assertTrue(
            "only the thinness object may sit between thinness and surface",
            schema.substring(thinness, surface).endsWith("\"title\":\"Thinness\"},"),
        )
        val afterThinness = schema.substring(thinness)
        assertTrue(afterThinness.contains("\"enum\":[\"fine\",\"extra_fine\"]"))
        assertTrue(afterThinness.contains("\"default\":null"))
        assertFalse("there is no thick thinness value", afterThinness.contains("\"thick\""))
    }

    @Test
    fun testCoercerPreservesButNeverCreatesThinness() {
        fun coerce(source: JSONObject, ddl: String = ""): JSONObject =
            ServerScoreCoercer.coerceInstruction(
                source = source,
                ddl = ddl,
                background = "white",
                detectColorKey = ServerScoreSemantics::detectColorKey,
                detectWeightKey = ServerScoreSemantics::detectWeightKey,
                visibleForeground = ServerScoreSemantics::visibleForeground,
            )

        assertEquals(
            "fine",
            coerce(JSONObject("""{"primitive":"line","thinness":"fine"}""")).getString("thinness"),
        )
        assertEquals(
            "extra_fine",
            coerce(JSONObject("""{"primitive":"line","thinness":"extra_fine"}""")).getString("thinness"),
        )
        assertFalse(coerce(JSONObject("""{"primitive":"line","thinness":"thick"}""")).has("thinness"))
        assertFalse(
            "DDL wording must not make the coercer invent thinness",
            coerce(JSONObject("""{"primitive":"line","weight":"pencil"}"""), "極細の鉛筆線を引く").has("thinness"),
        )
    }
}
