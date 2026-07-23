package app.inku.mobile.render

import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.pipeline.RenderRequest
import java.security.MessageDigest
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt
import kotlin.math.sin
import org.json.JSONArray
import org.json.JSONObject

class DefaultSvgRenderer : SvgRenderer {
    override fun render(request: RenderRequest): RenderResult {
        val score = JSONObject(request.scoreJson)
        val canvas = CanvasAspects.sizeFor(request.canvasAspect.ifBlank { score.optString("canvas", "square") })
        val catalog = ColorCatalogs.get(request.colorCatalogId)
        val colors = catalog.renderMap
        val background = colors[score.optString("background", "white")] ?: "#ffffff"
        val instructions = score.optJSONArray("instructions") ?: JSONArray()
        val renderSeed = if (score.has("render_seed") && !score.isNull("render_seed")) score.optLong("render_seed") else null
        val width = canvas.width.toDouble()
        val height = canvas.height.toDouble()
        val unit = min(width, height)
        val body = StringBuilder()
        val textureWeights = textureWeights(instructions)
        val neededBlurs = mutableMapOf<String, Double>()

        body.append("""<rect x="0" y="0" width="${canvas.width}" height="${canvas.height}" fill="$background"/>""")
        body.append("""<g clip-path="url(#canvas-clip)">""")
        for (i in 0 until instructions.length()) {
            val instruction = instructions.optJSONObject(i) ?: continue
            val expanded = expandArrangement(instruction)
            for ((index, mark) in expanded.withIndex()) {
                body.append(renderInstruction(mark, colors, width, height, unit, neededBlurs, index, renderSeed))
            }
        }
        body.append(renderPresenceLayer(score, colors, width, height))
        body.append("</g>")

        val svg = buildString {
            append("""<svg xmlns="http://www.w3.org/2000/svg" width="${canvas.width}" height="${canvas.height}" viewBox="0 0 ${canvas.width} ${canvas.height}">""")
            append("""<defs><clipPath id="canvas-clip"><rect x="0" y="0" width="${canvas.width}" height="${canvas.height}"/></clipPath>""")
            append(textureFilterDefs(textureWeights, unit))
            append(blurFilterDefs(neededBlurs))
            append("</defs>")
            append(body)
            append("</svg>")
        }
        val metadata = JSONObject()
            .put("render_engine_id", "default")
            .put("render_engine_version", "2")
            .put("render_canvas_aspect", CanvasAspects.normalize(request.canvasAspect))
            .put("render_canvas_aspect_id", CanvasAspects.normalize(request.canvasAspect))
            .put("render_canvas_aspect_ratio", CanvasAspects.ratioFor(request.canvasAspect))
            .put("render_color_catalog_id", catalog.id)
            .put("render_color_catalog_name", catalog.name)
            .put("render_color_catalog_sub", catalog.sub)
            .put("render_color_profile", JSONObject().put("id", "srgb").put("name", "sRGB IEC61966-2.1").put("standard", "IEC 61966-2-1:1999"))
            .put("render_color_map", JSONObject(colors))
        val hash = sha256(svg + metadata.toString())
        return RenderResult(svg = svg, metadataJson = metadata.put("render_hash", hash).toString(), renderHash = hash)
    }

    private fun renderInstruction(ins: JSONObject, colors: Map<String, String>, width: Double, height: Double, unit: Double, neededBlurs: MutableMap<String, Double>, index: Int = 0, renderSeed: Long? = null): String {
        val primitive = ins.optString("primitive", "line")
        val colorKey = ins.optString("color", "black")
        val weight = ins.optString("weight", "pen")
        val attrs = strokeAttrs(primitive, weight, colorKey, colors, ins, unit)
        val common = attrs.toSvgAttributes(includeFill = false)
        val fill = attrs.fill
        val raw = when (primitive) {
            "line" -> {
                val from = ins.optJSONArray("from")
                val to = ins.optJSONArray("to")
                val x1 = px(from?.optDouble(0, 0.5) ?: 0.5, width)
                val y1 = px(from?.optDouble(1, 0.0) ?: 0.0, height)
                val x2 = px(to?.optDouble(0, 0.5) ?: 0.5, width)
                val y2 = px(to?.optDouble(1, 1.0) ?: 1.0, height)
                if (weight != "rotring") {
                    renderHandStroke(ins, attrs, x1, y1, x2, y2, weight, unit, width, height, renderSeed)
                } else {
                    val variation = ins.optJSONObject("variation")
                    if (needsPathVariation(variation)) {
                        val points = variedLinePoints(x1, y1, x2, y2, variation, seedForInstruction(ins, renderSeed), ins, width, height, unit)
                            .joinToString(" ") { "${it.first},${it.second}" }
                        """<polyline points="$points" fill="none" $common/>"""
                    } else {
                        materialLineGroup(ins, attrs, x1, y1, x2, y2, unit) ?: """<line x1="$x1" y1="$y1" x2="$x2" y2="$y2" fill="none" $common/>"""
                    }
                }
            }
            "circle" -> {
                val center = ins.optJSONArray("center")
                val cx = px(center?.optDouble(0, 0.5) ?: 0.5, width)
                val cy = px(center?.optDouble(1, 0.5) ?: 0.5, height)
                val r = px(ins.optDouble("radius", 0.12), min(width, height))
                val variation = ins.optJSONObject("variation")
                val base = if (needsPathVariation(variation)) {
                    val pts = ServerRendererGeometry.variedCirclePoints(cx, cy, r, r, variation, seedForInstruction(ins), ins, width, height, unit)
                        .joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
                    """<polygon points="$pts" fill="$fill" $common/>"""
                } else {
                    """<circle cx="$cx" cy="$cy" r="$r" fill="$fill" $common/>"""
                }
                if (usesMaterialOutline(weight)) """<g>$base${materialCircleOutline(ins, attrs, cx, cy, r, unit)}</g>""" else base
            }
            "ellipse" -> {
                val center = ins.optJSONArray("center")
                val size = ins.optJSONArray("size")
                val cx = px(center?.optDouble(0, 0.5) ?: 0.5, width)
                val cy = px(center?.optDouble(1, 0.5) ?: 0.5, height)
                val rx = px((size?.optDouble(0, 0.26) ?: 0.26) / 2.0, width)
                val ry = px((size?.optDouble(1, 0.16) ?: 0.16) / 2.0, height)
                val variation = ins.optJSONObject("variation")
                val base = if (needsPathVariation(variation)) {
                    val pts = ServerRendererGeometry.variedCirclePoints(cx, cy, rx, ry, variation, seedForInstruction(ins), ins, width, height, unit)
                        .joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
                    """<polygon points="$pts" fill="$fill" $common/>"""
                } else {
                    """<ellipse cx="$cx" cy="$cy" rx="$rx" ry="$ry" fill="$fill" $common/>"""
                }
                if (usesMaterialOutline(weight)) """<g>$base${materialEllipseOutline(ins, attrs, cx, cy, rx, ry, unit)}</g>""" else base
            }
            "square" -> {
                val pos = ins.optJSONArray("position")
                val size = ins.optJSONArray("size")
                val x = px(pos?.optDouble(0, 0.38) ?: 0.38, width)
                val y = px(pos?.optDouble(1, 0.38) ?: 0.38, height)
                val w = px(size?.optDouble(0, 0.24) ?: 0.24, width)
                val h = px(size?.optDouble(1, 0.24) ?: 0.24, height)
                val variation = ins.optJSONObject("variation")
                val base = if (needsPathVariation(variation)) {
                    val rectPts = ServerRendererGeometry.rectPoints(x, y, w, h, 80)
                    val pts = ServerRendererGeometry.variedPolygonPoints(rectPts, variation, seedForInstruction(ins), x + w / 2.0, y + h / 2.0, ins, width, height, unit)
                        .joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
                    """<polygon points="$pts" fill="$fill" $common/>"""
                } else {
                    """<rect x="$x" y="$y" width="$w" height="$h" fill="$fill" $common/>"""
                }
                if (usesMaterialOutline(weight)) """<g>$base${materialRectOutline(ins, attrs, x, y, w, h, unit)}</g>""" else base
            }
            "triangle" -> {
                val points = trianglePoints(ins, width, height)
                val variation = ins.optJSONObject("variation")
                val pts = if (needsPathVariation(variation)) {
                    val pos = ins.optJSONArray("position")
                    val size = ins.optJSONArray("size")
                    val cx = px((pos?.optDouble(0, 0.35) ?: 0.35) + (size?.optDouble(0, 0.30) ?: 0.30) / 2.0, width)
                    val cy = px((pos?.optDouble(1, 0.35) ?: 0.35) + (size?.optDouble(1, 0.30) ?: 0.30) / 2.0, height)
                    ServerRendererGeometry.variedPolygonPoints(points, variation, seedForInstruction(ins), cx, cy, ins, width, height, unit)
                } else {
                    points
                }
                polygon(pts, fill, common)
            }
            "polygon" -> {
                val rawPoints = pointsForRegular(ins, ins.optInt("sides", 5).coerceIn(5, 8), width, height)
                val variation = ins.optJSONObject("variation")
                val pts = if (needsPathVariation(variation)) {
                    val center = ins.optJSONArray("center")
                    val position = ins.optJSONArray("position")
                    val size = ins.optJSONArray("size")
                    val cx = px(center?.optDouble(0) ?: ((position?.optDouble(0, 0.4) ?: 0.4) + (size?.optDouble(0, 0.2) ?: 0.2) / 2.0), width)
                    val cy = px(center?.optDouble(1) ?: ((position?.optDouble(1, 0.4) ?: 0.4) + (size?.optDouble(1, 0.2) ?: 0.2) / 2.0), height)
                    ServerRendererGeometry.variedPolygonPoints(rawPoints, variation, seedForInstruction(ins), cx, cy, ins, width, height, unit)
                } else {
                    rawPoints
                }
                polygon(pts, fill, common)
            }
            "arc" -> {
                val center = ins.optJSONArray("center")
                val cx = px(center?.optDouble(0, 0.5) ?: 0.5, width)
                val cy = px(center?.optDouble(1, 0.5) ?: 0.5, height)
                val r = px(ins.optDouble("radius", 0.18), min(width, height))
                val start = ins.optDouble("angle_start", 20.0)
                val end = ins.optDouble("angle_end", 300.0)
                val variation = ins.optJSONObject("variation")
                val path = ServerRendererGeometry.variedArcPathD(cx, cy, r, start, end, variation, seedForInstruction(ins), ins, width, height, unit)
                val base = """<path d="$path" fill="none" $common/>"""
                if (usesMaterialOutline(weight)) """<g>$base${materialArcOutline(ins, attrs, cx, cy, r, start, end, unit)}</g>""" else base
            }
            else -> ""
        }
        val rendered = applyRotation(raw, ins, width, height, primitive)
        val blurId = blurFilterId(ins.optJSONObject("variation"), ins, width, height, unit)
        if (blurId != null && ins.optJSONObject("variation") != null) {
            neededBlurs[blurId] = ServerRendererGeometry.blurStdPx(ins.optJSONObject("variation")!!, ins, width, height, unit)
        }
        return if (blurId != null) """<g filter="url(#$blurId)">$rendered</g>""" else rendered
    }

    private fun expandArrangement(ins: JSONObject): List<JSONObject> {

        val arr = ins.optJSONObject("arrangement") ?: return listOf(ins)
        val count = arr.optInt("count", 1).coerceIn(1, 1000)
        val layout = arr.optString("layout", "horizontal")
        val prepared = ensureLineCoords(ins, layout)
        if (count == 1) return listOf(applyColorCycle(copyWithoutArrangement(prepared), arr.optJSONArray("color_cycle"), 0))
        val path = arr.optString("path", "none")
        val preserveSpace = arr.optBoolean("preserve_space", false)
        val margin = if (preserveSpace) {
            max(arr.optDouble("margin", 0.1), 0.20)
        } else {
            arr.optDouble("margin", 0.1).coerceIn(0.0, 0.45)
        }
        val clusterCount = arr.optInt("cluster_count", 0)
        val rhythmSpacing = arr.optString("rhythm_spacing", "none")
        val base = prepared
        val seed = seedForInstruction(ins)
        return (0 until count).map { i ->
            val t = rhythmT(i, count, seed, rhythmSpacing)
            val target = if (clusterCount > 0 && layout in setOf("scatter", "horizontal", "vertical")) {
                clusteredPosition(
                    i = i,
                    count = count,
                    clusterCount = clusterCount,
                    path = pathFor(layout, path),
                    margin = margin,
                    density = arr.optString("density", "none"),
                    preserveSpace = preserveSpace,
                    seed = seed,
                    rhythmSpacing = rhythmSpacing,
                )
            } else if (path != "none") {
                pathPosition(i, count, margin, path, seed, rhythmSpacing)
            } else {
                when (layout) {
                    "vertical" -> margin to (margin + t * (1.0 - margin * 2.0))
                    "scatter" -> scatterPosition(i, margin, seed)
                    "radial" -> {
                        val center = arr.optJSONArray("center")
                        val cx = center?.optDouble(0, 0.5) ?: 0.5
                        val cy = center?.optDouble(1, 0.5) ?: 0.5
                        val a = Math.toRadians(t * 360.0)
                        (cx + cos(a) * arr.optDouble("radius", 0.3)) to (cy - sin(a) * arr.optDouble("radius", 0.3))
                    }
                    else -> (margin + t * (1.0 - margin * 2.0)) to 0.5
                }
            }
            val shifted = shiftTo(base, target.first, target.second)
            applyColorCycle(shifted, arr.optJSONArray("color_cycle"), i)
        }
    }

    private fun copyWithoutArrangement(ins: JSONObject): JSONObject = copyJsonObject(ins).also { it.remove("arrangement") }

    private fun ensureLineCoords(ins: JSONObject, layout: String): JSONObject {
        if (ins.optString("primitive", "line") != "line" || ins.has("from") || ins.has("to")) return ins
        val copy = copyJsonObject(ins)
        if (layout == "vertical") {
            copy.put("from", JSONArray(listOf(0.0, 0.5)))
            copy.put("to", JSONArray(listOf(1.0, 0.5)))
        } else {
            copy.put("from", JSONArray(listOf(0.5, 0.0)))
            copy.put("to", JSONArray(listOf(0.5, 1.0)))
        }
        return copy
    }

    private fun shiftTo(ins: JSONObject, targetX: Double, targetY: Double): JSONObject {
        val copy = copyJsonObject(ins)
        val arr = copy.optJSONObject("arrangement")
        copy.remove("arrangement")
        if (arr != null) {
            val notes = mutableListOf<String>()
            val density = arr.optString("density", "none")
            val fade = arr.optString("fade", "none")
            if (density != "none") notes.add("density=$density")
            if (fade != "none") notes.add("fade=$fade")
            if (arr.optBoolean("preserve_space", false)) notes.add("preserve_space")
            if (notes.isNotEmpty()) {
                val hint = copy.optString("color_hint", "")
                val effectNote = notes.joinToString("; ")
                copy.put("color_hint", if (hint.isBlank()) effectNote else "$hint; $effectNote")
            }
        }
        when (copy.optString("primitive", "line")) {
            "line" -> {
                val from = copy.optJSONArray("from") ?: JSONArray(listOf(0.5, 0.0))
                val to = copy.optJSONArray("to") ?: JSONArray(listOf(0.5, 1.0))
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

    private fun applyColorCycle(ins: JSONObject, cycle: JSONArray?, index: Int): JSONObject {
        if (cycle == null || cycle.length() == 0) return ins
        ins.put("color", cycle.optString(index % cycle.length(), ins.optString("color", "black")))
        val effectHint = renderEffectHint(ins.optString("color_hint", ""))
        if (effectHint == null) {
            ins.remove("color_hint")
        } else {
            ins.put("color_hint", effectHint)
        }
        return ins
    }

    private fun copyJsonObject(source: JSONObject): JSONObject {
        val copy = JSONObject()
        source.keys().forEach { key -> copy.put(key, source.opt(key)) }
        return copy
    }

    private fun renderEffectHint(colorHint: String): String? {
        if (colorHint.isBlank()) return null
        val hint = colorHint.lowercase().replace(Regex("""[\s:_()'".,/-]+"""), " ").trim()
        val effectTokens = listOf(
            "membrane", "haze", "fog", "mist", "atmosphere", "膜", "霞", "霧", "靄",
            "soft light", "柔らかな光", "陽光", "日差し",
            "scent", "fragrance", "香り", "匂",
            "waiting buds", "開花を待つ蕾", "蕾", "つぼみ",
            "five-sense", "五感",
            "fade directional", "fade=directional", "fade outward", "fade=outward",
            "reflection", "反射", "映り",
        )
        return effectTokens.filter { it in hint }.joinToString("; ").ifBlank { null }
    }

    private fun pathFor(layout: String, path: String): String = when {
        path != "none" -> path
        layout == "horizontal" -> "left_to_right"
        layout == "vertical" -> "top_to_bottom"
        else -> "none"
    }

    private fun scatterPosition(i: Int, margin: Double, seed: String): Pair<Double, Double> {
        val span = 1.0 - 2.0 * margin
        val digest = sha256Bytes("$seed:s:$i")
        val xv = uint32Le(digest, 0).toDouble() / 0xffffffffL.toDouble()
        val yv = uint32Le(digest, 4).toDouble() / 0xffffffffL.toDouble()
        return (margin + xv * span) to (margin + yv * span)
    }

    private fun rhythmT(i: Int, count: Int, seed: String, rhythmSpacing: String): Double {
        if (count <= 1) return 0.5
        val base = i.toDouble() / (count - 1).toDouble()
        return when (rhythmSpacing) {
            "syncopated" -> {
                val pulse = if (i % 2 == 0) -0.055 else 0.085
                clamp01(base + pulse * sin(base * Math.PI))
            }
            "accelerando" -> base * base
            "loose" -> {
                val jitter = (hash01(i, seed, "rhythm-loose") - 0.5) * 0.12 / maxOf(count / 8.0, 1.0)
                clamp01(base + jitter)
            }
            else -> base
        }
    }

    private fun pathPosition(i: Int, count: Int, margin: Double, path: String, seed: String, rhythmSpacing: String = "none"): Pair<Double, Double> {
        val span = 1.0 - 2.0 * margin
        val t = rhythmT(i, count, seed, rhythmSpacing)
        val jitterA = hash01(i, seed, "a") - 0.5
        val jitterB = hash01(i, seed, "b") - 0.5
        return when (path) {
            "diagonal" -> {
                val x = margin + t * span
                val y = 1.0 - margin - t * span
                clamp01(x + jitterA * 0.08) to clamp01(y + jitterB * 0.08)
            }
            "wave" -> {
                val x = margin + t * span
                val y = 0.5 + sin(t * Math.PI * 2.0) * 0.22 + jitterB * 0.08
                clamp01(x) to clamp01(y)
            }
            "top_to_bottom" -> clamp01(0.5 + jitterA * 0.30) to clamp01(margin + t * span)
            "left_to_right" -> clamp01(margin + t * span) to clamp01(0.5 + jitterB * 0.30)
            "right_half" -> clamp01(0.56 + hash01(i, seed, "x") * (0.44 - margin)) to clamp01(margin + hash01(i, seed, "y") * span)
            else -> scatterPosition(i, margin, seed)
        }
    }

    private fun clusteredPosition(
        i: Int,
        count: Int,
        clusterCount: Int,
        path: String,
        margin: Double,
        density: String,
        preserveSpace: Boolean,
        seed: String,
        rhythmSpacing: String = "none",
    ): Pair<Double, Double> {
        val nClusters = clusterCount.coerceIn(1, count)
        val clusterIndex = i % nClusters
        val localIndex = i / nClusters
        val localTotal = max(1, kotlin.math.ceil(count / nClusters.toDouble()).toInt())
        val centerMargin = max(margin, if (preserveSpace) 0.20 else margin)
        val center = if (path == "none") {
            scatterPosition(clusterIndex, centerMargin, seedForCluster(seed))
        } else {
            pathPosition(clusterIndex, nClusters, centerMargin, path, seedForCluster(seed), rhythmSpacing)
        }
        val axisAngle = when (path) {
            "diagonal" -> -Math.PI / 4.0
            "top_to_bottom" -> Math.PI / 2.0
            "left_to_right", "right_half", "wave" -> 0.0
            else -> hash01(clusterIndex, seed, "cluster-axis") * Math.PI * 2.0
        }
        val tx = cos(axisAngle)
        val ty = sin(axisAngle)
        val nx = -ty
        val ny = tx
        val localT = rhythmT(localIndex, localTotal, seed, rhythmSpacing)
        val centered = (localT - 0.5) * 2.0
        val radius = densityRadius(density, preserveSpace)
        val longSpan = radius * (1.45 + hash01(clusterIndex, seed, "cluster-long") * 0.95)
        val crossSpan = radius * (0.28 + hash01(clusterIndex, seed, "cluster-cross") * 0.32)
        val along = centered * longSpan + (hash01(i, seed, "cluster-along") - 0.5) * radius * 0.20
        val cross = (hash01(i, seed, "cluster-cross-jitter") - 0.5) * crossSpan * (1.25 - 0.45 * kotlin.math.abs(centered))
        val bend = sin(localT * Math.PI) * (hash01(clusterIndex, seed, "cluster-bend") - 0.5) * radius * 0.55
        val x = center.first + tx * along + nx * (cross + bend)
        val y = center.second + ty * along + ny * (cross + bend)
        return clamp01(x) to clamp01(y)
    }

    private fun densityRadius(density: String, preserveSpace: Boolean): Double {
        val base = when (density) {
            "low" -> 0.035
            "medium" -> 0.060
            "high" -> 0.085
            else -> 0.045
        }
        return base * if (preserveSpace) 0.85 else 1.0
    }

    private fun clamp01(value: Double): Double = value.coerceIn(0.0, 1.0)

    private fun pointsForRegular(ins: JSONObject, sides: Int, width: Double, height: Double): List<Pair<Double, Double>> {
        return ServerRendererGeometry.pointsForRegular(ins, sides, width, height)
    }

    private fun trianglePoints(ins: JSONObject, width: Double, height: Double): List<Pair<Double, Double>> {
        return ServerRendererGeometry.trianglePoints(ins, width, height)
    }

    private fun polygon(points: List<Pair<Double, Double>>, fill: String, common: String): String {
        val data = points.joinToString(" ") { "${it.first},${it.second}" }
        return """<polygon points="$data" fill="$fill" $common/>"""
    }

    private fun renderHandStroke(
        ins: JSONObject,
        attrs: SvgAttrs,
        x1: Double,
        y1: Double,
        x2: Double,
        y2: Double,
        weight: String,
        unit: Double,
        width: Double,
        height: Double,
        renderSeed: Long? = null
    ): String {
        val length = kotlin.math.hypot(x2 - x1, y2 - y1)
        val baseWidth = ServerRendererStyle.strokeWidth(weight, unit)
        val samples = ServerRendererGeometry.strokeSampleCount(length, unit)
        val seedStr = seedForInstruction(ins, renderSeed)
        val seedLong = seedStr.toULongOrNull()?.toLong() ?: 0L

        val stroke = ServerStrokeEngine.synthesizeStroke(
            start = Pair(x1, y1),
            end = Pair(x2, y2),
            baseWidth = baseWidth,
            weight = weight,
            seed = seedLong,
            samplesCount = samples
        )

        val groupClass = "stroke-engine-v1 controls-${stroke.samples.size} events-${stroke.eventCount}"
        val color = attrs.stroke
        val opacity = attrs.strokeOpacity

        val variation = ins.optJSONObject("variation")
        val outline = if (needsPathVariation(variation)) {
            val centerline = ServerRendererGeometry.variedLinePoints(x1, y1, x2, y2, variation, seedStr, ins, width, height, unit)
            val varied = ServerStrokeEngine.synthesizeStroke(
                start = Pair(x1, y1),
                end = Pair(x2, y2),
                baseWidth = baseWidth,
                weight = weight,
                seed = seedLong,
                samplesCount = centerline.size
            )
            ServerStrokeEngine.outlineForCenterline(centerline, varied.samples.map { it.width })
        } else {
            stroke.outline
        }

        val sb = StringBuilder()
        sb.append("""<g class="$groupClass">""")

        val pathD = ServerStrokeEngine.polygonPath(outline)
        val fillOpacityStr = fmt(opacity)
        sb.append("""<path d="$pathD" fill="$color" fill-opacity="$fillOpacityStr" stroke="none"/>""")

        if (weight in setOf("pencil", "crayon", "chalk", "brush_thin", "brush_thick")) {
            val mat = ServerRendererMaterial.lineGroup(ins, attrs, x1, y1, x2, y2, unit, includeBase = false)
            if (mat != null) {
                sb.append(mat)
            }
        }

        val style = ins.optString("style", "solid")
        if (style != "solid") {
            val styledWidth = kotlin.math.max(0.45 * (unit / 1000.0), baseWidth * 0.42)
            val styledAttrs = attrs.copy(strokeWidth = styledWidth, filter = null)
            val lineCommon = styledAttrs.toSvgAttributes(includeFill = false)
            sb.append("""<line x1="$x1" y1="$y1" x2="$x2" y2="$y2" fill="none" $lineCommon/>""")
        }

        if (weight == "drypoint") {
            val dx = x2 - x1
            val dy = y2 - y1
            val norm = kotlin.math.max(1e-6, kotlin.math.hypot(dx, dy))
            val nx = -dy / norm
            val ny = dx / norm
            val offset = stroke.burrSide * baseWidth
            val pointsStr = stroke.samples.joinToString(" ") { s ->
                "${fmt(s.x + nx * offset)},${fmt(s.y + ny * offset)}"
            }
            val burrWidth = fmt(baseWidth * 1.25)
            val burrOpacity = fmt(stroke.burrOpacity)
            sb.append("""<polyline points="$pointsStr" fill="none" stroke="$color" stroke-width="$burrWidth" stroke-opacity="$burrOpacity" stroke-linecap="round"/>""")
        }

        sb.append("</g>")
        return sb.toString()
    }

    private fun materialLineGroup(ins: JSONObject, attrs: SvgAttrs, x1: Double, y1: Double, x2: Double, y2: Double, unit: Double): String? {
        return ServerRendererMaterial.lineGroup(ins, attrs, x1, y1, x2, y2, unit)
    }

    private fun materialCircleOutline(ins: JSONObject, attrs: SvgAttrs, cx: Double, cy: Double, r: Double, unit: Double): String {
        return ServerRendererMaterial.circleOutline(ins, attrs, cx, cy, r, unit)
    }

    private fun materialEllipseOutline(ins: JSONObject, attrs: SvgAttrs, cx: Double, cy: Double, rx: Double, ry: Double, unit: Double): String {
        return ServerRendererMaterial.ellipseOutline(ins, attrs, cx, cy, rx, ry, unit)
    }

    private fun materialRectOutline(ins: JSONObject, attrs: SvgAttrs, x: Double, y: Double, w: Double, h: Double, unit: Double): String {
        return ServerRendererMaterial.rectOutline(ins, attrs, x, y, w, h, unit)
    }

    private fun materialArcOutline(ins: JSONObject, attrs: SvgAttrs, cx: Double, cy: Double, r: Double, start: Double, end: Double, unit: Double): String {
        return ServerRendererMaterial.arcOutline(ins, attrs, cx, cy, r, start, end, unit)
    }

    private fun usesMaterialOutline(weight: String): Boolean = ServerRendererMaterial.usesMaterialOutline(weight)

    private fun rotationCenter(ins: JSONObject, width: Double, height: Double, primitive: String): Pair<Double, Double> {
        return when (primitive) {
            "line" -> {
                val from = ins.optJSONArray("from")
                val to = ins.optJSONArray("to")
                val x = ((from?.optDouble(0, 0.1) ?: 0.1) + (to?.optDouble(0, 0.9) ?: 0.9)) / 2.0
                val y = ((from?.optDouble(1, 0.5) ?: 0.5) + (to?.optDouble(1, 0.5) ?: 0.5)) / 2.0
                px(x, width) to px(y, height)
            }
            "square", "triangle" -> {
                val pos = ins.optJSONArray("position")
                val size = ins.optJSONArray("size")
                val x = (pos?.optDouble(0, 0.35) ?: 0.35) + (size?.optDouble(0, 0.3) ?: 0.3) / 2.0
                val y = (pos?.optDouble(1, 0.35) ?: 0.35) + (size?.optDouble(1, 0.3) ?: 0.3) / 2.0
                px(x, width) to px(y, height)
            }
            else -> {
                val center = ins.optJSONArray("center")
                px(center?.optDouble(0, 0.5) ?: 0.5, width) to px(center?.optDouble(1, 0.5) ?: 0.5, height)
            }
        }
    }

    private fun applyRotation(element: String, ins: JSONObject, width: Double, height: Double, primitive: String): String {

        val rotation = ins.optDouble("rotation", 0.0)
        if (kotlin.math.abs(rotation) < 1e-9 || element.isBlank()) return element
        val center = rotationCenter(ins, width, height, primitive)
        return """<g transform="rotate($rotation ${center.first} ${center.second})">$element</g>"""
    }

    private fun renderPresenceLayer(score: JSONObject, colors: Map<String, String>, width: Double, height: Double): String {
        val presence = score.optJSONObject("presence") ?: return ""
        val kind = presence.optString("kind", "none")
        if (kind == "none") return ""
        val center = presence.optJSONArray("center")
        val cx = px(center?.optDouble(0, 0.52) ?: 0.52, width)
        val cy = px(center?.optDouble(1, 0.50) ?: 0.50, height)
        val unit = min(width, height)
        val color = colors["gray"] ?: "#888888"
        val dark = colors["black"] ?: "#111111"
        val visualLoad = score.optJSONArray("instructions")?.let { instructions ->
            (0 until instructions.length()).sumOf { i ->
                instructions.optJSONObject(i)?.optJSONObject("arrangement")?.optInt("count", 1) ?: 1
            }
        } ?: 1
        val loadOpacity = when {
            visualLoad >= 120 -> 0.52
            visualLoad >= 60 -> 0.70
            else -> 1.0
        }
        val intensity = presence.optString("intensity", "medium")
        val intensityOpacity = when (intensity) {
            "low" -> 0.13
            "high" -> 0.30
            else -> 0.21
        } * loadOpacity
        val gazeOpacity = when (presence.optString("gaze_pressure", "none")) {
            "low" -> 0.11
            "medium" -> 0.18
            "high" -> 0.26
            else -> 0.0
        } * loadOpacity
        val contourCount = when (presence.optString("contour_density", "low")) {
            "medium" -> 7
            "high" -> 11
            else -> 4
        }
        val radiusX = unit * when (intensity) {
            "low" -> 0.18
            "high" -> 0.30
            else -> 0.24
        }
        val radiusY = unit * when (intensity) {
            "low" -> 0.24
            "high" -> 0.40
            else -> 0.32
        }
        val stroke = max(1.2, unit * 0.003)
        val seed = score.toString()
        val phase = Math.PI * 2.0 * hash01(0, "$seed:presence-phase")
        val tilt = (hash01(1, "$seed:presence-tilt") - 0.5) * 1.2
        val out = StringBuilder()
        out.append("""<g id="presence_layer">""")
        when (presence.optString("symmetry", "none")) {
            "bilateral" -> {
                listOf(-1, 1, -1, 1).forEachIndexed { i, side ->
                    val yShift = (-0.36 + i * 0.24) * radiusY
                    val xOuter = side * radiusX * (0.34 + 0.10 * hash01(i, "$seed:sym-x"))
                    val xInner = side * radiusX * (0.10 + 0.08 * hash01(i, "$seed:sym-inner"))
                    out.append("""<line x1="${cx + xOuter}" y1="${cy + yShift - radiusY * 0.06}" x2="${cx + xInner}" y2="${cy + yShift + radiusY * (0.10 + tilt * 0.06)}" stroke="$color" stroke-width="$stroke" stroke-opacity="${intensityOpacity * 0.58}" stroke-linecap="round"/>""")
                }
            }
            "radial" -> {
                for (i in 0 until 6) {
                    val angle = phase + Math.PI * 2.0 * i / 6.0
                    val inner = radiusX * 0.28
                    val outer = radiusX * 0.86
                    out.append("""<line x1="${cx + cos(angle) * inner}" y1="${cy + sin(angle) * inner}" x2="${cx + cos(angle) * outer}" y2="${cy + sin(angle) * outer}" stroke="$color" stroke-width="$stroke" stroke-opacity="${intensityOpacity * 0.72}" stroke-linecap="round"/>""")
                }
            }
        }
        if (gazeOpacity > 0.0) {
            listOf(-1, 1, -1, 1, -1, 1).forEachIndexed { i, side ->
                val t = (i + 1).toDouble() / 7.0
                val angle = phase + side * (0.34 + 0.08 * i)
                val x1 = cx + cos(angle) * radiusX * (1.05 + 0.18 * (i % 2))
                val y1 = cy + sin(angle) * radiusY * (0.72 + 0.08 * i)
                val x2 = cx + cos(angle + Math.PI) * radiusX * 0.12
                val y2 = cy + (t - 0.5) * radiusY * 0.16
                out.append("""<line x1="$x1" y1="$y1" x2="$x2" y2="$y2" stroke="$dark" stroke-width="${stroke * 0.8}" stroke-opacity="$gazeOpacity" stroke-linecap="round"/>""")
            }
        }
        val flowAngle = phase * 0.35 + tilt
        val tx = cos(flowAngle)
        val ty = sin(flowAngle)
        val nx = -ty
        val ny = tx
        for (i in 0 until contourCount) {
            val t = (i + 0.5) / contourCount
            val along = (t - 0.5) * radiusX * (1.18 + 0.18 * hash01(i, "$seed:presence-flow-span"))
            var cross = sin(t * Math.PI * 1.7 + phase) * radiusY * 0.32
            cross += (hash01(i, "$seed:presence-flow-cross") - 0.5) * radiusY * 0.28
            val px = cx + tx * along + nx * cross
            val py = cy + ty * along + ny * cross
            val half = radiusX * (0.09 + 0.04 * hash01(i, "$seed:presence-flow-half"))
            val lift = radiusY * (0.05 + 0.04 * hash01(i, "$seed:presence-flow-lift"))
            val side = if (i % 2 == 0) 1.0 else -1.0
            val x1 = px - tx * half - nx * lift * side
            val y1 = py - ty * half - ny * lift * side
            val x2 = px + tx * half + nx * lift * side
            val y2 = py + ty * half + ny * lift * side
            val xm = px + nx * lift * side * 1.4
            val ym = py + ny * lift * side * 1.4
            out.append("""<path d="M $x1,$y1 Q $xm,$ym $x2,$y2" fill="none" stroke="$color" stroke-width="$stroke" stroke-opacity="${intensityOpacity * 0.82}" stroke-linecap="round"/>""")
        }
        if (kind == "group_like") {
            for (i in 0 until 7) {
                val t = (i - 3).toDouble() / 3.5
                val px = cx + tx * t * radiusX * 0.78 + nx * (hash01(i, "$seed:group-x") - 0.5) * radiusX * 0.20
                val py = cy + ty * t * radiusX * 0.78 + ny * (hash01(i, "$seed:group-y") - 0.5) * radiusY * 0.58
                out.append("""<circle cx="$px" cy="$py" r="${max(2.0, unit * 0.006)}" fill="$color" fill-opacity="${intensityOpacity * 0.72}"/>""")
            }
        } else if (kind == "creature_like") {
            for (i in 0 until 3) {
                val t = (i - 1) * 0.34
                out.append("""<line x1="${cx - radiusX * 0.30 + t * radiusX}" y1="${cy + radiusY * 0.32}" x2="${cx - radiusX * 0.05 + t * radiusX}" y2="${cy + radiusY * 0.44}" stroke="$color" stroke-width="$stroke" stroke-opacity="${intensityOpacity * 0.76}" stroke-linecap="round"/>""")
            }
        }
        out.append("</g>")
        return out.toString()
    }

    private fun strokeAttrs(primitive: String, weight: String, colorKey: String, colors: Map<String, String>, ins: JSONObject, unit: Double): SvgAttrs {
        return ServerRendererStyle.strokeAttrs(primitive, weight, colorKey, colors, ins, unit)
    }

    private fun outlineAttrs(attrs: SvgAttrs, strokeWidth: Double, opacity: Double, dash: String?): SvgAttrs {
        return ServerRendererStyle.outlineAttrs(attrs, strokeWidth, opacity, dash)
    }

    private fun strokeWidth(weight: String, unit: Double): Double {
        return ServerRendererStyle.strokeWidth(weight, unit)
    }

    private fun strokeOpacity(weight: String): Double = when (weight) {
        else -> ServerRendererStyle.strokeOpacity(weight)
    }

    private fun lineCap(weight: String): String = when (weight) {
        else -> ServerRendererStyle.lineCap(weight)
    }

    private fun dashStyle(style: String): String = when (style) {
        else -> ServerRendererStyle.dashStyle(style)
    }

    private fun dashValue(style: String): String? = when (style) {
        else -> ServerRendererStyle.dashValue(style)
    }

    private fun textureDash(weight: String): String? = when (weight) {
        else -> ServerRendererStyle.textureDash(weight)
    }

    private fun textureWeights(instructions: JSONArray): Set<String> {
        return ServerRendererStyle.textureWeights(instructions)
    }

    private fun filterAttr(weight: String, variation: JSONObject?): String {
        return ServerRendererStyle.filterAttr(weight, variation)
    }

    private fun textureFilterDefs(weights: Set<String>, unit: Double): String = buildString {
        append(ServerRendererStyle.textureFilterDefs(weights, unit))
    }

    private fun blurFilterDefs(neededBlurs: Map<String, Double>): String {
        return ServerRendererStyle.blurFilterDefs(neededBlurs)
    }

    private fun blurFilterId(variation: JSONObject?, ins: JSONObject, width: Double, height: Double, unit: Double): String? {
        return ServerRendererStyle.blurFilterId(variation, ins, width, height, unit)
    }

    private fun needsPathVariation(variation: JSONObject?): Boolean {
        return ServerRendererGeometry.needsPathVariation(variation)
    }

    private fun variedLinePoints(x1: Double, y1: Double, x2: Double, y2: Double, variation: JSONObject?, seed: String, ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        return ServerRendererGeometry.variedLinePoints(x1, y1, x2, y2, variation, seed, ins, width, height, unit)
    }



    private fun px(value: Double, scale: Double): Double = value * scale

    private fun fmt(value: Double): String = ServerRendererGeometry.fmt(value)

    private fun signedHash(i: Int, seed: String): Double = ServerRendererGeometry.signedHash(i, seed)

    private fun String.containsAny(vararg markers: String): Boolean = markers.any { contains(it) }

    private fun hash01(i: Int, seed: String): Double {
        return ServerRendererGeometry.hash01(i, seed)
    }

    private fun hash01(i: Int, seed: String, salt: String): Double {
        val digest = sha256Bytes("$seed:$salt:$i")
        return uint32Le(digest, 0).toDouble() / 0xffffffffL.toDouble()
    }

    private fun seedForInstruction(ins: JSONObject, renderSeed: Long? = null): String {
        val base = serverInstructionJson(ins)
        val key = if (renderSeed != null) "$base:render:$renderSeed" else base
        return uint64Le(sha256Bytes(key), 0).toString()
    }

    private fun seedForCluster(seed: String): String = ((seed.toULongOrNull() ?: 0UL) xor 0xC1A57UL).toString()

    private fun sha256Bytes(value: String): ByteArray = MessageDigest.getInstance("SHA-256").digest(value.toByteArray())

    private fun uint32Le(bytes: ByteArray, offset: Int): Long {
        return ((bytes[offset].toLong() and 0xffL)) or
            ((bytes[offset + 1].toLong() and 0xffL) shl 8) or
            ((bytes[offset + 2].toLong() and 0xffL) shl 16) or
            ((bytes[offset + 3].toLong() and 0xffL) shl 24)
    }

    private fun uint64Le(bytes: ByteArray, offset: Int): ULong {
        var value = 0UL
        for (i in 0 until 8) {
            value = value or ((bytes[offset + i].toULong() and 0xffUL) shl (8 * i))
        }
        return value
    }

    private fun serverInstructionJson(ins: JSONObject): String {
        return buildString {
            append("{")
            append("\"primitive\":"); append(jsonString(ins.optString("primitive", "line")))
            append(",\"from_\":"); append(coordJson(ins.optJSONArray("from")))
            append(",\"to\":"); append(coordJson(ins.optJSONArray("to")))
            append(",\"center\":"); append(coordJson(ins.optJSONArray("center")))
            append(",\"radius\":"); append(numberOrNull(ins, "radius"))
            append(",\"sides\":"); append(intOrNull(ins, "sides"))
            append(",\"position\":"); append(coordJson(ins.optJSONArray("position")))
            append(",\"size\":"); append(coordJson(ins.optJSONArray("size")))
            append(",\"angle_start\":"); append(numberOrNull(ins, "angle_start"))
            append(",\"angle_end\":"); append(numberOrNull(ins, "angle_end"))
            append(",\"rotation\":"); append(numberOrNull(ins, "rotation"))
            append(",\"filled\":"); append(ins.optBoolean("filled", false))
            append(",\"style\":"); append(jsonString(ins.optString("style", "solid")))
            append(",\"weight\":"); append(jsonString(ins.optString("weight", "pen")))
            append(",\"color\":"); append(jsonString(ins.optString("color", "black")))
            append(",\"color_hint\":"); append(stringOrNull(ins, "color_hint"))
            append(",\"variation\":"); append(variationJson(ins, ins.optJSONObject("variation")))
            append(",\"arrangement\":"); append(arrangementJson(ins.optJSONObject("arrangement")))
            append(",\"at\":null")
            append(",\"relation\":null")
            append(",\"surface\":null")
            append("}")
        }
    }

    private fun arrangementJson(arr: JSONObject?): String {
        if (arr == null) return "null"
        return buildString {
            append("{")
            append("\"count\":"); append(arr.optInt("count", 1).coerceIn(1, 1000))
            append(",\"layout\":"); append(jsonString(arr.optString("layout", "horizontal")))
            append(",\"path\":"); append(jsonString(arr.optString("path", "none")))
            append(",\"color_cycle\":"); append(stringArrayJson(arr.optJSONArray("color_cycle")))
            append(",\"margin\":"); append(doubleJson(arr.optDouble("margin", 0.1)))
            append(",\"center\":"); append(coordJson(arr.optJSONArray("center")))
            append(",\"radius\":"); append(numberOrNull(arr, "radius"))
            append(",\"density\":"); append(jsonString(arr.optString("density", "none")))
            append(",\"cluster_count\":"); append(intOrNull(arr, "cluster_count"))
            append(",\"fade\":"); append(jsonString(arr.optString("fade", "none")))
            append(",\"preserve_space\":"); append(arr.optBoolean("preserve_space", false))
            append(",\"rhythm_spacing\":"); append(jsonString(arr.optString("rhythm_spacing", "none")))
            append("}")
        }
    }

    private fun variationJson(ins: JSONObject, variation: JSONObject?): String {
        if (variation == null) return "null"
        val primitive = ins.optString("primitive", "line")
        if (primitive == "line" && !needsPathVariation(variation)) return "null"
        return buildString {
            append("{")
            append("\"amplitude\":"); append(jsonString(variation.optString("amplitude", "medium")))
            append(",\"frequency\":"); append(jsonString(variation.optString("frequency", "medium")))
            append(",\"quality\":"); append(jsonString(variation.optString("quality", "none")))
            append(",\"dimensions\":"); append(stringArrayJson(variation.optJSONArray("dimensions")))
            append("}")
        }
    }

    private fun coordJson(array: JSONArray?): String {
        if (array == null) return "null"
        return "[${doubleJson(array.optDouble(0, 0.0))},${doubleJson(array.optDouble(1, 0.0))}]"
    }

    private fun stringArrayJson(array: JSONArray?): String {
        if (array == null || array.length() == 0) return "[]"
        return (0 until array.length()).joinToString(prefix = "[", postfix = "]", separator = ",") { jsonString(array.optString(it)) }
    }

    private fun stringOrNull(obj: JSONObject, key: String): String = if (obj.has(key) && !obj.isNull(key)) jsonString(obj.optString(key)) else "null"

    private fun numberOrNull(obj: JSONObject, key: String): String = if (obj.has(key) && !obj.isNull(key)) doubleJson(obj.optDouble(key)) else "null"

    private fun intOrNull(obj: JSONObject, key: String): String = if (obj.has(key) && !obj.isNull(key)) obj.optInt(key).toString() else "null"

    private fun doubleJson(value: Double): String {
        if (!value.isFinite()) return "0.0"
        val text = java.math.BigDecimal.valueOf(value).stripTrailingZeros().toPlainString()
        return if ("." in text) text else "$text.0"
    }

    private fun jsonString(value: String): String = JSONObject.quote(value)

    private fun sha256(value: String): String {
        return MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString("") { "%02x".format(it) }
    }
}
