package app.inku.mobile.data

import app.inku.mobile.data.db.CanvasSearchEntry
import app.inku.mobile.data.refinement.SharedJuxtaposition
import app.inku.mobile.pipeline.NativePipelineBridge
import org.junit.Assert.assertEquals
import org.junit.Test

/** Which works lend a sentence, and what the lineage tells the core (Server's `api_juxtaposition`). */
class JuxtapositionInputsTest {
    private fun entry(id: String, input: String, source: String? = null) =
        CanvasSearchEntry(id = id, originalInput = input, sourceText = source, renderHash = "sha256:$id", renderMetadataJson = "{}")

    @Test
    fun theWorkItselfDemoWorksEmptyDescriptionsAndLockedWorksLendNothing() {
        val entries = listOf(
            entry("self", "今の作品。"),
            entry("demo", "[demo] 港の朝。"),
            entry("ddl", ""),
            entry("blank-source", "入力の文。", source = "  "),
            entry("locked", "固定の作品。"),
            entry("kept", "入力の文。", source = "記述の文。"),
            entry("plain", "入力だけの作品。"),
        )
        val sources = juxtapositionSources(entries, workId = "self", locked = setOf("locked")) { "<$it>" }
        assertEquals(
            listOf(SharedJuxtaposition.Source("kept", "<記述の文。>"), SharedJuxtaposition.Source("plain", "<入力だけの作品。>")),
            sources,
        )
    }

    @Test
    fun labelsAreRemovedByTheSharedRule() {
        // A leading number orders a batch and a bracketed comment names a source.
        val sources = juxtapositionSources(listOf(entry("a", "12. 雪原を渡る群れ。[出典]")), workId = "b", locked = emptySet(),
            describe = NativePipelineBridge::pipelineDescription)
        assertEquals("雪原を渡る群れ。", sources.single().text)
    }

    @Test
    fun theLineageKeepsOneOfARunAndReadsTheSentencesItAdded() {
        assertEquals(listOf("根の記述。", "次の記述。", "根の記述。"),
            juxtapositionLineage(listOf(" 根の記述。", "根の記述。", "", "次の記述。", "根の記述。")))
        assertEquals(listOf("足した一文。"), juxtapositionAdded(listOf(
            "{}",
            """{"edited_from_history_id":"w1","juxtaposition":{"sentence":" 足した一文。","rank":1}}""",
            """{"juxtaposition":{"sentence":""}}""",
            "",
            "not json",
        )))
    }
}
