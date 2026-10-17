package app.inku.mobile.pipeline

import java.io.File
import java.math.BigInteger
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The server's saved-variant cases must cross the production JNI byte boundary unchanged. */
class SharedSavedVariantsJniTest {
    private val cases: JSONObject by lazy {
        val identityCases = File(requireNotNull(System.getProperty("inku.identityCases")))
        JSONObject(identityCases.resolveSibling("saved-variant-cases.json").readText())
    }
    private val binding: SharedPipelineBinding = NativePipelineBridge

    private fun ask(request: JSONObject): JSONObject =
        JSONObject(binding.savedVariants(CoreIdentityJson.encode(request).encodeToByteArray()).toString(Charsets.UTF_8))

    private fun request(action: String): JSONObject = JSONObject().put("action", action)

    private fun assertJsonEquals(label: String, expected: Any, actual: Any) {
        assertEquals(label, CoreIdentityJson.canonical(expected), CoreIdentityJson.canonical(actual))
    }

    private fun assertOk(label: String, answer: JSONObject) {
        assertEquals(label, "inku.saved-variants.v1", answer.getString("schema"))
        assertEquals(label, "ok", answer.getString("outcome"))
    }

    @Test
    fun everyToolRowCrossesJniWithItsSavedScoreAndOwnerTypes() {
        val config = JSONObject(SharedPipelineConfigBuilder(binding).build(
            SharedPipelineConfigRequest("ja", "square", "default", bundledPluginsEnabled = false),
        ).configJson)
        val source = "赤の円を1個置く。\n青の円を1個置く。\n緑の円を1個置く。\n黒の円を1個置く。"
        val rows = cases.getJSONArray("tools")
        assertEquals(5, rows.length())
        for (rowIndex in 0 until rows.length()) {
            val row = rows.getJSONObject(rowIndex)
            val why = row.getString("why")
            val plan = ask(request("tool_plan")
                .put("config", config).put("source", source).put("score", row.getJSONObject("score"))
                .put("mode", "per_sentence").put("seed", 7L))
            assertOk("$why plan", plan)
            val drawn = JSONObject()
            val sentences = plan.getJSONArray("sentences")
            for (index in 0 until sentences.length()) {
                val sentence = sentences.getJSONObject(index)
                drawn.put(sentence.getInt("index").toString(), sentence.getString("tool"))
            }
            assertJsonEquals("$why drawn", row.getJSONObject("drawn"), drawn)
            val answer = ask(request("tool_render")
                .put("config", config).put("source", source).put("score", row.getJSONObject("score"))
                .put("mode", "per_sentence").put("tools", row.getJSONObject("asked")))
            assertOk(why, answer)
            assertJsonEquals(why, row.getJSONObject("score_with_tools"), answer.getJSONObject("score"))
            assertJsonEquals("$why asked tools", row.getJSONObject("asked"),
                answer.getJSONObject("derivation_metadata").getJSONObject("tools"))
        }
    }

    @Test
    fun toolPlanPreservesSeedsIncludingUnsignedMaximumAndEachMode() {
        val config = JSONObject(SharedPipelineConfigBuilder(binding).build(
            SharedPipelineConfigRequest("ja", "square", "default", bundledPluginsEnabled = false),
        ).configJson)
        val score = JSONObject().put("instructions", JSONArray()
            .put(JSONObject().put("weight", "brush_thin").put("arrangement", JSONObject()
                .put("resolved", JSONObject().put("owner", JSONObject()
                    .put("kind", "source_instruction").put("instruction_index", 0)))))
            .put(JSONObject().put("arrangement", JSONObject()
                .put("resolved", JSONObject().put("owner", JSONObject()
                    .put("kind", "source_instruction").put("instruction_index", 1))))))
        val source = "背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな円を1個置く。"
        val count = cases.getJSONObject("conditions").getInt("count")
        assertEquals(4, count)
        for (mode in listOf("uniform", "per_sentence")) {
            for (seed in listOf(7L, BigInteger("18446744073709551615"))) {
                val answer = ask(request("tool_plan")
                    .put("config", config).put("source", source).put("score", score)
                    .put("mode", mode).put("seed", seed))
                assertOk("$mode seed $seed", answer)
                assertEquals(mode, answer.getString("mode"))
                val labels = answer.getJSONArray("tool_labels")
                val values = JSONArray()
                for (index in 0 until labels.length()) values.put(labels.getJSONObject(index).getString("value"))
                assertJsonEquals("tool labels", cases.getJSONObject("conditions").getJSONArray("tools"), values)
                val drawn = answer.getJSONArray("sentences")
                assertEquals(2, drawn.length())
                assertEquals("brush_thin", drawn.getJSONObject(0).getString("tool"))
                assertEquals("pen", drawn.getJSONObject(1).getString("tool"))
                val entries = answer.getJSONArray("entries")
                assertEquals("$mode seed $seed", count, entries.length())
                val uniformTools = mutableSetOf<String>()
                for (index in 0 until entries.length()) {
                    val tools = entries.getJSONObject(index).getJSONObject("tools")
                    val first = tools.getString("0")
                    val second = tools.getString("1")
                    assertTrue(first in cases.getJSONObject("conditions").getJSONArray("tools").let { values ->
                        (0 until values.length()).map(values::getString)
                    })
                    assertTrue(second in cases.getJSONObject("conditions").getJSONArray("tools").let { values ->
                        (0 until values.length()).map(values::getString)
                    })
                    assertTrue(entries.getJSONObject(index).getJSONArray("changes").length() > 0)
                    if (mode == "uniform") {
                        assertEquals(first, second)
                        uniformTools += first
                    } else {
                        assertFalse(first == "brush_thin" || second == "pen")
                    }
                }
                if (mode == "uniform") assertEquals(count, uniformTools.size)
            }
        }
    }

    @Test
    fun everyGroundRowAndSentenceCrossesJni() {
        val rows = cases.getJSONArray("grounds")
        assertEquals(5, rows.length())
        for (rowIndex in 0 until rows.length()) {
            val row = rows.getJSONObject(rowIndex)
            val why = row.getString("why")
            val score = row.getJSONObject("score")
            val plan = ask(request("ground_plan").put("score", score))
            assertOk(why, plan)
            assertEquals(why, row.getString("current"), plan.getString("current"))
            val materials = JSONArray()
            val entries = plan.getJSONArray("entries")
            for (index in 0 until entries.length()) materials.put(entries.getJSONObject(index).getString("material"))
            assertJsonEquals("$why materials", row.getJSONArray("entries"), materials)
            val expected = row.getJSONObject("score_with_ground")
            for (material in expected.keys().asSequence()) {
                val drawn = ask(request("ground_render")
                    .put("score", score).put("source", "").put("material", material).put("language", "ja"))
                assertOk("$why $material", drawn)
                assertJsonEquals("$why $material score", expected.get(material), drawn.get("score"))
            }
        }
        val sentences = cases.getJSONArray("ground_sentences")
        assertEquals(8, sentences.length())
        val score = JSONObject().put("canvas", "square").put("instructions", JSONArray())
        for (rowIndex in 0 until sentences.length()) {
            val row = sentences.getJSONObject(rowIndex)
            val expected = row.getJSONObject("results")
            for (material in expected.keys().asSequence()) {
                val drawn = ask(request("ground_render")
                    .put("score", score).put("source", row.getString("ddl"))
                    .put("material", material).put("language", row.get("language")))
                assertOk("${row.getString("why")} $material", drawn)
                assertEquals("${row.getString("why")} $material", expected.getString(material), drawn.getString("ddl"))
            }
        }
    }

    @Test
    fun everyColorPageAndRenderPreservesLargeIndices() {
        val rows = cases.getJSONArray("colors")
        assertEquals(2, rows.length())
        for (rowIndex in 0 until rows.length()) {
            val row = rows.getJSONObject(rowIndex)
            val why = row.getString("why")
            fun base(action: String) = request(action).put("svg", row.getString("svg"))
                .put("color_map", row.getJSONObject("color_map")).put("work_id", row.getString("work_id"))
            val pages = row.getJSONObject("pages")
            for (cursor in pages.keys().asSequence()) {
                val answer = ask(base("color_plan").put("cursor", cursor.toLong()))
                assertOk("$why cursor $cursor", answer)
                val expected = pages.getJSONObject(cursor)
                for (field in listOf("entries", "next_cursor", "total")) {
                    assertJsonEquals("$why cursor $cursor $field", expected.get(field), answer.get(field))
                }
            }
            val colorMaps = row.getJSONObject("color_maps")
            for (index in colorMaps.keys().asSequence()) {
                val answer = ask(base("color_render").put("index", index.toLong()).put("catalog_id", "ink_season"))
                assertOk("$why index $index", answer)
                assertJsonEquals("$why index $index map", colorMaps.getJSONObject(index), answer.getJSONObject("color_map"))
                val metadata = answer.getJSONObject("derivation_metadata")
                assertEquals(index.toLong(), metadata.getLong("color_arrangement_index"))
                assertEquals("ink_season", metadata.getString("catalog_id"))
            }
            if (row.getJSONObject("color_map").length() == 13) {
                assertTrue("fixture must exercise a count above 32 bits", pages.getJSONObject("0").getLong("total") > Int.MAX_VALUE)
                assertEquals(6_227_020_799L, pages.getJSONObject("0").getLong("total"))
            }
        }
    }

    @Test
    fun everyColorRefusalAndMalformedRequestCrossesJni() {
        val rows = cases.getJSONArray("color_refusals")
        assertEquals(5, rows.length())
        for (rowIndex in 0 until rows.length()) {
            val row = rows.getJSONObject(rowIndex)
            val answer = ask(request("color_render")
                .put("svg", row.getString("svg")).put("color_map", row.getJSONObject("color_map"))
                .put("work_id", row.getString("work_id")).put("index", row.get("index"))
                .put("catalog_id", "x"))
            assertEquals(row.getString("why"), "refused", answer.getString("outcome"))
            assertEquals(row.getString("why"), row.getString("detail"), answer.getString("detail"))
        }
        val malformed = ask(JSONObject())
        assertEquals("invalid_request", malformed.getString("error"))
    }
}
