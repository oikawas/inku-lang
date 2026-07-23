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

    fun lineGroup(ins: JSONObject, attrs: SvgAttrs, x1: Double, y1: Double, x2: Double, y2: Double, unit: Double): String? {
        val weight = ins.optString("weight", "pen")
        if (weight !in setOf("pencil", "crayon", "chalk", "brush_thin", "brush_thick", "burin", "drypoint")) return null
        val seedStr = ins.toString()
        val seedInt = ServerRendererGeometry.seedToInt(seedStr)
        val scale = unit / 1000.0
        val lineLen = kotlin.math.hypot(x2 - x1, y2 - y1)
        val out = StringBuilder()
        out.append("""<g><line x1="$x1" y1="$y1" x2="$x2" y2="$y2" fill="none" ${attrs.toSvgAttributes(includeFill = false)}/>""")
        when (weight) {
            "pencil" -> {
                listOf(-0.9 * scale, 1.1 * scale).forEachIndexed { idx, amount ->
                    val (ox, oy) = ServerRendererGeometry.linePerpOffset(x1, y1, x2, y2, amount)
                    val jitter = ServerRendererGeometry.hashToUnit(idx, seedInt) * 0.6 * scale
                    val layer = attrs.copy(strokeWidth = 0.45 * scale, strokeOpacity = 0.26, dash = scaleDash("1,7", scale), filter = "url(#texture-pencil)")
                    out.append(lineElement(x1 + ox + jitter, y1 + oy, x2 + ox - jitter, y2 + oy, layer))
                }
                val spec = speckProfile("pencil", lineLen, unit)
                if (spec != null) {
                    out.append(powderSpecks(x1, y1, x2, y2, attrs, seedStr, count = spec.count, spread = spec.spread, radius = spec.radius, opacity = spec.opacity))
                }
            }
            "chalk" -> {
                listOf(-3.0 * scale, 3.4 * scale).forEachIndexed { idx, amount ->
                    val (ox, oy) = ServerRendererGeometry.linePerpOffset(x1, y1, x2, y2, amount)
                    val jitter = ServerRendererGeometry.hashToUnit(idx, seedInt) * 1.4 * scale
                    val layer = attrs.copy(strokeWidth = 1.1 * scale, strokeOpacity = 0.28, dash = scaleDash("8,12,1,8", scale))
                    out.append(lineElement(x1 + ox + jitter, y1 + oy, x2 + ox - jitter, y2 + oy, layer))
                }
                val spec = speckProfile("chalk", lineLen, unit)
                if (spec != null) {
                    out.append(powderSpecks(x1, y1, x2, y2, attrs, seedStr, count = spec.count, spread = spec.spread, radius = spec.radius, opacity = spec.opacity))
                }
            }
            "brush_thin" -> {
                listOf(-1.4 * scale, 1.8 * scale).forEachIndexed { idx, amount ->
                    val (ox, oy) = ServerRendererGeometry.linePerpOffset(x1, y1, x2, y2, amount)
                    val jitter = ServerRendererGeometry.hashToUnit(idx, seedInt) * 1.1 * scale
                    val layer = attrs.copy(strokeWidth = (0.9 + idx * 0.5) * scale, strokeOpacity = 0.32, dash = scaleDash(if (idx == 0) "22,9" else "14,8", scale))
                    out.append(lineElement(x1 + ox + jitter, y1 + oy, x2 + ox - jitter, y2 + oy, layer))
                }
            }
            else -> {
                val amounts = if (weight == "crayon") listOf(-3.2 * scale, -1.4 * scale, 2.0 * scale, 3.6 * scale) else listOf(-3.5 * scale, 2.8 * scale, 5.0 * scale)
                amounts.forEachIndexed { idx, amount ->
                    val (ox, oy) = ServerRendererGeometry.linePerpOffset(x1, y1, x2, y2, amount)
                    val jitter = ServerRendererGeometry.hashToUnit(idx, seedInt) * (if (weight == "crayon") 2.2 else 2.8) * scale
                    val layer = attrs.copy(
                        strokeWidth = max(0.8 * scale, ServerRendererStyle.strokeWidth(weight, unit) * if (weight == "crayon") 0.25 else 0.30),
                        strokeOpacity = if (weight == "crayon") 0.24 else 0.38,
                        dash = scaleDash(if (weight == "crayon") "2,5,9,7" else "18,7,3,11", scale),
                    )
                    out.append(lineElement(x1 + ox + jitter, y1 + oy, x2 + ox - jitter, y2 + oy, layer))
                }
                if (weight == "crayon") {
                    val spec = speckProfile("crayon", lineLen, unit)
                    if (spec != null) {
                        out.append(powderSpecks(x1, y1, x2, y2, attrs, seedStr, count = spec.count, spread = spec.spread, radius = spec.radius, opacity = spec.opacity))
                    }
                }
            }
        }
        out.append("</g>")
        return out.toString()
    }

    fun circleOutline(ins: JSONObject, attrs: SvgAttrs, cx: Double, cy: Double, r: Double, unit: Double): String {
        val seed = ins.toString()
        val weight = ins.optString("weight", "pen")
        val out = StringBuilder()
        materialOutlineProfile(weight, unit).forEach { (offset, width, opacity, dash) ->
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            out.append("""<circle cx="${ServerRendererGeometry.fmt(cx)}" cy="${ServerRendererGeometry.fmt(cy)}" r="${ServerRendererGeometry.fmt(max(0.0, r + offset))}" ${outline.toSvgAttributes()}/>""")
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
            out.append("""<ellipse cx="${ServerRendererGeometry.fmt(cx)}" cy="${ServerRendererGeometry.fmt(cy)}" rx="${ServerRendererGeometry.fmt(max(0.0, rx + offset))}" ry="${ServerRendererGeometry.fmt(max(0.0, ry + offset))}" ${outline.toSvgAttributes()}/>""")
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
            out.append("""<rect x="${ServerRendererGeometry.fmt(x - offset)}" y="${ServerRendererGeometry.fmt(y - offset)}" width="${ServerRendererGeometry.fmt(max(0.0, w + offset * 2.0))}" height="${ServerRendererGeometry.fmt(max(0.0, h + offset * 2.0))}" ${outline.toSvgAttributes()}/>""")
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
            out.append("""<path d="${ServerRendererGeometry.arcPathD(cx, cy, max(0.0, r + offset), start, end)}" ${outline.toSvgAttributes()}/>""")
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
        val rawProfiles = when (weight) {
            "pencil" -> listOf(OutlineProfile(-1.0, 0.45 * scale, 0.24, scaleDash("1,7", scale)), OutlineProfile(1.2, 0.5 * scale, 0.20, scaleDash("1,5", scale)))
            "chalk" -> listOf(OutlineProfile(-3.2, 1.2 * scale, 0.30, scaleDash("8,12,1,8", scale)), OutlineProfile(3.6, 1.0 * scale, 0.24, scaleDash("5,10,1,6", scale)))
            "brush_thin" -> listOf(OutlineProfile(-1.6, 1.0 * scale, 0.32, scaleDash("22,9", scale)), OutlineProfile(1.8, 1.4 * scale, 0.28, scaleDash("14,8", scale)))
            "brush_thick" -> listOf(OutlineProfile(-4.0, baseWidth * 0.28, 0.36, scaleDash("18,7,3,11", scale)), OutlineProfile(3.2, baseWidth * 0.22, 0.28, scaleDash("11,9", scale)))
            "crayon" -> listOf(OutlineProfile(-3.4, baseWidth * 0.24, 0.24, scaleDash("2,5,9,7", scale)), OutlineProfile(-1.5, baseWidth * 0.20, 0.20, scaleDash("4,8", scale)), OutlineProfile(2.4, baseWidth * 0.22, 0.22, scaleDash("2,5,9,7", scale)))
            "burin", "drypoint" -> listOf(OutlineProfile(-0.8, 0.4 * scale, 0.30, scaleDash("1,4", scale)))
            else -> emptyList()
        }
        return rawProfiles.map { prof ->
            prof.copy(
                offset = outlineOffsetPx(prof.offset, unit),
                opacity = outlineOpacity(prof.opacity),
            )
        }
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

