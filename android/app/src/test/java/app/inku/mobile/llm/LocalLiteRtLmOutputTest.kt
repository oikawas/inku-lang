package app.inku.mobile.llm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class LocalLiteRtLmOutputTest {

    @Test
    fun deltaChunksKeepTheirSpacesAndNewlinesUntilFinalNormalization() {
        val output = StringBuilder()

        LocalLiteRtLmOutput.appendStreamChunk(output, "A")
        LocalLiteRtLmOutput.appendStreamChunk(output, " B")
        LocalLiteRtLmOutput.appendStreamChunk(output, "\nC")

        assertEquals("A B\nC", output.toString())
    }

    @Test
    fun cumulativeChunksAppendOnlyTheirNewSuffix() {
        val output = StringBuilder()

        LocalLiteRtLmOutput.appendStreamChunk(output, "A")
        LocalLiteRtLmOutput.appendStreamChunk(output, "AB")
        LocalLiteRtLmOutput.appendStreamChunk(output, "AB")
        LocalLiteRtLmOutput.appendStreamChunk(output, "ABC")

        assertEquals("ABC", output.toString())
    }

    @Test
    fun japaneseVisionDescriptionRemovesTemplateMarkersAndClauseBreaks() {
        val raw = """
            <jturn>model赤い円がある。
            <jturn>modelその右に青い線がある。<end_of_turn>
        """.trimIndent()

        val description = LocalLiteRtLmOutput.visionDescription(raw, "ja")

        assertEquals("赤い円がある。その右に青い線がある。", description)
        assertFalse(description.contains("jturn"))
        assertFalse(description.contains('\n'))
    }

    @Test
    fun englishVisionDescriptionJoinsLinesWithOneSpace() {
        val raw = """
            <start_of_turn>modelA red circle overlaps
            a blue line.<end_of_turn>
        """.trimIndent()

        assertEquals(
            "A red circle overlaps a blue line.",
            LocalLiteRtLmOutput.visionDescription(raw, "en"),
        )
    }

    @Test
    fun ordinaryModelWordIsNotRemoved() {
        assertEquals(
            "A model stands beside a square.",
            LocalLiteRtLmOutput.visionDescription("A model stands beside a square.", "en"),
        )
    }
}
