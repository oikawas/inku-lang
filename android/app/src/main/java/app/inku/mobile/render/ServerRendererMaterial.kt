package app.inku.mobile.render

import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.sqrt
import org.json.JSONObject

internal object ServerRendererMaterial {
    private data class OutlineProfile(val offset: Double, val width: Double, val opacity: Double, val dash: String?)
    private data class SpeckProfile(val count: Int, val spread: Double, val radius: Double, val opacity: Double)

    fun usesMaterialOutline(weight: String): Boolean = materialOutlineProfile(weight, 1000.0).isNotEmpty() || baseSpeckProfile(weight) != null

    fun outlineOffsetPx(offset: Double, unit: Double): Double {
        val scale = unit / 1000.0
        val raw = offset * scale
        val floor = 0.0035 * unit
        if (floor <= 0 || kotlin.math.abs(raw) >= floor) return raw
        return java.lang.Math.copySign(floor, raw)
    }

    fun outlineOpacity(opacity: Double): Double {
        return kotlin.math.min(1.0, kotlin.math.max(opacity, 0.5))
    }

    fun speckOpacity(opacity: Double): Double {
        return kotlin.math.min(1.0, kotlin.math.max(opacity, 0.4))
    }

    fun scaleDash(spec: String?, scale: Double): String? {
        if (spec.isNullOrBlank()) return null
        return spec.split(",").joinToString(",") { part ->
            ServerRendererGeometry.fmt(part.trim().toDouble() * scale)
        }
    }

    fun hash01(i: Int, seed: Long, salt: String): Double {
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        val input = "${seed.toULong()}:$salt:$i".toByteArray(Charsets.UTF_8)
        val hash = digest.digest(input)
        var raw: Long = 0
        for (b in 0 until 4) {
            raw = raw or ((hash[b].toLong() and 0xFFL) shl (b * 8))
        }
        return raw.toDouble() / 4294967295.0
    }

    fun valueNoise1d(x: Double, seed: Long): Double {
        val xi = Math.floor(x).toInt()
        val xf = x - xi
        val v1 = ServerRendererGeometry.hashToUnit(xi, seed)
        val v2 = ServerRendererGeometry.hashToUnit(xi + 1, seed)
        val t = xf * xf * (3.0 - 2.0 * xf)
        return v1 * (1.0 - t) + v2 * t
    }

    fun offsetPolyline(
        points: List<Pair<Double, Double>>,
        amount: Double,
        wander: Double = 0.0,
        wanderPeriod: Double = 1.0,
        seed: Long = 0L
    ): List<Pair<Double, Double>> {
        val n = points.size
        if (n < 2) return points
        val out = mutableListOf<Pair<Double, Double>>()
        var arc = 0.0
        for (i in 0 until n) {
            val (tx, ty) = when (i) {
                0 -> Pair(points[1].first - points[0].first, points[1].second - points[0].second)
                n - 1 -> Pair(points[n - 1].first - points[n - 2].first, points[n - 1].second - points[n - 2].second)
                else -> Pair(points[i + 1].first - points[i - 1].first, points[i + 1].second - points[i - 1].second)
            }
            val length = Math.hypot(tx, ty).let { if (it == 0.0) 1.0 else it }
            val nx = -ty / length
            val ny = tx / length
            var off = amount
            if (wander != 0.0) {
                val period = Math.max(1e-6, wanderPeriod)
                off += wander * (valueNoise1d(arc / period, seed) * 2.0 - 1.0)
            }
            out.add(Pair(points[i].first + nx * off, points[i].second + ny * off))
            if (i < n - 1) {
                arc += Math.hypot(points[i + 1].first - points[i].first, points[i + 1].second - points[i].second)
            }
        }
        return out
    }

    fun variedDashPattern(dashUnits: Double, mark: Double, gap: Double, seed: Long): String {
        val period = Math.max(1.0, mark + gap)
        val count = Math.max(6, Math.min(28, (dashUnits / period).toInt() + 3))
        val vals = mutableListOf<String>()
        for (i in 0 until count) {
            val m = mark * (0.5 + 1.3 * hash01(i, seed, "dash-mark"))
            val g = gap * (0.45 + 1.5 * hash01(i, seed, "dash-gap"))
            vals.add(ServerRendererGeometry.fmt(m))
            vals.add(ServerRendererGeometry.fmt(g))
        }
        return vals.joinToString(",")
    }

    fun lineGroup(
        ins: JSONObject,
        attrs: SvgAttrs,
        x1: Double,
        y1: Double,
        x2: Double,
        y2: Double,
        unit: Double,
        includeBase: Boolean = true,
        renderSeed: Long? = null,
        centerline: List<Pair<Double, Double>>? = null
    ): String? {
        val weight = ins.optString("weight", "pen")
        if (weight !in setOf("pencil", "crayon", "chalk", "brush_thin", "brush_thick")) return null

        val seedInt = ServerRendererGeometry.seedForInstruction(ins, renderSeed)
        val scale = unit / 1000.0
        val offsetGain = 2.8
        val opacityGain = 1.8
        val spreadGain = 3.2
        val lineLen = Math.hypot(x2 - x1, y2 - y1)
        val dashUnits = lineLen / Math.max(1e-6, scale)

        val path = if (!centerline.isNullOrEmpty()) centerline else listOf(Pair(x1, y1), Pair(x2, y2))
        val out = StringBuilder()

        fun layerOpacity(v: Double): Double = outlineOpacity(v * opacityGain)
        fun layerOffset(amount: Double): Double = outlineOffsetPx(amount * scale * offsetGain, unit)

        fun emitLayer(amount: Double, layerAttrs: SvgAttrs, mark: Double, gap: Double, k: Int) {
            val offPx = layerOffset(amount)
            val layerSeed = seedInt + k * 7919L
            val wander = 0.35 * Math.abs(offPx) + 0.6 * scale
            val pts = offsetPolyline(path, offPx, wander = wander, wanderPeriod = 60.0 * scale, seed = layerSeed)
            val ptsStr = pts.joinToString(" ") { "${ServerRendererGeometry.fmt(it.first)},${ServerRendererGeometry.fmt(it.second)}" }
            val dashPattern = scaleDash(variedDashPattern(dashUnits, mark, gap, layerSeed), scale)
            val la = layerAttrs.copy(dash = dashPattern)
            out.append("""<polyline points="$ptsStr" fill="none" ${la.toSvgAttributes(includeFill = false)} class="material-outline"/>""")
        }

        if (includeBase) {
            val basePts = offsetPolyline(path, 0.0, wander = 0.5 * scale, wanderPeriod = 70.0 * scale, seed = seedInt)
            val basePtsStr = basePts.joinToString(" ") { "${ServerRendererGeometry.fmt(it.first)},${ServerRendererGeometry.fmt(it.second)}" }
            out.append("""<polyline points="$basePtsStr" fill="none" ${attrs.toSvgAttributes(includeFill = false)} class="material-outline"/>""")
        }

        when (weight) {
            "pencil" -> {
                listOf(-0.9, 1.1).forEachIndexed { k, amount ->
                    val layerAttrs = attrs.copy(
                        strokeWidth = 0.45 * scale,
                        strokeOpacity = layerOpacity(0.26),
                        filter = "url(#texture-pencil)"
                    )
                    emitLayer(amount, layerAttrs, 1.0, 7.0, k)
                }
                val spec = speckProfile("pencil", lineLen, unit)
                if (spec != null) {
                    out.append(powderSpecks(x1, y1, x2, y2, attrs, ins.toString(), count = spec.count, spread = spec.spread * spreadGain, radius = spec.radius, opacity = spec.opacity))
                }
            }
            "chalk" -> {
                listOf(-3.0, 3.4).forEachIndexed { k, amount ->
                    val layerAttrs = attrs.copy(
                        strokeWidth = 1.1 * scale,
                        strokeOpacity = layerOpacity(0.28)
                    )
                    emitLayer(amount, layerAttrs, 8.0, 11.0, k)
                }
                val spec = speckProfile("chalk", lineLen, unit)
                if (spec != null) {
                    out.append(powderSpecks(x1, y1, x2, y2, attrs, ins.toString(), count = spec.count, spread = spec.spread * spreadGain, radius = spec.radius, opacity = spec.opacity))
                }
            }
            "brush_thin" -> {
                listOf(-1.4, 1.8).forEachIndexed { k, amount ->
                    val layerAttrs = attrs.copy(
                        strokeWidth = (0.9 + k * 0.5) * scale,
                        strokeOpacity = layerOpacity(0.32)
                    )
                    emitLayer(amount, layerAttrs, 22.0, 9.0, k)
                }
            }
            else -> {
                val amounts = if (weight == "crayon") listOf(-3.2, -1.4, 2.0, 3.6) else listOf(-3.5, 2.8, 5.0)
                val (mark, gap) = if (weight == "crayon") Pair(6.0, 6.0) else Pair(14.0, 9.0)
                amounts.forEachIndexed { k, amount ->
                    val baseW = ServerRendererStyle.strokeWidth(weight, unit)
                    val layerAttrs = attrs.copy(
                        strokeWidth = Math.max(0.8 * scale, baseW * (if (weight == "crayon") 0.25 else 0.30)),
                        strokeOpacity = layerOpacity(if (weight == "crayon") 0.24 else 0.38)
                    )
                    emitLayer(amount, layerAttrs, mark, gap, k)
                }
                if (weight == "crayon") {
                    val spec = speckProfile("crayon", lineLen, unit)
                    if (spec != null) {
                        out.append(powderSpecks(x1, y1, x2, y2, attrs, ins.toString(), count = spec.count, spread = spec.spread * spreadGain, radius = spec.radius, opacity = spec.opacity))
                    }
                }
            }
        }
        return out.toString()
    }

    fun circleOutline(ins: JSONObject, attrs: SvgAttrs, cx: Double, cy: Double, r: Double, unit: Double): String {
        val weight = ins.optString("weight", "pen")
        val seed = ins.toString()
        val out = StringBuilder()
        materialOutlineProfile(weight, unit).forEach { (offset, width, opacity, dash) ->
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            out.append("""<circle cx="${ServerRendererGeometry.fmt(cx)}" cy="${ServerRendererGeometry.fmt(cy)}" r="${ServerRendererGeometry.fmt(max(0.0, r + offset))}" ${outline.toSvgAttributes()} class="material-outline"/>""")
        }
        val perim = 2.0 * Math.PI * r
        val spec = speckProfile(weight, perim, unit)
        out.append(specksAtPoints(ServerRendererGeometry.circlePoints(cx, cy, r, r, spec?.count ?: 0), attrs, seed, spec))
        return out.toString()
    }

    fun ellipseOutline(ins: JSONObject, attrs: SvgAttrs, cx: Double, cy: Double, rx: Double, ry: Double, unit: Double): String {
        val weight = ins.optString("weight", "pen")
        val seed = ins.toString()
        val out = StringBuilder()
        materialOutlineProfile(weight, unit).forEach { (offset, width, opacity, dash) ->
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            out.append("""<ellipse cx="${ServerRendererGeometry.fmt(cx)}" cy="${ServerRendererGeometry.fmt(cy)}" rx="${ServerRendererGeometry.fmt(max(0.0, rx + offset))}" ry="${ServerRendererGeometry.fmt(max(0.0, ry + offset))}" ${outline.toSvgAttributes()} class="material-outline"/>""")
        }
        val approxPerim = Math.PI * (3.0 * (rx + ry) - sqrt((3.0 * rx + ry) * (rx + 3.0 * ry)))
        val spec = speckProfile(weight, approxPerim, unit)
        out.append(specksAtPoints(ServerRendererGeometry.circlePoints(cx, cy, rx, ry, spec?.count ?: 0), attrs, seed, spec))
        return out.toString()
    }

    fun rectOutline(ins: JSONObject, attrs: SvgAttrs, x: Double, y: Double, w: Double, h: Double, unit: Double): String {
        val weight = ins.optString("weight", "pen")
        val seed = ins.toString()
        val out = StringBuilder()
        materialOutlineProfile(weight, unit).forEach { (offset, width, opacity, dash) ->
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            out.append("""<rect x="${ServerRendererGeometry.fmt(x - offset)}" y="${ServerRendererGeometry.fmt(y - offset)}" width="${ServerRendererGeometry.fmt(max(0.0, w + offset * 2.0))}" height="${ServerRendererGeometry.fmt(max(0.0, h + offset * 2.0))}" ${outline.toSvgAttributes()} class="material-outline"/>""")
        }
        val perim = 2.0 * (w + h)
        val spec = speckProfile(weight, perim, unit)
        out.append(specksAtPoints(ServerRendererGeometry.rectPoints(x, y, w, h, spec?.count ?: 0), attrs, seed, spec))
        return out.toString()
    }

    fun arcOutline(ins: JSONObject, attrs: SvgAttrs, cx: Double, cy: Double, r: Double, start: Double, end: Double, unit: Double): String {
        val weight = ins.optString("weight", "pen")
        val seed = ins.toString()
        val out = StringBuilder()
        materialOutlineProfile(weight, unit).forEach { (offset, width, opacity, dash) ->
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            out.append("""<path class="material-outline" d="${ServerRendererGeometry.arcPathD(cx, cy, max(0.0, r + offset), start, end)}" ${outline.toSvgAttributes()}/>""")
        }
        val deltaDeg = ((end - start) % 360.0 + 360.0) % 360.0
        val arcLen = 2.0 * Math.PI * r * (deltaDeg / 360.0)
        val spec = speckProfile(weight, arcLen, unit)
        out.append(specksAtPoints(ServerRendererGeometry.arcPoints(cx, cy, r, start, end, spec?.count ?: 0), attrs, seed, spec))
        return out.toString()
    }


    private fun materialOutlineProfile(weight: String, unit: Double): List<OutlineProfile> {
        val scale = unit / 1000.0
        val baseWidth = ServerRendererStyle.strokeWidth(weight, unit)
        val offsetGain = 2.8
        val opacityGain = 1.8
        val offsetFloor = 0.0035 * unit
        val opacityFloor = 0.50

        fun calcOffset(raw: Double): Double {
            val v = raw * scale * offsetGain
            return if (kotlin.math.abs(v) >= offsetFloor) v else (if (v < 0) -offsetFloor else offsetFloor)
        }

        fun calcOpacity(raw: Double): Double {
            return kotlin.math.max(opacityFloor, kotlin.math.min(1.0, raw * opacityGain))
        }

        val rawProfiles = when (weight) {
            "pencil" -> listOf(
                OutlineProfile(calcOffset(-1.0), 0.45 * scale, calcOpacity(0.24), scaleDash("1,7", scale)),
                OutlineProfile(calcOffset(1.2), 0.50 * scale, calcOpacity(0.20), scaleDash("1,5", scale))
            )
            "chalk" -> listOf(
                OutlineProfile(calcOffset(-3.2), 1.20 * scale, calcOpacity(0.30), scaleDash("8,12,1,8", scale)),
                OutlineProfile(calcOffset(3.6), 1.00 * scale, calcOpacity(0.24), scaleDash("5,10,1,6", scale))
            )
            "brush_thin" -> listOf(
                OutlineProfile(calcOffset(-1.6), 1.00 * scale, calcOpacity(0.32), scaleDash("22,9", scale)),
                OutlineProfile(calcOffset(1.8), 1.40 * scale, calcOpacity(0.28), scaleDash("14,8", scale))
            )
            "brush_thick" -> listOf(
                OutlineProfile(calcOffset(-4.0), baseWidth * 0.28, calcOpacity(0.36), scaleDash("18,7,3,11", scale)),
                OutlineProfile(calcOffset(3.2), baseWidth * 0.22, calcOpacity(0.28), scaleDash("11,9", scale))
            )
            "crayon" -> listOf(
                OutlineProfile(calcOffset(-3.4), baseWidth * 0.24, calcOpacity(0.24), scaleDash("2,5,9,7", scale)),
                OutlineProfile(calcOffset(-1.5), baseWidth * 0.20, calcOpacity(0.20), scaleDash("4,8", scale)),
                OutlineProfile(calcOffset(2.4), baseWidth * 0.22, calcOpacity(0.22), scaleDash("2,5,9,7", scale))
            )
            "burin", "drypoint" -> listOf(
                OutlineProfile(calcOffset(-0.8), 0.40 * scale, calcOpacity(0.30), scaleDash("1,4", scale))
            )
            else -> emptyList()
        }
        return rawProfiles
    }

    fun speckCount(baseCount: Int, pathLengthPx: Double, unit: Double): Int {
        val anchorPerim = unit * 1.2566370614359172
        val ratio = if (anchorPerim > 0) pathLengthPx / anchorPerim else 1.0
        val rawCount = Math.rint(baseCount * ratio * 2.6).toInt()
        return kotlin.math.max(10, kotlin.math.min(baseCount * 4, rawCount))
    }

    private fun baseSpeckProfile(weight: String): SpeckProfile? = when (weight) {
        "pencil" -> SpeckProfile(18, 1.8, 0.45, 0.20)
        "crayon" -> SpeckProfile(28, 4.0, 0.75, 0.18)
        "chalk" -> SpeckProfile(36, 5.5, 0.9, 0.26)
        else -> null
    }

    private fun speckProfile(weight: String, pathLenPx: Double, unit: Double): SpeckProfile? {
        val base = baseSpeckProfile(weight) ?: return null
        val scale = unit / 1000.0
        val count = speckCount(base.count, pathLenPx, unit)
        val opacity = speckOpacity(base.opacity)
        return SpeckProfile(count, base.spread * scale, base.radius * scale, opacity)
    }

    private fun lineElement(x1: Double, y1: Double, x2: Double, y2: Double, attrs: SvgAttrs): String {
        return """<line x1="$x1" y1="$y1" x2="$x2" y2="$y2" fill="none" ${attrs.toSvgAttributes(includeFill = false)}/>"""
    }

    private fun powderSpecks(x1: Double, y1: Double, x2: Double, y2: Double, attrs: SvgAttrs, seed: String, count: Int, spread: Double, radius: Double, opacity: Double): String {
        val out = StringBuilder()
        val (ux, uy) = ServerRendererGeometry.lineDirection(x1, y1, x2, y2)
        for (idx in 0 until count) {
            val t = (idx + 0.5) / count
            val px = x1 + (x2 - x1) * t
            val py = y1 + (y2 - y1) * t
            val (ox, oy) = ServerRendererGeometry.linePerpOffset(x1, y1, x2, y2, ServerRendererGeometry.signedHash(idx, seed) * spread)
            val along = ServerRendererGeometry.signedHash(idx + 101, seed) * spread * 0.45
            val r = max(0.35, radius * (0.75 + kotlin.math.abs(ServerRendererGeometry.signedHash(idx + 202, seed)) * 0.7))
            out.append("""<circle cx="${px + ox + ux * along}" cy="${py + oy + uy * along}" r="${ServerRendererGeometry.fmt(r)}" fill="${attrs.stroke}" stroke="none" opacity="${ServerRendererGeometry.fmt(opacity)}"/>""")
        }
        return out.toString()
    }

    private fun specksAtPoints(points: List<Pair<Double, Double>>, attrs: SvgAttrs, seed: String, profile: SpeckProfile?): String {
        if (profile == null || points.isEmpty()) return ""
        val out = StringBuilder()
        points.forEachIndexed { idx, point ->
            val ox = ServerRendererGeometry.signedHash(idx, seed) * profile.spread
            val oy = ServerRendererGeometry.signedHash(idx + 157, seed) * profile.spread
            val r = max(0.35, profile.radius * (0.75 + kotlin.math.abs(ServerRendererGeometry.signedHash(idx + 263, seed)) * 0.7))
            out.append("""<circle cx="${ServerRendererGeometry.fmt(point.first + ox)}" cy="${ServerRendererGeometry.fmt(point.second + oy)}" r="${ServerRendererGeometry.fmt(r)}" fill="${attrs.stroke}" stroke="none" opacity="${ServerRendererGeometry.fmt(profile.opacity)}"/>""")
        }
        return out.toString()
    }

    private fun ropeTwists(x1: Double, y1: Double, x2: Double, y2: Double, attrs: SvgAttrs, seed: String, unit: Double): String {
        val scale = unit / 1000.0
        val out = StringBuilder()
        val (ux, uy) = ServerRendererGeometry.lineDirection(x1, y1, x2, y2)
        val px = -uy
        val py = ux
        val twistAttrs = attrs.copy(strokeWidth = 1.2 * scale, strokeOpacity = 0.42, dash = null, filter = null)
        for (idx in 0 until 13) {
            val t = (idx + 0.5) / 13.0
            val cx = x1 + (x2 - x1) * t
            val cy = y1 + (y2 - y1) * t
            val phase = if (idx % 2 == 0) 1.0 else -1.0
            val span = (8.0 + kotlin.math.abs(ServerRendererGeometry.signedHash(idx, seed)) * 2.5) * scale
            val halfU = 3.0 * scale
            out.append(lineElement(cx - ux * halfU + px * span * phase, cy - uy * halfU + py * span * phase, cx + ux * halfU - px * span * phase, cy + uy * halfU - py * span * phase, twistAttrs))
        }
        return out.toString()
    }
}

