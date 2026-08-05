package app.inku.mobile.pipeline

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class WebDdlExpanderPhase3aTest {

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
        // manifest key renamed in v2.8.0; the expander parameter and the "#vary" salt stay frozen.
        val varySeed = if (!input.has("composition_seed") || input.isNull("composition_seed")) null else input.getLong("composition_seed")
        val enablePlugins = input.optBoolean("enable_plugins", true)
        val pluginInstructionsPresent = input.optBoolean("plugin_instructions_present", false)
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
            focus = focus,
            variationAmplitude = variationAmplitude,
            variationSeed = variationSeed,
        )

        assertEquals("Output mismatch for case: $caseName", expectedOutput, actualOutput)
    }

    @Test
    fun testPhase3aCorpusCasesMatchExactly() {
        val corpus = readReferenceCorpus()
        val phase3aCases = listOf(
            "A-base-ja",
            "A-base-en",
            "B-context-differs",
            "B-context-none",
            "B-vary-seed-0",
            "B-vary-seed-12345",
            "B-vary-seed-9223372036854775809",
        )

        for (caseName in phase3aCases) {
            verifyCorpusCase(corpus, caseName)
        }
    }

    @Test
    fun testContextTextNoLongerMovesTheOutputButFocusDoes() {
        val corpus = readReferenceCorpus()
        val differsObj = getCase(corpus, "B-context-differs")
        val noneObj = getCase(corpus, "B-context-none")

        val differsInput = differsObj.getJSONObject("input")
        val outputDiffers = WebDdlExpander.expandIntermediateDdl(
            ddl = differsInput.getString("ddl"),
            contextText = differsInput.getString("context_text"),
        )
        val outputNone = WebDdlExpander.expandIntermediateDdl(
            ddl = noneObj.getJSONObject("input").getString("ddl"),
            contextText = null,
        )

        assertEquals(differsObj.getString("output"), outputDiffers)
        assertEquals(noneObj.getString("output"), outputNone)
        // TRUE after the fold, FALSE before it: the context text fed the candidate
        // filter, and that filter went away with the staffage level (v2.11.0).
        assertEquals(outputDiffers, outputNone)

        // The control: the same call still moves when the focus moves.
        assertNotEquals(
            outputNone,
            WebDdlExpander.expandIntermediateDdl(
                ddl = noneObj.getJSONObject("input").getString("ddl"),
                contextText = null,
                focus = "upper_left",
            ),
        )
    }

    @Test
    fun testVarySeedNoLongerModifiesTheOutputButFocusDoes() {
        val ddl = "中心に黒い四角を置く。白い横線を三本引く。"
        val base = WebDdlExpander.expandIntermediateDdl(ddl, varySeed = null)
        val s0 = WebDdlExpander.expandIntermediateDdl(ddl, varySeed = 0L)
        val s12345 = WebDdlExpander.expandIntermediateDdl(ddl, varySeed = 12345L)

        // TRUE after the fold, FALSE before it: varySeed only salted the candidate
        // filter's seed context, and that filter is gone.
        assertEquals(base, s0)
        assertEquals(s0, s12345)

        // The control: the focus still authors the output.
        assertNotEquals(base, WebDdlExpander.expandIntermediateDdl(ddl, focus = "upper_edge"))
    }

    @Test
    fun testPhase3bVariationParametersActiveInPhase3b() {
        val ddl = "中心に黒い四角を置く。白い横線を三本引く。"
        val baseOutput = WebDdlExpander.expandIntermediateDdl(ddl)

        val outputWithVariation = WebDdlExpander.expandIntermediateDdl(
            ddl = ddl,
            variationAmplitude = "small",
            variationSeed = 12345L,
            enablePlugins = true,
        )

        assertNotEquals(baseOutput, outputWithVariation)
    }
}
