package app.inku.mobile.ui.theme

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What the token layer still has to keep (T-3).
 *
 * T-1 and T-2 froze the colour values `InkuApp.kt` held before the tokens were
 * extracted (measured on `1b734abc`), to show the extraction repainted nothing.
 * The 2026-09-24 redesign repainted the theme on purpose, so asserting those
 * values now would assert against the design rather than for it -- the same
 * reason the frozen dp list gave way to the grid below. Both were retired on
 * 2026-09-26.
 *
 * The dimensions are read through Java reflection rather than named, on
 * purpose: a test that names every token would fail to *compile* when one is
 * deleted, which is a build error rather than a named red test. The type sizes
 * are named directly.
 */
class ThemeTokensPreserveTheDrawingTest {

    /**
     * The grid every dimension sits on, and the line widths allowed off it.
     *
     * This replaces the frozen list of 53 pre-extraction dp values that stood
     * here through stage A. That list said "naming a distance must not move it",
     * which was the whole of stage A's claim. Stage B rebuilt the screens and
     * pulled the 22 off-grid values on by ruling (2026-08-08), so asserting the
     * old values now would assert against the contract rather than for it.
     *
     * What survives is the property the old list was protecting -- that a
     * distance is a decision someone made, not whatever the screen was written
     * with -- expressed as the grid instead of as a census.
     */
    private val gridStepDp = 4f

    /**
     * A line's width is not a distance: the 1dp border, and the strokes the
     * navigation marks and the camera's drawing figures are drawn with.
     */
    private val offGridExemptions = setOf(
        "Hairline",
        "NavigationMarkStroke",
        "CameraSavingOutlineWidth",
        "CameraSignalLine",
        "CameraPlotterStroke",
    )

    // --- T-3 ---------------------------------------------------------------

    @Test
    fun t3_everyDimensionSitsOnTheGridAndNoTypeSizeIsBelowTwelve() {
        val dp = dimenTokens()
        assertTrue(
            "expected the dimension tokens to be readable; found ${dp.size}",
            dp.size >= 20,
        )
        val offGrid = dp
            .filterKeys { it !in offGridExemptions }
            .filterValues { it % gridStepDp != 0f }
        assertEquals(
            "dimensions off the ${gridStepDp}dp grid: $offGrid",
            emptyMap<String, Float>(),
            offGrid,
        )

        // Line heights are paired with a size and are free to sit between the
        // steps; the sizes themselves are what Material 3 floors at 12sp.
        listOf(TypeScale.labelTiny, TypeScale.editorBody).forEach {
            assertTrue("type size $it is below Material 3's 12sp floor", it.value >= 12f)
        }
    }

    // --- reading the tokens -------------------------------------------------

    /**
     * `Dimens` is an object; `Dp` is a value class over `Float`.
     *
     * A getter that returns a value class is name-mangled -- `getHairline`
     * arrives as `getHairline-D9Ej5fM` -- so the hash is cut off. Reading the
     * names mattered from stage B on, where the report is a list of the tokens
     * that are off the grid rather than a count.
     */
    private fun dimenTokens(): Map<String, Float> {
        return Dimens::class.java.declaredMethods
            .filter { it.name.startsWith("get") && it.parameterCount == 0 }
            .filter { it.returnType == java.lang.Float.TYPE }
            .associate { m ->
                m.isAccessible = true
                m.name.removePrefix("get").substringBefore('-') to (m.invoke(Dimens) as Float)
            }
    }
}
