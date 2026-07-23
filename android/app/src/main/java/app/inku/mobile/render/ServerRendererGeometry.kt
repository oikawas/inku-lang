package app.inku.mobile.render

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
    fun px(value: Double, scale: Double): Double = min(max(value, 0.0), 1.0) * scale

    fun fmt(value: Double): String = "%.3f".format(java.util.Locale.US, value)

    fun seedToLong(seed: Any?): Long {
        return when (seed) {
            is Number -> seed.toLong()
            is String -> seed.toULongOrNull()?.toLong() ?: seed.toLongOrNull() ?: seed.hashCode().toLong()
            else -> 0L
        }
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
            val rx = size.getDouble(0) * width / 2.0
            val ry = size.getDouble(1) * height / 2.0
            return kotlin.math.sqrt(kotlin.math.max(0.0, rx * ry))
        }
        if (p in listOf("square", "triangle", "cloudform") && ins.has("size")) {
            val size = ins.getJSONArray("size")
            val w = size.getDouble(0) * width
            val h = size.getDouble(1) * height
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

    fun amplitudePx(variation: JSONObject, ins: JSONObject, width: Double, height: Double, unit: Double): Double {
        val rep = clampedRepresentativePx(ins, width, height, unit)
        val ampStr = variation.optString("amplitude", "medium")
        val ratio = when (ampStr) {
            "fine" -> 0.025
            "broad" -> 0.18
            else -> 0.08
        }
        return kotlin.math.min(ratio * rep, 0.40 * rep)
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

    fun trianglePoints(ins: JSONObject, width: Double, height: Double): List<Pair<Double, Double>> {
        val pos = ins.optJSONArray("position")
        val size = ins.optJSONArray("size")
        val x = px(pos?.optDouble(0, 0.35) ?: 0.35, width)
        val y = px(pos?.optDouble(1, 0.35) ?: 0.35, height)
        val w = px(size?.optDouble(0, 0.30) ?: 0.30, width)
        val h = px(size?.optDouble(1, 0.30) ?: 0.30, height)
        return listOf((x + w / 2.0) to y, x to (y + h), (x + w) to (y + h))
    }

    fun arcPathD(cx: Double, cy: Double, r: Double, startDeg: Double, endDeg: Double): String {
        val sa = Math.toRadians(startDeg)
        val ea = Math.toRadians(endDeg)
        val x1 = cx + r * cos(sa)
        val y1 = cy - r * sin(sa)
        val x2 = cx + r * cos(ea)
        val y2 = cy - r * sin(ea)
        val delta = ((endDeg - startDeg) % 360.0 + 360.0) % 360.0
        val largeArc = if (delta > 180.0) 1 else 0
        val sweep = if (endDeg > startDeg) 0 else 1
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

    fun needsPathVariation(variation: JSONObject?): Boolean {
        if (variation == null) return false
        val quality = variation.optString("quality", "none")
        if (quality == "none") return false
        val dimensions = variation.optJSONArray("dimensions") ?: return false
        for (i in 0 until dimensions.length()) {
            if (dimensions.optString(i) in setOf("position_x", "position_y", "radius")) return true
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
        if (variation == null || !needsPathVariation(variation)) return basePoints
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
        if (variation == null || !needsPathVariation(variation) || points.isEmpty()) return points
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

    fun variedArcPathD(cx: Double, cy: Double, r: Double, startDeg: Double, endDeg: Double, variation: JSONObject?, seed: Any?, count: Int = 60): String {
        return variedArcPathD(cx, cy, r, startDeg, endDeg, variation, seedToLong(seed), JSONObject(), 1000.0, 1000.0, 1000.0)
    }

    fun variedArcPathD(cx: Double, cy: Double, r: Double, startDeg: Double, endDeg: Double, variation: JSONObject?, seed: Any?, ins: JSONObject, width: Double, height: Double, unit: Double): String {
        return variedArcPathD(cx, cy, r, startDeg, endDeg, variation, seedToLong(seed), ins, width, height, unit)
    }

    fun variedArcPathD(cx: Double, cy: Double, r: Double, startDeg: Double, endDeg: Double, variation: JSONObject?, seed: Long, ins: JSONObject, width: Double, height: Double, unit: Double): String {
        if (variation == null || !needsPathVariation(variation)) {
            return arcPathD(cx, cy, r, startDeg, endDeg)
        }
        val deltaDeg = ((endDeg - startDeg) % 360.0 + 360.0) % 360.0
        val arcLen = 2.0 * Math.PI * r * (deltaDeg / 360.0)
        val count = segmentCount(arcLen, unit)
        val points = arcPoints(cx, cy, r, startDeg, endDeg, count)
        val dimensions = variation.optJSONArray("dimensions") ?: JSONArray()
        val axisX = (0 until dimensions.length()).any { dimensions.optString(it) == "position_x" }
        val axisY = (0 until dimensions.length()).any { dimensions.optString(it) == "position_y" }
        val amp = amplitudePx(variation, ins, width, height, unit)
        val center = cx to cy
        val variedPts = points.mapIndexed { i, pt ->
            val t = i.toDouble() / count.toDouble()
            val off = sampleOffset(t, variation, seed, i, amp)
            offsetContourPoint(pt.first, pt.second, off, center, axisX, axisY)
        }
        if (variedPts.isEmpty()) return ""
        val sb = StringBuilder("M ${fmt(variedPts[0].first)} ${fmt(variedPts[0].second)}")
        for (i in 1 until variedPts.size) {
            sb.append(" L ${fmt(variedPts[i].first)} ${fmt(variedPts[i].second)}")
        }
        return sb.toString()
    }

    fun fillScanAngle(seed: Any): Double {
        return hash01(0, seed, "fill-angle") * Math.PI
    }

    fun fillScanSpacing(ins: JSONObject, unit: Double): Double {
        val weight = ins.optString("weight", "pen")
        val baseWidth = ServerRendererStyle.strokeWidth(weight, unit)
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

    fun scanlineSegments(
        contour: List<Pair<Double, Double>>,
        angle: Double,
        spacing: Double,
        seed: Any
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
        val fillSpacingJitter = 0.24
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
            val jitter = 1.0 + (hash01(index, seed, "fill-spacing") - 0.5) * fillSpacingJitter
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

    fun shapeBbox(ins: JSONObject, width: Double, height: Double, unit: Double): DoubleArray? {
        val primitive = ins.optString("primitive", "")
        return when (primitive) {
            "circle" -> {
                val center = ins.optJSONArray("center")
                val cx = (center?.optDouble(0, 0.5) ?: 0.5) * width
                val cy = (center?.optDouble(1, 0.5) ?: 0.5) * height
                val r = ins.optDouble("radius", 0.12) * unit
                doubleArrayOf(cx - r, cy - r, r * 2.0, r * 2.0)
            }
            "ellipse" -> {
                val center = ins.optJSONArray("center")
                val size = ins.optJSONArray("size")
                val cx = (center?.optDouble(0, 0.5) ?: 0.5) * width
                val cy = (center?.optDouble(1, 0.5) ?: 0.5) * height
                val w = (size?.optDouble(0, 0.26) ?: 0.26) * width
                val h = (size?.optDouble(1, 0.16) ?: 0.16) * height
                doubleArrayOf(cx - w / 2.0, cy - h / 2.0, w, h)
            }
            "square", "triangle" -> {
                val pos = ins.optJSONArray("position")
                val size = ins.optJSONArray("size")
                val x = (pos?.optDouble(0, 0.38) ?: 0.38) * width
                val y = (pos?.optDouble(1, 0.38) ?: 0.38) * height
                val w = (size?.optDouble(0, 0.24) ?: 0.24) * width
                val h = (size?.optDouble(1, 0.24) ?: 0.24) * height
                doubleArrayOf(x, y, w, h)
            }
            "polygon" -> {
                val center = ins.optJSONArray("center")
                val pos = ins.optJSONArray("position")
                val size = ins.optJSONArray("size")
                val cx = (center?.optDouble(0) ?: ((pos?.optDouble(0, 0.4) ?: 0.4) + (size?.optDouble(0, 0.2) ?: 0.2) / 2.0)) * width
                val cy = (center?.optDouble(1) ?: ((pos?.optDouble(1, 0.4) ?: 0.4) + (size?.optDouble(1, 0.2) ?: 0.2) / 2.0)) * height
                val r = ins.optDouble("radius", (size?.optDouble(0, 0.22) ?: 0.22) / 2.0) * unit
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
        if (!needsPathVariation(variation)) return basePoints
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
}

