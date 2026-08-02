package app.inku.mobile.ui

import app.inku.mobile.render.ServerRendererStyle
import app.inku.mobile.ui.mascot.MascotArt
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MascotArtStage2Test {

    @Test
    fun t4_yuragiGridStructureAndCellBreakdown() {
        val grid = MascotArt.YURAGI_GRID
        assertEquals(25, grid.size)

        val redCells = grid.filter { it.type == MascotArt.YuragiCellType.RED }
        val eyeCells = grid.filter { it.type == MascotArt.YuragiCellType.EYE }
        val noneCells = grid.filter { it.type == MascotArt.YuragiCellType.NONE }

        assertEquals(13, redCells.size)
        assertEquals(2, eyeCells.size)
        assertEquals(10, noneCells.size)

        val claws = redCells.filter { it.isClawLeft || it.isClawRight }
        val legs = redCells.filter { it.isLeg }
        val incubators = redCells.filter { it.isIncubator }
        val baseRed = redCells.filter { !it.isClawLeft && !it.isClawRight && !it.isLeg && !it.isIncubator }

        assertEquals(2, claws.size)
        assertEquals(5, legs.size)
        assertEquals(1, incubators.size)
        assertEquals(5, baseRed.size)

        // Coordinates check against §2.2
        val leftClaw = claws.find { it.isClawLeft }
        val rightClaw = claws.find { it.isClawRight }
        assertEquals(-2, leftClaw?.x)
        assertEquals(-2, leftClaw?.y)
        assertEquals(2, rightClaw?.x)
        assertEquals(-2, rightClaw?.y)

        val incubatorCell = incubators.first()
        assertEquals(0, incubatorCell.x)
        assertEquals(0, incubatorCell.y)
    }

    @Test
    fun t5_yuragiBubblesParametersAndGrayColor() {
        val bubbles = MascotArt.YURAGI_BUBBLES
        assertEquals(8, bubbles.size)

        val expected = listOf(
            Triple(-25.0f, 1.2f, 0.0),
            Triple( 15.0f, 0.8f, 0.2),
            Triple(-10.0f, 1.5f, 0.4),
            Triple( 30.0f, 1.0f, 0.6),
            Triple( -5.0f, 1.8f, 0.8),
            Triple( 20.0f, 0.7f, 1.0),
            Triple(-35.0f, 1.1f, 1.2),
            Triple( 10.0f, 1.4f, 1.4)
        )

        for (i in 0 until 8) {
            val (expTx, expScale, expDelay) = expected[i]
            val actual = bubbles[i]
            assertEquals(expTx, actual.txPx, 0.001f)
            assertEquals(expScale, actual.scale, 0.001f)
            assertEquals(expDelay, actual.delaySeconds, 0.001)
        }

        assertEquals("#888888", MascotArt.COLOR_BUBBLE)
        assertEquals(ServerRendererStyle.DEFAULT_COLOR_MAP["gray"], MascotArt.COLOR_BUBBLE)
        assertNotEquals("#ffffff", MascotArt.COLOR_BUBBLE)
    }

    @Test
    fun t6_yuragiTimingAndRightEyeExtraWink() {
        assertEquals(1.5, MascotArt.YURAGI_CRAB_STEP_PERIOD_SEC, 0.0001)
        assertEquals(11.0, MascotArt.YURAGI_CLAW_LEFT_PERIOD_SEC, 0.0001)
        assertEquals(8.0, MascotArt.YURAGI_CLAW_RIGHT_PERIOD_SEC, 0.0001)
        assertEquals(0.6, MascotArt.YURAGI_LEG_TREMBLE_PERIOD_SEC, 0.0001)
        assertEquals(7.0, MascotArt.YURAGI_EYE_BLINK_PERIOD_SEC, 0.0001)
        assertEquals(4.0, MascotArt.YURAGI_INCUBATE_PERIOD_SEC, 0.0001)
        assertEquals(12.0, MascotArt.YURAGI_BUBBLE_PERIOD_SEC, 0.0001)

        // Wink test: right eye blinks at 67% (4.69s) while left eye does not
        val winkTimeSec = 4.69 // 4.69 / 7.0 = 0.67
        assertFalse(MascotArt.isLeftEyeBlinking(winkTimeSec))
        assertTrue(MascotArt.isRightEyeBlinking(winkTimeSec))

        // Both eyes blink at 97% (6.79s)
        val blinkTimeSec = 6.79 // 6.79 / 7.0 = 0.97
        assertTrue(MascotArt.isLeftEyeBlinking(blinkTimeSec))
        assertTrue(MascotArt.isRightEyeBlinking(blinkTimeSec))
    }
}
