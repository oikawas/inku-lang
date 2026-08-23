package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class HistoryStripModelLabelTest {

    @Test
    fun missingModelOmitsTheMetadataLine() {
        assertNull(historyStripModelLabel(null))
        assertNull(historyStripModelLabel("   "))
    }

    @Test
    fun providerPrefixIsRemovedFromTheDisplayName() {
        assertEquals("gpt-image-1", historyStripModelLabel("openai:gpt-image-1"))
    }

    @Test
    fun longDisplayNameUsesTheExistingFourteenCharacterRule() {
        assertEquals("abcdefghijklm…", historyStripModelLabel("provider:abcdefghijklmnop"))
    }

    @Test
    fun tooltipPreservesBothCompleteSavedModelIds() {
        assertEquals(
            "Stage 1: openai:gpt-image-1\nStage 2: gemini:imagen-3",
            historyStripModelTooltipText(" openai:gpt-image-1 ", " gemini:imagen-3 "),
        )
    }

    @Test
    fun tooltipMarksAMissingStage2ModelWithoutInventingOne() {
        assertEquals(
            "Stage 1: openai:gpt-image-1\nStage 2: —",
            historyStripModelTooltipText("openai:gpt-image-1", "   "),
        )
    }

    @Test
    fun missingStage1ModelKeepsTheExistingAbsentMetadataLine() {
        assertNull(historyStripModelTooltipText(null, "gemini:imagen-3"))
        assertNull(historyStripModelTooltipText("   ", "gemini:imagen-3"))
    }
}
