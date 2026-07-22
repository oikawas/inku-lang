package app.inku.mobile.render

import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin
import org.json.JSONObject

internal object ServerRendererMaterial {
    private data class OutlineProfile(val offset: Double, val width: Double, val opacity: Double, val dash: String?)
    private data class SpeckProfile(val count: Int, val spread: Double, val radius: Double, val opacity: Double)

    fun usesMaterialOutline(weight: String): Boolean = materialOutlineProfile(weight).isNotEmpty() || speckProfile(weight) != null

    fun lineGroup(ins: JSONObject, attrs: SvgAttrs, x1: Double, y1: Double, x2: Double, y2: Double): String? {
        val weight = ins.optString("weight", "pen")
        if (weight !in setOf("pencil", "crayon", "chalk", "brush_thin", "brush_thick", "burin", "drypoint")) return null
        val seedStr = ins.toString()
        val seedInt = ServerRendererGeometry.seedToInt(seedStr)
        val out = StringBuilder()
        out.append("""<g><line x1="$x1" y1="$y1" x2="$x2" y2="$y2" fill="none" ${attrs.toSvgAttributes(includeFill = false)}/>""")
        when (weight) {
            "pencil" -> {
                listOf(-0.9, 1.1).forEachIndexed { idx, amount ->
                    val (ox, oy) = ServerRendererGeometry.linePerpOffset(x1, y1, x2, y2, amount)
                    val jitter = ServerRendererGeometry.hashToUnit(idx, seedInt) * 0.6
                    val layer = attrs.copy(strokeWidth = 0.45, strokeOpacity = 0.26, dash = "1,7", filter = "url(#texture-pencil)")
                    out.append(lineElement(x1 + ox + jitter, y1 + oy, x2 + ox - jitter, y2 + oy, layer))
                }
                out.append(powderSpecks(x1, y1, x2, y2, attrs, seedStr, count = 18, spread = 1.8, radius = 0.45, opacity = 0.20))
            }
            "chalk" -> {
                listOf(-3.0, 3.4).forEachIndexed { idx, amount ->
                    val (ox, oy) = ServerRendererGeometry.linePerpOffset(x1, y1, x2, y2, amount)
                    val jitter = ServerRendererGeometry.hashToUnit(idx, seedInt) * 1.4
                    val layer = attrs.copy(strokeWidth = 1.1, strokeOpacity = 0.28, dash = "8,12,1,8")
                    out.append(lineElement(x1 + ox + jitter, y1 + oy, x2 + ox - jitter, y2 + oy, layer))
                }
                out.append(powderSpecks(x1, y1, x2, y2, attrs, seedStr, count = 34, spread = 5.5, radius = 0.9, opacity = 0.26))
            }
            "brush_thin" -> {
                listOf(-1.4, 1.8).forEachIndexed { idx, amount ->
                    val (ox, oy) = ServerRendererGeometry.linePerpOffset(x1, y1, x2, y2, amount)
                    val jitter = ServerRendererGeometry.hashToUnit(idx, seedInt) * 1.1
                    val layer = attrs.copy(strokeWidth = 0.9 + idx * 0.5, strokeOpacity = 0.32, dash = if (idx == 0) "22,9" else "14,8")
                    out.append(lineElement(x1 + ox + jitter, y1 + oy, x2 + ox - jitter, y2 + oy, layer))
                }
            }
            else -> {
                val amounts = if (weight == "crayon") listOf(-3.2, -1.4, 2.0, 3.6) else listOf(-3.5, 2.8, 5.0)
                amounts.forEachIndexed { idx, amount ->
                    val (ox, oy) = ServerRendererGeometry.linePerpOffset(x1, y1, x2, y2, amount)
                    val jitter = ServerRendererGeometry.hashToUnit(idx, seedInt) * if (weight == "crayon") 2.2 else 2.8
                    val layer = attrs.copy(
                        strokeWidth = max(0.8, ServerRendererStyle.strokeWidth(weight) * if (weight == "crayon") 0.25 else 0.30),
                        strokeOpacity = if (weight == "crayon") 0.24 else 0.38,
                        dash = if (weight == "crayon") "2,5,9,7" else "18,7,3,11",
                    )
                    out.append(lineElement(x1 + ox + jitter, y1 + oy, x2 + ox - jitter, y2 + oy, layer))
                }
                if (weight == "crayon") {
                    out.append(powderSpecks(x1, y1, x2, y2, attrs, seedStr, count = 26, spread = 4.0, radius = 0.75, opacity = 0.18))
                }
            }
        }
        out.append("</g>")
        return out.toString()
    }

    fun circleOutline(ins: JSONObject, attrs: SvgAttrs, cx: Double, cy: Double, r: Double): String {
        val seed = ins.toString()
        val weight = ins.optString("weight", "pen")
        val out = StringBuilder()
        materialOutlineProfile(weight).forEach { (offset, width, opacity, dash) ->
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            out.append("""<circle cx="$cx" cy="$cy" r="${max(0.0, r + offset)}" ${outline.toSvgAttributes()}/>""")
        }
        out.append(specksAtPoints(ServerRendererGeometry.circlePoints(cx, cy, r, r, speckProfile(weight)?.count ?: 0), attrs, seed, speckProfile(weight)))
        return out.toString()
    }

    fun ellipseOutline(ins: JSONObject, attrs: SvgAttrs, cx: Double, cy: Double, rx: Double, ry: Double): String {
        val weight = ins.optString("weight", "pen")
        val seed = ins.toString()
        val out = StringBuilder()
        materialOutlineProfile(weight).forEach { (offset, width, opacity, dash) ->
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            out.append("""<ellipse cx="$cx" cy="$cy" rx="${max(0.0, rx + offset)}" ry="${max(0.0, ry + offset)}" ${outline.toSvgAttributes()}/>""")
        }
        out.append(specksAtPoints(ServerRendererGeometry.circlePoints(cx, cy, rx, ry, speckProfile(weight)?.count ?: 0), attrs, seed, speckProfile(weight)))
        return out.toString()
    }

    fun rectOutline(ins: JSONObject, attrs: SvgAttrs, x: Double, y: Double, w: Double, h: Double): String {
        val weight = ins.optString("weight", "pen")
        val seed = ins.toString()
        val out = StringBuilder()
        materialOutlineProfile(weight).forEach { (offset, width, opacity, dash) ->
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            out.append("""<rect x="${x - offset}" y="${y - offset}" width="${max(0.0, w + offset * 2.0)}" height="${max(0.0, h + offset * 2.0)}" ${outline.toSvgAttributes()}/>""")
        }
        out.append(specksAtPoints(ServerRendererGeometry.rectPoints(x, y, w, h, speckProfile(weight)?.count ?: 0), attrs, seed, speckProfile(weight)))
        return out.toString()
    }

    fun arcOutline(ins: JSONObject, attrs: SvgAttrs, cx: Double, cy: Double, r: Double, start: Double, end: Double): String {
        val weight = ins.optString("weight", "pen")
        val seed = ins.toString()
        val out = StringBuilder()
        materialOutlineProfile(weight).forEach { (offset, width, opacity, dash) ->
            val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity, dash)
            out.append("""<path d="${ServerRendererGeometry.arcPathD(cx, cy, max(0.0, r + offset), start, end)}" ${outline.toSvgAttributes()}/>""")
        }
        out.append(specksAtPoints(ServerRendererGeometry.arcPoints(cx, cy, r, start, end, speckProfile(weight)?.count ?: 0), attrs, seed, speckProfile(weight)))
        return out.toString()
    }

    private fun materialOutlineProfile(weight: String): List<OutlineProfile> {
        val baseWidth = ServerRendererStyle.strokeWidth(weight)
        return when (weight) {
            "pencil" -> listOf(OutlineProfile(-1.0, 0.45, 0.24, "1,7"), OutlineProfile(1.2, 0.5, 0.20, "1,5"))
            "chalk" -> listOf(OutlineProfile(-3.2, 1.2, 0.30, "8,12,1,8"), OutlineProfile(3.6, 1.0, 0.24, "5,10,1,6"))
            "brush_thin" -> listOf(OutlineProfile(-1.6, 1.0, 0.32, "22,9"), OutlineProfile(1.8, 1.4, 0.28, "14,8"))
            "brush_thick" -> listOf(OutlineProfile(-4.0, baseWidth * 0.28, 0.36, "18,7,3,11"), OutlineProfile(3.2, baseWidth * 0.22, 0.28, "11,9"))
            "crayon" -> listOf(OutlineProfile(-3.4, baseWidth * 0.24, 0.24, "2,5,9,7"), OutlineProfile(-1.5, baseWidth * 0.20, 0.20, "4,8"), OutlineProfile(2.4, baseWidth * 0.22, 0.22, "2,5,9,7"))
            "burin", "drypoint" -> listOf(OutlineProfile(-0.8, 0.4, 0.30, "1,4"))
            else -> emptyList()
        }
    }

    private fun speckProfile(weight: String): SpeckProfile? = when (weight) {
        "pencil" -> SpeckProfile(18, 1.8, 0.45, 0.20)
        "crayon" -> SpeckProfile(28, 4.0, 0.75, 0.18)
        "chalk" -> SpeckProfile(36, 5.5, 0.9, 0.26)
        else -> null
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
            out.append("""<circle cx="${px + ox + ux * along}" cy="${py + oy + uy * along}" r="$r" fill="${attrs.stroke}" stroke="none" opacity="$opacity"/>""")
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
            out.append("""<circle cx="${point.first + ox}" cy="${point.second + oy}" r="$r" fill="${attrs.stroke}" stroke="none" opacity="${profile.opacity}"/>""")
        }
        return out.toString()
    }

    private fun ropeTwists(x1: Double, y1: Double, x2: Double, y2: Double, attrs: SvgAttrs, seed: String): String {
        val out = StringBuilder()
        val (ux, uy) = ServerRendererGeometry.lineDirection(x1, y1, x2, y2)
        val px = -uy
        val py = ux
        val twistAttrs = attrs.copy(strokeWidth = 1.2, strokeOpacity = 0.42, dash = null, filter = null)
        for (idx in 0 until 13) {
            val t = (idx + 0.5) / 13.0
            val cx = x1 + (x2 - x1) * t
            val cy = y1 + (y2 - y1) * t
            val phase = if (idx % 2 == 0) 1.0 else -1.0
            val span = 8.0 + kotlin.math.abs(ServerRendererGeometry.signedHash(idx, seed)) * 2.5
            val halfU = 3.0
            out.append(lineElement(cx - ux * halfU + px * span * phase, cy - uy * halfU + py * span * phase, cx + ux * halfU - px * span * phase, cy + uy * halfU - py * span * phase, twistAttrs))
        }
        return out.toString()
    }
}
