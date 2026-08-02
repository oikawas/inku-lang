package app.inku.mobile.ui.mascot

import app.inku.mobile.render.ServerRendererStyle

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

    // Palette colors referenced from ServerRendererStyle.DEFAULT_COLOR_MAP where available
    val COLOR_TOP: String = ServerRendererStyle.DEFAULT_COLOR_MAP["gray"]!!
    val COLOR_LEFT: String = ServerRendererStyle.DEFAULT_COLOR_MAP["black"]!!
    val COLOR_RIGHT: String = ServerRendererStyle.DEFAULT_COLOR_MAP["blue"]!!
    val COLOR_INCUBATE_LEFT: String = ServerRendererStyle.DEFAULT_COLOR_MAP["red"]!!
    val COLOR_INCUBATE_RIGHT: String = ServerRendererStyle.DEFAULT_COLOR_MAP["green"]!!
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
}
