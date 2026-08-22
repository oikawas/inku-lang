package app.inku.mobile.ui

import app.inku.mobile.data.db.HistoryItemEntity
import org.junit.Assert.assertEquals
import org.junit.Test

class HistorySourceTextTest {

    @Test
    fun sourceTextIsTheParentProseAndOriginalInputIsOnlyItsNullFallback() {
        assertEquals(
            "parent prose",
            sourceTextOf(historyItem(originalInput = "#7 stored prose", sourceText = " parent prose ")),
        )
        assertEquals(
            "#7 stored prose",
            sourceTextOf(historyItem(originalInput = " #7 stored prose ", sourceText = null)),
        )
    }

    private fun historyItem(originalInput: String, sourceText: String?): HistoryItemEntity = HistoryItemEntity(
        id = "history-id",
        createdAt = 0L,
        updatedAt = 0L,
        originalInput = originalInput,
        normalizedDdl = "",
        expandedDdl = null,
        scoreJson = "{}",
        displaySvg = "",
        stage1Model = null,
        stage2Model = null,
        renderMetadataJson = "{}",
        renderHash = "",
        renderHashShort = "",
        colorCatalogId = "",
        canvasAspect = "",
        starred = false,
        trashed = false,
        elapsedMs = null,
        tokenMetadataJson = null,
        sourceText = sourceText,
    )
}
