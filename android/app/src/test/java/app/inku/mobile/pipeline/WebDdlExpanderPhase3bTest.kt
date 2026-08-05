package app.inku.mobile.pipeline

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class WebDdlExpanderPhase3bTest {

    private fun readReferenceCorpus(): JSONObject {
        val stream = javaClass.getResourceAsStream("/server_reference/ddl_expand.json")
            ?: error("Resource /server_reference/ddl_expand.json not found")
        val content = stream.bufferedReader().use { it.readText() }
        return JSONObject(content)
    }

    private fun getCase(corpus: JSONObject, caseName: String): JSONObject {
        val cases = corpus.getJSONArray("cases")
        for (i in 0 until cases.length()) {
            val caseObj = cases.getJSONObject(i)
            if (caseObj.getString("case") == caseName) {
                return caseObj
            }
        }
        error("Case '$caseName' not found in reference corpus")
    }

    private fun parseSeed(input: JSONObject, key: String): Long? {
        if (!input.has(key) || input.isNull(key)) return null
        val raw = input.get(key)
        return when (raw) {
            is Number -> raw.toLong()
            is String -> raw.toULongOrNull()?.toLong() ?: raw.toLong()
            else -> raw.toString().toULongOrNull()?.toLong()
        }
    }

    private fun verifyCorpusCase(corpus: JSONObject, caseName: String) {
        val caseObj = getCase(corpus, caseName)
        val input = caseObj.getJSONObject("input")
        val expectedOutput = caseObj.getString("output")

        val ddl = input.getString("ddl")
        val lang = if (input.has("lang")) input.getString("lang") else "ja"
        val contextText = if (!input.has("context_text") || input.isNull("context_text")) null else input.getString("context_text")
        // manifest key renamed in v2.8.0; the expander parameter and the "#vary" salt stay frozen.
        val varySeed = parseSeed(input, "composition_seed")
        val enablePlugins = input.optBoolean("enable_plugins", true)
        val pluginInstructionsPresent = input.optBoolean("plugin_instructions_present", false)
        val focus = if (!input.has("focus") || input.isNull("focus")) null else input.getString("focus")
        val variationAmplitude = if (!input.has("variation_amplitude") || input.isNull("variation_amplitude")) null else input.getString("variation_amplitude")
        val variationSeed = parseSeed(input, "variation_seed")

        val variationReport = mutableMapOf<String, Any>()
        val actualOutput = WebDdlExpander.expandIntermediateDdl(
            ddl = ddl,
            lang = lang,
            contextText = contextText,
            varySeed = varySeed,
            enablePlugins = enablePlugins,
            pluginInstructionsPresent = pluginInstructionsPresent,
            focus = focus,
            variationAmplitude = variationAmplitude,
            variationSeed = variationSeed,
            variationReport = variationReport,
        )

        assertEquals("Output mismatch for case: $caseName", expectedOutput, actualOutput)

        if (caseObj.has("variation_report")) {
            val expectedReport = caseObj.getJSONObject("variation_report")
            val expectedFocus = expectedReport.getString("resolved_focus")
            val actualFocus = variationReport["resolved_focus"] as? String
            assertEquals("resolved_focus mismatch for case: $caseName", expectedFocus, actualFocus)

            val expectedMoved = expectedReport.getJSONArray("moved_axes")
            @Suppress("UNCHECKED_CAST")
            val actualMoved = (variationReport["moved_axes"] as? List<Map<String, String>>).orEmpty()
            assertEquals("moved_axes count mismatch for case: $caseName", expectedMoved.length(), actualMoved.size)

            for (i in 0 until expectedMoved.length()) {
                val expMovedObj = expectedMoved.getJSONObject(i)
                val actMovedMap = actualMoved[i]
                assertEquals("moved_axes[$i].axis mismatch for case: $caseName", expMovedObj.getString("axis"), actMovedMap["axis"])
                assertEquals("moved_axes[$i].from mismatch for case: $caseName", expMovedObj.getString("from"), actMovedMap["from"])
                assertEquals("moved_axes[$i].to mismatch for case: $caseName", expMovedObj.getString("to"), actMovedMap["to"])
            }
        }
    }

    @Test
    fun testPhase3bCorpus16CasesMatchExactly() {
        val corpus = readReferenceCorpus()
        val phase3bCases = listOf(
            "A-variation-amplitude-only",
            "A-variation-seed-only",
            "A-variation-small-1",
            "A-variation-small-12345",
            "A-variation-medium-1",
            "A-variation-medium-12345",
            "A-variation-large-1",
            "A-variation-large-12345",
            "B-variation-seed-9223372036854775809",
            "B-variation-seed-18446744073709551615",
            "B-variation-en",
            "B-focus-upper_left",
            "B-focus-lower_right",
            "B-focus-right_half",
            "B-focus-upper_edge",
            "B-focus-not-a-focus",
        )

        for (caseName in phase3bCases) {
            verifyCorpusCase(corpus, caseName)
        }
    }
}
