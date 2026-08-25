package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class HistoryThumbnailStripTest {

    private fun appSource(): String {
        var file = File("src/main/java/app/inku/mobile/ui/InkuApp.kt")
        if (!file.exists()) {
            file = File("app/src/main/java/app/inku/mobile/ui/InkuApp.kt")
        }
        assertTrue("InkuApp.kt must exist (searched in ./src and ./app/src)", file.exists())
        return file.readText()
    }

    @Test
    fun descriptionPanelStripHasNoStarCallbackOrStarUi() {
        val source = appSource()
        val panelStart = source.indexOf("if (!presentation && showControls && historyItems.isNotEmpty())")
        val panelEnd = source.indexOf("// Under the canvas", panelStart)
        assertTrue("description panel history strip call must exist", panelStart >= 0 && panelEnd > panelStart)
        val panelCall = source.substring(panelStart, panelEnd)
        assertFalse("description panel must not pass a Star callback to its strip", panelCall.contains("onToggleStar"))

        val stripStart = source.indexOf("private fun HistoryThumbnailStrip(")
        val stripEnd = source.indexOf("private fun HistoryScreen(", stripStart)
        assertTrue("HistoryThumbnailStrip implementation must exist", stripStart >= 0 && stripEnd > stripStart)
        val strip = source.substring(stripStart, stripEnd)
        assertFalse("HistoryThumbnailStrip must not accept or call a Star callback", strip.contains("onToggleStar"))
        assertFalse("HistoryThumbnailStrip must not render the Star badge", strip.contains("HistoryBadge("))
        assertFalse("HistoryThumbnailStrip must not derive Star UI state", strip.contains("historyStripStarControl"))
        assertFalse("HistoryThumbnailStrip must not render a Star glyph", strip.contains("★") || strip.contains("☆"))
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
