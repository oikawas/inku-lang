package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Three places where the port used to answer something else than the server, and
 * none of them can be gated by the frozen corpus: the 51 drawings hold no
 * cloudform carrying a `surface`, no arc whose end angle is below its start, and
 * no cluster whose `rhythm_spacing` is anything but "none" (measured on the
 * corpus at the branch point, `8b93bb9d`).
 *
 * So these are properties, and each expected number below was read off the
 * server itself -- `server/src/inku_server/renderer.py` at that same commit --
 * rather than off the port's previous answer. "It changed" would be true of a
 * wrong implementation too.
 */
class ThePortAnswersTheSameWayTheServerDoesTest {

    private val seed = 12345L

    /** 1618x1000, so `unit` (1000) and `width` are different numbers. */
    private val goldenWidth = 1618.0
    private val goldenHeight = 1000.0
    private val goldenUnit = 1000.0

    private val squareSide = 1000.0

    private fun cloudformWithSurface(): JSONObject = JSONObject(
        """
        {"primitive":"cloudform","center":[0.5,0.5],"size":[0.4,0.3],"weight":"pen",
         "surface":{"texture":"hatch","direction":"diagonal_falling","density":0.5,"opacity":0.3}}
        """.trimIndent()
    )

    private fun renderScore(instruction: JSONObject, aspect: String): String {
        val score = JSONObject().put("instructions", org.json.JSONArray().put(instruction))
        return DefaultSvgRenderer().render(
            RenderRequest(
                scoreJson = score.toString(),
                colorCatalogId = "default",
                canvasAspect = aspect,
                svgProfile = "editable",
                renderSeed = seed,
            )
        ).svg
    }

    private fun countOccurrences(haystack: String, needle: String): Int =
        haystack.split(needle).size - 1

    /**
     * T-85: a cloudform that states a surface gets one.
     *
     * The count is deliberately not asserted here -- how many rows a hatch lays
     * down follows the bbox, and that is T-86's question. This one asks only
     * whether the layer runs at all: before the cloudform branch existed,
     * `shapeBbox` answered null and `renderSurfaceVectors` returned "" on the
     * spot, so the answer was zero on any paper.
     */
    @Test
    fun testACloudformThatStatesASurfaceGetsOne() {
        for (aspect in listOf("square", "golden")) {
            val svg = renderScore(cloudformWithSurface(), aspect)
            assertTrue(
                "a cloudform with surface hatch must carry surface rows on $aspect",
                countOccurrences(svg, "surface-stroke-v1") >= 1,
            )
        }
    }

    /**
     * T-86: and its bounding box is the server's, to the digit.
     *
     * Read from `_shape_bbox` on the server: a cloudform's box is its centre and
     * size grown by 12%, `cx - w*0.56, cy - h*0.56, w*1.12, h*1.12`.
     *
     * Both papers are measured because the size goes through `_size_px`, which
     * puts a stated extent on the SHORT side. On a square canvas `unit` and
     * `width` are the same number and an implementation that multiplied by the
     * width would pass; on 1618x1000 it would answer 647.2 where the server
     * answers 400.
     */
    @Test
    fun testACloudformsBoundingBoxIsTheServers() {
        val golden = ServerRendererGeometry.shapeBbox(
            cloudformWithSurface(), goldenWidth, goldenHeight, goldenUnit
        )
        assertNotNull("a stated cloudform must have a bounding box", golden)
        assertEquals("x on golden", 585.0, golden!![0], 1e-9)
        assertEquals("y on golden", 332.0, golden[1], 1e-9)
        assertEquals("width on golden", 448.00000000000006, golden[2], 1e-9)
        assertEquals("height on golden", 336.00000000000006, golden[3], 1e-9)

        val square = ServerRendererGeometry.shapeBbox(
            cloudformWithSurface(), squareSide, squareSide, squareSide
        )
        assertNotNull("a stated cloudform must have a bounding box", square)
        assertEquals("x on square", 276.0, square!![0], 1e-9)
        assertEquals("y on square", 332.0, square[1], 1e-9)
        assertEquals("width on square", 448.00000000000006, square[2], 1e-9)
        assertEquals("height on square", 336.00000000000006, square[3], 1e-9)
    }

    /**
     * T-87: a cloudform missing either half has no box -- the same judgement the
     * server makes.
     *
     * `_shape_bbox` requires `center is not None and size is not None`; without
     * both, the server does not fall back to a default box, it declines the
     * branch (and `_render_instruction` refuses the instruction outright:
     * "cloudform requires center and size"). The complete cloudform is asserted
     * beside them on purpose: without that control, deleting the branch
     * altogether would leave this gate green.
     */
    @Test
    fun testACloudformMissingCentreOrSizeHasNoBox() {
        val noSize = cloudformWithSurface().apply { remove("size") }
        assertNull(
            "a cloudform without a size must have no bounding box",
            ServerRendererGeometry.shapeBbox(noSize, goldenWidth, goldenHeight, goldenUnit),
        )

        val noCentre = cloudformWithSurface().apply { remove("center") }
        assertNull(
            "a cloudform without a centre must have no bounding box",
            ServerRendererGeometry.shapeBbox(noCentre, goldenWidth, goldenHeight, goldenUnit),
        )

        assertNotNull(
            "the control: a cloudform stating both must still have one",
            ServerRendererGeometry.shapeBbox(
                cloudformWithSurface(), goldenWidth, goldenHeight, goldenUnit
            ),
        )

        // And the layer that reads the box draws nothing for the two that have
        // none, which is what the null is for.
        assertEquals(
            "no surface rows without a size",
            0,
            countOccurrences(renderScore(noSize, "golden"), "surface-stroke-v1"),
        )
        assertEquals(
            "no surface rows without a centre",
            0,
            countOccurrences(renderScore(noCentre, "golden"), "surface-stroke-v1"),
        )
    }

    // ---- [I-263] how long an arc is -------------------------------------

    /**
     * Both arcs below span the same 280 degrees, one written forwards and one
     * backwards, on a 1000x1000 canvas with r = 300. The server measures both at
     * `r * |radians(end) - radians(start)|` = 1466.0766 px, which is 4.886922
     * radii.
     */
    private fun pencilArc(start: Double, end: Double): JSONObject = JSONObject(
        """
        {"primitive":"arc","center":[0.5,0.5],"radius":0.3,
         "angle_start":$start,"angle_end":$end,"weight":"pencil"}
        """.trimIndent()
    )

    /** `rotring` is the one weight that stays geometric, so it reaches the other site. */
    private fun rotringVariedArc(start: Double, end: Double): JSONObject = JSONObject(
        """
        {"primitive":"arc","center":[0.5,0.5],"radius":0.3,
         "angle_start":$start,"angle_end":$end,"weight":"rotring",
         "variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_y"]}}
        """.trimIndent()
    )

    /** The powder the material layer lays along an arc; its count follows the arc's length. */
    private fun speckCount(svg: String): Int = Regex("<circle[ />]").findAll(svg).count()

    /**
     * How many points the varied arc is sampled at. The port writes them into a
     * `<polyline points>` now, the way the server does; before the arc contract
     * it wrote them into a `d`, one `L` per point after the opening `M`.
     */
    private fun variedArcPointCount(svg: String): Int {
        val pts = Regex(" points=\"([^\"]*)\"").find(svg)?.groupValues?.get(1) ?: return 0
        return pts.split(" ").size
    }

    /**
     * T-88: an arc written backwards is as long as the same arc written forwards.
     *
     * Two sites folded the difference into 0..360, and both are reached here:
     * the powder count on the hand-stroke path (pencil), and the sampling of a
     * varied geometric arc (rotring). Before, 300 -> 20 was read as 80 degrees:
     * 16 specks where the server puts 55, and 42 sample points where its length
     * buys 147.
     */
    @Test
    fun testAnArcWrittenBackwardsIsMeasuredEndToEnd() {
        val pencil = renderScore(pencilArc(300.0, 20.0), "square")
        assertEquals("the server puts 55 specks on this arc", 55, speckCount(pencil))
        assertTrue(
            "and samples its centreline 72 times",
            pencil.contains("arc-stroke-v1 controls-72 events-0"),
        )

        // 148 = `_segment_count` of that length plus the server's extra point.
        // The extra point and the <polyline> were the two divergences this
        // contract reported and left alone; the beat/arc/sheet contract closed
        // them, so the count read here is 148 and not 147. What is still
        // measured is the length that decides the sampling, 1466.0766 px -> 147
        // segments.
        assertEquals(
            "the varied arc is sampled at the length the server measures",
            148,
            variedArcPointCount(renderScore(rotringVariedArc(300.0, 20.0), "square")),
        )
    }

    /**
     * T-89: and the forward arc did not move.
     *
     * Without this half, "always take the absolute value" is not the only
     * implementation that passes T-88 -- reading every arc as its supplement
     * would pass it too, and would be wrong in the other direction.
     */
    @Test
    fun testTheForwardArcStillMeasuresTheSame() {
        val pencil = renderScore(pencilArc(20.0, 300.0), "square")
        assertEquals("the same 280 degrees, the same 55 specks", 55, speckCount(pencil))
        assertTrue(
            "and the same 72 samples",
            pencil.contains("arc-stroke-v1 controls-72 events-0"),
        )
        assertEquals(
            "and the same 148 sample points",
            148,
            variedArcPointCount(renderScore(rotringVariedArc(20.0, 300.0), "square")),
        )
    }

    /**
     * T-90: the two sites that already agreed with the server were not "unified"
     * along with the two that did not.
     *
     * `ServerRendererGeometry.arcPointsWithVariation` writes the length as
     * `2*pi*r*|end-start|/360`, which is the same number by a different route,
     * and `DefaultSvgRenderer`'s non-varied hand-stroke centreline writes it the
     * server's way already. Rewriting either would be a rounding change on paths
     * the frozen corpus does walk, so both are pinned to the server's counts.
     */
    @Test
    fun testTheTwoSitesThatAlreadyAgreedDidNotMove() {
        // `_arc_points_with_variation` on the server: `_segment_count + 1` = 148.
        val varied = ServerRendererGeometry.arcPointsWithVariation(
            500.0, 500.0, 300.0, 300.0, 20.0,
            JSONObject("""{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_y"]}"""),
            "12345", JSONObject(), squareSide, squareSide, squareSide,
        )
        assertEquals("the server samples this arc 148 times", 148, varied.size)

        // And the plain hand-stroke centreline, whose count rides
        // `_stroke_sample_count` of the same length.
        val plain = renderScore(pencilArc(300.0, 20.0), "square")
        assertTrue(
            "the plain centreline keeps the server's 72 samples",
            plain.contains("arc-stroke-v1 controls-72 events-0"),
        )
    }

    // ---- [I-267] the rhythm inside a cluster ----------------------------

    /**
     * Twenty members per cluster, three clusters, laid along the x axis so that
     * `along` -- the quantity the rhythm moves -- is read straight off the
     * anchor's x. `margin` is wide enough that nothing lands on the 0.02/0.98
     * clamp, which would flatten the very thing being measured.
     *
     * "loose" is the only spacing whose beat reads the seed at all
     * (`_rhythm_t`: accelerando and syncopated never touch it), so it is the
     * only one where a seed gate can be anything but vacuous.
     */
    private fun clusterInstruction(
        spacing: String,
        count: Int = 60,
        margin: Double = 0.3,
        density: String = "medium",
    ): JSONObject =
        JSONObject(
            """
            {"primitive":"circle","center":[0.5,0.5],"radius":0.01,
             "arrangement":{"layout":"horizontal","count":$count,"cluster_count":3,
                            "rhythm_spacing":"$spacing","density":"$density","margin":$margin,
                            "path":"left_to_right"}}
            """.trimIndent()
        )

    /** Twenty members in each of the three clusters, so that eighteen of them
     * sit away from the clamped ends and a chance agreement between two
     * unrelated beats is not mistaken for a shared one. */
    private val localTotal = 20

    /**
     * The seed the arrangement layer works at. It is the instruction's own -- the
     * whole instruction hashed with the placement seed -- so a score with a
     * different `rhythm_spacing` is a different seed, and no quantity can be
     * cancelled by subtracting one score's placement from another's.
     */
    private fun seedOf(ins: JSONObject): String {
        val method = DefaultSvgRenderer::class.java
            .getDeclaredMethod("seedForInstruction", JSONObject::class.java, java.lang.Long::class.java)
        method.isAccessible = true
        return method.invoke(DefaultSvgRenderer(), ins, seed) as String
    }

    /**
     * The band position of cluster `k`'s members, with the one term that does not
     * come from the beat taken back out.
     *
     * Along the band, a member sits at `centre + longSpan * (2t - 1) + (h - 0.5)
     * * radius * 0.20`, and the last term is drawn from the member's global index
     * -- known here, since the hash and the seed both are. Subtracting it leaves
     * something exactly affine in `t`, so what the beat did is all that is left
     * to explain, up to the two constants the cluster contributes.
     *
     * `path` is `left_to_right`, so the band's axis is x and this is read off the
     * anchor's x alone; the cross-axis terms land on y. The two members at each
     * end are dropped, because that is how far `clamp01` reaches: the beat's
     * jitter is the server's flat 0.16, so it swings +-0.08 either way, and with
     * twenty members `base` steps by 1/19 = 0.0526. Members 1 and 18 can
     * therefore still be pushed past 0 or 1, where `t` stops being affine and
     * nothing about the beat can be read off it. Members 2..17 start at 0.105,
     * which no swing reaches.
     */
    private fun bandPositions(spacing: String, clusterIndex: Int): List<Double> {
        val renderer = DefaultSvgRenderer()
        val ins = clusterInstruction(spacing)
        val seedText = seedOf(ins)
        val xs = renderer.expandArrangement(ins, seed, null, seed).map { renderer.anchor(it).first }
        // density "medium" with preserve_space unstated: `_density_radius` = 0.060.
        val radius = 0.060
        return (2 until localTotal - 2).map { j ->
            val i = j * 3 + clusterIndex
            xs[i] - (ServerRendererGeometry.hash01(i, seedText, "cluster-along") - 0.5) * radius * 0.20
        }
    }

    /** Least squares removal of the even spacing, which is linear in the local index. */
    private fun detrended(values: List<Double>): List<Double> {
        val n = values.size
        val xs = (0 until n).map { it.toDouble() }
        val mx = xs.average()
        val my = values.average()
        var sxy = 0.0
        var sxx = 0.0
        for (i in 0 until n) {
            sxy += (xs[i] - mx) * (values[i] - my)
            sxx += (xs[i] - mx) * (xs[i] - mx)
        }
        val slope = sxy / sxx
        return (0 until n).map { values[it] - (my + slope * (xs[it] - mx)) }
    }

    private fun correlation(a: List<Double>, b: List<Double>): Double {
        val ma = a.average()
        val mb = b.average()
        var num = 0.0
        var da = 0.0
        var db = 0.0
        for (i in a.indices) {
            num += (a[i] - ma) * (b[i] - mb)
            da += (a[i] - ma) * (a[i] - ma)
            db += (b[i] - mb) * (b[i] - mb)
        }
        return num / Math.sqrt(da * db)
    }

    /**
     * The beat the port's own "loose" rhythm draws at a given seed, up to scale.
     *
     * Only the seed's part is reproduced here -- the hash the jitter is drawn
     * from. What the rhythm then does with it is not copied, and is not what
     * these gates ask about.
     */
    private fun beatAt(seedText: String): List<Double> =
        detrended((2 until localTotal - 2).map { j ->
            ServerRendererGeometry.hash01(j, seedText, "rhythm-loose") - 0.5
        })

    private fun clusterSeeds(): Triple<String, String, String> {
        val base = seedOf(clusterInstruction("loose"))
        val asNumber = base.toULongOrNull() ?: 0UL
        return Triple(base, (asNumber xor 1UL).toString(), (asNumber xor 2UL).toString())
    }

    /**
     * T-91: three clusters keep three rhythms, not one rhythm three times.
     *
     * Stated without naming how the seeds are told apart, so that any per-cluster
     * stirring passes it -- the one that agrees with the server is T-93's
     * question. What fails here is the port's old reading, where every cluster
     * solved its beat at the same seed and the three displacements were the same
     * numbers to the last digit.
     */
    @Test
    fun testEachClusterKeepsItsOwnRhythm() {
        val first = detrended(bandPositions("loose", 0))
        assertTrue(
            "the beat must actually displace the members, or this gate measures nothing",
            first.map { Math.abs(it) }.average() > 1e-4,
        )
        assertTrue(
            "cluster 0 and cluster 1 must not share a beat",
            correlation(first, detrended(bandPositions("loose", 1))) < 0.5,
        )
        assertTrue(
            "cluster 0 and cluster 2 must not share a beat",
            correlation(first, detrended(bandPositions("loose", 2))) < 0.5,
        )
        // The control: with no beat at all, all three clusters sit evenly, so
        // what is left after the even spacing is removed is nothing to correlate.
        // This is what says the gate above is reading the rhythm and not the
        // arithmetic.
        assertTrue(
            "without a beat there is nothing left to differ",
            detrended(bandPositions("none", 0)).map { Math.abs(it) }.average() < 1e-9,
        )
    }

    /**
     * T-92: and where there is no beat, nothing was stirred.
     *
     * The twelve anchors are the server's own, read off `_expand_arrangement`
     * with the same seed and no canvas. Stirring outside the `rhythm_spacing !=
     * "none"` branch would move every one of them.
     */
    @Test
    fun testWithoutABeatThePlacementIsTheServers() {
        val renderer = DefaultSvgRenderer()
        val ins = clusterInstruction("none", count = 12, margin = 0.1, density = "high")
        val anchors = renderer.expandArrangement(ins, seed, null, seed).map { renderer.anchor(it) }
        val expected = listOf(
            0.02 to 0.412108440, 0.381984861 to 0.540708353, 0.750368641 to 0.551868780,
            0.077965005 to 0.394438308, 0.451416469 to 0.527475975, 0.842931054 to 0.528052283,
            0.153357421 to 0.432017834, 0.536152591 to 0.538947162, 0.924168182 to 0.555075823,
            0.248504234 to 0.409758126, 0.632627416 to 0.548302460, 0.980000000 to 0.561246458,
        )
        assertEquals("twelve members", expected.size, anchors.size)
        for (i in expected.indices) {
            assertEquals("member $i x", expected[i].first, anchors[i].first, 1e-9)
            assertEquals("member $i y", expected[i].second, anchors[i].second, 1e-9)
        }
    }

    /**
     * T-93: and the stirring is `seed xor cluster_index`, which is the server's.
     *
     * The displacement of cluster k is proportional to the beat the port's own
     * rhythm draws at one particular seed, so the seed can be named by asking
     * which candidate it follows. Three are offered: the server's `seed ^ k`, the
     * unstirred `seed`, and a spelling that mixes the two by text. Only the first
     * may match; "they differ per cluster" alone -- T-91 -- cannot tell the third
     * from the first.
     *
     * Note this asks which seed goes in, not what the rhythm does with it: the
     * port's "loose" is NOT the server's function (its jitter is
     * `0.12 / max(n/8, 1)` where the server's is a flat `0.16`, and accelerando
     * and syncopated differ too). That divergence is reported, not fixed here.
     */
    @Test
    fun testTheStirringIsSeedXorClusterIndex() {
        val (base, xor1, xor2) = clusterSeeds()
        for ((k, xorSeed) in listOf(1 to xor1, 2 to xor2)) {
            val observed = detrended(bandPositions("loose", k))
            assertEquals(
                "cluster $k follows the beat of seed xor $k",
                1.0,
                correlation(observed, beatAt(xorSeed)),
                1e-6,
            )
            assertTrue(
                "cluster $k must not follow the unstirred seed",
                correlation(observed, beatAt(base)) < 0.5,
            )
            assertTrue(
                "cluster $k must not follow a seed mixed as text",
                correlation(observed, beatAt("$base:$k")) < 0.5,
            )
        }
        // k = 0 is the case that tells xor from every other mixing: `seed ^ 0` is
        // the seed itself, so cluster 0's beat must be the unstirred one.
        assertEquals(
            "cluster 0 follows the seed itself",
            1.0,
            correlation(detrended(bandPositions("loose", 0)), beatAt(base)),
            1e-6,
        )
    }
}
