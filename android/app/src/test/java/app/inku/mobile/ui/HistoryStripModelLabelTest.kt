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

    @Test
    fun tooltipAddsTheSavedTimestampAndCatalogId() {
        assertEquals(
            "Stage 1: openai:gpt-image-1\n" +
                "Stage 2: gemini:imagen-3\n" +
                "Created: 2024-08-01T00:00:00Z\n" +
                "Color catalog: ink_season",
            historyStripModelTooltipText(
                stage1Model = "openai:gpt-image-1",
                stage2Model = "gemini:imagen-3",
                createdAt = 1_722_470_400_000L,
                colorCatalogId = " ink_season ",
                createdLabel = "Created",
                colorCatalogLabel = "Color catalog",
            ),
        )
    }

    @Test
    fun missingTimestampAndCatalogUseTheExistingAbsentMarker() {
        assertEquals(
            "Stage 1: openai:gpt-image-1\n" +
                "Stage 2: —\n" +
                "作成日: —\n" +
                "色カタログ: —",
            historyStripModelTooltipText(
                stage1Model = "openai:gpt-image-1",
                stage2Model = null,
                createdAt = 0L,
                colorCatalogId = "   ",
                createdLabel = "作成日",
                colorCatalogLabel = "色カタログ",
            ),
        )
    }

    @Test
    fun missingStage1StillOmitsTheTooltipWhenDetailsExist() {
        assertNull(
            historyStripModelTooltipText(
                stage1Model = null,
                stage2Model = "gemini:imagen-3",
                createdAt = 1_722_470_400_000L,
                colorCatalogId = "ink_season",
                createdLabel = "Created",
                colorCatalogLabel = "Color catalog",
            ),
        )
    }
}
