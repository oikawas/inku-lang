package app.inku.mobile.render

import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.pipeline.RenderRequest
import java.security.MessageDigest
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import org.json.JSONArray
import org.json.JSONObject

class DefaultSvgRenderer : SvgRenderer {
    override fun render(request: RenderRequest): RenderResult {
        val score = JSONObject(request.scoreJson)
        val canvas = CanvasAspects.sizeFor(request.canvasAspect.ifBlank { score.optString("canvas", "square") })
        val catalog = ColorCatalogs.get(request.colorCatalogId)
        val colors = catalog.map
        val background = colors[score.optString("background", "white")] ?: "#ffffff"
        val instructions = score.optJSONArray("instructions") ?: JSONArray()
        val body = StringBuilder()

        body.append("""<rect x="0" y="0" width="${canvas.width}" height="${canvas.height}" fill="$background"/>""")
        body.append("""<g clip-path="url(#canvas-clip)">""")
        for (i in 0 until instructions.length()) {
            val instruction = instructions.optJSONObject(i) ?: continue
            val expanded = expandArrangement(instruction)
            for (mark in expanded) {
                body.append(renderInstruction(mark, colors, canvas.width.toDouble(), canvas.height.toDouble()))
            }
        }
        body.append("</g>")

        val svg = buildString {
            append("""<svg xmlns="http://www.w3.org/2000/svg" width="${canvas.width}" height="${canvas.height}" viewBox="0 0 ${canvas.width} ${canvas.height}">""")
            append("""<defs><clipPath id="canvas-clip"><rect x="0" y="0" width="${canvas.width}" height="${canvas.height}"/></clipPath></defs>""")
            append(body)
            append("</svg>")
        }
        val metadata = JSONObject()
            .put("render_engine_id", "default")
            .put("render_engine_version", "1")
            .put("render_canvas_aspect", CanvasAspects.normalize(request.canvasAspect))
            .put("render_color_catalog_id", catalog.id)
            .put("render_color_catalog_name", catalog.name)
            .put("render_color_catalog_sub", catalog.sub)
            .put("render_color_profile", JSONObject().put("id", "srgb").put("name", "sRGB IEC61966-2.1").put("standard", "IEC 61966-2-1:1999"))
            .put("render_color_map", JSONObject(colors))
        val hash = sha256(svg + metadata.toString())
        return RenderResult(svg = svg, metadataJson = metadata.put("render_hash", hash).toString(), renderHash = hash)
    }

    private fun renderInstruction(ins: JSONObject, colors: Map<String, String>, width: Double, height: Double): String {
        val primitive = ins.optString("primitive", "line")
        val color = colors[ins.optString("color", "black")] ?: "#111111"
        val strokeWidth = strokeWidth(ins.optString("weight", "pen"))
        val style = dashStyle(ins.optString("style", "solid"))
        val common = """stroke="$color" stroke-width="$strokeWidth" stroke-linecap="round" stroke-linejoin="round"$style"""
        val fill = if (ins.optBoolean("filled", false) && primitive != "line") color else "none"
        return when (primitive) {
            "line" -> {
                val from = ins.optJSONArray("from")
                val to = ins.optJSONArray("to")
                val x1 = px(from?.optDouble(0, 0.1) ?: 0.1, width)
                val y1 = px(from?.optDouble(1, 0.5) ?: 0.5, height)
                val x2 = px(to?.optDouble(0, 0.9) ?: 0.9, width)
                val y2 = px(to?.optDouble(1, 0.5) ?: 0.5, height)
                """<line x1="$x1" y1="$y1" x2="$x2" y2="$y2" fill="none" $common/>"""
            }
            "circle" -> {
                val center = ins.optJSONArray("center")
                val cx = px(center?.optDouble(0, 0.5) ?: 0.5, width)
                val cy = px(center?.optDouble(1, 0.5) ?: 0.5, height)
                val r = px(ins.optDouble("radius", 0.12), min(width, height))
                """<circle cx="$cx" cy="$cy" r="$r" fill="$fill" $common/>"""
            }
            "ellipse" -> {
                val center = ins.optJSONArray("center")
                val size = ins.optJSONArray("size")
                val cx = px(center?.optDouble(0, 0.5) ?: 0.5, width)
                val cy = px(center?.optDouble(1, 0.5) ?: 0.5, height)
                val rx = px((size?.optDouble(0, 0.26) ?: 0.26) / 2.0, width)
                val ry = px((size?.optDouble(1, 0.16) ?: 0.16) / 2.0, height)
                """<ellipse cx="$cx" cy="$cy" rx="$rx" ry="$ry" fill="$fill" $common/>"""
            }
            "square" -> {
                val pos = ins.optJSONArray("position")
                val size = ins.optJSONArray("size")
                val x = px(pos?.optDouble(0, 0.38) ?: 0.38, width)
                val y = px(pos?.optDouble(1, 0.38) ?: 0.38, height)
                val w = px(size?.optDouble(0, 0.24) ?: 0.24, width)
                val h = px(size?.optDouble(1, 0.24) ?: 0.24, height)
                """<rect x="$x" y="$y" width="$w" height="$h" fill="$fill" $common/>"""
            }
            "triangle" -> polygon(pointsForRegular(ins, 3, width, height), fill, common)
            "polygon" -> polygon(pointsForRegular(ins, ins.optInt("sides", 5).coerceIn(5, 8), width, height), fill, common)
            "arc" -> {
                val center = ins.optJSONArray("center")
                val cx = px(center?.optDouble(0, 0.5) ?: 0.5, width)
                val cy = px(center?.optDouble(1, 0.5) ?: 0.5, height)
                val r = px(ins.optDouble("radius", 0.18), min(width, height))
                val start = Math.toRadians(ins.optDouble("angle_start", 20.0))
                val end = Math.toRadians(ins.optDouble("angle_end", 300.0))
                val x1 = cx + cos(start) * r
                val y1 = cy - sin(start) * r
                val x2 = cx + cos(end) * r
                val y2 = cy - sin(end) * r
                val large = if (kotlin.math.abs(ins.optDouble("angle_end", 300.0) - ins.optDouble("angle_start", 20.0)) > 180) 1 else 0
                """<path d="M $x1 $y1 A $r $r 0 $large 0 $x2 $y2" fill="none" $common/>"""
            }
            else -> ""
        }
    }

    private fun expandArrangement(ins: JSONObject): List<JSONObject> {
        val arr = ins.optJSONObject("arrangement") ?: return listOf(ins)
        val count = arr.optInt("count", 1).coerceIn(1, 1000)
        if (count == 1) return listOf(copyWithoutArrangement(ins))
        val layout = arr.optString("layout", "horizontal")
        val margin = arr.optDouble("margin", 0.1).coerceIn(0.0, 0.45)
        val base = copyWithoutArrangement(ins)
        return (0 until count).map { i ->
            val t = if (count <= 1) 0.5 else i.toDouble() / (count - 1).toDouble()
            val target = when (layout) {
                "vertical" -> margin to (margin + t * (1.0 - margin * 2.0))
                "scatter" -> hash01(i, ins.toString()) to hash01(i + 1000, ins.toString())
                "radial" -> {
                    val a = Math.toRadians(i * 360.0 / count)
                    (0.5 + cos(a) * arr.optDouble("radius", 0.3)) to (0.5 - sin(a) * arr.optDouble("radius", 0.3))
                }
                else -> (margin + t * (1.0 - margin * 2.0)) to 0.5
            }
            shiftTo(base, target.first, target.second)
        }
    }

    private fun copyWithoutArrangement(ins: JSONObject): JSONObject = JSONObject(ins.toString()).also { it.remove("arrangement") }

    private fun shiftTo(ins: JSONObject, targetX: Double, targetY: Double): JSONObject {
        val copy = JSONObject(ins.toString())
        when (copy.optString("primitive", "line")) {
            "line" -> {
                val from = copy.optJSONArray("from") ?: JSONArray(listOf(0.45, 0.25))
                val to = copy.optJSONArray("to") ?: JSONArray(listOf(0.55, 0.75))
                val ax = (from.optDouble(0) + to.optDouble(0)) / 2.0
                val ay = (from.optDouble(1) + to.optDouble(1)) / 2.0
                copy.put("from", JSONArray(listOf(from.optDouble(0) + targetX - ax, from.optDouble(1) + targetY - ay)))
                copy.put("to", JSONArray(listOf(to.optDouble(0) + targetX - ax, to.optDouble(1) + targetY - ay)))
            }
            "square", "triangle" -> {
                val size = copy.optJSONArray("size") ?: JSONArray(listOf(0.18, 0.18))
                copy.put("position", JSONArray(listOf(targetX - size.optDouble(0) / 2.0, targetY - size.optDouble(1) / 2.0)))
            }
            else -> copy.put("center", JSONArray(listOf(targetX, targetY)))
        }
        return copy
    }

    private fun pointsForRegular(ins: JSONObject, sides: Int, width: Double, height: Double): List<Pair<Double, Double>> {
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

    private fun polygon(points: List<Pair<Double, Double>>, fill: String, common: String): String {
        val data = points.joinToString(" ") { "${it.first},${it.second}" }
        return """<polygon points="$data" fill="$fill" $common/>"""
    }

    private fun strokeWidth(weight: String): Double = when (weight) {
        "hair" -> 0.5
        "pencil" -> 1.5
        "rotring" -> 1.0
        "crayon" -> 4.0
        "chalk" -> 3.0
        "brush_thin" -> 3.0
        "brush_thick" -> 8.0
        "rope" -> 10.0
        else -> 2.0
    }

    private fun dashStyle(style: String): String = when (style) {
        "dashed" -> " stroke-dasharray=\"12,8\""
        "dotted" -> " stroke-dasharray=\"2,6\""
        "dash_dot" -> " stroke-dasharray=\"12,6,2,6\""
        else -> ""
    }

    private fun px(value: Double, scale: Double): Double = min(max(value, 0.0), 1.0) * scale

    private fun hash01(i: Int, seed: String): Double {
        val digest = MessageDigest.getInstance("SHA-256").digest("$seed:$i".toByteArray())
        val raw = ((digest[0].toInt() and 0xff) shl 24) or ((digest[1].toInt() and 0xff) shl 16) or ((digest[2].toInt() and 0xff) shl 8) or (digest[3].toInt() and 0xff)
        return (raw.toLong() and 0xffffffffL).toDouble() / 0xffffffffL.toDouble()
    }

    private fun sha256(value: String): String {
        return MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString("") { "%02x".format(it) }
    }
}
