package app.inku.mobile.render

import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.CanvasSize
import app.inku.mobile.data.model.ColorCatalog
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.pipeline.RenderRequest
import app.inku.mobile.pipeline.ServerScoreCompat
import java.security.MessageDigest
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt
import kotlin.math.sin
import org.json.JSONArray
import org.json.JSONObject

internal const val FILL_DAB_SAMPLES = 5
internal const val FILL_DAB_MIN_TRAVEL = 0.90
internal const val FRAME_LO = 0.02
internal const val FRAME_HI = 0.98

class DefaultSvgRenderer(
    private val catalogResolver: (String?) -> ColorCatalog = ColorCatalogs::get,
) : SvgRenderer {
    override fun render(request: RenderRequest): RenderResult {
        // Saved works carry retired tool names. Migrate before anything reads `weight`,
        // the way the server's Instruction validator does on the way in.
        val score = ServerScoreCompat.migrateScore(JSONObject(request.scoreJson))
        val canvas = CanvasAspects.sizeFor(request.canvasAspect.ifBlank { score.optString("canvas", "square") })
        val catalog = catalogResolver(request.colorCatalogId)
        val snapshot = request.workColorSnapshot
        val colorMap = snapshot?.colorMap ?: catalog.renderMap
        val catalogId = snapshot?.catalogId ?: catalog.id
        val recordedCatalog = snapshot?.let { ColorCatalogs.find(it.catalogId) }
        val catalogName = snapshot?.catalogName?.takeIf { it.isNotEmpty() }
            ?: recordedCatalog?.name
            ?: catalogId
        val catalogSub = snapshot?.catalogSub?.takeIf { it.isNotEmpty() }
            ?: recordedCatalog?.sub
            ?: ""
        // The request decides; the Score is the fallback.
        //
        // The server takes the seed as an argument
        // (`renderer.render(..., render_seed=...)`) and its `Score` has no such
        // field at all, so reading one off the Score is this client's own. It
        // stays because it is how the frozen reference corpus hands the seed
        // over: `gen_android_reference.py` writes `render_seed` into the Score
        // of every baked case, and that generator belongs to the server. Moving
        // the fixtures onto the argument is a change to the generator, not to
        // this file.
        val renderSeed = request.renderSeed
            ?: if (score.has("render_seed") && !score.isNull("render_seed")) score.optLong("render_seed") else null
        val cmap = ServerRendererStyle.DEFAULT_COLOR_MAP + colorMap
        val assignment = ServerRendererStyle.computeColorAssignment(
            catalogMap = colorMap,
            renderSeed = renderSeed,
            catalogId = catalogId
        )
        val colors = cmap + assignment
        val bgKey = score.optString("background", "white")
        val background = assignment[bgKey] ?: colors[bgKey] ?: "#ffffff"
        val instructions = score.optJSONArray("instructions") ?: JSONArray()
        val wild = score.optBoolean("render_wild", score.optBoolean("wild", false))
        val width = canvas.width.toDouble()
        val height = canvas.height.toDouble()
        val unit = min(width, height)
        val body = StringBuilder()
        val textureWeights = textureWeights(instructions)
        val neededBlurs = mutableMapOf<String, Double>()

        // Placement is the composition seed's, the touch stays the performance
        // seed's (engine 23). Read with `is null` and never with `?:` on the
        // value: 0 is a seed a caller can legitimately state. Without a
        // composition seed the placement falls back to the performance seed, so
        // every drawing made before this split replays.
        val compositionSeed = request.compositionSeed
            ?: if (score.has("composition_seed") && !score.isNull("composition_seed")) {
                score.optLong("composition_seed")
            } else {
                null
            }
        val placementSeed = if (compositionSeed != null) compositionSeed else renderSeed

        val compositeInstructions = expandCompositeGroups(
            instructions,
            placementSeed,
            renderSeed,
            canvas,
        )
        val resolvedInstructions = resolvePerformanceScore(compositeInstructions, renderSeed, canvas)
        val structured = request.svgProfile == "editable"
        body.append("""<rect x="0" y="0" width="${canvas.width}" height="${canvas.height}" fill="$background"/>""")
        body.append("""<g clip-path="url(#canvas-clip)">""")
        for (i in 0 until resolvedInstructions.length()) {
            val instruction = resolvedInstructions.optJSONObject(i) ?: continue
            val primitive = instruction.optString("primitive", "line")
            val colorKey = instruction.optString("color", "black")
            val weight = instruction.optString("weight", "pen")
            val insId = "instruction_${"%03d".format(i)}_${primitive}_${colorKey}_${weight}"
            val expanded = expandArrangement(instruction, placementSeed, canvas, renderSeed)
            val insSb = StringBuilder()
            for ((index, mark) in expanded.withIndex()) {
                val markId = "mark_${"%03d".format(i)}_${"%03d".format(index)}_${primitive}"
                var elem = renderInstruction(mark, colors, width, height, unit, neededBlurs, i, renderSeed, wild, index)
                if (structured && elem.startsWith("<g ")) {
                    elem = elem.replaceFirst(">", """ id="$markId">""")
                } else if (structured && elem.startsWith("<path ")) {
                    elem = elem.replaceFirst(">", """ id="$markId">""")
                }
                insSb.append(elem)
            }
            if (structured) {
                body.append("""<g id="$insId">$insSb</g>""")
            } else {
                body.append(insSb)
            }
        }
        body.append(renderPresenceLayer(score, colors, width, height))
        body.append("</g>")

        val rawSvg = buildString {
            append("""<svg xmlns="http://www.w3.org/2000/svg" width="${canvas.width}" height="${canvas.height}" viewBox="0 0 ${canvas.width} ${canvas.height}">""")
            append("<defs>")
            if (request.svgProfile == "display") {
                append("""<clipPath id="canvas-clip"><rect x="0" y="0" width="${canvas.width}" height="${canvas.height}"/></clipPath>""")
            }
            append(textureFilterDefs(textureWeights, unit))
            append(blurFilterDefs(neededBlurs))
            append("</defs>")
            append(body)
            append("</svg>")
        }
        val svg = applyMasterGrid(rawSvg)
        val metadata = JSONObject()
            .put("render_engine_id", CompatibilityConstants.renderEngineId)
            .put("render_engine_version", CompatibilityConstants.renderEngineVersion)
            .put("render_canvas_aspect", CanvasAspects.normalize(request.canvasAspect))
            .put("render_canvas_aspect_id", CanvasAspects.normalize(request.canvasAspect))
            .put("render_canvas_aspect_ratio", CanvasAspects.ratioFor(request.canvasAspect))
            .put("render_color_catalog_id", catalogId)
            .put("render_color_catalog_name", if (snapshot == null) catalog.name else catalogName)
            .put("render_color_catalog_sub", if (snapshot == null) catalog.sub else catalogSub)
            .put("render_color_profile", JSONObject().put("id", "srgb").put("name", "sRGB IEC61966-2.1").put("standard", "IEC 61966-2-1:1999"))
            .put("render_color_map", JSONObject(colorMap))
        val hash = sha256(svg + metadata.toString())
        return RenderResult(svg = svg, metadataJson = metadata.put("render_hash", hash).toString(), renderHash = hash)
    }

    private fun renderInstruction(ins: JSONObject, colors: Map<String, String>, width: Double, height: Double, unit: Double, neededBlurs: MutableMap<String, Double>, index: Int = 0, renderSeed: Long? = null, wild: Boolean = false, markIndex: Int = 0): String {
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
                    renderHandStroke(ins, attrs, x1, y1, x2, y2, weight, unit, width, height, renderSeed, wild)
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
                if (usesHandStroke(weight)) {
                    val contour = if (variation != null && needsPathVariation(variation)) {
                        ServerRendererGeometry.variedCirclePoints(cx, cy, r, r, variation, seedForInstruction(ins, renderSeed), ins, width, height, unit)
                    } else {
                        val count = ServerRendererGeometry.strokeSampleCount(2.0 * Math.PI * r, unit)
                        ServerRendererGeometry.circlePoints(cx, cy, r, r, count)
                    }
                    val (fillGroup, regionFill) = interiorFill(ins, attrs, contour, unit, renderSeed, wild)
                    val bodyPts = if (needsPathVariation(variation)) contour else emptyList()
                    val body = renderBodyShape("circle", ins, attrs, regionFill, cx, cy, r, r, 0.0, 0.0, 0.0, 0.0, bodyPts)
                    val surfaceGroup = renderSurfaceVectors(ins, attrs, colors, width, height, unit, renderSeed, wild)
                    val (band, performed) = renderContourHandStroke(ins, attrs, contour, emptySet(), unit, width, height, renderSeed, wild)
                    val outline = if (usesMaterialOutline(weight)) {
                        // engine 28: every drawing rides the ink, not only the wild ones.
                        // While this was gated on wild, the strata sat on the ideal geometry
                        // and the ink wandered out from under them -- a dashed ghost beside
                        // the mark. The geometric helper below stays as a guard: every tool
                        // that owns a material layer is a hand-stroke tool, so `performed` is
                        // never empty where it is reached.
                        if (performed.isNotEmpty()) {
                            ServerRendererMaterial.performedOutline(ins, attrs, performed, unit, closed = true, pathLenPx = 2.0 * Math.PI * r, center = cx to cy, renderSeed = renderSeed, instructionSeed = seedForInstruction(ins, renderSeed))
                        } else {
                            materialCircleOutline(ins, attrs, cx, cy, r, unit)
                        }
                    } else ""
                    val fg = fillGroup ?: ""
                    """<g>$body$fg$band$outline$surfaceGroup</g>"""
                } else {
                    val regionFill = if (ins.has("surface") && !ins.isNull("surface")) false else ins.optBoolean("filled", false)
                    val base = if (needsPathVariation(variation)) {
                        val pts = ServerRendererGeometry.variedCirclePoints(cx, cy, r, r, variation, seedForInstruction(ins, renderSeed), ins, width, height, unit)
                            .joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
                        """<polygon points="$pts" fill="$fill" $common/>"""
                    } else {
                        """<circle cx="$cx" cy="$cy" r="$r" fill="$fill" $common/>"""
                    }
                    val surfaceGroup = renderSurfaceVectors(ins, attrs, colors, width, height, unit, renderSeed, wild)
                    val outline = if (usesMaterialOutline(weight)) materialCircleOutline(ins, attrs, cx, cy, r, unit) else ""
                    if (surfaceGroup.isNotEmpty() || usesMaterialOutline(weight)) """<g>$base$outline$surfaceGroup</g>""" else base
                }
            }
            "ellipse" -> {
                val center = ins.optJSONArray("center")
                val size = ins.optJSONArray("size")
                val cx = px(center?.optDouble(0, 0.5) ?: 0.5, width)
                val cy = px(center?.optDouble(1, 0.5) ?: 0.5, height)
                val (sizeW, sizeH) = ServerRendererGeometry.sizePx(size?.optDouble(0, 0.26) ?: 0.26, size?.optDouble(1, 0.16) ?: 0.16, width, height, unit)
                val rx = sizeW / 2.0
                val ry = sizeH / 2.0
                val variation = ins.optJSONObject("variation")
                if (usesHandStroke(weight)) {
                    val approxPerimeter = Math.PI * (3.0 * (rx + ry) - sqrt((3.0 * rx + ry) * (rx + 3.0 * ry)))
                    val contour = if (variation != null && needsPathVariation(variation)) {
                        ServerRendererGeometry.variedCirclePoints(cx, cy, rx, ry, variation, seedForInstruction(ins, renderSeed), ins, width, height, unit)
                    } else {
                        val count = ServerRendererGeometry.strokeSampleCount(approxPerimeter, unit)
                        ServerRendererGeometry.circlePoints(cx, cy, rx, ry, count)
                    }
                    val (fillGroup, regionFill) = interiorFill(ins, attrs, contour, unit, renderSeed, wild)
                    val bodyPts = if (needsPathVariation(variation)) contour else emptyList()
                    val body = renderBodyShape("ellipse", ins, attrs, regionFill, cx, cy, rx, ry, 0.0, 0.0, 0.0, 0.0, bodyPts)
                    val surfaceGroup = renderSurfaceVectors(ins, attrs, colors, width, height, unit, renderSeed, wild)
                    val (band, performed) = renderContourHandStroke(ins, attrs, contour, emptySet(), unit, width, height, renderSeed, wild)
                    val outline = if (usesMaterialOutline(weight)) {
                        // engine 28: every drawing rides the ink, not only the wild ones.
                        // While this was gated on wild, the strata sat on the ideal geometry
                        // and the ink wandered out from under them -- a dashed ghost beside
                        // the mark. The geometric helper below stays as a guard: every tool
                        // that owns a material layer is a hand-stroke tool, so `performed` is
                        // never empty where it is reached.
                        if (performed.isNotEmpty()) {
                            ServerRendererMaterial.performedOutline(ins, attrs, performed, unit, closed = true, pathLenPx = approxPerimeter, center = cx to cy, renderSeed = renderSeed, instructionSeed = seedForInstruction(ins, renderSeed))
                        } else {
                            materialEllipseOutline(ins, attrs, cx, cy, rx, ry, unit)
                        }
                    } else ""
                    val fg = fillGroup ?: ""
                    """<g>$body$fg$band$outline$surfaceGroup</g>"""
                } else {
                    val base = if (needsPathVariation(variation)) {
                        val pts = ServerRendererGeometry.variedCirclePoints(cx, cy, rx, ry, variation, seedForInstruction(ins, renderSeed), ins, width, height, unit)
                            .joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
                        """<polygon points="$pts" fill="$fill" $common/>"""
                    } else {
                        """<ellipse cx="$cx" cy="$cy" rx="$rx" ry="$ry" fill="$fill" $common/>"""
                    }
                    val surfaceGroup = renderSurfaceVectors(ins, attrs, colors, width, height, unit, renderSeed, wild)
                    val outline = if (usesMaterialOutline(weight)) materialEllipseOutline(ins, attrs, cx, cy, rx, ry, unit) else ""
                    if (surfaceGroup.isNotEmpty() || usesMaterialOutline(weight)) """<g>$base$outline$surfaceGroup</g>""" else base
                }
            }
            "square" -> {
                val pos = ins.optJSONArray("position")
                val size = ins.optJSONArray("size")
                val x = px(pos?.optDouble(0, 0.38) ?: 0.38, width)
                val y = px(pos?.optDouble(1, 0.38) ?: 0.38, height)
                val (w, h) = ServerRendererGeometry.sizePx(size?.optDouble(0, 0.24) ?: 0.24, size?.optDouble(1, 0.24) ?: 0.24, width, height, unit)
                val variation = ins.optJSONObject("variation")
                val corners = listOf(x to y, (x + w) to y, (x + w) to (y + h), x to (y + h))
                if (usesHandStroke(weight)) {
                    val seedStr = seedForInstruction(ins, renderSeed)
                    val (contour, anchors) = edgeContourWithAnchors(corners, variation, seedStr, ins, width, height, unit)
                    val fillContour = if (needsPathVariation(variation)) {
                        val rectPts = ServerRendererGeometry.rectPoints(x, y, w, h, 80)
                        ServerRendererGeometry.variedPolygonPoints(rectPts, variation, seedStr, x + w / 2.0, y + h / 2.0, ins, width, height, unit)
                    } else {
                        corners
                    }
                    val (fillGroup, regionFill) = interiorFill(ins, attrs, fillContour, unit, renderSeed, wild)
                    val bodyPts = if (needsPathVariation(variation)) fillContour else emptyList()
                    val body = renderBodyShape("square", ins, attrs, regionFill, 0.0, 0.0, 0.0, 0.0, x, y, w, h, bodyPts)
                    val surfaceGroup = renderSurfaceVectors(ins, attrs, colors, width, height, unit, renderSeed, wild)
                    val (band, performed) = renderContourHandStroke(ins, attrs, contour, anchors, unit, width, height, renderSeed, wild)
                    val outline = if (usesMaterialOutline(weight)) {
                        // engine 28: every drawing rides the ink, not only the wild ones.
                        // While this was gated on wild, the strata sat on the ideal geometry
                        // and the ink wandered out from under them -- a dashed ghost beside
                        // the mark. The geometric helper below stays as a guard: every tool
                        // that owns a material layer is a hand-stroke tool, so `performed` is
                        // never empty where it is reached.
                        if (performed.isNotEmpty()) {
                            ServerRendererMaterial.performedOutline(ins, attrs, performed, unit, closed = true, pathLenPx = 2.0 * (w + h), center = (x + w / 2.0) to (y + h / 2.0), renderSeed = renderSeed, instructionSeed = seedForInstruction(ins, renderSeed))
                        } else {
                            materialRectOutline(ins, attrs, x, y, w, h, unit)
                        }
                    } else ""
                    val fg = fillGroup ?: ""
                    """<g>$body$fg$band$outline$surfaceGroup</g>"""
                } else {
                    val base = if (needsPathVariation(variation)) {
                        val rectPts = ServerRendererGeometry.rectPoints(x, y, w, h, 80)
                        val pts = ServerRendererGeometry.variedPolygonPoints(rectPts, variation, seedForInstruction(ins, renderSeed), x + w / 2.0, y + h / 2.0, ins, width, height, unit)
                            .joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
                        """<polygon points="$pts" fill="$fill" $common/>"""
                    } else {
                        """<rect x="$x" y="$y" width="$w" height="$h" fill="$fill" $common/>"""
                    }
                    val surfaceGroup = renderSurfaceVectors(ins, attrs, colors, width, height, unit, renderSeed, wild)
                    val outline = if (usesMaterialOutline(weight)) materialRectOutline(ins, attrs, x, y, w, h, unit) else ""
                    if (surfaceGroup.isNotEmpty() || usesMaterialOutline(weight)) """<g>$base$outline$surfaceGroup</g>""" else base
                }
            }
            "triangle" -> {
                val points = trianglePoints(ins, width, height, unit)
                val variation = ins.optJSONObject("variation")
                if (usesHandStroke(weight)) {
                    val seedStr = seedForInstruction(ins, renderSeed)
                    val (contour, anchors) = edgeContourWithAnchors(points, variation, seedStr, ins, width, height, unit)
                    val pos = ins.optJSONArray("position")
                    val size = ins.optJSONArray("size")
                    val cx = px((pos?.optDouble(0, 0.35) ?: 0.35) + (size?.optDouble(0, 0.30) ?: 0.30) / 2.0, width)
                    val cy = px((pos?.optDouble(1, 0.35) ?: 0.35) + (size?.optDouble(1, 0.30) ?: 0.30) / 2.0, height)
                    val fillContour = if (needsPathVariation(variation)) {
                        ServerRendererGeometry.variedPolygonPoints(points, variation, seedStr, cx, cy, ins, width, height, unit)
                    } else {
                        points
                    }
                    val (fillGroup, regionFill) = interiorFill(ins, attrs, fillContour, unit, renderSeed, wild)
                    val bodyPts = if (needsPathVariation(variation)) fillContour else points
                    val body = renderBodyShape("polygon", ins, attrs, regionFill, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, bodyPts)
                    val surfaceGroup = renderSurfaceVectors(ins, attrs, colors, width, height, unit, renderSeed, wild)
                    val (band, performed) = renderContourHandStroke(ins, attrs, contour, anchors, unit, width, height, renderSeed, wild)
                    // engine 15: this function had no material-outline call at all, so triangle
                    // and polygon were the only closed figures left bare across all five tools
                    // that own a material layer. There is no analytic outline helper for a shape
                    // with arbitrary corners, so the strata are drawn from the performed
                    // centreline, wild or not - nothing frozen is being preserved here.
                    val outline = if (usesMaterialOutline(weight) && performed.isNotEmpty()) {
                        ServerRendererMaterial.performedOutline(
                            ins, attrs, performed, unit,
                            closed = true,
                            pathLenPx = closedPathLength(performed),
                            center = pointsCenter(bodyPts),
                            renderSeed = renderSeed,
                            instructionSeed = seedForInstruction(ins, renderSeed)
                        )
                    } else ""
                    val fg = fillGroup ?: ""
                    """<g>$body$fg$band$outline$surfaceGroup</g>"""
                } else {
                    val pts = if (needsPathVariation(variation)) {
                        val pos = ins.optJSONArray("position")
                        val size = ins.optJSONArray("size")
                        val cx = px((pos?.optDouble(0, 0.35) ?: 0.35) + (size?.optDouble(0, 0.30) ?: 0.30) / 2.0, width)
                        val cy = px((pos?.optDouble(1, 0.35) ?: 0.35) + (size?.optDouble(1, 0.30) ?: 0.30) / 2.0, height)
                        ServerRendererGeometry.variedPolygonPoints(points, variation, seedForInstruction(ins, renderSeed), cx, cy, ins, width, height, unit)
                    } else {
                        points
                    }
                    val base = polygon(pts, fill, common)
                    val surfaceGroup = renderSurfaceVectors(ins, attrs, colors, width, height, unit, renderSeed, wild)
                    if (surfaceGroup.isNotEmpty()) """<g>$base$surfaceGroup</g>""" else base
                }
            }
            "polygon" -> {
                val rawPoints = pointsForRegular(ins, ins.optInt("sides", 5).coerceIn(5, 8), width, height)
                val variation = ins.optJSONObject("variation")
                val center = ins.optJSONArray("center")
                val position = ins.optJSONArray("position")
                val size = ins.optJSONArray("size")
                val cx = px(center?.optDouble(0) ?: ((position?.optDouble(0, 0.4) ?: 0.4) + (size?.optDouble(0, 0.2) ?: 0.2) / 2.0), width)
                val cy = px(center?.optDouble(1) ?: ((position?.optDouble(1, 0.4) ?: 0.4) + (size?.optDouble(1, 0.2) ?: 0.2) / 2.0), height)
                if (usesHandStroke(weight)) {
                    val seedStr = seedForInstruction(ins, renderSeed)
                    val (contour, anchors) = edgeContourWithAnchors(rawPoints, variation, seedStr, ins, width, height, unit)
                    val fillContour = if (needsPathVariation(variation)) {
                        ServerRendererGeometry.variedPolygonPoints(rawPoints, variation, seedStr, cx, cy, ins, width, height, unit)
                    } else {
                        rawPoints
                    }
                    val (fillGroup, regionFill) = interiorFill(ins, attrs, fillContour, unit, renderSeed, wild)
                    val bodyPts = if (needsPathVariation(variation)) fillContour else rawPoints
                    val body = renderBodyShape("polygon", ins, attrs, regionFill, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, bodyPts)
                    val surfaceGroup = renderSurfaceVectors(ins, attrs, colors, width, height, unit, renderSeed, wild)
                    val (band, performed) = renderContourHandStroke(ins, attrs, contour, anchors, unit, width, height, renderSeed, wild)
                    // engine 15: this function had no material-outline call at all, so triangle
                    // and polygon were the only closed figures left bare across all five tools
                    // that own a material layer. There is no analytic outline helper for a shape
                    // with arbitrary corners, so the strata are drawn from the performed
                    // centreline, wild or not - nothing frozen is being preserved here.
                    val outline = if (usesMaterialOutline(weight) && performed.isNotEmpty()) {
                        ServerRendererMaterial.performedOutline(
                            ins, attrs, performed, unit,
                            closed = true,
                            pathLenPx = closedPathLength(performed),
                            center = pointsCenter(bodyPts),
                            renderSeed = renderSeed,
                            instructionSeed = seedForInstruction(ins, renderSeed)
                        )
                    } else ""
                    val fg = fillGroup ?: ""
                    """<g>$body$fg$band$outline$surfaceGroup</g>"""
                } else {
                    val pts = if (needsPathVariation(variation)) {
                        ServerRendererGeometry.variedPolygonPoints(rawPoints, variation, seedForInstruction(ins, renderSeed), cx, cy, ins, width, height, unit)
                    } else {
                        rawPoints
                    }
                    val base = polygon(pts, fill, common)
                    val surfaceGroup = renderSurfaceVectors(ins, attrs, colors, width, height, unit, renderSeed, wild)
                    if (surfaceGroup.isNotEmpty()) """<g>$base$surfaceGroup</g>""" else base
                }
            }
            "arc" -> {
                val center = ins.optJSONArray("center")
                val cx = px(center?.optDouble(0, 0.5) ?: 0.5, width)
                val cy = px(center?.optDouble(1, 0.5) ?: 0.5, height)
                val r = px(ins.optDouble("radius", 0.18), min(width, height))
                val start = ins.optDouble("angle_start", 20.0)
                val end = ins.optDouble("angle_end", 300.0)
                if (usesHandStroke(weight)) {
                    renderArcHandStroke(ins, attrs, cx, cy, r, start, end, unit, width, height, renderSeed, wild)
                } else {
                    val variation = ins.optJSONObject("variation")
                    val path = ServerRendererGeometry.variedArcPathD(cx, cy, r, start, end, variation, seedForInstruction(ins, renderSeed), ins, width, height, unit)
                    val base = """<path d="$path" fill="none" $common/>"""
                    val outline = if (usesMaterialOutline(weight)) materialArcOutline(ins, attrs, cx, cy, r, start, end, unit) else ""
                    if (outline.isNotEmpty()) """<g>$base$outline</g>""" else base
                }
            }
            "cloudform" -> {
                val center = ins.optJSONArray("center")
                val size = ins.optJSONArray("size")
                val cx = px(center?.optDouble(0, 0.5) ?: 0.5, width)
                val cy = px(center?.optDouble(1, 0.5) ?: 0.5, height)
                val (sw, sh) = ServerRendererGeometry.sizePx(size?.optDouble(0, 0.5) ?: 0.5, size?.optDouble(1, 0.34) ?: 0.34, width, height, unit)
                val contour = ServerRendererGeometry.generateCloudformContour(
                    center = cx to cy,
                    size = sw to sh,
                    performanceSeed = seedForInstruction(ins, renderSeed),
                    instructionIndex = index,
                    // The member's own place in the expanded group. Zero here
                    // drew every member of a group with the first one's blob;
                    // the server passes `mark_idx` on this path and 0 only on
                    // the three that resolve a relation. No case reached it
                    // until a group was something other than a circle.
                    markIndex = markIndex,
                    variation = ins.optJSONObject("variation"),
                    weight = weight,
                    pointCount = 49
                )
                // engine 15: the cloudform handed its Catmull-Rom path straight to the
                // document, so it had never once entered the stroke engine - while its class
                // claimed stroke-engine-touch, which was false. The dense polyline the
                // interior fill already samples now goes down the same road square, circle
                // and polygon take, so all three material mechanisms and the wild toggle
                // arrive together. The contour generator itself is untouched.
                val sampled = ServerRendererGeometry.sampleClosedCatmullRom(contour.points)
                val (fillGroup, regionFill) = interiorFill(ins, attrs, sampled, unit, renderSeed, wild)
                val hand = usesHandStroke(weight)
                // The class names only what is true: rotring stays geometric.
                val classAttr = "cloudform contour-v1" + (if (hand) " stroke-engine-touch" else "")
                val pathStr = when {
                    hand -> renderBodyShape("cloudform", ins, attrs, regionFill, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, emptyList(), pathD = contour.pathD, classAttr = classAttr)
                    fillGroup != null -> """<path class="$classAttr" d="${contour.pathD}" fill="none" $common/>"""
                    else -> """<path class="$classAttr" d="${contour.pathD}" fill="$fill" $common/>"""
                }
                if (fillGroup == null && !hand) {
                    pathStr
                } else {
                    val sb = StringBuilder("<g>").append(pathStr)
                    if (fillGroup != null) sb.append(fillGroup)
                    if (hand) {
                        val (band, performed) = renderContourHandStroke(ins, attrs, sampled, emptySet(), unit, width, height, renderSeed, wild)
                        sb.append(band)
                        if (usesMaterialOutline(weight)) {
                            sb.append(
                                ServerRendererMaterial.performedOutline(
                                    ins, attrs, performed, unit,
                                    closed = true,
                                    pathLenPx = closedPathLength(performed),
                                    center = pointsCenter(sampled),
                                    renderSeed = renderSeed,
                                    instructionSeed = seedForInstruction(ins, renderSeed)
                                )
                            )
                        }
                    }
                    sb.append("</g>").toString()
                }
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

    private fun quantizeValue(value: Double): Double {
        return kotlin.math.round(value * 1_000_000_000.0) / 1_000_000_000.0
    }

    private fun quantizeJsonObject(obj: JSONObject): JSONObject {
        val res = JSONObject()
        val keys = obj.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val v = obj.opt(key)
            when (v) {
                is Double -> res.put(key, quantizeValue(v))
                is Float -> res.put(key, quantizeValue(v.toDouble()))
                is JSONObject -> res.put(key, quantizeJsonObject(v))
                is JSONArray -> res.put(key, quantizeJsonArray(v))
                else -> res.put(key, v)
            }
        }
        return res
    }

    private fun quantizeJsonArray(arr: JSONArray): JSONArray {
        val res = JSONArray()
        for (i in 0 until arr.length()) {
            val v = arr.opt(i)
            when (v) {
                is Double -> res.put(quantizeValue(v))
                is Float -> res.put(quantizeValue(v.toDouble()))
                is JSONObject -> res.put(quantizeJsonObject(v))
                is JSONArray -> res.put(quantizeJsonArray(v))
                else -> res.put(v)
            }
        }
        return res
    }

    /**
     * The logical centre of a shape, which is the quantity the arrangement
     * moves. Not one field: `center` for the round primitives, the middle of
     * the bbox for `square` / `triangle` and the midpoint for a `line`. A
     * reader that knows only about `circle` is right for every group this
     * corpus held before engine 26 and wrong for the ones it holds now.
     */
    internal fun anchor(ins: JSONObject): Pair<Double, Double> {
        val p = ins.optString("primitive", "line")
        val from = ins.optJSONArray("from_") ?: ins.optJSONArray("from")
        val to = ins.optJSONArray("to")
        if (p == "line" && from != null && to != null) {
            return ((from.optDouble(0, 0.5) + to.optDouble(0, 0.5)) / 2.0) to ((from.optDouble(1, 0.0) + to.optDouble(1, 1.0)) / 2.0)
        }
        val center = ins.optJSONArray("center")
        if (p in setOf("circle", "ellipse", "arc", "polygon", "cloudform") && center != null) {
            return center.optDouble(0, 0.5) to center.optDouble(1, 0.5)
        }
        val position = ins.optJSONArray("position")
        val size = ins.optJSONArray("size")
        if (p in setOf("square", "triangle") && position != null && size != null) {
            return (position.optDouble(0, 0.0) + size.optDouble(0, 0.0) / 2.0) to (position.optDouble(1, 0.0) + size.optDouble(1, 0.0) / 2.0)
        }
        return 0.5 to 0.5
    }

    private fun fitAxisScales(anchorVal: Double, offsets: List<Double>): Pair<Double, Double> {
        val positive = offsets.filter { it > 0.0 }
        val negative = offsets.filter { it < 0.0 }
        val forward = if (positive.isNotEmpty()) min(1.0, (FRAME_HI - anchorVal) / positive.maxOrNull()!!) else 1.0
        val backward = if (negative.isNotEmpty()) min(1.0, (FRAME_LO - anchorVal) / negative.minOrNull()!!) else 1.0
        return max(forward, 0.0) to max(backward, 0.0)
    }

    private fun fitGroupToAnchor(ins: JSONObject, expanded: List<JSONObject>): List<JSONObject> {
        if (expanded.isEmpty()) return expanded
        val (ax, ay) = anchor(ins)
        val points = expanded.map { anchor(it) }
        val cx = points.sumOf { it.first } / points.size.toDouble()
        val cy = points.sumOf { it.second } / points.size.toDouble()
        val offsets = points.map { (px, py) -> (px - cx) to (py - cy) }
        val (xForward, xBackward) = fitAxisScales(ax, offsets.map { it.first })
        val (yForward, yBackward) = fitAxisScales(ay, offsets.map { it.second })
        return expanded.zip(offsets).map { (item, offset) ->
            val (dx, dy) = offset
            val tx = ax + dx * (if (dx > 0.0) xForward else xBackward)
            val ty = ay + dy * (if (dy > 0.0) yForward else yBackward)
            shiftTo(item, tx, ty)
        }
    }

    /**
     * The two seeds are separate on purpose (engine 23 and 25).
     * `placementSeed` decides where the members land, which is the composition
     * seed's business; `performanceSeed` decides how big each one is and which
     * way it faces, which belongs to the performance. Feeding the size from the
     * placement seed would make the drawing's shapes follow the composition
     * seed and undo that split on the day it was made.
     */
    internal fun expandArrangement(
        ins: JSONObject,
        placementSeed: Long? = null,
        canvas: CanvasSize? = null,
        performanceSeed: Long? = null
    ): List<JSONObject> {
        val arr = ins.optJSONObject("arrangement") ?: return listOf(ins)
        val layout = arr.optString("layout", "horizontal")
        val expanded = expandArrangementLayout(ins, placementSeed, canvas, performanceSeed)
        if (expanded.isEmpty()) return expanded
        val hasAt = ins.has("at") && !ins.isNull("at")
        val fitted = if (layout == "grid" && hasAt) {
            expanded
        } else {
            fitGroupToAnchor(ins, expanded)
        }
        return fitted.map { quantizeJsonObject(it) }
    }

    /**
     * The one exit every layout branch takes: fade, size, angle.
     *
     * Order matters. The colour cycle rebuilds `color_hint`, so a level written
     * before it is dropped -- and 43.5% of the groups in production state a
     * cycle; it is applied inside the layout branches, before this runs.
     *
     * Size and angle come last and are read by none of the three before them:
     * the fade ramp is measured from the anchors and the member count, and
     * neither the scale nor the turn moves an anchor, so engine 24's ceilings
     * arrive unchanged. The two are ordered size-then-angle for no reason that
     * shows: the size rule reads `radius` / `size` / the endpoints and the
     * angle rule reads `rotation`, so neither can see what the other wrote.
     *
     * `center` is the centre the layout laid the group around, for the branches
     * that have one -- a ring has to pass its own, because the centroid is not it.
     */
    private fun finishExpandedGroup(
        items: List<JSONObject>,
        arr: JSONObject,
        center: Pair<Double, Double>? = null,
        memberSeed: String? = null
    ): List<JSONObject> {
        val faded = ServerRendererFade.apply(items, arr, items.map { anchor(it) }, center)
        return ServerRendererMembers.applyRotations(
            ServerRendererMembers.applySizes(faded, arr, memberSeed),
            arr,
            memberSeed
        )
    }

    private fun expandArrangementLayout(
        ins: JSONObject,
        placementSeed: Long? = null,
        canvas: CanvasSize? = null,
        performanceSeed: Long? = null
    ): List<JSONObject> {
        val arr = ins.optJSONObject("arrangement") ?: return listOf(ins)
        val count = arr.optInt("count", 1).coerceIn(1, 1000)
        val layout = arr.optString("layout", "horizontal")
        val prepared = ensureLineCoords(ins, layout)
        // Derived from the instruction as stated, before any member is shifted,
        // so every member of one group is drawn from the same sequence.
        val memberSeed = seedForInstruction(ins, performanceSeed)
        if (count == 1 && layout != "grid") {
            return finishExpandedGroup(
                listOf(applyColorCycle(copyWithoutArrangement(prepared), arr.optJSONArray("color_cycle"), 0)),
                arr,
                memberSeed = memberSeed
            )
        }
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
        val seed = seedForInstruction(ins, placementSeed)

        if (layout == "grid") {
            val (x0, y0, x1, y1) = if (ins.has("at") && !ins.isNull("at")) {
                val atObj = ins.getJSONObject("at")
                val reg = atObj.optJSONArray("region")
                if (reg != null && reg.length() >= 4) {
                    listOf(reg.getDouble(0), reg.getDouble(1), reg.getDouble(2), reg.getDouble(3))
                } else {
                    listOf(margin, margin, 1.0 - margin, 1.0 - margin)
                }
            } else {
                listOf(margin, margin, 1.0 - margin, 1.0 - margin)
            }
            val regionWidth = max(x1 - x0, 1e-9)
            val regionHeight = max(y1 - y0, 1e-9)

            var rows = if (arr.has("rows") && !arr.isNull("rows")) arr.getInt("rows") else null
            var cols = if (arr.has("cols") && !arr.isNull("cols")) arr.getInt("cols") else null

            if (rows != null && cols != null) {
                // keep
            } else if (rows != null) {
                cols = minOf(64, maxOf(1, kotlin.math.ceil(count.toDouble() / rows).toInt()))
            } else if (cols != null) {
                rows = minOf(64, maxOf(1, kotlin.math.ceil(count.toDouble() / cols).toInt()))
            } else {
                var physicalAspect = regionWidth / regionHeight
                if (canvas != null) {
                    physicalAspect *= canvas.width.toDouble() / canvas.height.toDouble()
                }
                cols = minOf(64, maxOf(1, kotlin.math.ceil(kotlin.math.sqrt(count.toDouble() * physicalAspect)).toInt()))
                rows = minOf(64, maxOf(1, kotlin.math.ceil(count.toDouble() / cols).toInt()))
            }
            val rCount = rows
            val cCount = cols
            val cellWidth = regionWidth / cCount.toDouble()
            val cellHeight = regionHeight / rCount.toDouble()
            val jitter = arr.optDouble("jitter", 0.12)

            val seedULong = seed.toULongOrNull() ?: 0UL
            val rowSeed = (seedULong xor 0xA53CUL).toString()
            val colSeed = (seedULong xor 0xC3A5UL).toString()

            val targets = mutableListOf<Pair<Double, Double>>()
            for (r in 0 until rCount) {
                val rowT = rhythmT(r, rCount, rowSeed, rhythmSpacing)
                val cy = y0 + (0.5 + rowT * (rCount - 1)) * cellHeight
                for (c in 0 until cCount) {
                    val colT = rhythmT(c, cCount, colSeed, rhythmSpacing)
                    val cx = x0 + (0.5 + colT * (cCount - 1)) * cellWidth
                    val dx = (hash01(r * cCount + c, seed, "grid-jitter-x") - 0.5) * jitter * cellWidth
                    val dy = (hash01(r * cCount + c, seed, "grid-jitter-y") - 0.5) * jitter * cellHeight
                    targets.add(
                        minOf(x1, maxOf(x0, cx + dx)) to minOf(y1, maxOf(y0, cy + dy))
                    )
                }
            }
            return finishExpandedGroup(
                targets.mapIndexed { i, (tx, ty) ->
                    val shifted = shiftTo(base, tx, ty)
                    shifted.remove("at")
                    shifted.remove("relation")
                    applyColorCycle(shifted, arr.optJSONArray("color_cycle"), i)
                },
                arr,
                memberSeed = memberSeed
            )
        }

        // The centre the layout laid the group around, for the one branch that
        // has one of its own. A ring must be measured from here and not from
        // the centroid of its marks: the rhythm spans 0 to 1 inclusive, so the
        // first mark is drawn twice and pulls the mean off the axis.
        var layoutCenter: Pair<Double, Double>? = null

        val laid = (0 until count).map { i ->
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
                    canvas = canvas,
                )
            } else if (path != "none") {
                pathPosition(i, count, margin, path, seed, rhythmSpacing, canvas)
            } else {
                when (layout) {
                    "vertical" -> margin to (margin + t * (1.0 - margin * 2.0))
                    "scatter" -> scatterPosition(i, margin, seed)
                    "radial" -> {
                        val (ax, ay) = anchor(prepared)
                        val center = arr.optJSONArray("center")
                        val cx = if (center != null && center.length() >= 2) center.optDouble(0, ax) else ax
                        val cy = if (center != null && center.length() >= 2) center.optDouble(1, ay) else ay
                        val a = Math.toRadians(t * 360.0)
                        // The server reads a falsy radius -- absent, null or an explicit 0.0 --
                        // as "unstated" and turns the ring at 0.3 (renderer.py:1861,
                        // `r = arr.radius if arr.radius else 0.3`). optDouble would keep a
                        // declared 0.0 and collapse every mark onto the centre, so the zero
                        // is folded into the default here to match.
                        val declaredRadius = arr.optDouble("radius", 0.0)
                        val r = if (declaredRadius != 0.0) declaredRadius else 0.3
                        layoutCenter = cx to cy
                        (cx + r * cos(a)) to (cy - r * sin(a))
                    }
                    else -> (margin + t * (1.0 - margin * 2.0)) to 0.5
                }
            }
            val shifted = shiftTo(base, target.first, target.second)
            applyColorCycle(shifted, arr.optJSONArray("color_cycle"), i)
        }
        return finishExpandedGroup(laid, arr, layoutCenter, memberSeed)
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

    /**
     * Where member `i` of a path-following group lands, in normalized space.
     *
     * engine 32: the cross-axis spread goes on the short side. A path has two
     * quantities and they are not the same kind. Along its line,
     * `margin + t * span` says how much of the paper the group uses -- that is
     * the paper's own length and stays proportional. Across it, the wave's swing
     * and the jitter are the shape of the path, and written straight they became
     * `0.22 * width` across and `0.22 * height` down, so the same wave came out
     * with a swing of 220px on the square canvas and 44px on the pillar. Only
     * the second is levelled here; `margin` and `span` are untouched.
     *
     * `canvas` is stated by every caller on purpose -- a default would let a new
     * call site keep the old behaviour without saying so.
     */
    private fun pathPosition(i: Int, count: Int, margin: Double, path: String, seed: String, rhythmSpacing: String, canvas: CanvasSize?): Pair<Double, Double> {
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
        rhythmSpacing: String,
        canvas: CanvasSize?,
    ): Pair<Double, Double> {
        val nClusters = clusterCount.coerceIn(1, count)
        val clusterIndex = i % nClusters
        val localIndex = i / nClusters
        val localTotal = max(1, kotlin.math.ceil(count / nClusters.toDouble()).toInt())
        val centerMargin = max(margin, if (preserveSpace) 0.20 else margin)
        val center = if (path == "none") {
            scatterPosition(clusterIndex, centerMargin, seedForCluster(seed))
        } else {
            // R3 (author, 2026-08-12): where the cluster sits is not a shape, so
            // the canvas is deliberately NOT forwarded to this one call.
            // Forwarding it would level the centres too, and "the middle cluster
            // is above the others" would stop meaning the same thing on paper of
            // a different shape.
            pathPosition(clusterIndex, nClusters, centerMargin, path, seedForCluster(seed), rhythmSpacing, null)
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
        val localT = if (rhythmSpacing != "none" && localTotal > 1) {
            rhythmT(localIndex, localTotal, seed, rhythmSpacing)
        } else {
            (localIndex + 0.5) / localTotal.toDouble()
        }
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

    private fun trianglePoints(ins: JSONObject, width: Double, height: Double, unit: Double): List<Pair<Double, Double>> {
        return ServerRendererGeometry.trianglePoints(ins, width, height, unit)
    }

    private fun usesHandStroke(weight: String): Boolean {
        return weight != "rotring" && weight in GRAMMARS
    }

    private fun edgeContourWithAnchors(
        corners: List<Pair<Double, Double>>,
        variation: JSONObject?,
        seedStr: String,
        ins: JSONObject,
        width: Double,
        height: Double,
        unit: Double
    ): Pair<List<Pair<Double, Double>>, Set<Int>> {
        val result = mutableListOf<Pair<Double, Double>>()
        val anchors = mutableSetOf<Int>()
        val n = corners.size
        val seedLong = ServerRendererGeometry.seedToLong(seedStr)
        for (i in 0 until n) {
            val start = corners[i]
            val end = corners[(i + 1) % n]
            anchors.add(result.size)
            val edge = if (variation == null || !needsPathVariation(variation)) {
                val len = kotlin.math.hypot(end.first - start.first, end.second - start.second)
                val segments = ServerRendererGeometry.strokeSampleCount(len, unit)
                (0..segments).map { k ->
                    val t = k.toDouble() / segments.toDouble()
                    (start.first + (end.first - start.first) * t) to (start.second + (end.second - start.second) * t)
                }
            } else {
                val edgeSeed = seedLong + (i + 1) * 7919L
                ServerRendererGeometry.variedLinePoints(start.first, start.second, end.first, end.second, variation, edgeSeed, ins, width, height, unit)
            }
            if (edge.size > 1) {
                result.addAll(edge.dropLast(1))
            } else {
                result.addAll(edge)
            }
        }
        return result to anchors
    }

    private fun renderContourHandStroke(
        ins: JSONObject,
        attrs: SvgAttrs,
        contour: List<Pair<Double, Double>>,
        anchors: Set<Int>,
        unit: Double,
        width: Double,
        height: Double,
        renderSeed: Long? = null,
        wild: Boolean = false
    ): Pair<String, List<Pair<Double, Double>>> {
        val weight = ins.optString("weight", "pen")
        val baseWidth = ServerRendererStyle.strokeWidth(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale })
        val gridStep = gridStepPx(weight, unit)
        val seedStr = seedForInstruction(ins, renderSeed)
        val seedLong = ServerRendererGeometry.seedToLong(seedStr)

        val stroke = ServerStrokeEngine.synthesizeAlong(
            centerline = contour,
            baseWidth = baseWidth,
            weight = weight,
            seed = seedLong,
            closed = true,
            anchors = anchors,
            gridStep = gridStep,
            wild = wild
        )

        val groupClass = "contour-stroke-v1 controls-${stroke.samples.size} events-${stroke.eventCount}"
        val color = attrs.stroke
        val opacity = attrs.strokeOpacity

        val sb = StringBuilder()
        sb.append("""<g class="$groupClass">""")
        addRasterBleed(sb, stroke.samples, stroke.gridStep, color)

        val pathD = ServerStrokeEngine.contourStrokePath(stroke)
        val textureFilterWeights = setOf("pencil", "crayon", "chalk", "brush_thin", "brush_thick", "drypoint")
        val filterAttr = if (weight in textureFilterWeights && weight != "drypoint") """ filter="url(#texture-$weight)"""" else ""
        val fillOpacityStr = fmt(opacity)

        sb.append("""<path d="$pathD" fill="$color" fill-opacity="$fillOpacityStr" fill-rule="evenodd" stroke="none"$filterAttr/>""")

        if (weight == "drypoint") {
            val offset = stroke.burrSide * baseWidth
            val normals = ServerStrokeEngine.centerlineNormals(stroke.samples.map { it.x to it.y }, closed = true)
            val burrPoints = stroke.samples.zip(normals).map { (sample, normal) ->
                (sample.x + normal.first * offset) to (sample.y + normal.second * offset)
            }
            val ptsStr = burrPoints.joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
            val burrOpacityStr = fmt(stroke.burrOpacity)
            val burrWidthStr = fmt(baseWidth * 1.25)
            sb.append("""<polygon points="$ptsStr" fill="none" stroke="$color" stroke-width="$burrWidthStr" stroke-opacity="$burrOpacityStr" stroke-linecap="round"$filterAttr/>""")
        }

        sb.append("</g>")
        val performed = stroke.samples.map { it.x to it.y }
        return sb.toString() to performed
    }

    private fun renderBodyShape(
        primitive: String,
        ins: JSONObject,
        attrs: SvgAttrs,
        regionFill: Boolean,
        cx: Double, cy: Double, rx: Double, ry: Double,
        x: Double, y: Double, w: Double, h: Double,
        pts: List<Pair<Double, Double>>,
        pathD: String? = null,
        classAttr: String? = null
    ): String {
        val fillVal = if (regionFill) attrs.fill else "none"
        val fillOpacityAttr = if (regionFill && attrs.fillOpacity != null) """ fill-opacity="${attrs.fillOpacity}"""" else ""
        val isSolid = ins.optString("style", "solid") == "solid"
        val strokeAttr = if (isSolid) {
            """stroke="none""""
        } else {
            val sw = attrs.strokeWidth * 0.42
            val dashAttr = if (!attrs.dash.isNullOrBlank()) """ stroke-dasharray="${attrs.dash}"""" else ""
            """stroke="${attrs.stroke}" stroke-width="${fmt(sw)}" stroke-linecap="${attrs.strokeLinecap}" stroke-opacity="${attrs.strokeOpacity}"$dashAttr"""
        }

        return when (primitive) {
            "circle" -> {
                if (pts.isNotEmpty()) {
                    val ptsStr = pts.joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
                    """<polygon points="$ptsStr" fill="$fillVal"$fillOpacityAttr $strokeAttr/>"""
                } else {
                    """<circle cx="$cx" cy="$cy" r="$rx" fill="$fillVal"$fillOpacityAttr $strokeAttr/>"""
                }
            }
            "ellipse" -> {
                if (pts.isNotEmpty()) {
                    val ptsStr = pts.joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
                    """<polygon points="$ptsStr" fill="$fillVal"$fillOpacityAttr $strokeAttr/>"""
                } else {
                    """<ellipse cx="$cx" cy="$cy" rx="$rx" ry="$ry" fill="$fillVal"$fillOpacityAttr $strokeAttr/>"""
                }
            }
            "square" -> {
                if (pts.isNotEmpty()) {
                    val ptsStr = pts.joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
                    """<polygon points="$ptsStr" fill="$fillVal"$fillOpacityAttr $strokeAttr/>"""
                } else {
                    """<rect x="$x" y="$y" width="$w" height="$h" fill="$fillVal"$fillOpacityAttr $strokeAttr/>"""
                }
            }
            "polygon" -> {
                val ptsStr = pts.joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
                """<polygon points="$ptsStr" fill="$fillVal"$fillOpacityAttr $strokeAttr/>"""
            }
            "cloudform" -> {
                val cls = if (classAttr != null) """class="$classAttr" """ else ""
                """<path $cls d="$pathD" fill="$fillVal"$fillOpacityAttr $strokeAttr/>"""
            }
            else -> ""
        }
    }

    // Perimeter of a closed polyline, and the centre used to settle the normal direction
    // by majority vote. Mirrors _closed_path_length / _points_center in renderer.py.
    private fun closedPathLength(path: List<Pair<Double, Double>>): Double {
        if (path.size < 2) return 0.0
        return path.indices.sumOf { i ->
            val a = path[i]
            val b = path[(i + 1) % path.size]
            kotlin.math.hypot(b.first - a.first, b.second - a.second)
        }
    }

    private fun pointsCenter(path: List<Pair<Double, Double>>): Pair<Double, Double> {
        if (path.isEmpty()) return 0.0 to 0.0
        return (path.sumOf { it.first } / path.size) to (path.sumOf { it.second } / path.size)
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
        renderSeed: Long? = null,
        wild: Boolean = false
    ): String {
        val length = kotlin.math.hypot(x2 - x1, y2 - y1)
        val baseWidth = ServerRendererStyle.strokeWidth(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale })
        val gridStep = gridStepPx(weight, unit)
        val samples = ServerRendererGeometry.strokeSampleCount(length, unit)
        val seedStr = seedForInstruction(ins, renderSeed)
        val seedLong = seedStr.toULongOrNull()?.toLong() ?: 0L

        val stroke = ServerStrokeEngine.synthesizeStroke(
            start = Pair(x1, y1),
            end = Pair(x2, y2),
            baseWidth = baseWidth,
            weight = weight,
            seed = seedLong,
            samplesCount = samples,
            wild = wild,
            gridStep = gridStep
        )

        val groupClass = "stroke-engine-v1 controls-${stroke.samples.size} events-${stroke.eventCount}"
        val color = attrs.stroke
        val opacity = attrs.strokeOpacity

        val variation = ins.optJSONObject("variation")
        var materialCenterline = stroke.samples.map { Pair(it.x, it.y) }
        val outline = if (needsPathVariation(variation)) {
            val centerline = ServerRendererGeometry.variedLinePoints(x1, y1, x2, y2, variation, seedStr, ins, width, height, unit)
            val varied = ServerStrokeEngine.synthesizeStroke(
                start = Pair(x1, y1),
                end = Pair(x2, y2),
                baseWidth = baseWidth,
                weight = weight,
                seed = seedLong,
                samplesCount = centerline.size,
                wild = wild,
                gridStep = gridStep
            )
            materialCenterline = centerline
            ServerStrokeEngine.outlineForCenterline(centerline, varied.samples.map { it.width }, varied.cuts)
        } else {
            stroke.outline
        }

        val sb = StringBuilder()
        sb.append("""<g class="$groupClass">""")
        addRasterBleed(sb, stroke.samples, stroke.gridStep, color)

        val pathD = ServerStrokeEngine.polygonPath(outline)
        val fillOpacityStr = fmt(opacity)
        sb.append("""<path d="$pathD" fill="$color" fill-opacity="$fillOpacityStr" stroke="none"/>""")

        if (weight in setOf("pencil", "pen", "crayon", "chalk", "brush_thin", "brush_thick")) {
            val mat = ServerRendererMaterial.lineGroup(ins, attrs, x1, y1, x2, y2, unit, includeBase = false, renderSeed = renderSeed, centerline = materialCenterline, instructionSeed = seedLong)
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

    private fun materialLineGroup(ins: JSONObject, attrs: SvgAttrs, x1: Double, y1: Double, x2: Double, y2: Double, unit: Double, renderSeed: Long? = null, centerline: List<Pair<Double, Double>>? = null): String? {
        val seedStr = seedForInstruction(ins, renderSeed)
        val seedLong = seedStr.toULongOrNull()?.toLong() ?: 0L
        return ServerRendererMaterial.lineGroup(ins, attrs, x1, y1, x2, y2, unit, renderSeed = renderSeed, centerline = centerline, instructionSeed = seedLong)
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
        // Commas, and the master grid's six decimals: what svgwrite writes on
        // the server. Spaces are valid SVG and read the same, but the corpus is
        // compared as text.
        return """<g transform="rotate(${fmt(rotation)},${fmt(center.first)},${fmt(center.second)})">$element</g>"""
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

    private fun applyMasterGrid(svg: String): String {
        val attrRe = Regex("""([\w:-]+)="([^"]*)"""")
        val numRe = Regex("""-?\d+\.\d+(?:[eE][-+]?\d+)?""")
        val ungriddedAttrs = setOf("version", "class", "id")

        return attrRe.replace(svg) { match ->
            val name = match.groupValues[1]
            val value = match.groupValues[2]
            if (name in ungriddedAttrs || "." !in value) {
                match.value
            } else {
                val gridded = numRe.replace(value) { nMatch ->
                    ServerRendererGeometry.fmt(nMatch.value.toDouble())
                }
                """$name="$gridded""""
            }
        }
    }

    private fun signedHash(i: Int, seed: String): Double = ServerRendererGeometry.signedHash(i, seed)

    private fun String.containsAny(vararg markers: String): Boolean = markers.any { contains(it) }

    private fun hash01(i: Int, seed: String): Double {
        return ServerRendererGeometry.hash01(i, seed)
    }

    private fun hash01(i: Int, seed: String, salt: String): Double {
        val digest = sha256Bytes("$seed:$salt:$i")
        return uint32Le(digest, 0).toDouble() / 0xffffffffL.toDouble()
    }

    /**
     * A render seed is a Python `int` on the other side, and the keys it goes
     * into are hashed as text. Kotlin's `Long` holds the same 64 bits but prints
     * the top half of the range as a negative number, so every key that names a
     * seed asks for it in the unsigned form. Below 2^63 -- which is every seed
     * `new_render_seed` can produce -- the two spellings are the same string;
     * above it, only this one agrees with the server.
     */
    private fun unsignedSeed(seed: Long): String = java.lang.Long.toUnsignedString(seed)

    private fun seedForInstruction(ins: JSONObject, renderSeed: Long? = null): String {
        val base = serverInstructionJson(ins)
        val key = if (renderSeed != null) "$base:render:${unsignedSeed(renderSeed)}" else base
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

    // render engine 15: the seed key is an allowlist, not the whole instruction dump.
    // Fields the performance never consumes - color, color_hint, at, relation, and every
    // arrangement field but jitter - used to re-roll the marks, so an annotation coerce
    // wrote onto an instruction changed the drawing. Mirrors _SEED_INSTRUCTION_FIELDS and
    // _SEED_ARRANGEMENT_FIELDS in renderer.py, in that order.
    private fun serverInstructionJson(ins: JSONObject): String {
        return buildString {
            append("{")
            append("\"primitive\":"); append(jsonString(ins.optString("primitive", "line")))
            append(",\"from_\":"); append(coordJson(ins.optJSONArray("from_") ?: ins.optJSONArray("from")))
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
            append(",\"thinness\":"); append(stringOrNull(ins, "thinness"))
            // server pops the two defaults so a plain instruction keeps the shorter key.
            val mode = ins.optString("mode", "additive")
            if (mode != "additive") { append(",\"mode\":"); append(jsonString(mode)) }
            if (ins.has("carve_depth") && !ins.isNull("carve_depth")) {
                append(",\"carve_depth\":"); append(jsonString(ins.optString("carve_depth")))
            }
            append(",\"variation\":"); append(variationJson(ins, ins.optJSONObject("variation")))
            append(",\"arrangement\":"); append(seedArrangementJson(ins.optJSONObject("arrangement")))
            append(",\"surface\":"); append(surfaceJson(ins.optJSONObject("surface")))
            append("}")
        }
    }

    // Only jitter survives into the seed key (_SEED_ARRANGEMENT_FIELDS).
    private fun seedArrangementJson(arr: JSONObject?): String {
        if (arr == null) return "null"
        return "{\"jitter\":${doubleJson(arr.optDouble("jitter", 0.12))}}"
    }

    private fun surfaceJson(surface: JSONObject?): String {
        if (surface == null) return "null"
        return buildString {
            append("{")
            append("\"texture\":"); append(jsonString(surface.optString("texture", "none")))
            append(",\"density\":"); append(doubleJson(surface.optDouble("density", 0.35)))
            append(",\"scale\":"); append(doubleJson(surface.optDouble("scale", 0.35)))
            append(",\"opacity\":"); append(doubleJson(surface.optDouble("opacity", 0.28)))
            append(",\"bleed\":"); append(doubleJson(surface.optDouble("bleed", 0.0)))
            append(",\"direction\":"); append(jsonString(surface.optString("direction", "none")))
            val sg = surface.optString("spacing_gradient", "none")
            if (sg != "none") {
                append(",\"spacing_gradient\":"); append(jsonString(sg))
            }
            val ts = surface.optInt("tone_steps", 3)
            if (ts != 3) {
                append(",\"tone_steps\":"); append(ts)
            }
            append(",\"seed\":"); append(intOrNull(surface, "seed"))
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
        val quality = variation.optString("quality", "none")
        val dimsArr = variation.optJSONArray("dimensions")
        val dimsSet = mutableSetOf<String>()
        if (dimsArr != null) {
            for (i in 0 until dimsArr.length()) {
                dimsSet.add(dimsArr.optString(i))
            }
        }
        val isPink = quality == "pink"
        val needsPathVar = quality in setOf("perlin", "wave", "white") && ("position_x" in dimsSet || "position_y" in dimsSet)
        val needsContourVar = quality in setOf("perlin", "wave", "white") && ("position_x" in dimsSet || "position_y" in dimsSet || "radius" in dimsSet)

        val fields: List<String>? = when {
            primitive == "cloudform" -> listOf("amplitude", "frequency", "quality")
            isPink -> listOf("amplitude", "quality")
            primitive == "line" -> if (needsPathVar) listOf("amplitude", "frequency", "quality", "dimensions") else null
            needsContourVar -> listOf("amplitude", "frequency", "quality", "dimensions")
            else -> null
        }
        if (fields == null) return "null"

        val parts = mutableListOf<String>()
        for (field in fields) {
            when (field) {
                "amplitude" -> parts.add("\"amplitude\":" + jsonString(variation.optString("amplitude", "medium")))
                "frequency" -> parts.add("\"frequency\":" + jsonString(variation.optString("frequency", "medium")))
                "quality" -> parts.add("\"quality\":" + jsonString(variation.optString("quality", "none")))
                "dimensions" -> parts.add("\"dimensions\":" + stringArrayJson(variation.optJSONArray("dimensions")))
            }
        }
        return parts.joinToString(prefix = "{", postfix = "}", separator = ",")
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

    private fun dumpSurfaceJson(surface: JSONObject?): String {
        if (surface == null) return "null"
        return buildString {
            append("{")
            append("\"texture\":"); append(jsonString(surface.optString("texture", "none")))
            append(",\"density\":"); append(doubleJson(surface.optDouble("density", 0.35)))
            append(",\"scale\":"); append(doubleJson(surface.optDouble("scale", 0.35)))
            append(",\"opacity\":"); append(doubleJson(surface.optDouble("opacity", 0.28)))
            append(",\"bleed\":"); append(doubleJson(surface.optDouble("bleed", 0.0)))
            append(",\"direction\":"); append(jsonString(surface.optString("direction", "none")))
            append(",\"spacing_gradient\":"); append(jsonString(surface.optString("spacing_gradient", "none")))
            append(",\"tone_steps\":"); append(surface.optInt("tone_steps", 3))
            append(",\"seed\":"); append(intOrNull(surface, "seed"))
            append("}")
        }
    }

    private fun surfaceSeed(ins: JSONObject, insIdx: Int = 0, markIdx: Int = 0, renderSeed: Long? = null): String {
        val surfaceObj = ins.optJSONObject("surface")
        if (surfaceObj != null && surfaceObj.has("seed") && !surfaceObj.isNull("seed")) {
            return surfaceObj.optLong("seed").toULong().toString()
        }
        val dumpJson = buildString {
            append("{")
            append("\"primitive\":"); append(jsonString(ins.optString("primitive", "line")))
            append(",\"note\":"); append(stringOrNull(ins, "note"))
            append(",\"from\":"); append(coordJson(ins.optJSONArray("from_") ?: ins.optJSONArray("from")))
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
            append(",\"mode\":"); append(jsonString(ins.optString("mode", "additive")))
            append(",\"carve_depth\":"); append(stringOrNull(ins, "carve_depth"))
            append(",\"color\":"); append(jsonString(ins.optString("color", "black")))
            append(",\"color_hint\":"); append(stringOrNull(ins, "color_hint"))
            append(",\"variation\":"); append(variationJson(ins, ins.optJSONObject("variation")))
            append(",\"arrangement\":"); append(arrangementJson(ins.optJSONObject("arrangement")))
            append(",\"at\":null")
            append(",\"relation\":null")
            append(",\"thinness\":"); append(stringOrNull(ins, "thinness"))
            append(",\"surface\":"); append(dumpSurfaceJson(ins.optJSONObject("surface")))
            append("}")
        }
        val key = "$dumpJson:surface:$insIdx:$markIdx:${renderSeed?.let { unsignedSeed(it) } ?: "None"}"
        return uint64Le(sha256Bytes(key), 0).toString()
    }

    private fun jsonString(value: String): String = JSONObject.quote(value)

    private fun renderSurfaceVectors(
        ins: JSONObject,
        attrs: SvgAttrs,
        colors: Map<String, String>,
        width: Double,
        height: Double,
        unit: Double,
        renderSeed: Long? = null,
        wild: Boolean = false
    ): String {
        val surface = ins.optJSONObject("surface") ?: return ""
        val texture = surface.optString("texture", "none")
        if (texture == "none") return ""
        val bbox = ServerRendererGeometry.shapeBbox(ins, width, height, unit) ?: return ""
        val x = bbox[0]
        val y = bbox[1]
        val w = bbox[2]
        val h = bbox[3]
        val colorKey = if (surface.has("color") && !surface.isNull("color")) surface.optString("color") else ins.optString("color", "black")
        val color = colors[colorKey] ?: "#111111"
        val opacity = kotlin.math.min(0.75, surface.optDouble("opacity", 0.3))
        val density = kotlin.math.max(0.02, surface.optDouble("density", 0.5))

        if (texture in setOf("hatch", "crosshatch")) {
            val angle = ServerRendererGeometry.surfaceLineAngle(surface.optString("direction", "diagonal_falling"))
            val spacing = max(5.0, unit * (0.010 + (1.0 - density) * 0.025))
            val span = kotlin.math.hypot(w, h) * 1.3
            val cx = x + w / 2.0
            val cy = y + h / 2.0
            val count = min(80, max(3, (span / spacing).toInt()))
            val angles = mutableListOf(angle)
            val seedStr = surfaceSeed(ins, 0, 0, renderSeed)
            if (texture == "crosshatch") {
                angles.add(angle + Math.toRadians(60.0 + ServerRendererGeometry.hash01(8, seedStr, "cross-angle") * 30.0))
            }
            val weight = ins.optString("weight", "pen")
            val usesHand = usesHandStroke(weight)
            val spacingGradient = surface.optString("spacing_gradient", "none")
            val sb = StringBuilder()
            for ((layerIndex, layerAngle) in angles.withIndex()) {
                val lux = cos(layerAngle)
                val luy = sin(layerAngle)
                val lnx = -luy
                val lny = lux
                val startIdx = Math.floorDiv(-count, 2)
                val endIdx = Math.floorDiv(count, 2)
                for (i in startIdx..endIdx) {
                    val progress = (i + count / 2.0) / max(1, count)
                    val gradient = when (spacingGradient) {
                        "coarse_to_dense" -> 1.35 - progress * 0.7
                        "dense_to_coarse" -> 0.65 + progress * 0.7
                        else -> 1.0
                    }
                    val offset = i * spacing * gradient + ServerRendererGeometry.hashToUnit(i + layerIndex * 401 + 500, seedStr) * spacing * 0.12
                    val ox = lnx * offset
                    val oy = lny * offset
                    val p1x = cx + ox - lux * span / 2.0
                    val p1y = cy + oy - luy * span / 2.0
                    val p2x = cx + ox + lux * span / 2.0
                    val p2y = cy + oy + luy * span / 2.0
                    val lineWidth = max(0.45, unit * 0.0016)
                    val hatchClass = "hatch-spacing-%.3f".format(java.util.Locale.US, spacing * gradient)
                    val opacityStr = fmt(opacity)
                    val strokeWidthStr = fmt(lineWidth)

                    if (!usesHand) {
                        sb.append("""<line class="surface-stroke-v1 $hatchClass" x1="${fmt(p1x)}" y1="${fmt(p1y)}" x2="${fmt(p2x)}" y2="${fmt(p2y)}" stroke="$color" stroke-width="$strokeWidthStr" stroke-opacity="$opacityStr" stroke-linecap="round"/>""")
                    } else {
                        val countSamples = max(2, ServerRendererGeometry.strokeSampleCount(span, unit))
                        val centerline = (0 until countSamples).map { k ->
                            val t = k.toDouble() / (countSamples - 1).toDouble()
                            (p1x + (p2x - p1x) * t) to (p1y + (p2y - p1y) * t)
                        }
                        val strokeSeed = ServerRendererGeometry.fillStrokeSeed(seedStr, i + layerIndex * 4096)
                        val gridStep = gridStepPx(weight, unit)
                        val hatchStroke = ServerStrokeEngine.synthesizeAlong(centerline, lineWidth, weight, strokeSeed, closed = false, gridStep = gridStep, wild = wild)
                        val pathD = ServerStrokeEngine.contourStrokePath(hatchStroke)
                        sb.append("""<path class="surface-stroke-v1 $hatchClass" d="$pathD" fill="$color" fill-opacity="$opacityStr" stroke="none"/>""")
                    }
                }
            }
            return sb.toString()
        }
        return ""
    }

    /**
     * The inside of a closed shape, filled with the material's own strokes.
     *
     * Engine 22 took the three regularities the eye reads as a raster out of
     * this function. The scan angle now moves per stroke, the pitch is drawn
     * far wider, and the ends leave the contour instead of being cut at the
     * intersection -- which they can only do because the underlay is holding
     * the boundary underneath. All three amplitudes come from the tool
     * (`fillHand`) and are zero for a machine, so `computer` still lays the
     * same exact raster it did.
     */
    internal fun renderFillStrokes(
        ins: JSONObject,
        attrs: SvgAttrs,
        contour: List<Pair<Double, Double>>,
        unit: Double,
        renderSeed: Long? = null,
        wild: Boolean = false,
        instructionSeed: Any? = null
    ): String? {
        if (contour.size < 3) return null
        val weight = ins.optString("weight", "pen")
        val baseWidth = ServerRendererStyle.strokeWidth(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale })
        val gridStep = gridStepPx(weight, unit)
        val seedStr = instructionSeed ?: seedForInstruction(ins, renderSeed)
        val hand = ServerRendererFill.fillHand(ins)
        val raster = (GRAMMARS[weight] ?: GRAMMARS.getValue("pen")).periodic
        val angle = ServerRendererGeometry.fillScanAngle(seedStr)
        // A screen's raster keeps the classic pitch so the gaps between the
        // lines stay readable; a hand tool is free to pack to the coverage the
        // underlay made possible.
        val spacing = if (raster) {
            ServerRendererGeometry.fillScanSpacing(ins, unit)
        } else {
            baseWidth / ServerRendererFill.COVERAGE_TARGET
        }
        val pitchCv = if (hand != 0.0) {
            ServerRendererFill.PITCH_CV_MIN + ServerRendererFill.PITCH_CV_SPAN * hand
        } else {
            0.0
        }
        val segments = ServerRendererGeometry.scanlineSegments(
            contour, angle, spacing, seedStr, pitchCv * kotlin.math.sqrt(12.0)
        )
        if (segments.map { it.first }.toSet().size < ServerRendererFill.MIN_SCANLINES) return null

        val color = attrs.stroke
        val opacity = attrs.fillOpacity ?: attrs.strokeOpacity
        // The marks sit close over the field. A ratio of the underlay's, never
        // an absolute, so a description asking for a pale fill keeps the
        // relation -- and never darker than the ink the description specified.
        val markOpacity = min(
            opacity,
            opacity * ServerRendererFill.UNDERLAY_OPACITY_RATIO *
                ServerRendererFill.SCAN_CONTRAST * ServerRendererFill.fillContrast(ins)
        )
        val minimum = baseWidth * ServerRendererFill.MIN_STROKE_WIDTHS
        val angleAmp = ServerRendererFill.angleAmplitude(hand)
        val reach = if (hand != 0.0) {
            baseWidth * (ServerRendererFill.REACH_WIDTHS_MIN + ServerRendererFill.REACH_WIDTHS_SPAN * hand)
        } else {
            0.0
        }
        val paths = mutableListOf<String>()

        for ((order, seg) in segments.withIndex()) {
            val index = seg.first
            val segStart = seg.second
            val segEnd = seg.third
            val chord = kotlin.math.hypot(segEnd.first - segStart.first, segEnd.second - segStart.second)
            if (chord <= minimum) continue
            var ux = (segEnd.first - segStart.first) / chord
            var uy = (segEnd.second - segStart.second) / chord
            val mx = (segStart.first + segEnd.first) / 2
            val my = (segStart.second + segEnd.second) / 2
            // Turn this row on its own midpoint, then cut it against the
            // contour again. Rotating the chord and keeping its old length
            // would make the reach a fraction of a line the stroke no longer
            // travels: near the edge of a round form a few degrees change the
            // span several-fold.
            val t0: Double
            val t1: Double
            if (angleAmp != 0.0) {
                val delta = (ServerRendererGeometry.hash01(order, seedStr, "fill-angle-stroke") - 0.5) * 2 * angleAmp
                val cosD = kotlin.math.cos(delta)
                val sinD = kotlin.math.sin(delta)
                val rx = ux * cosD - uy * sinD
                val ry = ux * sinD + uy * cosD
                ux = rx
                uy = ry
                val span = ServerRendererFill.lineSpans(contour, mx to my, ux to uy)
                    .firstOrNull { it.first <= 0.0 && 0.0 <= it.second } ?: continue
                t0 = span.first
                t1 = span.second
            } else {
                t0 = -chord / 2
                t1 = chord / 2
            }
            val length = t1 - t0
            if (length <= minimum) continue
            // One end overshoots the contour, the other may fall short of it.
            // The sign is drawn per end: an implementation that only insets
            // would leave the edge as tidy as the cut it replaced.
            var r0 = reach
            var r1 = reach
            if (ServerRendererGeometry.hash01(order, seedStr, "fill-reach-start") < 0.5) r0 = -r0
            if (ServerRendererGeometry.hash01(order, seedStr, "fill-reach-end") < 0.5) r1 = -r1
            var p0 = (mx + ux * (t0 - r0)) to (my + uy * (t0 - r0))
            var p1 = (mx + ux * (t1 + r1)) to (my + uy * (t1 + r1))
            if (index % 2 != 0) {
                val tmp = p0
                p0 = p1
                p1 = tmp
            }
            val span = kotlin.math.hypot(p1.first - p0.first, p1.second - p0.second)
            val count = max(2, ServerRendererGeometry.strokeSampleCount(span, unit))
            val centerline = (0 until count).map { i ->
                val t = i.toDouble() / (count - 1).toDouble()
                (p0.first + (p1.first - p0.first) * t) to (p0.second + (p1.second - p0.second) * t)
            }
            // A raster line is one line with a soft edge, so it is laid twice:
            // a wide faint halo and a narrow dense core on the same centreline.
            // Two real elements rather than a blur, because filters are
            // display-only and the machine has to look the same in every profile.
            val layers = if (raster) {
                listOf(
                    (baseWidth * ServerRendererFill.RASTER_HALO_WIDTHS) to (markOpacity - ServerRendererFill.RASTER_HALO_STEP),
                    (baseWidth * ServerRendererFill.RASTER_CORE_WIDTHS) to markOpacity
                )
            } else {
                listOf(baseWidth to markOpacity)
            }
            for ((width, layerOpacity) in layers) {
                val d = if (raster) {
                    // Straight, because a raster line is straight. Performing
                    // it through the tool grammar bent it along its run.
                    ServerRendererFill.rasterBand(p0, p1, width)
                } else {
                    ServerStrokeEngine.contourStrokePath(
                        ServerStrokeEngine.synthesizeAlong(
                            centerline = centerline,
                            baseWidth = width,
                            weight = weight,
                            seed = ServerRendererGeometry.fillStrokeSeed(seedStr, order),
                            closed = false,
                            gridStep = gridStep,
                            wild = wild,
                            terminal = "loaded"
                        )
                    )
                }
                val textureFilterWeights = setOf("pencil", "crayon", "chalk", "brush_thin", "brush_thick", "drypoint")
                val filterAttr = if (weight in textureFilterWeights && weight != "drypoint") """ filter="url(#texture-$weight)"""" else ""
                paths.add("""<path d="$d" fill="$color" fill-opacity="${fmt(layerOpacity)}" stroke="none"$filterAttr/>""")
            }
        }

        if (paths.isEmpty()) return null
        return """<g class="fill-stroke-v1 strokes-${paths.size}">${paths.joinToString("")}</g>"""
    }

    /**
     * The upper layer of a fill, made of scattered marks rather than scan lines.
     *
     * Below the coverage threshold a pass of parallel lines does not become a
     * field -- closing the gaps would take eight times the lines at pencil
     * width -- and that is not how the tool is used: a pencil rubs a tone
     * rather than ruling it. The underlay already holds the field, so these
     * marks only have to give it grain.
     *
     * The scatter is the whole of the difference from the scan branch. Length,
     * direction and end treatment are the scan branch's own: what separates a
     * rubbed tone from a ruled one is that the marks are not on rows.
     */
    internal fun renderFillTexture(
        ins: JSONObject,
        attrs: SvgAttrs,
        contour: List<Pair<Double, Double>>,
        unit: Double,
        renderSeed: Long? = null,
        wild: Boolean = false,
        instructionSeed: Any? = null
    ): String? {
        if (contour.size < 3) return null
        val weight = ins.optString("weight", "pen")
        val seedStr = instructionSeed ?: seedForInstruction(ins, renderSeed)
        val pitch = ServerRendererGeometry.fillScanSpacing(ins, unit)
        val width = ServerRendererStyle.strokeWidth(
            weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale }
        )
        val xs = contour.map { it.first }
        val ys = contour.map { it.second }
        val spanLimit = kotlin.math.hypot(xs.max() - xs.min(), ys.max() - ys.min())
        val count = ServerRendererFill.textureMarkCount(contour, pitch)
        val points = ServerRendererFill.surfaceScatter(contour, count, seedStr)
        if (points.isEmpty()) return null

        val color = attrs.stroke
        val opacity = attrs.fillOpacity ?: attrs.strokeOpacity
        // The marks rise out of the field; they are not drawn on top of it.
        val markOpacity = min(
            opacity,
            opacity * ServerRendererFill.UNDERLAY_OPACITY_RATIO *
                ServerRendererFill.TEXTURE_CONTRAST * ServerRendererFill.fillContrast(ins)
        )
        val gridStep = gridStepPx(weight, unit)
        val hand = ServerRendererFill.fillHand(ins)
        val baseAngle = ServerRendererGeometry.fillScanAngle(seedStr)
        val spread = ServerRendererFill.angleAmplitude(hand)
        val reach = width * (ServerRendererFill.REACH_WIDTHS_MIN + ServerRendererFill.REACH_WIDTHS_SPAN * hand)
        val sb = StringBuilder("""<g class="fill-texture-v1 marks-${points.size}">""")
        for ((index, point) in points.withIndex()) {
            val (px, py) = point
            // The marks run the region's one direction, wobbling by the few
            // degrees the hand gives -- the same band the scan branch draws
            // from. What makes this branch a rubbed tone is where the marks
            // are put, which is a scatter, not which way they run.
            val angle = baseAngle + (ServerRendererGeometry.hash01(index, seedStr, "fill-texture-angle") - 0.5) * 2 * spread
            val half = spanLimit
            val dx = kotlin.math.cos(angle)
            val dy = kotlin.math.sin(angle)
            val span = ServerRendererFill.lineSpans(contour, px to py, dx to dy)
                .firstOrNull { it.first <= 0.0 && 0.0 <= it.second } ?: continue
            val r0 = if (ServerRendererGeometry.hash01(index, seedStr, "fill-texture-reach-start") >= 0.5) reach else -reach
            val r1 = if (ServerRendererGeometry.hash01(index, seedStr, "fill-texture-reach-end") >= 0.5) reach else -reach
            val start = max(-half, span.first - r0)
            val end = min(half, span.second + r1)
            if (end - start <= width) continue
            // One tone per mark, drawn from a band centred on the branch
            // contrast. The mean is unchanged; what is new is that two
            // neighbouring marks are no longer the same grey.
            var tone = markOpacity * (
                1.0 + (ServerRendererGeometry.hash01(index, seedStr, "fill-texture-tone") - 0.5) * 2 * ServerRendererFill.TEXTURE_TONE_SPREAD
                )
            tone = min(opacity, tone)
            val length = end - start
            val samples = max(2, ServerRendererGeometry.strokeSampleCount(length, unit))
            val centerline = (0 until samples).map { i ->
                val t = start + length * i / (samples - 1).toDouble()
                (px + dx * t) to (py + dy * t)
            }
            val d = ServerStrokeEngine.contourStrokePath(
                ServerStrokeEngine.synthesizeAlong(
                    centerline = centerline,
                    baseWidth = width,
                    weight = weight,
                    seed = ServerRendererGeometry.fillStrokeSeed(seedStr, index),
                    closed = false,
                    gridStep = gridStep,
                    wild = wild,
                    terminal = "loaded"
                )
            )
            val textureFilterWeights = setOf("pencil", "crayon", "chalk", "brush_thin", "brush_thick", "drypoint")
            val filterAttr = if (weight in textureFilterWeights && weight != "drypoint") """ filter="url(#texture-$weight)"""" else ""
            sb.append("""<path d="$d" fill="$color" fill-opacity="${fmt(tone)}" stroke="none"$filterAttr/>""")
        }
        sb.append("</g>")
        return sb.toString()
    }

    internal fun renderFillDab(
        ins: JSONObject,
        attrs: SvgAttrs,
        contour: List<Pair<Double, Double>>,
        unit: Double,
        renderSeed: Long? = null,
        wild: Boolean = false,
        instructionSeed: Any? = null
    ): String? {
        if (contour.size < 3) return null
        val minX = contour.minOf { it.first }
        val maxX = contour.maxOf { it.first }
        val minY = contour.minOf { it.second }
        val maxY = contour.maxOf { it.second }
        val width = maxX - minX
        val height = maxY - minY
        if (width <= 0.0 || height <= 0.0) return null

        val centerX = (minX + maxX) * 0.5
        val centerY = (minY + maxY) * 0.5
        val alongX = width >= height
        val longAxis = max(width, height)
        val shortAxis = min(width, height)
        val travel = max(longAxis - shortAxis, longAxis * FILL_DAB_MIN_TRAVEL)
        val centerline = (0 until FILL_DAB_SAMPLES).map { index ->
            val t = index.toDouble() / (FILL_DAB_SAMPLES - 1).toDouble() - 0.5
            if (alongX) {
                (centerX + travel * t) to centerY
            } else {
                centerX to (centerY + travel * t)
            }
        }

        val weight = ins.optString("weight", "pen")
        val thinness = ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale }
        val baseWidth = max(ServerRendererStyle.strokeWidth(weight, unit, thinness), shortAxis)
        val seed = instructionSeed ?: seedForInstruction(ins, renderSeed)
        val stroke = ServerStrokeEngine.synthesizeAlong(
            centerline = centerline,
            baseWidth = baseWidth,
            weight = weight,
            seed = ServerRendererGeometry.fillStrokeSeed(seed, 0),
            closed = false,
            gridStep = gridStepPx(weight, unit),
            wild = wild
        )
        val d = ServerStrokeEngine.contourStrokePath(stroke)
        val opacity = attrs.fillOpacity ?: attrs.strokeOpacity
        val filterWeights = setOf("pencil", "crayon", "chalk", "brush_thin", "brush_thick")
        val filterAttr = if (weight in filterWeights) """ filter="url(#texture-$weight)"""" else ""
        return """<g class="fill-dab-v1"><path d="$d" fill="${attrs.stroke}" fill-opacity="${fmt(opacity)}" stroke="none"$filterAttr/></g>"""
    }

    /**
     * The interior, and whether it degraded to a region fill.
     *
     * Engine 22 puts an underlay under the marks and splits what goes on top:
     * scan lines where the tool is wide enough for them to become a field,
     * scattered marks where it is not. The underlay is common to both branches
     * -- the threshold decides only what sits on it -- because the works the
     * author named as striped were drawn with pen, crayon and pencil, and a
     * design that gave the underlay to the wide branch alone would reach none
     * of them.
     *
     * A dab is not a filled area, so it gets no underlay. It is one touch of
     * the tool, it has no scan strokes to let off the contour, and an underlay
     * would put back exactly the flat region fill engine 16 took out of tiny
     * shapes.
     */
    internal fun interiorFill(
        ins: JSONObject,
        attrs: SvgAttrs,
        contour: List<Pair<Double, Double>>,
        unit: Double,
        renderSeed: Long? = null,
        wild: Boolean = false,
        instructionSeed: Any? = null
    ): Pair<String?, Boolean> {
        val regionFill = if (ins.has("surface") && !ins.isNull("surface")) false else ins.optBoolean("filled", false)
        if (!regionFill) return null to false
        val weight = ins.optString("weight", "pen")
        if (!usesHandStroke(weight)) return null to true
        if (contour.size < 3) return null to true
        val seedStr = instructionSeed ?: seedForInstruction(ins, renderSeed)

        if (!ServerRendererFill.isScannable(ins, contour, unit, seedStr)) {
            val dab = renderFillDab(ins, attrs, contour, unit, renderSeed, wild, instructionSeed)
            return if (dab == null) null to true else dab to false
        }

        val scanBranch = ServerRendererFill.takesScanBranch(ins, unit)
        val marks = if (scanBranch) {
            renderFillStrokes(ins, attrs, contour, unit, renderSeed, wild, instructionSeed)
        } else {
            renderFillTexture(ins, attrs, contour, unit, renderSeed, wild, instructionSeed)
        }
        if (marks == null) {
            // Nothing survived the minimum-length filter. Fall through to the
            // dab rather than leaving a bare underlay: an area with no mark on
            // it is the flat fill this engine has been taking apart since 9.
            val dab = renderFillDab(ins, attrs, contour, unit, renderSeed, wild, instructionSeed)
            return if (dab == null) null to true else dab to false
        }

        // The field's mottling is the texture branch's, and only its. The scan
        // branch packs to the coverage the author set and its own strokes
        // already leave the field uneven, so a second mechanism here would be
        // doing what that one already does.
        val tones = if (scanBranch) emptyList() else ServerRendererFill.fieldTones(contour, seedStr)
        val opacity = attrs.fillOpacity ?: attrs.strokeOpacity
        val underlay = ServerRendererFill.underlaySvg(contour, attrs.stroke, opacity, tones)
        return """<g class="fill-v2">$underlay$marks</g>""" to false
    }

    private fun renderArcHandStroke(
        ins: JSONObject,
        attrs: SvgAttrs,
        cx: Double,
        cy: Double,
        r: Double,
        startDeg: Double,
        endDeg: Double,
        unit: Double,
        width: Double,
        height: Double,
        renderSeed: Long? = null,
        wild: Boolean = false
    ): String {
        val weight = ins.optString("weight", "pen")
        val gridStep = gridStepPx(weight, unit)
        val seedStr = seedForInstruction(ins, renderSeed)
        val seedLong = ServerRendererGeometry.seedToLong(seedStr)
        val variation = ins.optJSONObject("variation")
        val varied = ServerRendererGeometry.needsPathVariation(variation)

        val centerline = if (varied && variation != null) {
            ServerRendererGeometry.arcPointsWithVariation(cx, cy, r, startDeg, endDeg, variation, seedStr, ins, width, height, unit)
        } else {
            val arcLen = r * kotlin.math.abs(Math.toRadians(endDeg) - Math.toRadians(startDeg))
            val count = ServerRendererGeometry.strokeSampleCount(arcLen, unit)
            ServerRendererGeometry.arcPoints(cx, cy, r, startDeg, endDeg, count)
        }

        val baseWidth = ServerRendererStyle.strokeWidth(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale })
        val stroke = ServerStrokeEngine.synthesizeAlong(
            centerline = centerline,
            baseWidth = baseWidth,
            weight = weight,
            seed = seedLong,
            closed = false,
            gridStep = gridStep,
            wild = wild
        )

        val groupClass = "arc-stroke-v1 controls-${stroke.samples.size} events-${stroke.eventCount}"
        val sb = StringBuilder()
        sb.append("""<g class="$groupClass">""")
        addRasterBleed(sb, stroke.samples, stroke.gridStep, attrs.stroke)

        val isSolid = ins.optString("style", "solid") == "solid"
        val intentStrokeAttr = if (isSolid) {
            """stroke="none""""
        } else {
            val sw = attrs.strokeWidth * 0.42
            val dashAttr = if (!attrs.dash.isNullOrBlank()) """ stroke-dasharray="${attrs.dash}"""" else ""
            """stroke="${attrs.stroke}" stroke-width="${fmt(sw)}" stroke-linecap="${attrs.strokeLinecap}" stroke-opacity="${attrs.strokeOpacity}"$dashAttr"""
        }

        if (varied) {
            val ptsStr = centerline.joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
            sb.append("""<polyline points="$ptsStr" fill="none" $intentStrokeAttr/>""")
        } else {
            val d = ServerRendererGeometry.arcPathD(cx, cy, r, startDeg, endDeg)
            sb.append("""<path d="$d" fill="none" $intentStrokeAttr/>""")
        }

        val color = attrs.stroke
        val opacity = attrs.strokeOpacity
        val pathD = ServerStrokeEngine.contourStrokePath(stroke)
        val textureFilterWeights = setOf("pencil", "crayon", "chalk", "brush_thin", "brush_thick", "drypoint")
        val filterAttr = if (weight in textureFilterWeights && weight != "drypoint") """ filter="url(#texture-$weight)"""" else ""
        val fillOpacityStr = fmt(opacity)

        sb.append("""<path d="$pathD" fill="$color" fill-opacity="$fillOpacityStr" stroke="none"$filterAttr/>""")

        if (weight == "drypoint") {
            val offset = stroke.burrSide * baseWidth
            val normals = ServerStrokeEngine.centerlineNormals(centerline, closed = false)
            val burrPoints = centerline.zip(normals).map { (pt, normal) ->
                (pt.first + normal.first * offset) to (pt.second + normal.second * offset)
            }
            val ptsStr = burrPoints.joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
            val burrOpacityStr = fmt(stroke.burrOpacity)
            val burrWidthStr = fmt(baseWidth * 1.25)
            val filterDrypoint = if (weight in textureFilterWeights) """ filter="url(#texture-drypoint)"""" else ""
            sb.append("""<polygon points="$ptsStr" fill="none" stroke="$color" stroke-width="$burrWidthStr" stroke-opacity="$burrOpacityStr" stroke-linecap="round"$filterDrypoint/>""")
        }

        if (usesMaterialOutline(weight)) {
            // engine 28: the band's own samples, not the ideal arc. The geometric helper
            // stayed on `r + offset` and was left behind whenever the ink wandered, which
            // is the ghost the author saw beside the mark.
            val deltaDeg = ((endDeg - startDeg) % 360.0 + 360.0) % 360.0
            val arcLen = 2.0 * Math.PI * r * (deltaDeg / 360.0)
            val performed = stroke.samples.map { it.x to it.y }
            sb.append(ServerRendererMaterial.performedOutline(ins, attrs, performed, unit, closed = false, pathLenPx = arcLen, center = cx to cy, renderSeed = renderSeed, instructionSeed = seedForInstruction(ins, renderSeed)))
        }

        sb.append("</g>")
        return sb.toString()
    }

    private fun instructionExtent(ins: JSONObject): Double {
        if (ins.has("radius") && !ins.isNull("radius")) {
            return max(kotlin.math.abs(ins.optDouble("radius")), 1e-9)
        }
        val size = ins.optJSONArray("size")
        if (size != null) {
            return max(kotlin.math.hypot(size.optDouble(0), size.optDouble(1)), 1e-9)
        }
        val from = ins.optJSONArray("from_") ?: ins.optJSONArray("from")
        val to = ins.optJSONArray("to")
        if (from != null && to != null) {
            return max(
                kotlin.math.hypot(
                    to.optDouble(0) - from.optDouble(0),
                    to.optDouble(1) - from.optDouble(1),
                ),
                1e-9,
            )
        }
        return 1.0
    }

    private fun scaleInstruction(ins: JSONObject, scale: Double): JSONObject {
        val copy = copyJsonObject(ins)
        if (kotlin.math.abs(scale - 1.0) < 1e-12) return copy
        val (ax, ay) = anchor(copy)
        val fromKey = if (copy.has("from_")) "from_" else "from"
        val from = copy.optJSONArray(fromKey)
        val to = copy.optJSONArray("to")
        if (from != null && to != null) {
            copy.put(
                fromKey,
                JSONArray(
                    listOf(
                        ax + (from.optDouble(0) - ax) * scale,
                        ay + (from.optDouble(1) - ay) * scale,
                    )
                ),
            )
            copy.put(
                "to",
                JSONArray(
                    listOf(
                        ax + (to.optDouble(0) - ax) * scale,
                        ay + (to.optDouble(1) - ay) * scale,
                    )
                ),
            )
        }
        if (copy.has("radius") && !copy.isNull("radius")) {
            copy.put("radius", copy.optDouble("radius") * scale)
        }
        val size = copy.optJSONArray("size")
        if (size != null) {
            copy.put(
                "size",
                JSONArray(listOf(size.optDouble(0) * scale, size.optDouble(1) * scale)),
            )
        }
        return copy
    }

    private fun compositeMemberCopy(
        member: JSONObject,
        sourceAnchor: Pair<Double, Double>,
        targetHead: JSONObject,
        rotationDelta: Double,
        scale: Double,
        color: String?,
    ): JSONObject {
        val scaled = scaleInstruction(member, scale)
        val memberAnchor = anchor(scaled)
        val dx = memberAnchor.first - sourceAnchor.first
        val dy = memberAnchor.second - sourceAnchor.second
        val radians = Math.toRadians(rotationDelta)
        val rotated = (
            dx * kotlin.math.cos(radians) - dy * kotlin.math.sin(radians)
        ) to (
            dx * kotlin.math.sin(radians) + dy * kotlin.math.cos(radians)
        )
        val targetAnchor = anchor(targetHead)
        val moved = moveAnchorTo(
            scaled,
            (targetAnchor.first + rotated.first) to (targetAnchor.second + rotated.second),
            keepRelation = true,
        )
        moved.remove("arrangement")
        if (rotationDelta != 0.0) {
            moved.put("rotation", member.optDouble("rotation", 0.0) + rotationDelta)
        }
        if (color != null) moved.put("color", color)
        return moved
    }

    private fun expandCompositeGroups(
        instructions: JSONArray,
        placementSeed: Long?,
        performanceSeed: Long?,
        canvas: CanvasSize,
    ): JSONArray {
        val result = JSONArray()
        var index = 0
        while (index < instructions.length()) {
            val head = instructions.optJSONObject(index) ?: break
            val arrangement = head.optJSONObject("arrangement")
            val groupSize = arrangement?.optInt("group_size", 1) ?: 1
            if (arrangement == null || groupSize <= 1 || index + groupSize > instructions.length()) {
                result.put(copyJsonObject(head))
                index += 1
                continue
            }
            var preparedHead = copyJsonObject(head)
            if (performanceSeed != null) {
                preparedHead = resolveAtRegion(preparedHead, performanceSeed, index, canvas)
            }
            val copies = expandArrangement(preparedHead, placementSeed, canvas, performanceSeed)
            val sourceAnchor = anchor(preparedHead)
            val sourceRotation = preparedHead.optDouble("rotation", 0.0)
            val sourceExtent = instructionExtent(preparedHead)
            val hasCycle = (arrangement.optJSONArray("color_cycle")?.length() ?: 0) > 0
            for (copyHead in copies) {
                result.put(copyHead)
                val rotationDelta = copyHead.optDouble("rotation", 0.0) - sourceRotation
                val scale = instructionExtent(copyHead) / sourceExtent
                val color = if (hasCycle) copyHead.optString("color", "black") else null
                for (memberOffset in 1 until groupSize) {
                    val member = instructions.getJSONObject(index + memberOffset)
                    result.put(
                        compositeMemberCopy(
                            member,
                            sourceAnchor,
                            copyHead,
                            rotationDelta,
                            scale,
                            color,
                        )
                    )
                }
            }
            index += groupSize
        }
        return result
    }

    private fun resolvePerformanceScore(instructions: JSONArray, renderSeed: Long?, canvas: CanvasSize?): JSONArray {
        if (renderSeed == null) return instructions
        val result = JSONArray()
        val resolved = mutableListOf<JSONObject>()
        for (i in 0 until instructions.length()) {
            val original = instructions.optJSONObject(i) ?: continue
            var ins = JSONObject(original.toString())
            val arr = ins.optJSONObject("arrangement")
            if (arr != null && arr.optString("layout") == "grid") {
                ins.remove("relation")
            } else {
                ins = resolveAtRegion(ins, renderSeed, i, canvas)
                ins = resolveRelation(ins, resolved, renderSeed, i)
            }
            resolved.add(ins)
            result.put(ins)
        }
        return result
    }

    internal fun resolveAtRegion(ins: JSONObject, seed: Long, index: Int, canvas: CanvasSize?): JSONObject {
        val at = ins.optJSONObject("at") ?: return ins
        val region = at.optJSONArray("region") ?: return ins
        if (region.length() < 4) return ins
        val x0 = region.getDouble(0)
        val y0 = region.getDouble(1)
        val x1 = region.getDouble(2)
        val y1 = region.getDouble(3)
        val x = x0 + (x1 - x0) * ServerRendererGeometry.hash01(index, seed, "region-x")
        val y = y0 + (y1 - y0) * ServerRendererGeometry.hash01(index, seed, "region-y")
        return moveAnchorTo(ins, x to y, keepRelation = true)
    }

    private fun resolveRelation(ins: JSONObject, previous: List<JSONObject>, seed: Long, index: Int): JSONObject {
        val rel = ins.optJSONObject("relation") ?: return ins
        val type = rel.optString("type", "")
        if (type == "touching") {
            return resolveTouchingRelation(ins, previous, seed, index)
        }
        if (type == "between" && previous.size < 2) {
            ins.remove("relation")
            return ins
        }
        if (type != "between" && previous.isEmpty()) {
            ins.remove("relation")
            return ins
        }
        val prev = previous.lastOrNull() ?: return ins
        val prevCenter = instructionCenter(prev, seed, index - 1)
        val prevRadius = instructionRadius(prev, seed, index - 1)
        val gapStr = rel.optString("gap", "medium")
        val gap = relationGap(seed, index, gapStr)

        val target = when (type) {
            "between" -> {
                val other = previous.getOrNull(previous.size - 2) ?: return ins
                val otherCenter = instructionCenter(other, seed, index - 2)
                val jitter = 0.08 * (ServerRendererGeometry.hash01(index, seed, "between-jitter") - 0.5)
                clamp01((prevCenter.first + otherCenter.first) / 2.0 + jitter) to clamp01((prevCenter.second + otherCenter.second) / 2.0 - jitter)
            }
            "along" -> {
                val pPrimitive = prev.optString("primitive", "")
                if (pPrimitive == "line" && prev.has("from") && prev.has("to")) {
                    val geom = canvasEndpointGeometry(prev, seed, index - 1)
                    if (geom != null) {
                        val (lineStart, lineEnd) = geom[0] to geom[1]
                        val t = 0.18 + 0.64 * ServerRendererGeometry.hash01(index, seed, "along-t")
                        val lx = lineStart.first + (lineEnd.first - lineStart.first) * t
                        val ly = lineStart.second + (lineEnd.second - lineStart.second) * t
                        val dx = lineEnd.first - lineStart.first
                        val dy = lineEnd.second - lineStart.second
                        val len = kotlin.math.max(kotlin.math.hypot(dx, dy), 1e-9)
                        val ox = -dy / len * gap
                        val oy = dx / len * gap
                        val side = if (ServerRendererGeometry.hash01(index, seed, "along-side") < 0.5) -1.0 else 1.0
                        clamp01(lx + ox * side) to clamp01(ly + oy * side)
                    } else {
                        val angle = 2.0 * Math.PI * ServerRendererGeometry.hash01(index, seed, "along-angle")
                        clamp01(prevCenter.first + kotlin.math.cos(angle) * (prevRadius + gap)) to clamp01(prevCenter.second + kotlin.math.sin(angle) * (prevRadius + gap))
                    }
                } else if (pPrimitive == "cloudform" && prev.has("center") && prev.has("size")) {
                    val pCenter = prev.getJSONArray("center")
                    val pSize = prev.getJSONArray("size")
                    val contour = ServerRendererGeometry.generateCloudformContour(
                        center = pCenter.getDouble(0) to pCenter.getDouble(1),
                        size = pSize.getDouble(0) to pSize.getDouble(1),
                        performanceSeed = seedForInstruction(prev, seed),
                        instructionIndex = index - 1,
                        markIndex = 0,
                        variation = prev.optJSONObject("variation"),
                        weight = prev.optString("weight", "pen")
                    )
                    val ptIdx = (ServerRendererGeometry.hash01(index, seed, "along-cloudform") * contour.points.size).toInt()
                    val pt = contour.points[ptIdx % contour.points.size]
                    val rot = prev.optDouble("rotation", 0.0)
                    val (px, py) = rotatePoint(pt, pCenter.getDouble(0) to pCenter.getDouble(1), rot)
                    val dx = px - prevCenter.first
                    val dy = py - prevCenter.second
                    val dist = kotlin.math.max(kotlin.math.hypot(dx, dy), 1e-9)
                    clamp01(px + dx / dist * gap) to clamp01(py + dy / dist * gap)
                } else {
                    val angle = 2.0 * Math.PI * ServerRendererGeometry.hash01(index, seed, "along-angle")
                    clamp01(prevCenter.first + kotlin.math.cos(angle) * (prevRadius + gap)) to clamp01(prevCenter.second + kotlin.math.sin(angle) * (prevRadius + gap))
                }
            }
            "cutting" -> {
                val targetCenter = prevCenter
                if (ins.optString("primitive", "") == "line") {
                    val angle = 2.0 * Math.PI * ServerRendererGeometry.hash01(index, seed, "cut-angle")
                    val length = 0.28 + 0.18 * ServerRendererGeometry.hash01(index, seed, "cut-length")
                    ins.remove("relation")
                    ins.remove("at")
                    ins.put("from", JSONArray(listOf(
                        clamp01(targetCenter.first - kotlin.math.cos(angle) * length / 2.0),
                        clamp01(targetCenter.second - kotlin.math.sin(angle) * length / 2.0)
                    )))
                    ins.put("to", JSONArray(listOf(
                        clamp01(targetCenter.first + kotlin.math.cos(angle) * length / 2.0),
                        clamp01(targetCenter.second + kotlin.math.sin(angle) * length / 2.0)
                    )))
                    return ins
                }
                targetCenter
            }
            else -> { // not_touching
                val ownRadius = instructionRadius(ins, seed, index)
                val distance = prevRadius + ownRadius + gap
                val angle = 2.0 * Math.PI * ServerRendererGeometry.hash01(index, seed, "not-touching-angle")
                clamp01(prevCenter.first + kotlin.math.cos(angle) * distance) to clamp01(prevCenter.second + kotlin.math.sin(angle) * distance)
            }
        }
        return moveAnchorTo(ins, target)
    }

    private fun resolveTouchingRelation(ins: JSONObject, previous: List<JSONObject>, seed: Long, index: Int): JSONObject {
        val primitive = ins.optString("primitive", "")
        if (primitive !in setOf("line", "arc") || previous.isEmpty()) {
            ins.remove("relation")
            return ins
        }
        val prior = previous.last()
        if (prior.optString("primitive", "") !in setOf("line", "arc")) {
            ins.remove("relation")
            return ins
        }
        val priorGeom = canvasEndpointGeometry(prior, seed, index - 1)
        if (priorGeom == null) {
            ins.remove("relation")
            return ins
        }
        val start = priorGeom[0]
        val end = priorGeom[1]
        ins.remove("relation")
        ins.put("rotation", JSONObject.NULL)

        if (primitive == "line") {
            ins.put("from", JSONArray(listOf(start.first, start.second)))
            ins.put("to", JSONArray(listOf(end.first, end.second)))
            return ins
        }

        val ownSagitta = performedArcSagitta(ins, seed, index)
        if (ownSagitta == null || kotlin.math.abs(ownSagitta) <= 1e-12) {
            return ins
        }
        var sagitta = ownSagitta
        if (prior.optString("primitive", "") == "arc") {
            val priorSagitta = performedArcSagitta(prior, seed, index - 1)
            if (priorSagitta != null && kotlin.math.abs(priorSagitta) > 1e-12) {
                sagitta = -Math.copySign(kotlin.math.abs(ownSagitta), priorSagitta)
            }
        }
        try {
            val geom = ServerRendererGeometry.arcFromEndpointsAndSagitta(start, end, sagitta)
            ins.put("center", JSONArray(listOf(geom.center.first, geom.center.second)))
            ins.put("radius", geom.radius)
            ins.put("angle_start", geom.angleStart)
            ins.put("angle_end", geom.angleEnd)
        } catch (e: Exception) {
            // failed
        }
        return ins
    }

    private fun performedArcSagitta(ins: JSONObject, seed: Long, index: Int): Double? {
        if (ins.optString("primitive", "") != "arc" || !ins.has("center") || !ins.has("radius") || !ins.has("angle_start") || !ins.has("angle_end")) return null
        val endpoints = canvasEndpointGeometry(ins, seed, index) ?: return null
        val start = endpoints[0]
        val end = endpoints[1]
        val angleStart = ins.getDouble("angle_start")
        val angleEnd = ins.getDouble("angle_end")
        val delta = ServerRendererGeometry.minorArcDelta(angleStart, angleEnd)
        val center = ins.getJSONArray("center")
        val cx = center.getDouble(0)
        val cy = center.getDouble(1)
        val r = ins.getDouble("radius")
        val rot = ins.optDouble("rotation", 0.0)
        val localApex = ServerRendererGeometry.arcPoint(cx to cy, r, angleStart + delta / 2.0)
        val apex = rotatePoint(localApex, cx to cy, rot)
        val chordX = end.first - start.first
        val chordY = end.second - start.second
        val length = kotlin.math.hypot(chordX, chordY)
        if (length <= 1e-12) return null
        val mx = (start.first + end.first) / 2.0
        val my = (start.second + end.second) / 2.0
        val nx = -chordY / length
        val ny = chordX / length
        return (apex.first - mx) * nx + (apex.second - my) * ny
    }

    private fun canvasEndpointGeometry(ins: JSONObject, seed: Long, index: Int): Array<Pair<Double, Double>>? {
        val primitive = ins.optString("primitive", "")
        val rot = ins.optDouble("rotation", 0.0)
        if (primitive == "line" && ins.has("from") && ins.has("to")) {
            val from = ins.getJSONArray("from")
            val to = ins.getJSONArray("to")
            val p1 = from.getDouble(0) to from.getDouble(1)
            val p2 = to.getDouble(0) to to.getDouble(1)
            val anchor = ((p1.first + p2.first) / 2.0) to ((p1.second + p2.second) / 2.0)
            val r1 = rotatePoint(p1, anchor, rot)
            val r2 = rotatePoint(p2, anchor, rot)
            return arrayOf(r1, r2)
        }
        if (primitive == "arc" && ins.has("center") && ins.has("radius") && ins.has("angle_start") && ins.has("angle_end")) {
            val center = ins.getJSONArray("center")
            val cx = center.getDouble(0)
            val cy = center.getDouble(1)
            val r = ins.getDouble("radius")
            val aStart = ins.getDouble("angle_start")
            val aEnd = ins.getDouble("angle_end")
            val p1 = ServerRendererGeometry.arcPoint(cx to cy, r, aStart)
            val p2 = ServerRendererGeometry.arcPoint(cx to cy, r, aEnd)
            val r1 = rotatePoint(p1, cx to cy, rot)
            val r2 = rotatePoint(p2, cx to cy, rot)
            return arrayOf(r1, r2)
        }
        return null
    }

    private fun instructionCenter(ins: JSONObject, seed: Long, index: Int): Pair<Double, Double> {
        val p = ins.optString("primitive", "")
        if (ins.has("center") && !ins.isNull("center")) {
            val c = ins.getJSONArray("center")
            return c.getDouble(0) to c.getDouble(1)
        }
        if (ins.has("position") && !ins.isNull("position")) {
            val pos = ins.getJSONArray("position")
            val size = ins.optJSONArray("size")
            val w = size?.optDouble(0, 0.24) ?: 0.24
            val h = size?.optDouble(1, 0.24) ?: 0.24
            return (pos.getDouble(0) + w / 2.0) to (pos.getDouble(1) + h / 2.0)
        }
        if (p == "line" && ins.has("from") && ins.has("to")) {
            val f = ins.getJSONArray("from")
            val t = ins.getJSONArray("to")
            return ((f.getDouble(0) + t.getDouble(0)) / 2.0) to ((f.getDouble(1) + t.getDouble(1)) / 2.0)
        }
        return 0.5 to 0.5
    }

    private fun instructionRadius(ins: JSONObject, seed: Long, index: Int): Double {
        if (ins.has("radius") && !ins.isNull("radius")) return ins.getDouble("radius")
        if (ins.has("size") && !ins.isNull("size")) {
            val s = ins.getJSONArray("size")
            return kotlin.math.max(s.optDouble(0, 0.2), s.optDouble(1, 0.2)) / 2.0
        }
        return 0.1
    }

    private fun relationGap(seed: Long, index: Int, gap: String): Double {
        val (lo, hi) = when (gap) {
            "narrow" -> 0.02 to 0.05
            "wide" -> 0.15 to 0.30
            else -> 0.06 to 0.12
        }
        return lo + (hi - lo) * ServerRendererGeometry.hash01(index, seed, "relation-gap")
    }

    private fun moveAnchorTo(ins: JSONObject, target: Pair<Double, Double>, keepRelation: Boolean = false): JSONObject {
        if (!keepRelation) ins.remove("relation")
        ins.remove("at")
        val primitive = ins.optString("primitive", "")
        val current = instructionCenter(ins, 0L, 0)
        val dx = target.first - current.first
        val dy = target.second - current.second
        if (primitive == "line" && ins.has("from") && ins.has("to")) {
            val f = ins.getJSONArray("from")
            val t = ins.getJSONArray("to")
            ins.put("from", JSONArray(listOf(clamp01(f.getDouble(0) + dx), clamp01(f.getDouble(1) + dy))))
            ins.put("to", JSONArray(listOf(clamp01(t.getDouble(0) + dx), clamp01(t.getDouble(1) + dy))))
        } else if (ins.has("center") && !ins.isNull("center")) {
            ins.put("center", JSONArray(listOf(clamp01(target.first), clamp01(target.second))))
        } else if (primitive in setOf("square", "triangle")) {
            if (ins.has("position") && !ins.isNull("position")) {
                val pos = ins.getJSONArray("position")
                ins.put("position", JSONArray(listOf(clamp01(pos.getDouble(0) + dx), clamp01(pos.getDouble(1) + dy))))
            } else {
                val size = ins.optJSONArray("size") ?: JSONArray(listOf(0.2, 0.2))
                val w = size.optDouble(0, 0.2)
                val h = size.optDouble(1, 0.2)
                ins.put("size", size)
                ins.put("position", JSONArray(listOf(clamp01(target.first - w / 2.0), clamp01(target.second - h / 2.0))))
            }
        }
        return ins
    }

    private fun rotatePoint(point: Pair<Double, Double>, center: Pair<Double, Double>, degrees: Double): Pair<Double, Double> {
        val rad = Math.toRadians(degrees)
        val cos = kotlin.math.cos(rad)
        val sin = kotlin.math.sin(rad)
        val dx = point.first - center.first
        val dy = point.second - center.second
        return (center.first + dx * cos - dy * sin) to (center.second + dx * sin + dy * cos)
    }

    private fun gridStepPx(weight: String, unit: Double): Double {
        val grammar = GRAMMARS[weight] ?: return 0.0
        if (grammar.quantize <= 0.0) return 0.0
        return unit * grammar.quantize
    }

    private fun addRasterBleed(sb: StringBuilder, samples: List<StrokeSample>, gridStep: Double, color: String) {
        if (gridStep <= 0.0) return
        val half = gridStep / 2.0
        for (sample in samples) {
            if (sample.residual <= 0.0) continue
            val x = ServerStrokeEngine.gridPoint(sample.x, gridStep)
            val y = ServerStrokeEngine.gridPoint(sample.y, gridStep)
            val opacity = RASTER_BLEED_OPACITY * Math.min(1.0, sample.residual / half)
            sb.append("""<rect x="${fmt(x - half)}" y="${fmt(y - half)}" width="${fmt(gridStep)}" height="${fmt(gridStep)}" fill="$color" fill-opacity="${fmt(opacity)}" stroke="none" class="raster-bleed"/>""")
        }
    }

    private fun sha256(value: String): String {
        return MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString("") { "%02x".format(it) }
    }
}

private const val RASTER_BLEED_OPACITY: Double = 0.45
