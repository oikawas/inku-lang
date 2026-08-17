package app.inku.mobile.render

import app.inku.mobile.data.model.CanvasSize
import java.security.MessageDigest
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt
import org.json.JSONArray
import org.json.JSONObject

internal object ServerRendererGeometry {
    const val MASTER_GRID_DECIMALS: Int = 6

    /** Engine 21's pitch jitter, kept as the default `scanlineSegments` uses. */
    const val FILL_SPACING_JITTER: Double = 0.24

    /**
     * The shapes that have an interior, 1-to-1 with `CLOSED_SHAPES` in `schema.py`.
     *
     * `cloudform` belongs here: it is a closed contour like the other five, and the
     * five-element sets scattered through [DefaultSvgRenderer] are about which
     * primitives a particular branch draws, not about which ones have an inside.
     * Copying one of those here would freeze that branch's list on the day it was
     * copied -- the same reason the server keeps this set in one place.
     */
    val CLOSED_SHAPES: Set<String> = setOf("circle", "ellipse", "square", "triangle", "polygon", "cloudform")

    /**
     * `filled=true` and `surface.texture="solid"` are two ways of writing one request.
     *
     * Ported from `fill_is_asked_for` in `schema.py`, and kept in one place for the
     * reason that docstring gives: a reader that holds its own copy freezes the day's
     * judgement, and the same description written the other way then takes another
     * road. The readers here are the renderer's own fill and coerce's tempering of a
     * large filled shape.
     */
    fun fillIsAskedFor(ins: JSONObject): Boolean {
        if (ins.optBoolean("filled", false)) return true
        val surface = ins.optJSONObject("surface") ?: return false
        return surface.optString("texture", "none") == "solid"
    }

    /**
     * Whether `surface` carries the interior (closed shapes only; a line has none).
     *
     * `solid` does not count. It is the material's default fill rather than a
     * printmaker's mark, and the layer that draws a surface does not put down a single
     * stroke for it -- see [fillsInterior]. Ported from `_has_surface_texture`.
     */
    fun hasSurfaceTexture(ins: JSONObject): Boolean {
        val surface = ins.optJSONObject("surface") ?: return false
        val texture = surface.optString("texture", "none")
        return texture != "none" && texture != "solid" && ins.optString("primitive", "line") in CLOSED_SHAPES
    }

    /**
     * Whether the interior is filled. Ported from `_fills_interior`.
     *
     * A fill is the material's default way of covering an interior and a `surface`
     * texture is an explicit print-making mark; the drawing never shows both.
     */
    fun fillsInterior(ins: JSONObject): Boolean {
        if (hasSurfaceTexture(ins)) return false
        return fillIsAskedFor(ins)
    }

    fun px(value: Double, scale: Double): Double = min(max(value, 0.0), 1.0) * scale

    /**
     * A mark's extents in px. Both follow the short edge, so a mark keeps the proportion
     * the description gave it: a square stays square, and a 2:1 ellipse stays 2:1 on any
     * canvas. Before engine 30 the two extents were stretched separately, so `size
     * [0.4, 0.2]` -- a wide ellipse -- came out taller than it was wide on a pillar.
     *
     * The aspect decides where a mark SITS, not what shape it IS: placement still goes
     * through [px], which keeps using width and height. `width` and `height` are taken
     * here because the server's `_size_px` takes the whole canvas, and because a caller
     * should not have to know which of the three this reads.
     *
     * No clamp, unlike [px]: the server's `_size_px` has none, and a client that clamps
     * where the server does not sends `size` outside 0..1 down a different road.
     */
    fun sizePx(sizeW: Double, sizeH: Double, width: Double, height: Double, unit: Double): Pair<Double, Double> =
        Pair(sizeW * unit, sizeH * unit)

    fun fmt(value: Double): String {
        val text = "%.${MASTER_GRID_DECIMALS}f".format(java.util.Locale.US, value)
        return if (text.startsWith("-") && text.toDouble() == 0.0) text.substring(1) else text
    }

    fun seedToLong(seed: Any?): Long {
        return when (seed) {
            is Number -> seed.toLong()
            is String -> seed.toULongOrNull()?.toLong() ?: seed.toLongOrNull() ?: seed.hashCode().toLong()
            else -> seed?.hashCode()?.toLong() ?: 0L
        }
    }

    fun seedForInstruction(ins: JSONObject, renderSeed: Long? = null): Long {
        val localSeed = ins.optLong("render_seed", -1L)
        val effectiveSeed = if (localSeed != -1L) localSeed else renderSeed
        if (effectiveSeed != null) return effectiveSeed
        return seedToLong(ins.toString())
    }

    private fun formatSeed(seed: Any): String {
        return when (seed) {
            is Long -> seed.toULong().toString()
            is ULong -> seed.toString()
            is String -> seed.toULongOrNull()?.toString() ?: seed
            else -> seed.toString()
        }
    }

    fun signedHash(i: Int, seed: Any): Double {
        val seedStr = formatSeed(seed)
        val digest = MessageDigest.getInstance("SHA-256").digest("$seedStr:$i".toByteArray())
        var raw = 0L
        for (offset in 0 until 8) {
            raw = raw or ((digest[offset].toLong() and 0xffL) shl (8 * offset))
        }
        return raw.toDouble() / 9_223_372_036_854_775_808.0
    }

    fun hash01(i: Int, seed: Any, salt: String = ""): Double {
        val seedStr = formatSeed(seed)
        val rawStr = "$seedStr:$salt:$i"
        val digest = MessageDigest.getInstance("SHA-256").digest(rawStr.toByteArray(Charsets.UTF_8))
        val raw = (digest[0].toLong() and 0xffL) or
            ((digest[1].toLong() and 0xffL) shl 8) or
            ((digest[2].toLong() and 0xffL) shl 16) or
            ((digest[3].toLong() and 0xffL) shl 24)
        return (raw and 0xffffffffL).toDouble() / 0xffffffffL.toDouble()
    }

    fun hashToUnit(i: Int, seed: Any): Double {
        val seedStr = formatSeed(seed)
        val rawStr = "$seedStr:$i"
        val digest = MessageDigest.getInstance("SHA-256").digest(rawStr.toByteArray(Charsets.UTF_8))
        var raw = 0L
        for (offset in 0 until 8) {
            raw = raw or ((digest[offset].toLong() and 0xffL) shl (8 * offset))
        }
        return raw.toDouble() / 9223372036854775808.0
    }

    fun wavePhase(seed: Any): Double {
        return hash01(0, seed, "wave-phase") * 2.0 * Math.PI
    }

    fun valueNoise1D(x: Double, seed: Any): Double {
        val xi = floor(x).toInt()
        val xf = x - xi
        val v1 = hashToUnit(xi, seed)
        val v2 = hashToUnit(xi + 1, seed)
        val t = xf * xf * (3.0 - 2.0 * xf)
        return v1 * (1.0 - t) + v2 * t
    }

    fun periodicValueNoise1D(x: Double, seed: Any, period: Int): Double {
        val xi = floor(x).toInt()
        val xf = x - xi
        val p = max(1, period)
        val v1 = hashToUnit(Math.floorMod(xi, p), seed)
        val v2 = hashToUnit(Math.floorMod(xi + 1, p), seed)
        val t = xf * xf * (3.0 - 2.0 * xf)
        return v1 * (1.0 - t) + v2 * t
    }

    fun representativeSizePx(ins: JSONObject, width: Double, height: Double, unit: Double): Double {
        val p = ins.optString("primitive", "")
        if (p in listOf("circle", "polygon", "arc") && ins.has("radius")) {
            return ins.getDouble("radius") * unit
        }
        if (p == "ellipse" && ins.has("size")) {
            val size = ins.getJSONArray("size")
            val (w, h) = sizePx(size.getDouble(0), size.getDouble(1), width, height, unit)
            val rx = w / 2.0
            val ry = h / 2.0
            return kotlin.math.sqrt(kotlin.math.max(0.0, rx * ry))
        }
        if (p in listOf("square", "triangle", "cloudform") && ins.has("size")) {
            val size = ins.getJSONArray("size")
            val (w, h) = sizePx(size.getDouble(0), size.getDouble(1), width, height, unit)
            return kotlin.math.min(w, h) / 2.0
        }
        if (p == "line") {
            val fromArr = if (ins.has("from")) ins.getJSONArray("from") else null
            val toArr = if (ins.has("to")) ins.getJSONArray("to") else null
            val x1 = (fromArr?.getDouble(0) ?: 0.5) * width
            val y1 = (fromArr?.getDouble(1) ?: 0.0) * height
            val x2 = (toArr?.getDouble(0) ?: 0.5) * width
            val y2 = (toArr?.getDouble(1) ?: 1.0) * height
            return kotlin.math.hypot(x2 - x1, y2 - y1)
        }
        return unit * 0.02
    }

    fun clampedRepresentativePx(ins: JSONObject, width: Double, height: Double, unit: Double): Double {
        return kotlin.math.max(representativeSizePx(ins, width, height, unit), unit * 0.02)
    }

    // The wander, unlike the bleed, is measured in stroke widths (engine 28).
    // It is a property of the tool meeting the paper, not of how big the figure
    // is: scaling it by the figure made a large arc leave its own line by eleven
    // widths while a small one stayed on it, because the same 8% of a radius is
    // invisible under a brush and a different line under a pencil. The
    // vocabulary is unchanged (fine/medium/broad); only the ruler moved.
    // `PRIMITIVE_AMP_GAIN` is the server's per-primitive calibration hook and is
    // empty there, so every primitive multiplies by 1.0.
    internal val amplitudeWidths = mapOf("fine" to 0.35, "medium" to 0.6, "broad" to 2.0)

    fun amplitudePx(variation: JSONObject, ins: JSONObject, width: Double, height: Double, unit: Double): Double {
        val strokeWidthPx = ServerRendererStyle.strokeWidth(
            ins.optString("weight", "pen"),
            unit,
            ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale }
        )
        val rep = clampedRepresentativePx(ins, width, height, unit)
        val ampStr = variation.optString("amplitude", "medium")
        val amp = amplitudeWidths[ampStr] ?: amplitudeWidths.getValue("medium")
        // The representative-size clamp stays: it is the safety valve that keeps
        // a figure smaller than its own mark from wandering further than it is wide.
        return kotlin.math.min(amp * strokeWidthPx, 0.40 * rep)
    }

    fun blurStdPx(variation: JSONObject, ins: JSONObject, width: Double, height: Double, unit: Double): Double {
        val rep = clampedRepresentativePx(ins, width, height, unit)
        val ampStr = variation.optString("amplitude", "medium")
        val ratio = when (ampStr) {
            "fine" -> 0.009
            "broad" -> 0.07
            else -> 0.03
        }
        return kotlin.math.max(unit * 0.0005, ratio * rep)
    }

    fun segmentCount(pathLenPx: Double, unit: Double): Int {
        val target = unit * 0.01
        if (target <= 0) return 32
        val cnt = Math.rint(pathLenPx / target).toInt()
        return kotlin.math.max(32, kotlin.math.min(200, cnt))
    }

    fun strokeSampleCount(lengthPx: Double, unit: Double): Int {
        val target = unit * (1.0 / 49.0)
        if (target <= 0) return 17
        val cnt = Math.rint(lengthPx / target).toInt()
        return kotlin.math.max(17, kotlin.math.min(129, cnt))
    }

    fun getFrequencyCycles(variation: JSONObject): Double {
        return when (variation.optString("frequency", "medium")) {
            "slow" -> 2.0
            "high" -> 14.0
            else -> 6.0
        }
    }

    private fun xorSeed(seed: Any, mask: Long): Any {
        return when (seed) {
            is Long -> seed xor mask
            is Int -> (seed.toLong() xor mask).toInt()
            is ULong -> seed xor mask.toULong()
            is Number -> seed.toLong() xor mask
            is String -> {
                val ul = seed.toULongOrNull()
                if (ul != null) (ul xor mask.toULong()).toString()
                else ((seed.toLongOrNull() ?: seed.hashCode().toLong()) xor mask).toString()
            }
            else -> mask
        }
    }

    fun sampleOffset(t: Double, variation: JSONObject, seed: Any, segment: Int, amp: Double): Double {
        val freq = getFrequencyCycles(variation)
        return when (variation.optString("quality", "none")) {
            "wave" -> sin(t * 2.0 * Math.PI * freq + wavePhase(seed)) * amp
            "perlin" -> valueNoise1D(t * freq, seed) * amp
            "pink" -> (
                valueNoise1D(t * freq, seed) * amp +
                    valueNoise1D(t * freq * 2.0, xorSeed(seed, 0x9E37L)) * amp * 0.5
                ) / 1.5
            "white" -> hashToUnit(segment, seed) * amp
            else -> 0.0
        }
    }

    fun sampleOffsetPeriodic(t: Double, variation: JSONObject, seed: Any, segment: Int, amp: Double): Double {
        val freq = getFrequencyCycles(variation)
        return when (variation.optString("quality", "none")) {
            "wave" -> sin(t * 2.0 * Math.PI * freq + wavePhase(seed)) * amp
            "perlin" -> periodicValueNoise1D(t * freq, seed, max(1, kotlin.math.round(freq).toInt())) * amp
            "white" -> hashToUnit(segment, seed) * amp
            else -> 0.0
        }
    }

    fun offsetContourPoint(
        x: Double,
        y: Double,
        off: Double,
        center: Pair<Double, Double>,
        axisX: Boolean,
        axisY: Boolean,
    ): Pair<Double, Double> {
        if (axisX && !axisY) return (x + off) to y
        if (axisY && !axisX) return x to (y + off)
        val dx = x - center.first
        val dy = y - center.second
        val dist = hypot(dx, dy)
        if (dist < 1e-6) return (x + off) to y
        val nx = dx / dist
        val ny = dy / dist
        return (x + off * nx) to (y + off * ny)
    }

    fun pointsForRegular(ins: JSONObject, sides: Int, width: Double, height: Double): List<Pair<Double, Double>> {
        val center = ins.optJSONArray("center")
        val position = ins.optJSONArray("position")
        val size = ins.optJSONArray("size")
        val cxRatio = center?.optDouble(0) ?: ((position?.optDouble(0, 0.4) ?: 0.4) + (size?.optDouble(0, 0.2) ?: 0.2) / 2.0)
        val cyRatio = center?.optDouble(1) ?: ((position?.optDouble(1, 0.4) ?: 0.4) + (size?.optDouble(1, 0.2) ?: 0.2) / 2.0)
        val r = px(ins.optDouble("radius", (size?.optDouble(0, 0.22) ?: 0.22) / 2.0), min(width, height))
        val cx = px(cxRatio, width)
        val cy = px(cyRatio, height)
        return (0 until sides).map { i ->
            val a = -Math.PI / 2.0 + i * Math.PI * 2.0 / sides
            (cx + cos(a) * r) to (cy + sin(a) * r)
        }
    }

    fun trianglePoints(ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        val pos = ins.optJSONArray("position")
        val size = ins.optJSONArray("size")
        val x = px(pos?.optDouble(0, 0.35) ?: 0.35, width)
        val y = px(pos?.optDouble(1, 0.35) ?: 0.35, height)
        val (w, h) = sizePx(size?.optDouble(0, 0.30) ?: 0.30, size?.optDouble(1, 0.30) ?: 0.30, width, height, unit)
        return listOf((x + w / 2.0) to y, x to (y + h), (x + w) to (y + h))
    }

    fun arcPathD(cx: Double, cy: Double, r: Double, startDeg: Double, endDeg: Double): String {
        val sa = Math.toRadians(startDeg)
        val ea = Math.toRadians(endDeg)
        val x1 = cx + r * cos(sa)
        val y1 = cy - r * sin(sa)
        val x2 = cx + r * cos(ea)
        val y2 = cy - r * sin(ea)
        val delta = endDeg - startDeg
        val largeArc = if (kotlin.math.abs(delta) > 180.0) 1 else 0
        val sweep = if (delta > 0.0) 0 else 1
        return "M ${fmt(x1)} ${fmt(y1)} A ${fmt(r)} ${fmt(r)} 0 $largeArc $sweep ${fmt(x2)} ${fmt(y2)}"
    }

    fun circlePoints(cx: Double, cy: Double, rx: Double, ry: Double, count: Int): List<Pair<Double, Double>> {
        if (count <= 0) return emptyList()
        return (0 until count).map { i ->
            val a = i * 2.0 * Math.PI / count
            (cx + cos(a) * rx) to (cy + sin(a) * ry)
        }
    }

    fun rectPoints(x: Double, y: Double, w: Double, h: Double, count: Int): List<Pair<Double, Double>> {
        if (count <= 0) return emptyList()
        val perimeter = max(1.0, 2.0 * (w + h))
        return (0 until count).map { i ->
            val d = ((i + 0.5) / count) * perimeter
            when {
                d <= w -> (x + d) to y
                d <= w + h -> (x + w) to (y + d - w)
                d <= 2.0 * w + h -> (x + w - (d - w - h)) to (y + h)
                else -> x to (y + h - (d - 2.0 * w - h))
            }
        }
    }

    fun arcPoints(cx: Double, cy: Double, r: Double, startDeg: Double, endDeg: Double, count: Int): List<Pair<Double, Double>> {
        val n = if (count <= 1) 2 else count
        if (count <= 0) return emptyList()
        val start = Math.toRadians(startDeg)
        val end = Math.toRadians(endDeg)
        return (0 until n).map { i ->
            val a = start + (end - start) * i / (n - 1).toDouble()
            (cx + cos(a) * r) to (cy - sin(a) * r)
        }
    }

    fun linePerpOffset(x1: Double, y1: Double, x2: Double, y2: Double, amount: Double): Pair<Double, Double> {
        val dx = x2 - x1
        val dy = y2 - y1
        val length = sqrt(dx * dx + dy * dy)
        if (length < 1e-6) return 0.0 to 0.0
        return (-dy / length * amount) to (dx / length * amount)
    }

    fun lineDirection(x1: Double, y1: Double, x2: Double, y2: Double): Pair<Double, Double> {
        val dx = x2 - x1
        val dy = y2 - y1
        val length = sqrt(dx * dx + dy * dy)
        if (length < 1e-6) return 1.0 to 0.0
        return (dx / length) to (dy / length)
    }

    /**
     * The qualities that are not a wobble at all.
     *
     * Written as an exclusion, the way the server writes it (`v.quality in ("none",
     * "pink")`), rather than as the list of qualities that do wobble. The two spell
     * the same set today because `Quality` holds exactly five words, but they are not
     * the same condition: a sixth word added to the schema joins the wobble under the
     * exclusion and is silently dropped under the enumeration.
     *
     * `pink` is a bleed, not a wobble. The server draws it with `feGaussianBlur` and
     * lets no variation reach the point run -- see [ServerRendererStyle.blurFilterId].
     */
    private val NO_VARIATION_QUALITIES: Set<String> = setOf("none", "pink")

    /** The axes a line's wobble rides on. Ported from `_needs_path_variation`. */
    private val PATH_VARIATION_DIMS: Set<String> = setOf("position_x", "position_y")

    /**
     * The axes a contour's wobble rides on. Ported from `_CONTOUR_VARIATION_DIMS`.
     *
     * `radius` is the shape's own natural axis, so it belongs to the closed figures
     * and the arc and to nothing else: a line has no radius to vary along.
     */
    private val CONTOUR_VARIATION_DIMS: Set<String> = setOf("position_x", "position_y", "radius")

    /**
     * Whether a line's point run wobbles. Ported from `_needs_path_variation`.
     *
     * The server keeps two gates because the two roads do not read the same axes, and
     * the port held one that read all three from every call site. A line asked to vary
     * on `radius` alone therefore wobbled here and stayed straight on the server
     * (ledger I-278).
     */
    fun needsPathVariation(variation: JSONObject?): Boolean =
        needsVariation(variation, PATH_VARIATION_DIMS)

    /** Whether an arc's or a closed shape's contour wobbles. Ported from `_needs_contour_variation`. */
    fun needsContourVariation(variation: JSONObject?): Boolean =
        needsVariation(variation, CONTOUR_VARIATION_DIMS)

    private fun needsVariation(variation: JSONObject?, dims: Set<String>): Boolean {
        if (variation == null) return false
        if (variation.optString("quality", "none") in NO_VARIATION_QUALITIES) return false
        // A variation with no `dimensions` rides on nothing: the server's `any(...)`
        // over an empty list is false, and the absent array is read the same way here.
        val dimensions = variation.optJSONArray("dimensions") ?: return false
        for (i in 0 until dimensions.length()) {
            if (dimensions.optString(i) in dims) return true
        }
        return false
    }

    fun variedLinePoints(x1: Double, y1: Double, x2: Double, y2: Double, variation: JSONObject?, seed: String): List<Pair<Double, Double>> {
        return variedLinePoints(x1, y1, x2, y2, variation, seedToLong(seed), JSONObject(), 1000.0, 1000.0, 1000.0)
    }

    fun variedLinePoints(x1: Double, y1: Double, x2: Double, y2: Double, variation: JSONObject?, seed: Long): List<Pair<Double, Double>> {
        return variedLinePoints(x1, y1, x2, y2, variation, seed, JSONObject(), 1000.0, 1000.0, 1000.0)
    }

    fun variedLinePoints(x1: Double, y1: Double, x2: Double, y2: Double, variation: JSONObject?, seed: String, ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        return variedLinePoints(x1, y1, x2, y2, variation, seedToLong(seed), ins, width, height, unit)
    }

    fun variedLinePoints(x1: Double, y1: Double, x2: Double, y2: Double, variation: JSONObject?, seed: Long, ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        if (variation == null) return listOf(x1 to y1, x2 to y2)
        val dx = x2 - x1
        val dy = y2 - y1
        val length = sqrt(dx * dx + dy * dy)
        if (length < 1e-6) return listOf(x1 to y1, x2 to y2)
        val perpX = -dy / length
        val perpY = dx / length
        val dimensions = variation.optJSONArray("dimensions") ?: JSONArray()
        val axisX = (0 until dimensions.length()).any { dimensions.optString(it) == "position_x" }
        val axisY = (0 until dimensions.length()).any { dimensions.optString(it) == "position_y" }
        val amp = amplitudePx(variation, ins, width, height, unit)
        val result = mutableListOf(x1 to y1)
        val segments = segmentCount(length, unit)
        for (i in 1 until segments) {
            val t = i.toDouble() / segments.toDouble()
            val offset = sampleOffset(t, variation, seed, i, amp)
            var x = x1 + dx * t
            var y = y1 + dy * t
            if (axisX && !axisY) {
                x += offset
            } else if (axisY && !axisX) {
                y += offset
            } else {
                x += offset * perpX
                y += offset * perpY
            }
            result.add(x to y)
        }
        result.add(x2 to y2)
        return result
    }

    fun variedCirclePoints(cx: Double, cy: Double, rx: Double, ry: Double, variation: JSONObject?, seed: Any?, count: Int = 100): List<Pair<Double, Double>> {
        return variedCirclePoints(cx, cy, rx, ry, variation, seedToLong(seed), JSONObject(), 1000.0, 1000.0, 1000.0)
    }

    fun variedCirclePoints(cx: Double, cy: Double, rx: Double, ry: Double, variation: JSONObject?, seed: Any?, ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        return variedCirclePoints(cx, cy, rx, ry, variation, seedToLong(seed), ins, width, height, unit)
    }

    fun variedCirclePoints(cx: Double, cy: Double, rx: Double, ry: Double, variation: JSONObject?, seed: Long, ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        val approxPerimeter = Math.PI * (3.0 * (rx + ry) - sqrt((3.0 * rx + ry) * (rx + 3.0 * ry)))
        val count = segmentCount(approxPerimeter, unit)
        val basePoints = circlePoints(cx, cy, rx, ry, count)
        if (variation == null || !needsContourVariation(variation)) return basePoints
        val dimensions = variation.optJSONArray("dimensions") ?: JSONArray()
        val axisX = (0 until dimensions.length()).any { dimensions.optString(it) == "position_x" }
        val axisY = (0 until dimensions.length()).any { dimensions.optString(it) == "position_y" }
        val amp = amplitudePx(variation, ins, width, height, unit)
        val center = cx to cy
        return basePoints.mapIndexed { i, pt ->
            val t = i.toDouble() / count.toDouble()
            val off = sampleOffsetPeriodic(t, variation, seed, i, amp)
            offsetContourPoint(pt.first, pt.second, off, center, axisX, axisY)
        }
    }

    fun variedPolygonPoints(points: List<Pair<Double, Double>>, variation: JSONObject?, seed: Any?, cx: Double, cy: Double): List<Pair<Double, Double>> {
        return variedPolygonPoints(points, variation, seedToLong(seed), cx, cy, JSONObject(), 1000.0, 1000.0, 1000.0)
    }

    fun variedPolygonPoints(points: List<Pair<Double, Double>>, variation: JSONObject?, seed: Any?, cx: Double, cy: Double, ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        return variedPolygonPoints(points, variation, seedToLong(seed), cx, cy, ins, width, height, unit)
    }

    fun variedPolygonPoints(points: List<Pair<Double, Double>>, variation: JSONObject?, seed: Long, cx: Double, cy: Double, ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        if (variation == null || !needsContourVariation(variation) || points.isEmpty()) return points
        val dimensions = variation.optJSONArray("dimensions") ?: JSONArray()
        val axisX = (0 until dimensions.length()).any { dimensions.optString(it) == "position_x" }
        val axisY = (0 until dimensions.length()).any { dimensions.optString(it) == "position_y" }
        val amp = amplitudePx(variation, ins, width, height, unit)
        val center = cx to cy
        val count = points.size
        return points.mapIndexed { i, pt ->
            val t = i.toDouble() / count.toDouble()
            val off = sampleOffsetPeriodic(t, variation, seed, i, amp)
            offsetContourPoint(pt.first, pt.second, off, center, axisX, axisY)
        }
    }

    fun variedArcPoints(cx: Double, cy: Double, r: Double, startDeg: Double, endDeg: Double, variation: JSONObject, seed: Any?, count: Int = 60): List<Pair<Double, Double>> {
        return variedArcPoints(cx, cy, r, startDeg, endDeg, variation, seedToLong(seed), JSONObject(), 1000.0, 1000.0, 1000.0)
    }

    fun variedArcPoints(cx: Double, cy: Double, r: Double, startDeg: Double, endDeg: Double, variation: JSONObject, seed: Any?, ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        return variedArcPoints(cx, cy, r, startDeg, endDeg, variation, seedToLong(seed), ins, width, height, unit)
    }

    /**
     * The server's `_arc_points_with_variation`, for the arc that stays
     * geometric (`rotring`) and so never enters the stroke engine.
     *
     * The hand-stroke path has had its own copy of this all along
     * (`arcPointsWithVariation` below) and that one already agreed with the
     * server. This one did not, in four ways at once: it took
     * `segmentCount` points where the server takes one more, it sampled the
     * wobble at `i / count` where the server samples at `i / last`, and it let
     * the two end points wobble, which the server holds fixed so that a
     * `touching` contact stays a contact.
     *
     * The arc's length is the difference between its two ends -- not that
     * difference folded back into 0..360 -- and it is written the server's way,
     * `r * |radians(end) - radians(start)|`. The hand path writes the same
     * number as `2*pi*r*|end-start|/360` and is deliberately left spelled that
     * way: the two agree to the last digit on every arc either of them is given,
     * and rewriting one of them would be a change to a path the frozen corpus
     * walks for nothing gained.
     */
    fun variedArcPoints(cx: Double, cy: Double, r: Double, startDeg: Double, endDeg: Double, variation: JSONObject, seed: Long, ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        val arcLen = r * Math.abs(Math.toRadians(endDeg) - Math.toRadians(startDeg))
        val basePoints = arcPoints(cx, cy, r, startDeg, endDeg, segmentCount(arcLen, unit) + 1)
        val dimensions = variation.optJSONArray("dimensions") ?: JSONArray()
        val axisX = (0 until dimensions.length()).any { dimensions.optString(it) == "position_x" }
        val axisY = (0 until dimensions.length()).any { dimensions.optString(it) == "position_y" }
        val amp = amplitudePx(variation, ins, width, height, unit)
        val center = cx to cy
        val last = basePoints.size - 1
        if (last <= 0) return basePoints
        val result = mutableListOf(basePoints[0])
        for (i in 1 until last) {
            val (x, y) = basePoints[i]
            val off = sampleOffset(i.toDouble() / last.toDouble(), variation, seed, i, amp)
            result.add(offsetContourPoint(x, y, off, center, axisX, axisY))
        }
        result.add(basePoints[last])
        return result
    }

    /**
     * Per-axis factors that put a normalized extent on the short edge.
     *
     * Engine 30 did this for a mark's own size; engine 31 does it for what the
     * arrangement layer spreads -- the ring and the region -- and engine 32 for
     * the cluster's band and a path's cross-axis spread. A normalized extent
     * becomes pixels through the canvas width on x and the canvas height on y,
     * so on a non-square canvas the same number means a different number of
     * pixels per axis. Scaling each axis by `unit / that axis` makes both come
     * out `unit` pixels, which is what keeps a ring round and a square region
     * square.
     */
    fun shortSideScales(canvas: CanvasSize?): Pair<Double, Double> {
        if (canvas == null) return 1.0 to 1.0
        return shortSideScales(canvas.width.toDouble(), canvas.height.toDouble(), canvas.unit.toDouble())
    }

    fun shortSideScales(width: Double, height: Double, unit: Double): Pair<Double, Double> =
        (unit / width) to (unit / height)

    /**
     * R3: the region's centre stays put, its extent goes to short-side units.
     *
     * The centre is deliberately left proportional -- "upper right" is the upper
     * right of any canvas -- so only the half-extents are scaled.
     */
    fun regionInShortSideUnits(region: List<Double>, canvas: CanvasSize?): List<Double> {
        val (sx, sy) = shortSideScales(canvas)
        if (sx == 1.0 && sy == 1.0) {
            // A square canvas has to come out byte-identical, and centre +/-
            // half-extent does not round-trip in floating point: on the server
            // [0.6, 0.18, 0.82, 0.4] moved y0 by 2.78e-17, enough to cross a
            // rounding boundary downstream and change a frozen square case.
            return region
        }
        val x0 = region[0]
        val y0 = region[1]
        val x1 = region[2]
        val y1 = region[3]
        val cx = (x0 + x1) / 2.0
        val cy = (y0 + y1) / 2.0
        val hx = (x1 - x0) / 2.0
        val hy = (y1 - y0) / 2.0
        return listOf(cx - hx * sx, cy - hy * sy, cx + hx * sx, cy + hy * sy)
    }

    /** Ramanujan's second approximation, which is what the server measures with. */
    fun ellipsePerimeter(rx: Double, ry: Double): Double {
        val a = kotlin.math.abs(rx)
        val b = kotlin.math.abs(ry)
        if (a + b <= 0.0) return 0.0
        val d = (a - b) / (a + b)
        val h = d * d
        return Math.PI * (a + b) * (1.0 + 3.0 * h / (10.0 + sqrt(4.0 - 3.0 * h)))
    }

    /** 1:1 with renderer.py `_polygon_points`: sides clamped to 5..8, first vertex at -90 degrees. */
    fun polygonPoints(cx: Double, cy: Double, r: Double, sides: Int, rotationDeg: Double): List<Pair<Double, Double>> {
        val count = min(max(sides, 5), 8)
        val start = Math.toRadians(rotationDeg - 90.0)
        return (0 until count).map { i ->
            val a = start + Math.PI * 2.0 * i / count
            (cx + cos(a) * r) to (cy + sin(a) * r)
        }
    }

    fun fillScanAngle(seed: Any): Double {
        return hash01(0, seed, "fill-angle") * Math.PI
    }

    fun fillScanSpacing(ins: JSONObject, unit: Double): Double {
        val weight = ins.optString("weight", "pen")
        val thinness = ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale }
        val baseWidth = ServerRendererStyle.strokeWidth(weight, unit, thinness)
        return max(baseWidth * 1.5, unit * 0.012)
    }

    fun fillStrokeSeed(seed: Any, index: Int): Long {
        val seedStr = formatSeed(seed)
        val digest = MessageDigest.getInstance("SHA-256").digest("$seedStr:fill-stroke:$index".toByteArray(Charsets.UTF_8))
        var raw = 0L
        for (offset in 0 until 8) {
            raw = raw or ((digest[offset].toLong() and 0xffL) shl (8 * offset))
        }
        return raw
    }

    /**
     * One surface stroke's seed, so the surface layer does not share a waveform
     * with the fill or the contour.
     *
     * The same shape as [fillStrokeSeed] with the label the server uses, which
     * is what keeps the two apart: the label is the only thing separating a
     * sweep's hand from a fill stroke's at the same index.
     */
    fun surfaceStrokeSeed(seed: Any, index: Int): Long {
        val seedStr = formatSeed(seed)
        val digest = MessageDigest.getInstance("SHA-256").digest("$seedStr:surface-stroke:$index".toByteArray(Charsets.UTF_8))
        var raw = 0L
        for (offset in 0 until 8) {
            raw = raw or ((digest[offset].toLong() and 0xffL) shl (8 * offset))
        }
        return raw
    }

    /**
     * `jitter` is the full width of the uniform pitch multiplier, so the
     * coefficient of variation of the gaps is `jitter / sqrt(12)`. The default
     * is the engine-21 value; the fill branch passes its own, drawn from the
     * tool's hand.
     */
    fun scanlineSegments(
        contour: List<Pair<Double, Double>>,
        angle: Double,
        spacing: Double,
        seed: Any,
        jitterWidth: Double = FILL_SPACING_JITTER
    ): List<Triple<Int, Pair<Double, Double>, Pair<Double, Double>>> {
        if (contour.isEmpty()) return emptyList()
        val ux = cos(angle)
        val uy = sin(angle)
        val nx = -uy
        val ny = ux
        val projections = contour.map { it.first * nx + it.second * ny }
        val lo = projections.minOrNull() ?: return emptyList()
        val hi = projections.maxOrNull() ?: return emptyList()
        val segments = mutableListOf<Triple<Int, Pair<Double, Double>, Pair<Double, Double>>>()
        var offset = lo + spacing * 0.5
        var index = 0
        val n = contour.size
        while (offset < hi && index < 4096) {
            val hits = mutableListOf<Double>()
            for (edge in 0 until n) {
                val ax = contour[edge].first
                val ay = contour[edge].second
                val bx = contour[(edge + 1) % n].first
                val by = contour[(edge + 1) % n].second
                val da = ax * nx + ay * ny - offset
                val db = bx * nx + by * ny - offset
                if ((da <= 0.0 && db > 0.0) || (db <= 0.0 && da > 0.0)) {
                    val t = da / (da - db)
                    val px = ax + (bx - ax) * t
                    val py = ay + (by - ay) * t
                    hits.add(px * ux + py * uy)
                }
            }
            hits.sort()
            for (pair in 0 until hits.size - 1 step 2) {
                val s0 = hits[pair]
                val s1 = hits[pair + 1]
                segments.add(
                    Triple(
                        index,
                        (nx * offset + ux * s0) to (ny * offset + uy * s0),
                        (nx * offset + ux * s1) to (ny * offset + uy * s1)
                    )
                )
            }
            val jitter = 1.0 + (hash01(index, seed, "fill-spacing") - 0.5) * jitterWidth
            offset += spacing * jitter
            index += 1
        }
        return segments
    }

    fun surfaceLineAngle(direction: String): Double {
        return when (direction) {
            "horizontal" -> 0.0
            "vertical" -> Math.PI / 2.0
            "diagonal_rising" -> -Math.PI / 4.0
            "diagonal_falling" -> Math.PI / 4.0
            else -> Math.PI / 4.0
        }
    }

    /**
     * The box a surface is laid inside, or null when the shape never said where
     * it is.
     *
     * Every branch of the server's `_shape_bbox` makes the same demand: both of
     * the fields that place the shape have to be stated, and when either is
     * missing the branch is declined and the walk falls through to `return
     * None`. The one reader of this answer is `renderSurfaceVectors`, whose
     * `?: return ""` turns a null into "no surface at all".
     *
     * Measured 2026-08-17: that reader asks `surfaceContour` first, and it makes
     * the same demand on the same fields, so while these branches filled a
     * missing field in with a default the surface was suppressed anyway and no
     * drawing moved. The two gates agree by hand, not by construction -- this
     * one is here so the answer matches the server's whoever reads it next.
     *
     * "Missing" means the key is absent or JSON null, never falsy: a `center`
     * of `[0, 0]` and a `radius` of `0` are both stated, and the server reads
     * them as stated (`is not None`).
     */
    fun shapeBbox(ins: JSONObject, width: Double, height: Double, unit: Double): DoubleArray? {
        val primitive = ins.optString("primitive", "")
        return when (primitive) {
            "circle" -> {
                val center = ins.optJSONArray("center")
                if (center == null || ins.isNull("radius")) return null
                val cx = center.optDouble(0, 0.5) * width
                val cy = center.optDouble(1, 0.5) * height
                val r = ins.optDouble("radius", 0.12) * unit
                doubleArrayOf(cx - r, cy - r, r * 2.0, r * 2.0)
            }
            "ellipse" -> {
                val center = ins.optJSONArray("center")
                val size = ins.optJSONArray("size")
                if (center == null || size == null) return null
                val cx = center.optDouble(0, 0.5) * width
                val cy = center.optDouble(1, 0.5) * height
                val (w, h) = sizePx(size.optDouble(0, 0.26), size.optDouble(1, 0.16), width, height, unit)
                doubleArrayOf(cx - w / 2.0, cy - h / 2.0, w, h)
            }
            "cloudform" -> {
                val center = ins.optJSONArray("center")
                val size = ins.optJSONArray("size")
                if (center == null || size == null) {
                    null
                } else {
                    val cx = center.optDouble(0, 0.5) * width
                    val cy = center.optDouble(1, 0.5) * height
                    // Through sizePx, so the extent lands on the short side the way
                    // engine 30 put it there; the ellipse and square branches ask
                    // the same way.
                    val (w, h) = sizePx(size.optDouble(0, 0.5), size.optDouble(1, 0.34), width, height, unit)
                    doubleArrayOf(cx - w * 0.56, cy - h * 0.56, w * 1.12, h * 1.12)
                }
            }
            "square", "triangle" -> {
                val pos = ins.optJSONArray("position")
                val size = ins.optJSONArray("size")
                if (pos == null || size == null) return null
                val x = pos.optDouble(0, 0.38) * width
                val y = pos.optDouble(1, 0.38) * height
                val (w, h) = sizePx(size.optDouble(0, 0.24), size.optDouble(1, 0.24), width, height, unit)
                doubleArrayOf(x, y, w, h)
            }
            // The server builds a polygon's box out of `center` and `radius`
            // and out of nothing else: it does not read `position` for the
            // centre, and it does not read `size` for the radius. A polygon
            // that states where its corners reach but never where it sits has
            // no box, the same as one that states neither.
            "polygon" -> {
                val center = ins.optJSONArray("center")
                val radius = if (ins.isNull("radius")) null else ins.optDouble("radius", 0.12)
                if (center == null || radius == null) return null
                val cx = center.optDouble(0, 0.5) * width
                val cy = center.optDouble(1, 0.5) * height
                val r = radius * unit
                doubleArrayOf(cx - r, cy - r, r * 2.0, r * 2.0)
            }
            else -> null
        }
    }

    fun arcPointsWithVariation(
        cx: Double,
        cy: Double,
        r: Double,
        startDeg: Double,
        endDeg: Double,
        variation: JSONObject,
        seed: Any,
        ins: JSONObject,
        width: Double,
        height: Double,
        unit: Double
    ): List<Pair<Double, Double>> {
        val arcLen = 2.0 * Math.PI * r * (Math.abs(endDeg - startDeg) / 360.0)
        val count = segmentCount(arcLen, unit) + 1
        val basePoints = arcPoints(cx, cy, r, startDeg, endDeg, count)
        if (!needsContourVariation(variation)) return basePoints
        val dimensions = variation.optJSONArray("dimensions") ?: JSONArray()
        val axisX = (0 until dimensions.length()).any { dimensions.optString(it) == "position_x" }
        val axisY = (0 until dimensions.length()).any { dimensions.optString(it) == "position_y" }
        val amp = amplitudePx(variation, ins, width, height, unit)
        val center = cx to cy
        val seedLong = seedToLong(seed)
        val last = basePoints.size - 1
        if (last <= 0) return basePoints
        val result = mutableListOf(basePoints[0])
        for (i in 1 until last) {
            val (x, y) = basePoints[i]
            val t = i.toDouble() / last.toDouble()
            val off = sampleOffset(t, variation, seedLong, i, amp)
            result.add(offsetContourPoint(x, y, off, center, axisX, axisY))
        }
        result.add(basePoints[last])
        return result
    }

    data class ArcGeometry(
        val center: Pair<Double, Double>,
        val radius: Double,
        val angleStart: Double,
        val angleEnd: Double
    )

    fun minorArcDelta(angleStart: Double, angleEnd: Double): Double {
        var diff = (angleEnd - angleStart + 180.0) % 360.0
        if (diff < 0) diff += 360.0
        return diff - 180.0
    }

    fun arcPoint(center: Pair<Double, Double>, radius: Double, angleDegrees: Double): Pair<Double, Double> {
        val rad = Math.toRadians(angleDegrees)
        return (center.first + radius * cos(rad)) to (center.second - radius * sin(rad))
    }

    fun arcFromEndpointsAndSagitta(
        start: Pair<Double, Double>,
        end: Pair<Double, Double>,
        sagitta: Double
    ): ArcGeometry {
        val dx = end.first - start.first
        val dy = end.second - start.second
        val chord = hypot(dx, dy)
        val height = kotlin.math.abs(sagitta)
        require(chord > 1e-12) { "arc chord must be non-zero" }
        require(height > 1e-12 && height < chord / 2.0) { "arc sagitta must be positive and smaller than half the chord" }

        val radius = chord * chord / (8.0 * height) + height / 2.0
        val midpoint = ((start.first + end.first) / 2.0) to ((start.second + end.second) / 2.0)
        val normal = (-dy / chord) to (dx / chord)
        val sign = if (sagitta > 0.0) 1.0 else -1.0
        val center = (midpoint.first - sign * (radius - height) * normal.first) to
            (midpoint.second - sign * (radius - height) * normal.second)

        fun angle(p: Pair<Double, Double>): Double {
            return Math.toDegrees(kotlin.math.atan2(-(p.second - center.second), p.first - center.first))
        }

        val angleStart = angle(start)
        val delta = minorArcDelta(angleStart, angle(end))
        require(kotlin.math.abs(delta) < 180.0 - 1e-9) { "arc must use a sweep smaller than 180 degrees" }
        return ArcGeometry(
            center = center,
            radius = radius,
            angleStart = angleStart,
            angleEnd = angleStart + delta
        )
    }

    data class CloudContour(
        val points: List<Pair<Double, Double>>,
        val pathD: String
    )

    private fun cloudformUnit(seed: Long, label: String, index: Int): Double {
        val seedStr = seed.toULong().toString()
        val rawStr = "$seedStr:$label:$index"
        val digest = MessageDigest.getInstance("SHA-256").digest(rawStr.toByteArray(Charsets.UTF_8))
        var raw = 0L
        for (offset in 0 until 8) {
            raw = raw or ((digest[offset].toLong() and 0xffL) shl (8 * offset))
        }
        val ulongVal = raw.toULong()
        return ulongVal.toDouble() / 18446744073709551615.0
    }

    fun cloudformSeed(performanceSeed: Any?, instructionIndex: Int, markIndex: Int): Long {
        val perfSeedStr = when (performanceSeed) {
            is Long -> performanceSeed.toULong().toString()
            is ULong -> performanceSeed.toString()
            is String -> performanceSeed.toULongOrNull()?.toString() ?: performanceSeed
            else -> performanceSeed?.toString() ?: "None"
        }
        val rawStr = "cloudform-v1:$perfSeedStr:$instructionIndex:$markIndex"
        val digest = MessageDigest.getInstance("SHA-256").digest(rawStr.toByteArray(Charsets.UTF_8))
        var raw = 0L
        for (offset in 0 until 8) {
            raw = raw or ((digest[offset].toLong() and 0xffL) shl (8 * offset))
        }
        return raw
    }

    private fun frequencyRange(variation: JSONObject?): IntRange {
        val frequency = variation?.optString("frequency", "medium") ?: "medium"
        return when (frequency) {
            "slow" -> 2..5
            "high" -> 5..10
            else -> 3..7
        }
    }

    private fun variationGain(variation: JSONObject?): Double {
        if (variation == null) return 0.16
        return when (variation.optString("amplitude", "medium")) {
            "fine" -> 0.10
            "medium" -> 0.17
            "broad" -> 0.25
            else -> 0.17
        }
    }

    private fun spectrumPower(variation: JSONObject?): Double {
        val quality = variation?.optString("quality", "pink") ?: "pink"
        return when (quality) {
            "wave" -> 1.15
            "pink" -> 0.50
            "perlin" -> 0.72
            "white" -> 0.0
            "none" -> 0.58
            else -> 0.50
        }
    }

    private fun normalizedHarmonicSignal(
        theta: Double,
        seed: Long,
        label: String,
        frequencies: IntRange,
        spectrumPower: Double
    ): Double {
        var total = 0.0
        var normalizer = 0.0
        for (harmonic in frequencies) {
            val amplitude = 1.0 / Math.pow(harmonic.toDouble(), spectrumPower)
            val phase = 2.0 * Math.PI * cloudformUnit(seed, "$label-phase", harmonic)
            val sign = if (cloudformUnit(seed, "$label-sign", harmonic) < 0.5) -1.0 else 1.0
            total += sign * amplitude * cos(harmonic * theta + phase)
            normalizer += amplitude
        }
        return total / max(normalizer, 1e-9)
    }

    private fun baseRadius(
        theta: Double,
        seed: Long,
        variation: JSONObject?,
        weight: String
    ): Double {
        val gain = variationGain(variation)
        val primary = normalizedHarmonicSignal(
            theta,
            seed,
            "contour",
            frequencyRange(variation),
            spectrumPower(variation)
        )
        val grammar = GRAMMARS[weight] ?: GRAMMARS["pen"]!!
        val touchGain = grammar.energyLateral * 0.018
        val touch = normalizedHarmonicSignal(
            theta,
            seed xor 0x7001L,
            "touch",
            9..14,
            0.65
        )
        return max(0.58, min(1.12, 0.88 + gain * primary + touchGain * touch))
    }

    private fun curvatureRadius(before: Pair<Double, Double>, point: Pair<Double, Double>, after: Pair<Double, Double>): Double {
        val a = hypot(point.first - before.first, point.second - before.second)
        val b = hypot(after.first - point.first, after.second - point.second)
        val c = hypot(before.first - after.first, before.second - after.second)
        val twiceArea = kotlin.math.abs(
            (point.first - before.first) * (after.second - before.second) -
            (point.second - before.second) * (after.first - before.first)
        )
        if (twiceArea < 1e-9) return Double.POSITIVE_INFINITY
        return a * b * c / (2.0 * twiceArea)
    }

    private fun closedCatmullRomPath(points: List<Pair<Double, Double>>): String {
        val count = points.size
        require(count >= 3) { "cloudform contour requires at least three points" }
        val fmt3 = { v: Double -> "%.3f".format(java.util.Locale.US, v) }
        val sb = StringBuilder()
        sb.append("M ").append(fmt3(points[0].first)).append(" ").append(fmt3(points[0].second))
        for (i in 0 until count) {
            val p0 = points[(i - 1 + count) % count]
            val p1 = points[i]
            val p2 = points[(i + 1) % count]
            val p3 = points[(i + 2) % count]
            val c1x = p1.first + (p2.first - p0.first) / 6.0
            val c1y = p1.second + (p2.second - p0.second) / 6.0
            val c2x = p2.first - (p3.first - p1.first) / 6.0
            val c2y = p2.second - (p3.second - p1.second) / 6.0
            sb.append(" C ").append(fmt3(c1x)).append(" ").append(fmt3(c1y))
                .append(" ").append(fmt3(c2x)).append(" ").append(fmt3(c2y))
                .append(" ").append(fmt3(p2.first)).append(" ").append(fmt3(p2.second))
        }
        sb.append(" Z")
        return sb.toString()
    }

    fun sampleClosedCatmullRom(
        points: List<Pair<Double, Double>>,
        samplesPerSegment: Int = 5
    ): List<Pair<Double, Double>> {
        val count = points.size
        val numSamples = max(2, samplesPerSegment)
        val sampled = mutableListOf<Pair<Double, Double>>()
        for (i in 0 until count) {
            val p0 = points[(i - 1 + count) % count]
            val p1 = points[i]
            val p2 = points[(i + 1) % count]
            val p3 = points[(i + 2) % count]
            val c1x = p1.first + (p2.first - p0.first) / 6.0
            val c1y = p1.second + (p2.second - p0.second) / 6.0
            val c2x = p2.first - (p3.first - p1.first) / 6.0
            val c2y = p2.second - (p3.second - p1.second) / 6.0
            for (step in 0 until numSamples) {
                val t = step.toDouble() / numSamples.toDouble()
                val inv = 1.0 - t
                val x = inv * inv * inv * p1.first + 3.0 * inv * inv * t * c1x + 3.0 * inv * t * t * c2x + t * t * t * p2.first
                val y = inv * inv * inv * p1.second + 3.0 * inv * inv * t * c1y + 3.0 * inv * t * t * c2y + t * t * t * p2.second
                sampled.add(x to y)
            }
        }
        return sampled
    }

    fun generateCloudformContour(
        center: Pair<Double, Double>,
        size: Pair<Double, Double>,
        performanceSeed: Any?,
        instructionIndex: Int,
        markIndex: Int,
        variation: JSONObject? = null,
        weight: String = "pen",
        pointCount: Int = 49
    ): CloudContour {
        val count = max(24, min(72, pointCount))
        val seed = cloudformSeed(performanceSeed, instructionIndex, markIndex)
        val rx = max(1e-6, size.first / 2.0)
        val ry = max(1e-6, size.second / 2.0)
        val angles = (0 until count).map { 2.0 * Math.PI * it.toDouble() / count.toDouble() }
        val baseRadii = angles.map { baseRadius(it, seed, variation, weight) }
        val basePoints = angles.zip(baseRadii).map { (theta, r) ->
            (center.first + rx * r * cos(theta)) to (center.second + ry * r * sin(theta))
        }
        val lengths = (0 until count).map { i ->
            hypot(
                basePoints[(i + 1) % count].first - basePoints[i].first,
                basePoints[(i + 1) % count].second - basePoints[i].second
            )
        }
        val perimeter = max(lengths.sum(), 1e-9)
        val arcPositions = mutableListOf<Double>()
        var travelled = 0.0
        for (len in lengths) {
            arcPositions.add(travelled / perimeter)
            travelled += len
        }
        val gain = variationGain(variation)
        val nominalScale = min(rx, ry)
        val displaced = mutableListOf<Pair<Double, Double>>()
        for (i in 0 until count) {
            val basePoint = basePoints[i]
            val arcPos = arcPositions[i]
            val before = basePoints[(i - 1 + count) % count]
            val after = basePoints[(i + 1) % count]
            val tx = after.first - before.first
            val ty = after.second - before.second
            val tangentLen = max(hypot(tx, ty), 1e-9)
            var nx = -ty / tangentLen
            var ny = tx / tangentLen
            val towardCenterX = center.first - basePoint.first
            val towardCenterY = center.second - basePoint.second
            if (nx * towardCenterX + ny * towardCenterY < 0) {
                nx = -nx
                ny = -ny
            }
            val waistSignal = normalizedHarmonicSignal(
                2.0 * Math.PI * arcPos,
                seed xor 0xC10D5EEDL,
                "waist",
                2..4,
                0.72
            )
            val reqSignal = max(0.0, -waistSignal)
            val requested = reqSignal * reqSignal * (0.08 + gain * 0.36) * nominalScale
            val curvatureR = curvatureRadius(before, basePoint, after)
            var nonlocalSeparation = Double.POSITIVE_INFINITY
            for (otherIdx in 0 until count) {
                val diff1 = (otherIdx - i + count) % count
                val diff2 = (i - otherIdx + count) % count
                if (min(diff1, diff2) > 3) {
                    val dist = hypot(basePoint.first - basePoints[otherIdx].first, basePoint.second - basePoints[otherIdx].second)
                    if (dist < nonlocalSeparation) {
                        nonlocalSeparation = dist
                    }
                }
            }
            val distToCenter = hypot(basePoint.first - center.first, basePoint.second - center.second)
            val radialClearance = max(0.0, distToCenter - nominalScale * 0.48)
            val maximum = min(
                min(curvatureR * 0.20, nonlocalSeparation * 0.18),
                min(radialClearance * 0.50, nominalScale * (0.08 + gain * 0.36))
            )
            val distance = min(requested, maximum)
            displaced.add((basePoint.first + nx * distance) to (basePoint.second + ny * distance))
        }
        return CloudContour(points = displaced, pathD = closedCatmullRomPath(displaced))
    }
}


