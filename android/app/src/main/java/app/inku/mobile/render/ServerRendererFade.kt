package app.inku.mobile.render

import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.hypot

/**
 * Render engine 24: the fade reaches every member of a group.
 *
 * Kotlin port of `_fade_levels` / `_apply_fade_levels` / `_fade_level_from_hint`
 * in server/src/inku_server/renderer.py. `Arrangement.fade` declares how a group
 * falls off, and the renderer used to answer it with one constant for the whole
 * group -- the same number on the nearest mark and the farthest. "It fades from
 * the centre to the edge" was drawn as "all of it is a bit pale".
 */
object ServerRendererFade {

    private val NEAR_FAR: Map<String, Pair<Double, Double>> = mapOf(
        "outward" to (0.62 to 0.18),
        "directional" to (0.70 to 0.26)
    )
    const val FILL_RATIO_OUTWARD = 0.55
    const val FILL_RATIO_DIRECTIONAL = 0.625
    // A group whose members are all the same distance from the centre is not an
    // "outward" fade at all: a ring is equidistant by construction, and so is a
    // pair. Ranking one by index would draw a gradient running once around the
    // ring, which is a pattern the description never states.
    private const val SPAN_EPS = 1e-9

    private val LEVEL_RE = Regex("""fade_level=(\d+(?:\.\d+)?)""")
    private val LEVEL_TAG_RE = Regex("""(?:;\s*)?fade_level=\d+(?:\.\d+)?""")

    /** Read a member's ceiling out of the raw hint. */
    fun levelFromHint(colorHint: String?): Double? {
        if (colorHint.isNullOrEmpty()) return null
        return LEVEL_RE.find(colorHint)?.groupValues?.get(1)?.toDoubleOrNull()
    }

    /**
     * Drop the engine-24 level tag, keeping `fade=<mode>` itself.
     *
     * The surface seed hashes the whole instruction dump, so a per-member tag
     * would move the texture of every mark in a fading group.
     */
    fun stripLevel(colorHint: String?): String? {
        if (colorHint == null || "fade_level=" !in colorHint) return colorHint
        val stripped = LEVEL_TAG_RE.replace(colorHint, "").trim().trim(';').trim()
        return stripped.ifEmpty { null }
    }

    fun round4(value: Double): Double = Math.round(value * 10000.0) / 10000.0

    /**
     * One opacity ceiling per member, or null when the group cannot fade.
     *
     * `outward` reads the distance from the group's centre: the stated
     * `arrangement.center` when there is one, the centre the layout laid the
     * group around when the layout has one of its own, and the centroid of the
     * expanded anchors otherwise. `directional` reads the expansion order,
     * which is the order the path lays the members down in.
     *
     * A ring passes its own centre because the centroid is not it: the rhythm
     * spans 0 to 1 inclusive, so the first mark is drawn twice and pulls the
     * mean off the axis by radius/count.
     */
    fun levels(
        anchors: List<Pair<Double, Double>>,
        arr: JSONObject,
        center: Pair<Double, Double>?
    ): List<Double>? {
        val mode = arr.optString("fade", "none")
        val nearFar = NEAR_FAR[mode] ?: return null
        if (anchors.size < 2) return null
        val (near, far) = nearFar
        val count = anchors.size
        val ratios: List<Double>
        if (mode == "directional") {
            ratios = (0 until count).map { it.toDouble() / (count - 1) }
        } else {
            val stated = arr.optJSONArray("center")
            val cx: Double
            val cy: Double
            if (stated != null && stated.length() >= 2) {
                cx = stated.getDouble(0)
                cy = stated.getDouble(1)
            } else if (center != null) {
                cx = center.first
                cy = center.second
            } else {
                cx = anchors.sumOf { it.first } / count
                cy = anchors.sumOf { it.second } / count
            }
            val distances = anchors.map { hypot(it.first - cx, it.second - cy) }
            val span = (distances.max()) - (distances.min())
            if (span < SPAN_EPS) return null
            val nearest = distances.min()
            ratios = distances.map { (it - nearest) / span }
        }
        return ratios.map { near + (far - near) * it }
    }

    /**
     * Write each member's ceiling onto its `color_hint`.
     *
     * `color_hint` is the carriage because an instruction has no opacity field
     * and `fade=<mode>` already travels there. It is outside the fields the
     * performance seed is drawn from, so the tag moves no seed and the hand
     * stays byte-identical.
     */
    fun apply(
        items: List<JSONObject>,
        arr: JSONObject,
        anchors: List<Pair<Double, Double>>,
        center: Pair<Double, Double>?
    ): List<JSONObject> {
        val levels = levels(anchors, arr, center) ?: return items
        return items.mapIndexed { index, item ->
            val hint = if (item.has("color_hint") && !item.isNull("color_hint")) {
                item.optString("color_hint")
            } else {
                null
            }
            val tag = "fade_level=" + String.format(java.util.Locale.US, "%.4f", levels[index])
            item.put("color_hint", if (!hint.isNullOrEmpty()) "$hint; $tag" else tag)
            item
        }
    }

    /** Whether two doubles are the same number, for the degenerate-span test. */
    internal fun near(a: Double, b: Double): Boolean = abs(a - b) < SPAN_EPS
}
