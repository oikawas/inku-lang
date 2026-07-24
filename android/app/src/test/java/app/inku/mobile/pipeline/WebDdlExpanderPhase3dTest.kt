package app.inku.mobile.pipeline

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class WebDdlExpanderPhase3dTest {

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

    private fun verifyCorpusCase(corpus: JSONObject, caseName: String) {
        val caseObj = getCase(corpus, caseName)
        val input = caseObj.getJSONObject("input")
        val expectedOutput = caseObj.getString("output")

        val ddl = input.getString("ddl")
        val lang = if (input.has("lang")) input.getString("lang") else "ja"
        val contextText = if (!input.has("context_text") || input.isNull("context_text")) null else input.getString("context_text")
        val varySeed = if (!input.has("vary_seed") || input.isNull("vary_seed")) null else input.getLong("vary_seed")
        val enablePlugins = input.optBoolean("enable_plugins", true)
        val pluginInstructionsPresent = input.optBoolean("plugin_instructions_present", false)
        val tenkei = input.optString("tenkei", "auto")
        val focus = if (!input.has("focus") || input.isNull("focus")) null else input.getString("focus")
        val variationAmplitude = if (!input.has("variation_amplitude") || input.isNull("variation_amplitude")) null else input.getString("variation_amplitude")
        val variationSeed = if (!input.has("variation_seed") || input.isNull("variation_seed")) null else input.getLong("variation_seed")

        val actualOutput = WebDdlExpander.expandIntermediateDdl(
            ddl = ddl,
            lang = lang,
            contextText = contextText,
            varySeed = varySeed,
            enablePlugins = enablePlugins,
            pluginInstructionsPresent = pluginInstructionsPresent,
            tenkei = tenkei,
            focus = focus,
            variationAmplitude = variationAmplitude,
            variationSeed = variationSeed,
        )

        assertEquals("Output mismatch for case: $caseName", expectedOutput, actualOutput)
    }

    @Test
    fun testPhase3dCorpusCasesMatchExactly() {
        val corpus = readReferenceCorpus()
        val phase3dCases = listOf(
            "A-plugin-enabled",
            "A-plugin-disabled",
            "B-plugin-instructions-present"
        )

        for (caseName in phase3dCases) {
            verifyCorpusCase(corpus, caseName)
        }
    }

    @Test
    fun testNaturePluginMacroSensitivityToAvoidTautology() {
        val corpus = readReferenceCorpus()
        val caseObj = getCase(corpus, "A-plugin-enabled")
        val input = caseObj.getJSONObject("input")
        val expectedOutput = caseObj.getString("output")

        val ddl = input.getString("ddl")
        val lang = if (input.has("lang")) input.getString("lang") else "ja"

        // Disabling plugins explicitly should produce a different output (133 bytes vs 120 bytes)
        val disabledOutput = WebDdlExpander.expandIntermediateDdl(
            ddl = ddl,
            lang = lang,
            enablePlugins = false
        )

        assertNotEquals(
            "Disabling plugin macros should alter output for A-plugin-enabled to prevent tautology test",
            expectedOutput,
            disabledOutput
        )
    }
}
