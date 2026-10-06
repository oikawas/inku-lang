package app.inku.mobile.render

import org.junit.Assert.assertEquals
import org.junit.Test

class DisplayWindowGeometryTest {
    // A 4x zoom with pan and a 90-degree picture must select the original SVG's
    // axes, then place that region back at the same displayed fractions.
    @Test
    fun rotatedZoomUsesSourceAxesAndPlacesTheSameWindow() {
        val input = displayWindowInput(200.0, 100.0, 300.0, 200.0, 4.0, 50.0, -20.0, 90)!!
        assertEquals(DisplayRect(0.0, 0.0, 400.0, 800.0), input.zoomed)
        assertEquals(DisplayRect(120.0, 300.0, 200.0, 300.0), input.visible)
        val region = DisplayRegion(400, 800, 120, 300, 200, 300)
        val shown = displayedWindowFraction(region, 90)
        assertEquals(0.25, shown.x, 0.000001)
        assertEquals(0.3, shown.y, 0.000001)
        assertEquals(0.375, shown.width, 0.000001)
        assertEquals(0.5, shown.height, 0.000001)
    }
}
