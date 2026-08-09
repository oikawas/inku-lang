package app.inku.mobile.render

import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Render engine 22: the underlay, and the branch above it.
 *
 * Kotlin port of the `# --- render engine 22` section of
 * server/src/inku_server/renderer.py. Until here the stroke WAS the fill, so a
 * stroke that crossed the outline spilled paint outside the shape and every
 * scan line had to be cut at the intersection -- the third regularity the eye
 * reads as a raster. With the boundary held by an underlay, the marks are free.
 */
object ServerRendererFill {

    // The one threshold. Which marks go on top of the underlay is decided by
    // how much of the field one pass of scan lines would cover -- the stroke
    // width over the scan pitch -- and by nothing else. A list of tool names
    // would cut the frozen corpus identically today and diverge the moment a
    // description asks for a thin crayon.
    const val COVERAGE_BRANCH = 0.2
    // What the scan branch packs to once it has an underlay under it.
    const val COVERAGE_TARGET = 0.9
    // The underlay's opacity as a ratio of the marks' own, never an absolute:
    // a work whose description asked for a pale fill keeps a pale underlay.
    const val UNDERLAY_OPACITY_RATIO = 0.75

    // The three amplitudes that turn a raster into a hand. The tool picks its
    // place in each band through `ToolGrammar.fillHand`, which is 0 for the
    // machines, so all three collapse to nothing there.
    const val ANGLE_MIN_DEG = 2.2
    const val ANGLE_SPAN_DEG = 1.6
    const val PITCH_CV_MIN = 0.24
    const val PITCH_CV_SPAN = 0.10
    // How far each end of a scan stroke reaches past the contour, or falls
    // short of it, in multiples of the tool's own width. The sign is drawn per
    // end, so one stroke can overshoot at the landing and undershoot at the
    // lift. A width and not a length: "how precisely can this tool stop where
    // it means to" belongs to the tool, not to how big the shape is.
    const val REACH_WIDTHS_MIN = 1.0
    const val REACH_WIDTHS_SPAN = 0.5

    // The texture branch. Below the threshold the tool is too thin for parallel
    // lines to become a field -- a pencil rubs a tone rather than ruling one.
    // 1.0 lays the same total stroke length one classic scan pass laid.
    const val TEXTURE_DENSITY = 1.0
    // How much darker a mark is than the field it sits on. The marks rise out
    // of the fill; they are not drawn on top of it.
    const val TEXTURE_CONTRAST = 1.10
    // Half-width of the per-mark draw around that contrast. Centred on it, so
    // the MEAN tone of the branch is unchanged and only its spread is new. The
    // floor of the band is 1.0: a mark paler than its field still darkens it,
    // because the two are composited. Light comes from the field being uneven.
    const val TEXTURE_TONE_SPREAD = 0.10

    // The field's own mottling. A flat field is what made a thin-tool fill read
    // as one even tone, and varying the MARKS did not move it. The pale patches
    // are HOLES in a layer rather than dark patches drawn on top: a patch on
    // top would put a second colour into the fill, while a hole shows whatever
    // is under the work, which is what a thinner load of ink does.
    const val FIELD_TONE_DROP = 0.10
    const val FIELD_TONE_LAYERS = 2
    // A patch is a NEST of rings, each ring a hole in its own layer, so its rim
    // comes down in as many steps as there are rings instead of in one. Not a
    // filter: filters are display-only and the mottling has to survive the
    // `compat` and `editable` profiles.
    const val FIELD_TONE_RINGS = 3
    const val FIELD_TONE_RING_STEP = 0.22
    const val FIELD_TONE_COUNT_MIN = 3
    const val FIELD_TONE_COUNT_SPAN = 3
    const val FIELD_TONE_RADIUS_MIN = 0.18
    const val FIELD_TONE_RADIUS_SPAN = 0.17
    const val FIELD_TONE_INSET = 0.04
    const val FIELD_TONE_WOBBLE = 0.24
    const val FIELD_TONE_ROUGHNESS = 0.10
    const val FIELD_TONE_SEGMENTS = 32
    // The scan branch's own contrast.
    const val SCAN_CONTRAST = 1.15

    // The machine's fill: a raster line, not a hatch. A dense core that bleeds
    // at its edges, with a faint shadow visible between the lines -- built out
    // of two real elements rather than a blur, because filters are display-only.
    // The halo is a fixed STEP below the core and not a fraction of it.
    const val RASTER_HALO_WIDTHS = 2.6
    const val RASTER_HALO_STEP = 0.10
    const val RASTER_CORE_WIDTHS = 0.55

    const val MIN_SCANLINES = 3
    const val MIN_STROKE_WIDTHS = 1.2

    private fun grammar(weight: String): ToolGrammar =
        GRAMMARS[weight] ?: GRAMMARS.getValue("pen")

    fun fillHand(ins: JSONObject): Double = grammar(ins.optString("weight", "pen")).fillHand

    /** The tool's own multiplier on whichever branch contrast applies. */
    fun fillContrast(ins: JSONObject): Double =
        grammar(ins.optString("weight", "pen")).fillContrast

    /**
     * How much of the field one pass of scan lines covers: width over pitch.
     *
     * A ratio of two lengths, so it does not move with the canvas: the same
     * instruction reaches the same branch on every aspect.
     */
    fun coverage(ins: JSONObject, unit: Double): Double {
        val weight = ins.optString("weight", "pen")
        val thinness = ins.optString("thinness").takeIf { it in ServerRendererStyle.thinnessToWidthScale }
        return ServerRendererStyle.strokeWidth(weight, unit, thinness) /
            ServerRendererGeometry.fillScanSpacing(ins, unit)
    }

    /**
     * Scan lines at or above the coverage threshold, texture below it.
     *
     * A periodic tool keeps the scan branch whatever its coverage: exact
     * repetition is the computer's signature and the texture branch has no
     * regular placement to carry it. This reads the machine property the
     * grammar already declares; it is not a list of tool names.
     */
    fun takesScanBranch(ins: JSONObject, unit: Double): Boolean {
        if (grammar(ins.optString("weight", "pen")).periodic) return true
        return coverage(ins, unit) >= COVERAGE_BRANCH
    }

    /**
     * Half-width of the per-mark angle draw, in radians, from the tool's hand.
     *
     * The constants state a standard deviation, so the half-width of the
     * uniform draw that produces it is sqrt(3) times as wide. A machine draws
     * nothing: zero has to be exact, and `fillHand` is pinned at zero there.
     */
    fun angleAmplitude(hand: Double): Double {
        if (hand == 0.0) return 0.0
        return Math.toRadians(ANGLE_MIN_DEG + ANGLE_SPAN_DEG * hand) * sqrt(3.0)
    }

    /**
     * Is the shape big enough to be filled at all, or is it one touch?
     *
     * Measured at the classic pitch, not at the one the scan branch now packs
     * to: "too small to be scanned" is a property of the shape and the tool
     * that was settled in engine 16, and re-deciding it against a denser pitch
     * would quietly turn dabs back into fills.
     */
    fun isScannable(ins: JSONObject, contour: List<Pair<Double, Double>>, unit: Double, seed: Any): Boolean {
        val segments = ServerRendererGeometry.scanlineSegments(
            contour,
            ServerRendererGeometry.fillScanAngle(seed),
            ServerRendererGeometry.fillScanSpacing(ins, unit),
            seed
        )
        return segments.map { it.first }.toSet().size >= MIN_SCANLINES
    }

    fun polygonArea(contour: List<Pair<Double, Double>>): Double {
        var total = 0.0
        for (index in contour.indices) {
            val (ax, ay) = contour[index]
            val (bx, by) = contour[(index + 1) % contour.size]
            total += ax * by - bx * ay
        }
        return abs(total) / 2.0
    }

    /**
     * Where an infinite line through `point` runs inside the closed contour.
     *
     * Returned as entry/exit parameters along `direction`, in pairs, so a
     * concave form gives several spans and none of them crosses the void.
     * `scanlineSegments` cuts every row at one shared angle; this cuts one row
     * at its own, which is how "how far past the contour" gets measured against
     * the line the stroke actually travels.
     */
    fun lineSpans(
        contour: List<Pair<Double, Double>>,
        point: Pair<Double, Double>,
        direction: Pair<Double, Double>
    ): List<Pair<Double, Double>> {
        val (ux, uy) = direction
        val hits = mutableListOf<Double>()
        for (edge in contour.indices) {
            val (ax, ay) = contour[edge]
            val (bx, by) = contour[(edge + 1) % contour.size]
            val ex = bx - ax
            val ey = by - ay
            val denom = ux * ey - uy * ex
            if (abs(denom) < 1e-12) continue
            val dx = ax - point.first
            val dy = ay - point.second
            val tEdge = (dx * uy - dy * ux) / denom
            if (tEdge < 0.0 || tEdge >= 1.0) continue
            hits.add((dx + ex * tEdge) * ux + (dy + ey * tEdge) * uy)
        }
        hits.sort()
        val spans = mutableListOf<Pair<Double, Double>>()
        var i = 0
        while (i + 1 < hits.size) {
            spans.add(hits[i] to hits[i + 1])
            i += 2
        }
        return spans
    }

    /** The spans of a line through `point` that actually contain `point`. */
    private fun spansAcross(
        contour: List<Pair<Double, Double>>,
        point: Pair<Double, Double>,
        direction: Pair<Double, Double>
    ): Pair<Double, Double>? =
        lineSpans(contour, point, direction).firstOrNull { it.first <= 0.0 && 0.0 <= it.second }

    /**
     * A disc pulled out of round by two low harmonics and roughened per vertex.
     *
     * The harmonics are the patch's own shape and do not depend on `ring`, so
     * the rings of one patch are the same blob at different sizes. The
     * roughness does depend on it, and it MULTIPLIES the radius rather than
     * adding to it: that bounds one ring against the next by the ratio of their
     * scales alone, so a rough inner ring cannot cross out through a pinched
     * outer one.
     */
    fun wobblyBlob(
        cx: Double,
        cy: Double,
        radius: Double,
        seed: Any,
        index: Int,
        ring: Int = 0
    ): List<Pair<Double, Double>> {
        val h = ServerRendererGeometry::hash01
        val amp2 = FIELD_TONE_WOBBLE * (h(index, seed, "fill-blob-h2") - 0.5) * 2
        val amp3 = FIELD_TONE_WOBBLE * (h(index, seed, "fill-blob-h3") - 0.5) * 2
        val phase2 = h(index, seed, "fill-blob-p2") * 2 * Math.PI
        val phase3 = h(index, seed, "fill-blob-p3") * 2 * Math.PI
        val points = mutableListOf<Pair<Double, Double>>()
        for (step in 0 until FIELD_TONE_SEGMENTS) {
            val theta = step * 2 * Math.PI / FIELD_TONE_SEGMENTS
            val rough = (
                h(
                    (index * FIELD_TONE_SEGMENTS + step) * FIELD_TONE_RINGS + ring,
                    seed,
                    "fill-blob-edge"
                ) - 0.5
                ) * 2
            val r = radius *
                (1.0 + amp2 * sin(2 * theta + phase2) + amp3 * sin(3 * theta + phase3)) *
                (1.0 + FIELD_TONE_ROUGHNESS * rough)
            points.add((cx + cos(theta) * r) to (cy + sin(theta) * r))
        }
        return points
    }

    /**
     * Pull every vertex back inside the contour, along its own ray from `centre`.
     *
     * A hole that crosses the outline is not a hole: even-odd counts one
     * crossing out there and paints the region OUTSIDE the form. Clamping per
     * vertex keeps the patch's own shape wherever it already fitted.
     */
    fun clampInside(
        points: List<Pair<Double, Double>>,
        centre: Pair<Double, Double>,
        contour: List<Pair<Double, Double>>,
        inset: Double
    ): List<Pair<Double, Double>>? {
        val out = mutableListOf<Pair<Double, Double>>()
        for ((x, y) in points) {
            val dx = x - centre.first
            val dy = y - centre.second
            val distance = hypot(dx, dy)
            if (distance <= 1e-9) return null
            val ux = dx / distance
            val uy = dy / distance
            val span = spansAcross(contour, centre, ux to uy) ?: return null
            val limit = span.second - inset
            if (limit <= 0) return null
            val scale = min(1.0, limit / distance)
            out.add((centre.first + ux * distance * scale) to (centre.second + uy * distance * scale))
        }
        return out
    }

    /**
     * The paler places in the field, one layer per (set, ring).
     *
     * Isotropic on purpose: this is how much ink the ground took where the tool
     * passed, which belongs to the sheet and has no direction of its own. A
     * patch is kept only if ALL of its rings survive the clamp -- half a nest is
     * the single step this replaced.
     */
    fun fieldTonePatches(
        contour: List<Pair<Double, Double>>,
        seed: Any,
        shortSide: Double
    ): List<List<List<Pair<Double, Double>>>> {
        if (contour.size < 3 || shortSide <= 0) return emptyList()
        val h = ServerRendererGeometry::hash01
        val cx = contour.sumOf { it.first } / contour.size
        val cy = contour.sumOf { it.second } / contour.size
        val inset = shortSide * FIELD_TONE_INSET
        val layers = mutableListOf<List<List<Pair<Double, Double>>>>()
        for (layer in 0 until FIELD_TONE_LAYERS) {
            val count = FIELD_TONE_COUNT_MIN +
                (h(layer, seed, "fill-field-tone-count") * FIELD_TONE_COUNT_SPAN).toInt()
            val rings: List<MutableList<List<Pair<Double, Double>>>> =
                List(FIELD_TONE_RINGS) { mutableListOf() }
            for (step in 0 until count) {
                val index = layer * 64 + step
                val bearing = h(index, seed, "fill-field-tone-angle") * 2 * Math.PI
                val radius = shortSide *
                    (FIELD_TONE_RADIUS_MIN + FIELD_TONE_RADIUS_SPAN * h(index, seed, "fill-field-tone-radius"))
                val span = spansAcross(contour, cx to cy, cos(bearing) to sin(bearing)) ?: continue
                val place = span.second * h(index, seed, "fill-field-tone-place") * 0.6
                val centre = (cx + cos(bearing) * place) to (cy + sin(bearing) * place)
                val nest = mutableListOf<List<Pair<Double, Double>>>()
                for (ring in 0 until FIELD_TONE_RINGS) {
                    val blob = wobblyBlob(
                        centre.first,
                        centre.second,
                        radius * (1.0 - FIELD_TONE_RING_STEP * ring),
                        seed,
                        index,
                        ring
                    )
                    val clamped = clampInside(blob, centre, contour, inset) ?: break
                    nest.add(clamped)
                }
                if (nest.size < FIELD_TONE_RINGS) continue
                nest.forEachIndexed { ring, outline -> rings[ring].add(outline) }
            }
            layers.addAll(rings.filter { it.isNotEmpty() })
        }
        return layers
    }

    /** The pale patches of one texture-branch fill, in the picture's own units. */
    fun fieldTones(
        contour: List<Pair<Double, Double>>,
        seed: Any
    ): List<List<List<Pair<Double, Double>>>> {
        if (contour.isEmpty()) return emptyList()
        val xs = contour.map { it.first }
        val ys = contour.map { it.second }
        val shortSide = min(
            (xs.max() - xs.min()),
            (ys.max() - ys.min())
        )
        return fieldTonePatches(contour, seed, shortSide)
    }

    /**
     * The field itself, laid as a real element under whatever marks go on top.
     *
     * Both branches get one. Not a filter: an underlay built out of a filter
     * would make the fill VANISH in the `compat` and `editable` profiles.
     *
     * `tones` are the paler places, laid as holes in the layers stacked over a
     * darker base. Where every layer is present they composite to exactly the
     * flat opacity the field used to have, so the mottling does not move the
     * tone; where some are missing the field is paler by that many steps.
     */
    fun underlaySvg(
        contour: List<Pair<Double, Double>>,
        color: String,
        opacity: Double,
        tones: List<List<List<Pair<Double, Double>>>>
    ): String {
        val fmt = ServerRendererGeometry::fmt
        val field = opacity * UNDERLAY_OPACITY_RATIO
        if (tones.isEmpty()) {
            val points = contour.joinToString(" ") { "${fmt(it.first)},${fmt(it.second)}" }
            return """<polygon class="fill-underlay-v1" fill="$color" fill-opacity="${fmt(field)}" """ +
                """points="$points" stroke="none" />"""
        }
        val base = field * (1.0 - FIELD_TONE_DROP)
        val sb = StringBuilder("""<g class="fill-field-v2">""")
        sb.append(
            """<path class="fill-underlay-v1 field-base" d="${ServerStrokeEngine.polygonPath(contour)}" """ +
                """fill="$color" fill-opacity="${fmt(base)}" fill-rule="evenodd" stroke="none" />"""
        )
        // Solved so that the base under all the layers equals the flat field
        // exactly: (1 - base)(1 - each)^n = 1 - field.
        val rest = if (base < 1.0) (1.0 - field) / (1.0 - base) else 1.0
        val each = 1.0 - Math.pow(rest, 1.0 / tones.size)
        for (patches in tones) {
            val d = (listOf(ServerStrokeEngine.polygonPath(contour)) +
                patches.map { ServerStrokeEngine.polygonPath(it) }).joinToString(" ")
            sb.append(
                """<path class="fill-underlay-v1 tones-${patches.size}" d="$d" """ +
                    """fill="$color" fill-opacity="${fmt(each)}" fill-rule="evenodd" stroke="none" />"""
            )
        }
        sb.append("</g>")
        return sb.toString()
    }

    /**
     * One straight scan line of the machine's raster, as a band.
     *
     * Four corners and nothing else. The tool grammar is deliberately not on
     * this path: a performed line wanders by a third of its width, which over a
     * run this long stops reading as a straight line, and straightness is what
     * the machine's fill is. Not quantised -- rounding the four corners onto
     * the lattice made the band's width vary from line to line.
     */
    fun rasterBand(start: Pair<Double, Double>, end: Pair<Double, Double>, width: Double): String {
        val dx = end.first - start.first
        val dy = end.second - start.second
        val length = hypot(dx, dy)
        if (length <= 0) return ""
        val nx = -dy / length * width / 2
        val ny = dx / length * width / 2
        val corners = listOf(
            (start.first + nx) to (start.second + ny),
            (end.first + nx) to (end.second + ny),
            (end.first - nx) to (end.second - ny),
            (start.first - nx) to (start.second - ny)
        )
        return "M " + corners.joinToString(" L ") {
            String.format(java.util.Locale.US, "%.2f %.2f", it.first, it.second)
        } + " Z"
    }

    fun pointInPolygon(x: Double, y: Double, contour: List<Pair<Double, Double>>): Boolean {
        var inside = false
        var j = contour.size - 1
        for (i in contour.indices) {
            val (xi, yi) = contour[i]
            val (xj, yj) = contour[j]
            if ((yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) {
                inside = !inside
            }
            j = i
        }
        return inside
    }

    /**
     * Scatter positions inside the contour, drawn from the scan segments.
     *
     * The same `scanlineSegments` the fill uses, so a concave form stays inside
     * its own outline and nothing lands in the bounding box but outside the form.
     */
    fun surfaceScatter(
        contour: List<Pair<Double, Double>>,
        count: Int,
        seed: Any
    ): List<Pair<Double, Double>> {
        if (count <= 0 || contour.size < 3) return emptyList()
        val h = ServerRendererGeometry::hash01
        val angle = ServerRendererGeometry.fillScanAngle(seed)
        val xs = contour.map { it.first }
        val ys = contour.map { it.second }
        val diagonal = max(1e-6, hypot(xs.max() - xs.min(), ys.max() - ys.min()))
        val rows = max(2, Math.round(sqrt(count * 1.6)).toInt())
        val spacing = diagonal / rows
        val segments = ServerRendererGeometry.scanlineSegments(contour, angle, spacing, seed)
        val lengths = segments.map { hypot(it.third.first - it.second.first, it.third.second - it.second.second) }
        val total = lengths.sum()
        if (total <= 0.0) return emptyList()
        val nx = -sin(angle)
        val ny = cos(angle)
        val points = mutableListOf<Pair<Double, Double>>()
        for (index in segments.indices) {
            val (_, start, end) = segments[index]
            val share = count * lengths[index] / total
            var taken = share.toInt()
            if (h(index, seed, "surface-share") < share - taken) taken += 1
            for (j in 0 until taken) {
                val saltIndex = index * 4096 + j
                val u = (j + h(saltIndex, seed, "surface-u")) / taken
                var px = start.first + (end.first - start.first) * u
                var py = start.second + (end.second - start.second) * u
                val drift = (h(saltIndex, seed, "surface-n") - 0.5) * spacing * 0.8
                val qx = px + nx * drift
                val qy = py + ny * drift
                if (pointInPolygon(qx, qy, contour)) {
                    px = qx
                    py = qy
                }
                points.add(px to py)
            }
        }
        return points
    }

    /**
     * The mean chord of the form, which is what a full-length mark will be.
     *
     * For a circle `area / shortSide` is exactly it, and for anything else it
     * is the right order. Only the COUNT is decided from it; the LENGTH is the
     * form's own.
     */
    fun textureMarkCount(contour: List<Pair<Double, Double>>, pitch: Double): Int {
        val xs = contour.map { it.first }
        val ys = contour.map { it.second }
        val shortSide = min(xs.max() - xs.min(), ys.max() - ys.min())
        val area = polygonArea(contour)
        val meanChord = if (shortSide > 0) max(pitch, area / shortSide) else pitch
        return max(MIN_SCANLINES, (area / (pitch * meanChord) * TEXTURE_DENSITY).toInt())
    }
}
