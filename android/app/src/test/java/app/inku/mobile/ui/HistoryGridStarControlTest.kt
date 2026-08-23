package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class HistoryGridStarControlTest {
    @Test
    fun starredWorkShowsFilledStar() {
        assertEquals("★", historyGridStarSymbol(starred = true))
    }

    @Test
    fun unstarredWorkShowsEmptyStar() {
        assertEquals("☆", historyGridStarSymbol(starred = false))
    }
}
