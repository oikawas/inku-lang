package app.inku.mobile.ui.export

import app.inku.mobile.ui.i18n.InkuFailure
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

/**
 * The PNG export height is 64..2160 (the author, 2026-10-06), and a height out
 * of range is refused rather than quietly drawn at another size. The width is
 * the paper's, and it is checked against the raster crate's limits before
 * anything is drawn.
 */
class PngExportSizeTest {

    @Test
    fun aSquareIsDrawnAt2160AndRefusedAt2161() {
        assertEquals(PngExportSize(2160, 2160), PngExportSize.of(2160, 1.0))
        assertThrows(InkuFailure::class.java) { PngExportSize.of(2161, 1.0) }
        assertThrows(InkuFailure::class.java) { PngExportSize.of(63, 1.0) }
        assertEquals(PngExportSize(64, 64), PngExportSize.of(64, 1.0))
    }

    @Test
    fun theWidthIsThePapersAndARasterBeyondTheCrateIsRefused() {
        assertEquals("half to even, like the paper size", PngExportSize(3840, 2160), PngExportSize.of(2160, 16.0 / 9.0))
        // 8192 wide is the crate's limit; one more is refused before drawing.
        assertEquals(8192, PngExportSize.of(2048, 4.0).width)
        assertThrows(InkuFailure::class.java) { PngExportSize.of(2049, 4.0) }
        // Within both dimensions but over the pixel count.
        assertThrows(InkuFailure::class.java) { PngExportSize.of(2160, 3.6) }
    }
}
