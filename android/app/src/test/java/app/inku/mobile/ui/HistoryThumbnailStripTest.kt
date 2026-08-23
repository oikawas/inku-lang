package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class HistoryThumbnailStripTest {

    @Test
    fun starControlShowsFilledStarForStarredWork() {
        val control = historyStripStarControl(starred = true, stripEnabled = true)

        assertEquals("★", control.symbol)
        assertEquals(true, control.enabled)
    }

    @Test
    fun starControlShowsEmptyStarForUnstarredWork() {
        val control = historyStripStarControl(starred = false, stripEnabled = true)

        assertEquals("☆", control.symbol)
        assertEquals(true, control.enabled)
    }

    @Test
    fun starControlIsDisabledWhileStripIsLocked() {
        val control = historyStripStarControl(starred = true, stripEnabled = false)

        assertEquals("★", control.symbol)
        assertEquals(false, control.enabled)
    }

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
