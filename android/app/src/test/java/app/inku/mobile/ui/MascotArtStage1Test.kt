package app.inku.mobile.ui

import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.ui.mascot.MascotArt
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MascotArtStage1Test {

    @Test
    fun t1_incuGridStructureAndIncubatorCoordinates() {
        val grid = MascotArt.INCU_GRID
        assertEquals(25, grid.size)

        val topCells = grid.filter { it.face == MascotArt.IncuFace.TOP }
        val leftCells = grid.filter { it.face == MascotArt.IncuFace.LEFT }
        val rightCells = grid.filter { it.face == MascotArt.IncuFace.RIGHT }
        val emptyCells = grid.filter { it.face == MascotArt.IncuFace.NONE }
        val incubatorCells = grid.filter { it.isIncubator }

        assertEquals(5, topCells.size)
        assertEquals(5, leftCells.size)
        assertEquals(5, rightCells.size)
        assertEquals(10, emptyCells.size)
        assertEquals(3, incubatorCells.size)

        val topIncubator = incubatorCells.find { it.face == MascotArt.IncuFace.TOP }
        val leftIncubator = incubatorCells.find { it.face == MascotArt.IncuFace.LEFT }
        val rightIncubator = incubatorCells.find { it.face == MascotArt.IncuFace.RIGHT }

        assertEquals(0, topIncubator?.x)
        assertEquals(-1, topIncubator?.y)

        assertEquals(0, leftIncubator?.x)
        assertEquals(1, leftIncubator?.y)

        assertEquals(1, rightIncubator?.x)
        assertEquals(1, rightIncubator?.y)

        // Counts alone do not hold the picture: a face moved to another cell keeps
        // every count intact. Compare all 25 cells against the web source of truth
        // (IncuMascot.svelte), including the per-cell breathe delay -- the set of
        // delays is unchanged when two cells swap theirs.
        val byPos = grid.associateBy { it.x to it.y }
        assertEquals(25, byPos.size)
        val expected = listOf(
            Triple(-2 to -2, MascotArt.IncuFace.NONE, false) to 0.0,
            Triple(-1 to -2, MascotArt.IncuFace.NONE, false) to -0.2,
            Triple(0 to -2, MascotArt.IncuFace.TOP, false) to -0.4,
            Triple(1 to -2, MascotArt.IncuFace.NONE, false) to -0.2,
            Triple(2 to -2, MascotArt.IncuFace.NONE, false) to 0.0,
            Triple(-2 to -1, MascotArt.IncuFace.NONE, false) to -0.2,
            Triple(-1 to -1, MascotArt.IncuFace.TOP, false) to -0.4,
            Triple(0 to -1, MascotArt.IncuFace.TOP, true) to -0.6,
            Triple(1 to -1, MascotArt.IncuFace.TOP, false) to -0.4,
            Triple(2 to -1, MascotArt.IncuFace.NONE, false) to -0.2,
            Triple(-2 to 0, MascotArt.IncuFace.LEFT, false) to -0.4,
            Triple(-1 to 0, MascotArt.IncuFace.LEFT, false) to -0.6,
            Triple(0 to 0, MascotArt.IncuFace.TOP, false) to -0.8,
            Triple(1 to 0, MascotArt.IncuFace.RIGHT, false) to -0.6,
            Triple(2 to 0, MascotArt.IncuFace.RIGHT, false) to -0.4,
            Triple(-2 to 1, MascotArt.IncuFace.NONE, false) to -0.2,
            Triple(-1 to 1, MascotArt.IncuFace.LEFT, false) to -0.4,
            Triple(0 to 1, MascotArt.IncuFace.LEFT, true) to -0.6,
            Triple(1 to 1, MascotArt.IncuFace.RIGHT, true) to -0.4,
            Triple(2 to 1, MascotArt.IncuFace.RIGHT, false) to -0.2,
            Triple(-2 to 2, MascotArt.IncuFace.NONE, false) to 0.0,
            Triple(-1 to 2, MascotArt.IncuFace.NONE, false) to -0.2,
            Triple(0 to 2, MascotArt.IncuFace.LEFT, false) to -0.4,
            Triple(1 to 2, MascotArt.IncuFace.RIGHT, false) to -0.2,
            Triple(2 to 2, MascotArt.IncuFace.NONE, false) to 0.0,
        )
        for ((key, delay) in expected) {
            val (pos, face, incubator) = key
            val cell = byPos[pos]
            assertEquals("face at " + pos, face, cell?.face)
            assertEquals("incubator at " + pos, incubator, cell?.isIncubator)
            assertEquals("delay at " + pos, delay, cell?.delaySeconds ?: 99.0, 0.0001)
        }
    }

    @Test
    fun t2_incuColorConstantsMatchSpecAndDefaultColorMap() {
        assertEquals("#888888", MascotArt.COLOR_TOP)
        assertEquals("#111111", MascotArt.COLOR_LEFT)
        assertEquals("#2c3e91", MascotArt.COLOR_RIGHT)
        assertEquals("#a2342a", MascotArt.COLOR_INCUBATE_LEFT)
        assertEquals("#2f6b3a", MascotArt.COLOR_INCUBATE_RIGHT)
        assertEquals("#555555", MascotArt.COLOR_INCUBATE_TOP)

        val defaultColors = ColorCatalogs.get("default").renderMap
        assertEquals(defaultColors["gray"], MascotArt.COLOR_TOP)
        assertEquals(defaultColors["black"], MascotArt.COLOR_LEFT)
        assertEquals(defaultColors["blue"], MascotArt.COLOR_RIGHT)
        assertEquals(defaultColors["red"], MascotArt.COLOR_INCUBATE_LEFT)
        assertEquals(defaultColors["green"], MascotArt.COLOR_INCUBATE_RIGHT)
    }

    @Test
    fun t3_incuTimingAndDelayDistribution() {
        assertEquals(15.0, MascotArt.INCU_SPIN_PERIOD_SEC, 0.0001)
        assertEquals(4.0, MascotArt.INCU_BREATHE_PERIOD_SEC, 0.0001)
        assertEquals(5.0, MascotArt.INCU_INCUBATE_LEFT_PERIOD_SEC, 0.0001)
        assertEquals(7.0, MascotArt.INCU_INCUBATE_RIGHT_PERIOD_SEC, 0.0001)
        assertEquals(6.0, MascotArt.INCU_INCUBATE_TOP_PERIOD_SEC, 0.0001)

        val uniqueDelays = MascotArt.INCU_GRID.map { it.delaySeconds }.toSet()
        val expectedDelays = setOf(0.0, -0.2, -0.4, -0.6, -0.8)
        assertEquals(expectedDelays, uniqueDelays)
    }
}
