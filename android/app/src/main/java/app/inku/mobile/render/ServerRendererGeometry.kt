package app.inku.mobile.render

import java.security.MessageDigest
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt
import org.json.JSONArray
import org.json.JSONObject

internal object ServerRendererGeometry {
    fun px(value: Double, scale: Double): Double = min(max(value, 0.0), 1.0) * scale

    fun fmt(value: Double): String = "%.3f".format(java.util.Locale.US, value)

    fun signedHash(i: Int, seed: String): Double {
        val digest = MessageDigest.getInstance("SHA-256").digest("$seed:$i".toByteArray())
        var raw = 0L
        for (offset in 0 until 8) {
            raw = raw or ((digest[offset].toLong() and 0xffL) shl (8 * offset))
        }
        return raw.toDouble() / 9_223_372_036_854_775_808.0
    }

    fun hash01(i: Int, seed: String): Double {
        val digest = MessageDigest.getInstance("SHA-256").digest("$seed:$i".toByteArray())
        val raw = ((digest[0].toLong() and 0xffL)) or
            ((digest[1].toLong() and 0xffL) shl 8) or
            ((digest[2].toLong() and 0xffL) shl 16) or
            ((digest[3].toLong() and 0xffL) shl 24)
        return (raw and 0xffffffffL).toDouble() / 0xffffffffL.toDouble()
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
        if (quality == "none" || quality == "pink") return false
        val dimensions = variation.optJSONArray("dimensions") ?: return false
        for (i in 0 until dimensions.length()) {
            if (dimensions.optString(i) in setOf("position_x", "position_y")) return true
        }
        return false
    }

    fun variedLinePoints(x1: Double, y1: Double, x2: Double, y2: Double, variation: JSONObject?, seed: String): List<Pair<Double, Double>> {
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
        val result = mutableListOf(x1 to y1)
        val segments = 80
        for (i in 1 until segments) {
            val t = i.toDouble() / segments.toDouble()
            val offset = variationOffset(t, i, variation, seed)
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

    private fun variationOffset(t: Double, segment: Int, variation: JSONObject, seed: String): Double {
        val amp = when (variation.optString("amplitude", "medium")) {
            "fine" -> 7.0
            "broad" -> 30.0
            else -> 12.0
        }
        val freq = when (variation.optString("frequency", "medium")) {
            "slow" -> 2.0
            "high" -> 14.0
            else -> 6.0
        }
        return when (variation.optString("quality", "none")) {
            "wave" -> sin(t * Math.PI * 2.0 * freq) * amp
            "perlin" -> smoothNoise(t * freq, seed) * amp
            "white" -> signedHash(segment, seed) * amp
            else -> 0.0
        }
    }

    private fun smoothNoise(x: Double, seed: String): Double {
        val xi = kotlin.math.floor(x).toInt()
        val xf = x - xi
        val v1 = signedHash(xi, seed)
        val v2 = signedHash(xi + 1, seed)
        val t = xf * xf * (3.0 - 2.0 * xf)
        return v1 * (1.0 - t) + v2 * t
    }
}
