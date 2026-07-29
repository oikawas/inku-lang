package app.inku.mobile.render

import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.sqrt
import org.json.JSONObject

internal object ServerRendererMaterial {
    internal data class OutlineProfile(val offset: Double, val width: Double, val opacity: Double, val dash: String?)
    private data class SpeckProfile(val count: Int, val spread: Double, val radius: Double, val opacity: Double)

    // render engine 15: strength is darkness, not distance. The intensity ladder answered
    // "the material layer reads weak" by multiplying the outline offset (2.8x) and putting
    // a 3.5px floor under it, which pushed the trace 3.5-14x the band's half-width away and
    // made it read as a second contour. The table's own values were always 0.7-2.3x the
    // half-width. The opacity lever (1.8 with a 0.50 floor) is untouched.
    private const val OUTLINE_OFFSET_GAIN = 1.0
    private const val OUTLINE_OFFSET_FLOOR_RATIO = 0.0
    private const val OUTLINE_OPACITY_GAIN = 1.8

    // The intensity ladder's speck lever. _speck_profile applies it once, at the source,
    // so every caller gets the same powder; the port had left it out of the profile and
    // put 3.2 in the straight-line path alone.
    private const val SPECK_SPREAD_GAIN = 1.8

    // The tools that own a material outline. `_material_line_group` reads the same set as
    // the closed contours do, so a tool cannot come out clothed on a circle and bare on a
    // line. burin and drypoint are deliberately absent: they carry plate_tone and burr
    // instead, which are separate mechanisms.
    private val MATERIAL_OUTLINE_WEIGHTS = setOf(
        "pencil", "chalk", "brush_thin", "brush_thick", "crayon", "pen"
    )

    fun usesMaterialOutline(weight: String): Boolean = materialOutlineProfile(weight, 1000.0).isNotEmpty() || baseSpeckProfile(weight) != null

    fun outlineOffsetPx(offset: Double, unit: Double): Double {
        val floor = OUTLINE_OFFSET_FLOOR_RATIO * unit
        if (floor <= 0.0 || kotlin.math.abs(offset) >= floor) return offset
        return java.lang.Math.copySign(floor, offset)
    }

    fun outlineOpacity(opacity: Double): Double {
        return kotlin.math.min(1.0, kotlin.math.max(opacity, 0.50))
    }

    fun speckOpacity(opacity: Double): Double {
        return kotlin.math.min(1.0, kotlin.math.max(opacity, 0.40))
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
        val raw = (hash[0].toLong() and 0xFFL) or
            ((hash[1].toLong() and 0xFFL) shl 8) or
            ((hash[2].toLong() and 0xFFL) shl 16) or
            ((hash[3].toLong() and 0xFFL) shl 24)
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
            val len = Math.hypot(tx, ty)
            val length = if (len == 0.0) 1.0 else len
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
            vals.add(java.lang.String.format(java.util.Locale.US, "%.3f", m))
            vals.add(java.lang.String.format(java.util.Locale.US, "%.3f", g))
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
        centerline: List<Pair<Double, Double>>? = null,
        instructionSeed: Long? = null
    ): String? {
        val weight = ins.optString("weight", "pen")
        // engine 15: the gate reads the same spec table as the closed contours, so a tool
        // added to the table cannot come out clothed on a circle and bare on a line.
        if (weight !in MATERIAL_OUTLINE_WEIGHTS) return null

        val seedInt = instructionSeed ?: ServerRendererGeometry.seedForInstruction(ins, renderSeed)
        val scale = unit / 1000.0
        val offsetGain = OUTLINE_OFFSET_GAIN
        val opacityGain = OUTLINE_OPACITY_GAIN
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
                    out.append(powderSpecks(x1, y1, x2, y2, attrs, ins.toString(), count = spec.count, spread = spec.spread, radius = spec.radius, opacity = spec.opacity))
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
                val spec = speckProfile("chalk", lineLen, unit, baseCountOverride = 34)
                if (spec != null) {
                    out.append(powderSpecks(x1, y1, x2, y2, attrs, ins.toString(), count = spec.count, spread = spec.spread, radius = spec.radius, opacity = spec.opacity))
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
            "pen" -> {
                // The two tines of a split nib, running symmetrically just outside the
                // band edge. No specks: powder is the mark of a soft, crumbling medium.
                listOf(-1.40, 1.40).forEachIndexed { k, amount ->
                    val layerAttrs = attrs.copy(
                        strokeWidth = (0.38 - k * 0.04) * scale,
                        strokeOpacity = layerOpacity(0.24 - k * 0.04)
                    )
                    emitLayer(amount, layerAttrs, 14.0 - k * 2.0, 3.0 + k, k)
                }
            }
            else -> {
                val amounts = if (weight == "crayon") listOf(-3.2, -1.4, 2.0, 3.6) else listOf(-3.5, 2.8, 5.0)
                val (mark, gap) = if (weight == "crayon") Pair(6.0, 6.0) else Pair(14.0, 9.0)
                amounts.forEachIndexed { k, amount ->
                    val baseW = ServerRendererStyle.strokeWidth(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale })
                    val layerAttrs = attrs.copy(
                        strokeWidth = Math.max(0.8 * scale, baseW * (if (weight == "crayon") 0.25 else 0.30)),
                        strokeOpacity = layerOpacity(if (weight == "crayon") 0.24 else 0.38)
                    )
                    emitLayer(amount, layerAttrs, mark, gap, k)
                }
                if (weight == "crayon") {
                    val spec = speckProfile("crayon", lineLen, unit, baseCountOverride = 26)
                    if (spec != null) {
                        out.append(powderSpecks(x1, y1, x2, y2, attrs, ins.toString(), count = spec.count, spread = spec.spread, radius = spec.radius, opacity = spec.opacity))
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
        materialOutlineProfile(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale }).forEach { (offset, width, opacity, dash) ->
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
        materialOutlineProfile(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale }).forEach { (offset, width, opacity, dash) ->
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
        materialOutlineProfile(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale }).forEach { (offset, width, opacity, dash) ->
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
        materialOutlineProfile(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale }).forEach { (offset, width, opacity, dash) ->
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            out.append("""<path class="material-outline" d="${ServerRendererGeometry.arcPathD(cx, cy, max(0.0, r + offset), start, end)}" ${outline.toSvgAttributes()}/>""")
        }
        val deltaDeg = ((end - start) % 360.0 + 360.0) % 360.0
        val arcLen = 2.0 * Math.PI * r * (deltaDeg / 360.0)
        val spec = speckProfile(weight, arcLen, unit)
        out.append(specksAtPoints(ServerRendererGeometry.arcPoints(cx, cy, r, start, end, spec?.count ?: 0), attrs, seed, spec))
        return out.toString()
    }

    fun offsetPerformedPath(
        path: List<Pair<Double, Double>>,
        offset: Double,
        closed: Boolean,
        center: Pair<Double, Double>
    ): List<Pair<Double, Double>> {
        val normals = ServerStrokeEngine.centerlineNormals(path, closed)
        var votes = 0
        for (i in path.indices) {
            val (x, y) = path[i]
            val (nx, ny) = normals[i]
            if (nx * (x - center.first) + ny * (y - center.second) >= 0.0) votes++ else votes--
        }
        val sign = if (votes >= 0) 1.0 else -1.0
        return path.indices.map { i ->
            val (x, y) = path[i]
            val (nx, ny) = normals[i]
            Pair(x + nx * offset * sign, y + ny * offset * sign)
        }
    }

    fun performedOutline(
        ins: JSONObject,
        attrs: SvgAttrs,
        path: List<Pair<Double, Double>>,
        unit: Double,
        closed: Boolean,
        pathLenPx: Double,
        center: Pair<Double, Double>,
        renderSeed: Long? = null,
        // The speck seed is the instruction seed, which only the caller can build. The
        // geometry-side fallback here returns the render seed itself, so leaving it to
        // compute its own put the powder in the wrong places.
        instructionSeed: String? = null
    ): String {
        val weight = ins.optString("weight", "pen")
        val seedStr = instructionSeed ?: ServerRendererGeometry.seedForInstruction(ins, renderSeed).toString()
        val out = StringBuilder()
        materialOutlineProfile(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale }).forEach { (offset, width, opacity, dash) ->
            val pts = offsetPerformedPath(path, offset, closed, center)
            val ptsStr = pts.joinToString(" ") { "${ServerRendererGeometry.fmt(it.first)},${ServerRendererGeometry.fmt(it.second)}" }
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            val tag = if (closed) "polygon" else "polyline"
            out.append("""<$tag points="$ptsStr" ${outline.toSvgAttributes()} class="material-outline"/>""")
        }
        val spec = speckProfile(weight, pathLenPx, unit)
        if (spec != null && spec.count > 0 && path.isNotEmpty()) {
            val resampled = (0 until spec.count).map { idx ->
                path[minOf(path.size - 1, (idx * path.size) / spec.count)]
            }
            out.append(specksAtPoints(resampled, attrs, seedStr.toString(), spec))
        }
        return out.toString()
    }


    internal fun materialOutlineProfile(weight: String, unit: Double, thinness: String? = null): List<OutlineProfile> {
        val scale = unit / 1000.0
        val baseWidth = ServerRendererStyle.strokeWidth(weight, unit, thinness)
        val offsetGain = OUTLINE_OFFSET_GAIN
        val opacityGain = OUTLINE_OPACITY_GAIN
        val offsetFloor = OUTLINE_OFFSET_FLOOR_RATIO * unit
        val opacityFloor = 0.50

        fun calcOffset(raw: Double): Double {
            val v = raw * scale * offsetGain
            if (offsetFloor <= 0.0) return v
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
            // engine 15: the most used tool in production stops being a bare one. The trace
            // is the two tines of a split nib, running just outside the band edge at +/-1.0px.
            "pen" -> listOf(
                OutlineProfile(calcOffset(-1.40), 0.38 * scale, calcOpacity(0.24), scaleDash("14,3", scale)),
                OutlineProfile(calcOffset(1.40), 0.34 * scale, calcOpacity(0.20), scaleDash("12,4", scale))
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

    /**
     * `baseCountOverride` is the straight line's own count table. The server's
     * `_material_line_group` calls `_speck_count` with 18 / 34 / 26 rather than the closed
     * contours' 18 / 36 / 28; the port had been reading the closed-contour numbers there.
     */
    private fun speckProfile(weight: String, pathLenPx: Double, unit: Double, baseCountOverride: Int? = null): SpeckProfile? {
        val base = baseSpeckProfile(weight) ?: return null
        val scale = unit / 1000.0
        val count = speckCount(baseCountOverride ?: base.count, pathLenPx, unit)
        val opacity = speckOpacity(base.opacity)
        return SpeckProfile(count, base.spread * scale * SPECK_SPREAD_GAIN, base.radius * scale, opacity)
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
}

