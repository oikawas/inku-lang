package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.SharedPipelineBinding
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class ToolChangeTest {
    @Test
    fun planAndRenderMapCoreAnswersAndPreserveUnsignedSeedAndRawScore() {
        val score = """{"large":18446744073709551615,"instructions":[]}"""
        val binding = RecordingVariantsBinding { request ->
            when {
                request.contains("\"action\":\"tool_plan\"") -> """{"schema":"inku.saved-variants.v1","outcome":"ok",
                    "mode":"uniform","tool_labels":[{"value":"pen","ja":"ペン","en":"pen"}],
                    "sentences":[{"index":0,"tool":"pen"}],
                    "entries":[{"tools":{"0":"chalk"},"changes":[{"index":0,"from":"pen","to":"chalk"}],"ddl":"chalk DDL"}]}"""
                else -> """{"schema":"inku.saved-variants.v1","outcome":"ok","score":$score,
                    "ddl":"chalk DDL","derivation_metadata":{"tool_mode":"uniform","tools":{"0":"chalk"},
                    "changes":[{"index":0,"from":"pen","to":"chalk"}]}}"""
            }
        }
        val source = ToolChangePlanner.source("source DDL", score, "{}", binding)
        val option = ToolChangePlanner.options(source, ToolChangeMode.Uniform, Long.MIN_VALUE).single()
        assertTrue(binding.requests.first().contains("\"seed\":9223372036854775808"))
        assertTrue(binding.requests.first().contains("\"score\":$score"))
        assertEquals(mapOf(0 to "pen"), option.source.drawn)
        assertEquals(listOf(TouchTool("pen", "ペン", "pen")), option.source.tools)
        assertEquals(mapOf(0 to "chalk"), option.tools)
        assertEquals(listOf(ToolChange(0, "pen", "chalk")), option.changes)
        assertEquals("chalk DDL", option.ddl)
        val rendered = ToolChangePlanner.render(option)
        assertEquals(score, rendered.scoreJson)
        assertEquals("chalk DDL", rendered.ddl)
        assertEquals("uniform", rendered.derivationMetadata["tool_mode"])
        assertEquals(rendered.derivationMetadata, option.metadata())
    }

    @Test
    fun refusalDetailComesFromCoreWithoutHostRewrite() {
        val binding = RecordingVariantsBinding {
            """{"schema":"inku.saved-variants.v1","outcome":"refused","reason":"no_change","detail":"core says: no change"}"""
        }
        val source = ToolChangePlanner.source("DDL", "{}", "{}", binding)
        val error = assertThrows(IllegalArgumentException::class.java) {
            ToolChangePlanner.render(source, ToolChangeMode.Uniform, mapOf(0 to "pen"))
        }
        assertEquals("core says: no change", error.message)
    }
}

internal class RecordingVariantsBinding(private val answer: (String) -> String) : SharedPipelineBinding {
    val requests = mutableListOf<String>()
    override fun savedVariants(inputBytes: ByteArray): ByteArray {
        val request = inputBytes.toString(Charsets.UTF_8)
        requests += request
        return answer(request).encodeToByteArray()
    }
    override fun versionReport(): String = error("unexpected")
    override fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray): ByteArray = error("unexpected")
    override fun canvasRegistry(): String = error("unexpected")
    override fun resolvePalette(inputBytes: ByteArray): ByteArray = error("unexpected")
    override fun resolveMacroCatalog(inputBytes: ByteArray): ByteArray = error("unexpected")
    override fun renderSaved(inputBytes: ByteArray): ByteArray = error("unexpected")
}
