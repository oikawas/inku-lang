package app.inku.mobile.ui

import app.inku.mobile.render.ServerRendererStyle
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
    }

    @Test
    fun t2_incuColorConstantsMatchSpecAndDefaultColorMap() {
        assertEquals("#888888", MascotArt.COLOR_TOP)
        assertEquals("#111111", MascotArt.COLOR_LEFT)
        assertEquals("#2c3e91", MascotArt.COLOR_RIGHT)
        assertEquals("#a2342a", MascotArt.COLOR_INCUBATE_LEFT)
        assertEquals("#2f6b3a", MascotArt.COLOR_INCUBATE_RIGHT)
        assertEquals("#555555", MascotArt.COLOR_INCUBATE_TOP)

        assertEquals(ServerRendererStyle.DEFAULT_COLOR_MAP["gray"], MascotArt.COLOR_TOP)
        assertEquals(ServerRendererStyle.DEFAULT_COLOR_MAP["black"], MascotArt.COLOR_LEFT)
        assertEquals(ServerRendererStyle.DEFAULT_COLOR_MAP["blue"], MascotArt.COLOR_RIGHT)
        assertEquals(ServerRendererStyle.DEFAULT_COLOR_MAP["red"], MascotArt.COLOR_INCUBATE_LEFT)
        assertEquals(ServerRendererStyle.DEFAULT_COLOR_MAP["green"], MascotArt.COLOR_INCUBATE_RIGHT)
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
