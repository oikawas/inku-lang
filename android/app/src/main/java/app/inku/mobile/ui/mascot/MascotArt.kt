package app.inku.mobile.ui.mascot

import app.inku.mobile.data.model.ColorCatalogs

/**
 * Pure Kotlin data structures and constants for Incu and Yuragi mascots.
 * Free of Compose UI dependencies to allow JVM unit testing.
 */
object MascotArt {

    enum class IncuFace {
        TOP,
        LEFT,
        RIGHT,
        NONE
    }

    data class IncuCell(
        val x: Int,
        val y: Int,
        val face: IncuFace,
        val isIncubator: Boolean,
        val delaySeconds: Double
    )

    private val defaultColors = ColorCatalogs.get("default").renderMap

    val COLOR_TOP: String = defaultColors.getValue("gray")
    val COLOR_LEFT: String = defaultColors.getValue("black")
    val COLOR_RIGHT: String = defaultColors.getValue("blue")
    val COLOR_INCUBATE_LEFT: String = defaultColors.getValue("red")
    val COLOR_INCUBATE_RIGHT: String = defaultColors.getValue("green")
    val COLOR_INCUBATE_TOP: String = "#555555" // Custom mascot-specific shade

    // Timing constants for Incu
    const val INCU_SPIN_PERIOD_SEC = 15.0
    const val INCU_BREATHE_PERIOD_SEC = 4.0
    const val INCU_INCUBATE_LEFT_PERIOD_SEC = 5.0
    const val INCU_INCUBATE_RIGHT_PERIOD_SEC = 7.0
    const val INCU_INCUBATE_TOP_PERIOD_SEC = 6.0

    /**
     * The 5x5 (25 cells) grid representation of Incu mascot.
     */
    val INCU_GRID: List<IncuCell> = listOf(
        // Row 1 (y = -2)
        IncuCell(-2, -2, IncuFace.NONE, false, 0.0),
        IncuCell(-1, -2, IncuFace.NONE, false, -0.2),
        IncuCell( 0, -2, IncuFace.TOP,  false, -0.4),
        IncuCell( 1, -2, IncuFace.NONE, false, -0.2),
        IncuCell( 2, -2, IncuFace.NONE, false, 0.0),

        // Row 2 (y = -1)
        IncuCell(-2, -1, IncuFace.NONE, false, -0.2),
        IncuCell(-1, -1, IncuFace.TOP,  false, -0.4),
        IncuCell( 0, -1, IncuFace.TOP,  true,  -0.6),
        IncuCell( 1, -1, IncuFace.TOP,  false, -0.4),
        IncuCell( 2, -1, IncuFace.NONE, false, -0.2),

        // Row 3 (y = 0)
        IncuCell(-2,  0, IncuFace.LEFT,  false, -0.4),
        IncuCell(-1,  0, IncuFace.LEFT,  false, -0.6),
        IncuCell( 0,  0, IncuFace.TOP,   false, -0.8),
        IncuCell( 1,  0, IncuFace.RIGHT, false, -0.6),
        IncuCell( 2,  0, IncuFace.RIGHT, false, -0.4),

        // Row 4 (y = 1)
        IncuCell(-2,  1, IncuFace.NONE,  false, -0.2),
        IncuCell(-1,  1, IncuFace.LEFT,  false, -0.4),
        IncuCell( 0,  1, IncuFace.LEFT,  true,  -0.6),
        IncuCell( 1,  1, IncuFace.RIGHT, true,  -0.4),
        IncuCell( 2,  1, IncuFace.RIGHT, false, -0.2),

        // Row 5 (y = 2)
        IncuCell(-2,  2, IncuFace.NONE,  false, 0.0),
        IncuCell(-1,  2, IncuFace.NONE,  false, -0.2),
        IncuCell( 0,  2, IncuFace.LEFT,  false, -0.4),
        IncuCell( 1,  2, IncuFace.RIGHT, false, -0.2),
        IncuCell( 2,  2, IncuFace.NONE,  false, 0.0),
    )

    // --- Yuragi Mascot Definitions ---

    enum class YuragiCellType {
        RED,
        EYE,
        NONE
    }

    data class YuragiCell(
        val x: Int,
        val y: Int,
        val type: YuragiCellType,
        val isClawLeft: Boolean = false,
        val isClawRight: Boolean = false,
        val isLeg: Boolean = false,
        val legDelaySeconds: Double = 0.0,
        val isIncubator: Boolean = false,
        val isEyeLeft: Boolean = false,
        val isEyeRight: Boolean = false
    )

    data class YuragiBubble(
        val txPx: Float,
        val scale: Float,
        val delaySeconds: Double
    )

    val COLOR_RED: String = defaultColors.getValue("red")
    val COLOR_EYE_WHITE: String = defaultColors.getValue("white")
    val COLOR_EYE_BLACK: String = defaultColors.getValue("black")
    val COLOR_INCUBATE_INK: String = "#555555"
    val COLOR_BUBBLE: String = defaultColors.getValue("gray")

    const val YURAGI_CRAB_STEP_PERIOD_SEC = 1.5
    const val YURAGI_CLAW_LEFT_PERIOD_SEC = 11.0
    const val YURAGI_CLAW_RIGHT_PERIOD_SEC = 8.0
    const val YURAGI_LEG_TREMBLE_PERIOD_SEC = 0.6
    const val YURAGI_INCUBATE_PERIOD_SEC = 4.0
    const val YURAGI_EYE_BLINK_PERIOD_SEC = 7.0
    const val YURAGI_BUBBLE_PERIOD_SEC = 12.0

    val YURAGI_GRID: List<YuragiCell> = listOf(
        // Row 1 (y = -2): claws
        YuragiCell(-2, -2, YuragiCellType.RED, isClawLeft = true),
        YuragiCell(-1, -2, YuragiCellType.NONE),
        YuragiCell( 0, -2, YuragiCellType.NONE),
        YuragiCell( 1, -2, YuragiCellType.NONE),
        YuragiCell( 2, -2, YuragiCellType.RED, isClawRight = true),

        // Row 2 (y = -1): arms and eyes
        YuragiCell(-2, -1, YuragiCellType.RED),
        YuragiCell(-1, -1, YuragiCellType.EYE, isEyeLeft = true),
        YuragiCell( 0, -1, YuragiCellType.RED),
        YuragiCell( 1, -1, YuragiCellType.EYE, isEyeRight = true),
        YuragiCell( 2, -1, YuragiCellType.RED),

        // Row 3 (y = 0): body and incubator
        YuragiCell(-2,  0, YuragiCellType.RED, isLeg = true, legDelaySeconds = 0.0),
        YuragiCell(-1,  0, YuragiCellType.RED),
        YuragiCell( 0,  0, YuragiCellType.RED, isIncubator = true),
        YuragiCell( 1,  0, YuragiCellType.RED),
        YuragiCell( 2,  0, YuragiCellType.RED, isLeg = true, legDelaySeconds = 0.3),

        // Row 4 (y = 1): lower legs
        YuragiCell(-2,  1, YuragiCellType.RED, isLeg = true, legDelaySeconds = 0.1),
        YuragiCell(-1,  1, YuragiCellType.NONE),
        YuragiCell( 0,  1, YuragiCellType.RED, isLeg = true, legDelaySeconds = 0.2),
        YuragiCell( 1,  1, YuragiCellType.NONE),
        YuragiCell( 2,  1, YuragiCellType.RED, isLeg = true, legDelaySeconds = 0.4),

        // Row 5 (y = 2): empty
        YuragiCell(-2,  2, YuragiCellType.NONE),
        YuragiCell(-1,  2, YuragiCellType.NONE),
        YuragiCell( 0,  2, YuragiCellType.NONE),
        YuragiCell( 1,  2, YuragiCellType.NONE),
        YuragiCell( 2,  2, YuragiCellType.NONE)
    )

    val YURAGI_BUBBLES: List<YuragiBubble> = listOf(
        YuragiBubble(-25.0f, 1.2f, 0.0),
        YuragiBubble( 15.0f, 0.8f, 0.2),
        YuragiBubble(-10.0f, 1.5f, 0.4),
        YuragiBubble( 30.0f, 1.0f, 0.6),
        YuragiBubble( -5.0f, 1.8f, 0.8),
        YuragiBubble( 20.0f, 0.7f, 1.0),
        YuragiBubble(-35.0f, 1.1f, 1.2),
        YuragiBubble( 10.0f, 1.4f, 1.4)
    )

    fun isLeftEyeBlinking(timeSec: Double): Boolean {
        val phase = (timeSec % YURAGI_EYE_BLINK_PERIOD_SEC) / YURAGI_EYE_BLINK_PERIOD_SEC
        return phase in 0.96..0.98
    }

    fun isRightEyeBlinking(timeSec: Double): Boolean {
        val phase = (timeSec % YURAGI_EYE_BLINK_PERIOD_SEC) / YURAGI_EYE_BLINK_PERIOD_SEC
        return (phase in 0.66..0.68) || (phase in 0.96..0.98) // Wink at 0.66..0.68 + blink at 0.96..0.98
    }
}
