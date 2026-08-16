package app.inku.mobile.data.model

data class CanvasAspect(
    val id: String,
    val category: String,
    val label: String,
    val ratioW: Double,
    val ratioH: Double,
    val intent: String,
)

data class CanvasSize(
    val width: Int,
    val height: Int,
) {
    val unit: Int get() = minOf(width, height)
}

object CanvasAspects {
    const val basePx = 1000

    val all = listOf(
        CanvasAspect("square", "Basic", "Square", 1.0, 1.0, "Standard square canvas"),
        CanvasAspect("golden", "Standard", "Golden Ratio", 1.618, 1.0, "Classical Western proportion"),
        CanvasAspect("a4", "Modern", "A4 Root Rectangle", 1.0, 1.414, "Modern print-oriented root rectangle"),
        CanvasAspect("b4", "Modern", "B4 Root Rectangle", 1.0, 1.414, "Modern print-oriented root rectangle"),
        CanvasAspect("pillar", "Classic JP", "Pillar", 1.0, 5.0, "Tall Japanese pillar-picture format"),
        CanvasAspect("oban", "Ukiyoe", "Oban", 2.0, 3.0, "Ukiyo-e oban woodblock proportion"),
        CanvasAspect("wide", "Cinema", "CinemaScope", 2.35, 1.0, "Wide cinematic panorama"),
        CanvasAspect("byobu", "Classic JP", "Byobu", 2.2, 1.0, "Japanese folding screen panel based on one half of a six-panel pair"),
        CanvasAspect("vertical", "Mobile", "Mobile Vertical", 9.0, 16.0, "Contemporary phone-screen format"),
        CanvasAspect("pixel9_landscape_safe", "Mobile", "Pixel 9 Landscape Safe", 9.0, 5.0, "Pixel 9 landscape canvas with side margins for the camera cutout"),
    )

    private val byId = all.associateBy { it.id }

    fun normalize(id: String?): String = if (id != null && byId.containsKey(id)) id else "square"

    fun ratioFor(id: String?): Double {
        val aspect = byId.getValue(normalize(id))
        return aspect.ratioW / aspect.ratioH
    }

    /**
     * The paper's pixel width, rounded the way the server rounds it.
     *
     * `canvas_size_for_aspect` is `round(CANVAS_BASE_PX * ratio)` and Python's
     * `round` sends a half to the even neighbour. Truncating instead put `oban`
     * at 666 px where the server puts it at 667, and every coordinate on that
     * sheet followed the width. `Math.rint` is the half-to-even one;
     * `Math.round` and `kotlin.math.round` send a half upwards and would move
     * `vertical` from 562 to 563, trading one disagreement for another.
     *
     * The server states the same expression in both of its branches, so there
     * is one branch here.
     */
    fun sizeFor(id: String?): CanvasSize {
        val ratio = ratioFor(id)
        return CanvasSize(width = Math.rint(basePx * ratio).toInt(), height = basePx)
    }
}
