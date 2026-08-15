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

    // The material layer is a tone beside the mark, not a second mark: no stratum may be
    // wider than this share of the tool's own stroke. The tools that already state their
    // strata as a ratio chose 0.20-0.28 and the absolute ones land between 0.17 and 0.47,
    // so the cap is set where pencil and chalk already sit: it moves the two outliers and
    // leaves the rest untouched (author's ruling, 2026-08-09).
    internal const val MATERIAL_OUTLINE_MAX_WIDTH_RATIO = 0.33

    /** (offsetPx, absolute width px, baseWidth ratio, opacity, dasharray) -- all unit-relative. */
    private data class OutlineSpec(
        val offset: Double,
        val absWidth: Double,
        val widthRatio: Double,
        val opacity: Double,
        val dash: String
    )

    // The tools that own a material outline. `lineGroup` reads the same table as the closed
    // contours do, so a tool cannot come out clothed on a circle and bare on a line. burin
    // and drypoint are deliberately absent: they carry plate_tone and burr instead, which
    // are separate mechanisms.
    private val MATERIAL_OUTLINE_SPECS: Map<String, List<OutlineSpec>> = mapOf(
        "pencil" to listOf(
            OutlineSpec(-1.0, 0.45, 0.0, 0.24, "1,7"),
            OutlineSpec(1.2, 0.5, 0.0, 0.20, "1,5")
        ),
        "chalk" to listOf(
            OutlineSpec(-3.2, 1.2, 0.0, 0.30, "8,12,1,8"),
            OutlineSpec(3.6, 1.0, 0.0, 0.24, "5,10,1,6")
        ),
        "brush_thin" to listOf(
            OutlineSpec(-1.6, 1.0, 0.0, 0.32, "22,9"),
            OutlineSpec(1.8, 1.4, 0.0, 0.28, "14,8")
        ),
        "brush_thick" to listOf(
            OutlineSpec(-4.0, 0.0, 0.28, 0.36, "18,7,3,11"),
            OutlineSpec(3.2, 0.0, 0.22, 0.28, "11,9")
        ),
        "crayon" to listOf(
            OutlineSpec(-3.4, 0.0, 0.24, 0.24, "2,5,9,7"),
            OutlineSpec(-1.5, 0.0, 0.20, 0.20, "4,8"),
            OutlineSpec(2.4, 0.0, 0.22, 0.22, "2,5,9,7")
        ),
        // engine 15: the most used tool in production stops being a bare one. The trace
        // is the two tines of a split nib, running just outside the band edge at +/-1.40px.
        "pen" to listOf(
            OutlineSpec(-1.40, 0.38, 0.0, 0.24, "14,3"),
            OutlineSpec(1.40, 0.34, 0.0, 0.20, "12,4")
        ),
    )

    private val MATERIAL_OUTLINE_WEIGHTS = MATERIAL_OUTLINE_SPECS.keys

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

    /**
     * How far a stratum drifts off its own offset along the path.
     *
     * Strata that stay exactly parallel read as engraved rails rather than as a tool's own
     * edges. Both emitters (the straight tools and the performed contours) ask here, so
     * the amount is stated once and a test can bound the layer's distance to the ink
     * without restating the formula.
     */
    fun outlineWanderPx(offsetPx: Double, unit: Double): Double =
        0.35 * kotlin.math.abs(offsetPx) + 0.6 * (unit / 1000.0)

    /**
     * The coverage and grain a tool's dash pattern implies.
     *
     * The patterns in [MATERIAL_OUTLINE_SPECS] carry a tool's character -- the pen is
     * nearly continuous, the pencil is mostly gap -- and that tuning is worth keeping once
     * the cadence is gone. Coverage is the share of the path the pattern marked; grain is
     * its natural wavelength.
     */
    fun dashSpecStats(dash: String?): Pair<Double, Double> {
        if (dash.isNullOrBlank()) return Pair(1.0, 0.0)
        var values = dash.split(",").mapNotNull { it.trim().takeIf { s -> s.isNotEmpty() }?.toDouble() }
            .map { kotlin.math.abs(it) }
        if (values.isEmpty() || values.sum() <= 0.0) return Pair(1.0, 0.0)
        // An odd-length pattern swaps marks and gaps on every repeat, so read it twice.
        if (values.size % 2 == 1) values = values + values
        val marks = values.filterIndexed { i, _ -> i % 2 == 0 }
        val gaps = values.filterIndexed { i, _ -> i % 2 == 1 }
        val coverage = marks.sum() / values.sum()
        val grain = marks.sum() / marks.size + gaps.sum() / gaps.size
        return Pair(coverage, grain)
    }

    /** The paper's tooth at two scales, read along the path. Roughly 0..1. */
    fun contactField(t: Double, seed: Long): Double =
        0.62 * valueNoise1d(t, seed) + 0.38 * valueNoise1d(t * 2.7 + 13.1, seed + 977L)

    /**
     * Paper-contact decisions share the SVG's six-decimal length lattice (engine 29).
     * At engine 28 this is the identity: the lattice arrives with the next stage.
     */
    fun quantiseContactLength(value: Double): Double = value

    /**
     * Walk a polyline and emit a point every `step` px of arc length.
     *
     * `resamplePoints` picks by index, which is even only when the source vertices are.
     * The contact field is read against distance on the paper, so it needs a walk that is
     * even in length.
     */
    fun resampleByLength(
        points: List<Pair<Double, Double>>,
        step: Double,
        closed: Boolean
    ): List<Pair<Double, Double>> {
        val quantisedStep = quantiseContactLength(step)
        if (quantisedStep <= 0.0 || points.size < 2) return points.toList()
        val path = if (closed) points + listOf(points[0]) else points
        val out = mutableListOf(path[0])
        var carry = 0.0
        for (i in 0 until path.size - 1) {
            val (ax, ay) = path[i]
            val (bx, by) = path[i + 1]
            val seg = quantiseContactLength(Math.hypot(bx - ax, by - ay))
            if (seg <= 1e-9) continue
            var travelled = quantisedStep - carry
            while (travelled <= seg) {
                val f = travelled / seg
                out.add(Pair(ax + (bx - ax) * f, ay + (by - ay) * f))
                travelled += quantisedStep
            }
            carry = (carry + seg) % quantisedStep
        }
        return out
    }

    /**
     * The pieces of an outline where the tool actually met the paper.
     *
     * A dasharray repeats. However long the pattern, a long contour walks through it
     * several times and the eye finds the cadence -- and the material layer is not a dotted
     * line, it is where a tool dragged across a grain and kept losing the paper. So
     * presence is a smooth noise field read along the arc length, and the outline exists
     * where the field clears a threshold.
     *
     * The threshold is the (1 - coverage) quantile of the field's own samples, not a
     * constant: that way each tool keeps the share of the path its dash pattern used to
     * mark, while nothing about the spacing repeats. Fragments come back with a weight, so
     * the thinly-touching ones are fainter than the ones the tool bore down on.
     */
    fun contactFragments(
        points: List<Pair<Double, Double>>,
        coverage: Double,
        grainPx: Double,
        seed: Long,
        closed: Boolean
    ): List<Pair<List<Pair<Double, Double>>, Double>> {
        if (points.size < 2) return emptyList()
        if (grainPx <= 0.0 || coverage >= 0.999) return listOf(Pair(points.toList(), 1.0))

        val ring = if (closed) points.drop(1) + listOf(points[0]) else points.drop(1)
        var sum = 0.0
        for (i in ring.indices) {
            val a = points[i]
            val b = ring[i]
            sum += quantiseContactLength(Math.hypot(b.first - a.first, b.second - a.second))
        }
        val total = quantiseContactLength(sum)
        if (total <= 1e-6) return emptyList()
        val grain = quantiseContactLength(grainPx)
        // Three samples per grain resolves a skip; the cap keeps a long contour from
        // turning into thousands of SVG vertices.
        val step = quantiseContactLength(max(max(grain / 3.0, total / 600.0), 0.8))
        val walk = resampleByLength(points, step, closed)
        if (walk.size < 3) return listOf(Pair(points.toList(), 1.0))

        val field = DoubleArray(walk.size) { contactField(it * step / grain, seed) }
        val ordered = field.sortedArray()
        val index = kotlin.math.min(ordered.size - 1, max(0, ((1.0 - coverage) * ordered.size).toInt()))
        val threshold = ordered[index]
        val span = max(1e-6, ordered[ordered.size - 1] - threshold)

        val runs = mutableListOf<MutableList<Int>>()
        var current = mutableListOf<Int>()
        for (i in field.indices) {
            if (field[i] >= threshold) {
                current.add(i)
            } else if (current.isNotEmpty()) {
                runs.add(current)
                current = mutableListOf()
            }
        }
        if (current.isNotEmpty()) runs.add(current)
        // On a closed path the seam is not an end: a run that touches both ends is one
        // fragment that happens to be written in two halves.
        if (closed && runs.size > 1 && runs[0][0] == 0 && runs[runs.size - 1].last() == field.size - 1) {
            val merged = (runs[runs.size - 1] + runs[0]).toMutableList()
            runs[0] = merged
            runs.removeAt(runs.size - 1)
        }

        /**
         * Where the field crosses the threshold between two samples. Without this the ends
         * of every fragment land on a sample, so every length is a multiple of `step` and
         * the lengths themselves become the cadence -- the regularity comes back through
         * the sampling instead of through the pattern.
         */
        fun crossing(outside: Int, inside: Int): Pair<Double, Double> {
            val fOut = field[outside]
            val fIn = field[inside]
            if (kotlin.math.abs(fIn - fOut) < 1e-9) return walk[inside]
            val f = kotlin.math.min(1.0, max(0.0, (threshold - fOut) / (fIn - fOut)))
            val (ax, ay) = walk[outside]
            val (bx, by) = walk[inside]
            return Pair(ax + (bx - ax) * f, ay + (by - ay) * f)
        }

        val fragments = mutableListOf<Pair<List<Pair<Double, Double>>, Double>>()
        for (run in runs) {
            val piece = mutableListOf<Pair<Double, Double>>()
            run.forEach { piece.add(walk[it]) }
            if (run[0] - 1 >= 0) piece.add(0, crossing(run[0] - 1, run[0]))
            if (run.last() + 1 < field.size) piece.add(crossing(run.last() + 1, run.last()))
            if (piece.size < 2) continue
            var pieceSum = 0.0
            for (i in 0 until piece.size - 1) {
                pieceSum += quantiseContactLength(
                    Math.hypot(piece[i + 1].first - piece[i].first, piece[i + 1].second - piece[i].second)
                )
            }
            val length = quantiseContactLength(pieceSum)
            if (length < 0.6) continue
            val margin = run.sumOf { field[it] - threshold } / run.size
            val weight = kotlin.math.min(1.0, 0.55 + 0.75 * (margin / span))
            fragments.add(Pair(piece.toList(), weight))
        }
        return fragments
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

        val path = if (!centerline.isNullOrEmpty()) centerline else listOf(Pair(x1, y1), Pair(x2, y2))
        val out = StringBuilder()

        fun layerOpacity(v: Double): Double = outlineOpacity(v * opacityGain)
        fun layerOffset(amount: Double): Double = outlineOffsetPx(amount * scale * offsetGain, unit)

        // Each stratum gets its own seed, so its weave and its contact are out of step
        // with the others.
        //
        // engine 28: the dasharray is gone. Its pattern was long, but a pattern still
        // repeats, and this layer is the tool losing the paper's grain -- not a dotted
        // line (author's ruling, 2026-08-09). `mark` and `gap` now say what share of the
        // line the tool held and at what wavelength, and the contact field decides where.
        fun emitLayer(amount: Double, layerAttrs: SvgAttrs, mark: Double, gap: Double, k: Int) {
            val offPx = layerOffset(amount)
            val layerSeed = seedInt + k * 7919L
            val pts = offsetPolyline(
                path, offPx,
                wander = outlineWanderPx(offPx, unit),
                wanderPeriod = 60.0 * scale,
                seed = layerSeed
            )
            // Same reason as `outlineAttrs`: the tool's own texture dash would cut the
            // fragments a second time, on a fixed cadence.
            val la = layerAttrs.copy(dash = null)
            val baseOpacity = la.strokeOpacity
            for ((piece, fragmentWeight) in contactFragments(
                pts, mark / max(1e-6, mark + gap), (mark + gap) * scale, layerSeed, closed = false
            )) {
                val ptsStr = piece.joinToString(" ") { "${ServerRendererGeometry.fmt(it.first)},${ServerRendererGeometry.fmt(it.second)}" }
                val frag = la.copy(strokeOpacity = baseOpacity * fragmentWeight)
                out.append("""<polyline points="$ptsStr" fill="none" ${frag.toSvgAttributes(includeFill = false)} class="material-outline stratum-$k"/>""")
            }
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

    /**
     * Offset the performed centreline along its normal by `offset`; positive is outward.
     *
     * The normal's sign flips with the contour's winding (a circle points inward, an arc
     * outward), so it is settled once by a vote against the figure's centre, which is what
     * lines the strata up with the geometric helpers' `r + offset`.
     *
     * `wander` adds a low-frequency drift to the offset along the arc length, the same way
     * [offsetPolyline] does it for the straight tools: strata that stay exactly parallel
     * read as engraved rails rather than as a tool's own edges.
     */
    fun offsetPerformedPath(
        path: List<Pair<Double, Double>>,
        offset: Double,
        closed: Boolean,
        center: Pair<Double, Double>,
        wander: Double = 0.0,
        wanderPeriod: Double = 1.0,
        seed: Long = 0L
    ): List<Pair<Double, Double>> {
        val normals = ServerStrokeEngine.centerlineNormals(path, closed)
        var votes = 0
        for (i in path.indices) {
            val (x, y) = path[i]
            val (nx, ny) = normals[i]
            if (nx * (x - center.first) + ny * (y - center.second) >= 0.0) votes++ else votes--
        }
        val sign = if (votes >= 0) 1.0 else -1.0
        val out = mutableListOf<Pair<Double, Double>>()
        var arc = 0.0
        for (i in path.indices) {
            val (x, y) = path[i]
            val (nx, ny) = normals[i]
            var off = offset
            if (wander != 0.0) {
                off += wander * (valueNoise1d(arc / max(1e-6, wanderPeriod), seed) * 2.0 - 1.0)
            }
            out.add(Pair(x + nx * off * sign, y + ny * off * sign))
            if (i + 1 < path.size) {
                arc += Math.hypot(path[i + 1].first - x, path[i + 1].second - y)
            }
        }
        return out
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
        val seedStr = instructionSeed
            ?: java.lang.Long.toUnsignedString(ServerRendererGeometry.seedForInstruction(ins, renderSeed))
        val seedLong = seedStr.toULongOrNull()?.toLong() ?: 0L
        val scale = unit / 1000.0
        val out = StringBuilder()
        materialOutlineProfile(weight, unit, ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale })
            .forEachIndexed { k, (offset, width, opacity, dash) ->
                val layerSeed = seedLong + k * 7919L
                val (coverage, grain) = dashSpecStats(dash)
                val pts = offsetPerformedPath(
                    path, offset, closed, center,
                    wander = outlineWanderPx(offset, unit),
                    wanderPeriod = 60.0 * scale,
                    seed = layerSeed
                )
                // engine 28: the dasharray is gone. Its pattern was long, but a pattern
                // still repeats, and this layer is the tool losing the paper's grain --
                // not a dotted line. The dash spec now says what share of the path the
                // tool held and at what wavelength, and the contact field decides where.
                for ((piece, fragmentWeight) in contactFragments(pts, coverage, grain * scale, layerSeed, closed)) {
                    val ptsStr = piece.joinToString(" ") { "${ServerRendererGeometry.fmt(it.first)},${ServerRendererGeometry.fmt(it.second)}" }
                    val outline = ServerRendererStyle.outlineAttrs(attrs, width, opacity * fragmentWeight, null)
                    out.append("""<polyline points="$ptsStr" ${outline.toSvgAttributes()} class="material-outline stratum-$k"/>""")
                }
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


    /**
     * A stratum's (offset, width, opacity, dasharray). All unit-relative.
     *
     * A line drawn thin wears a material layer that thins with it, so the base is the
     * instruction's own width: pinning it to the nominal one would thin the ink alone and
     * leave the material behind.
     */
    internal fun materialOutlineProfile(weight: String, unit: Double, thinness: String? = null): List<OutlineProfile> {
        val spec = MATERIAL_OUTLINE_SPECS[weight] ?: return emptyList()
        val scale = unit / 1000.0
        val baseWidth = ServerRendererStyle.strokeWidth(weight, unit, thinness)
        val nominalWidth = ServerRendererStyle.strokeWidth(weight, unit)
        val half = baseWidth / 2.0
        return spec.map { s ->
            // engine 28: both of these are read against the tool's own mark now. While the
            // layer sat on the ideal geometry its distance to the band was incidental, so
            // the table could carry absolute numbers and nobody saw what they came to
            // beside the ink. Riding the band, two of them showed.
            //
            // The cap reads the tool's NOMINAL stroke, not the thinned one: how wide the
            // tone is belongs to the tool's own grain, and paper tooth and powder do not
            // get finer because the line was drawn finer. Where it SITS is a different
            // question, and that one is asked of the actual mark -- which is why `half`
            // below comes from `baseWidth` and the cap here comes from `nominalWidth`.
            val width = kotlin.math.min(
                s.absWidth * scale + baseWidth * s.widthRatio,
                nominalWidth * MATERIAL_OUTLINE_MAX_WIDTH_RATIO
            )
            // A stratum centred inside the mark cannot be tone beside it; it only thickens
            // the mark. Put it on the edge and let the wander take it out.
            val raw = outlineOffsetPx(s.offset * scale * OUTLINE_OFFSET_GAIN, unit)
            val placed = java.lang.Math.copySign(max(kotlin.math.abs(raw), half), raw)
            OutlineProfile(placed, width, outlineOpacity(s.opacity * OUTLINE_OPACITY_GAIN), scaleDash(s.dash, scale))
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

