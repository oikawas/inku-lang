package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class HistoryThumbnailStripTest {

    @Test
    fun selectedIdMapsToItsExistingHistoryIndex() {
        val historyIds = listOf("latest", "middle", "oldest")

        assertEquals(0, selectedHistoryStripIndex(historyIds, "latest"))
        assertEquals(1, selectedHistoryStripIndex(historyIds, "middle"))
    }

    @Test
    fun absentSelectionHasNoHistoryIndex() {
        val historyIds = listOf("latest", "middle", "oldest")

        assertEquals(-1, selectedHistoryStripIndex(historyIds, null))
        assertEquals(-1, selectedHistoryStripIndex(historyIds, "missing"))
    }
}
