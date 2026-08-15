package app.inku.mobile.render

import app.inku.mobile.data.model.CanvasSize
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What the arrangement layer spreads is measured on the short side (engine 31
 * and 32), so a ring stays round and a band stays a band on paper of any shape.
 *
 * None of this can be gated by the frozen corpus: `render-engine-31/` through
 * `-34/` are byte-identical to `-30/` apart from `manifest.json`, and the corpus
 * holds one non-square case, a line with no arrangement at all. These are
 * therefore properties, and each is stated as a distance rather than as "the two
 * canvases differ" -- the old engine differs too.
 */
class ASpreadKeepsItsFormTest {

    private val square = CanvasSize(1000, 1000)

    /** Same short side as [square], so a levelled extent comes out the same pixels. */
    private val oban = CanvasSize(1000, 1500)

    private val seed = 12345L

    private fun renderer() = DefaultSvgRenderer()

    private fun pxBounds(
        anchors: List<Pair<Double, Double>>,
        canvas: CanvasSize,
    ): Pair<Double, Double> {
        val xs = anchors.map { it.first * canvas.width }
        val ys = anchors.map { it.second * canvas.height }
        return (xs.maxOrNull()!! - xs.minOrNull()!!) to (ys.maxOrNull()!! - ys.minOrNull()!!)
    }

    private fun ringAnchors(canvas: CanvasSize): List<Pair<Double, Double>> {
        val renderer = renderer()
        // Nine members, so the ring is sampled every 45 degrees and its bounding
        // box is exactly the diameter on both axes. Eight would be sampled every
        // 51.4 degrees, whose box is 1.90r across and 1.95r down for a perfectly
        // round ring, and the gate would be measuring the sampling.
        val ins = JSONObject(
            """
            {"primitive":"circle","center":[0.5,0.5],"radius":0.02,
             "arrangement":{"layout":"radial","count":9,"radius":0.3,"center":[0.5,0.5]}}
            """.trimIndent()
        )
        return renderer.expandArrangement(ins, seed, canvas, seed).map { renderer.anchor(it) }
    }

    /** T-79: the ring is round -- the same pixels across as down, on either paper. */
    @Test
    fun testRingIsRoundInPixelsOnANonSquareCanvas() {
        for (canvas in listOf(square, oban)) {
            val (widthPx, heightPx) = pxBounds(ringAnchors(canvas), canvas)
            assertEquals(
                "ring diameter across and down must be the same pixels on ${canvas.width}x${canvas.height}",
                widthPx,
                heightPx,
                0.01,
            )
        }
        // And it is the description's radius that decides those pixels, not the
        // paper: 0.3 of the short side, twice over.
        val (widthPx, _) = pxBounds(ringAnchors(oban), oban)
        assertEquals("the ring's diameter is 0.6 of the short side", 600.0, widthPx, 0.01)
    }

    /**
     * T-80, first half: `at.region`'s extent buys the same pixels on both axes.
     *
     * The region is recovered from the placement rather than recomputed here: a
     * mark lands at `x0 + (x1 - x0) * u` with `u` from the same public hash the
     * renderer uses, so two indices give two equations and the extent falls out
     * exactly. Writing the expected region out by hand would be a second copy of
     * the rule under test.
     */
    @Test
    fun testAtRegionExtentIsAxisIndependentInPixels() {
        val renderer = renderer()
        fun anchorAt(index: Int, canvas: CanvasSize): Pair<Double, Double> {
            val ins = JSONObject(
                """{"primitive":"circle","center":[0.5,0.5],"radius":0.02,"at":{"region":[0.3,0.3,0.7,0.7]}}"""
            )
            return renderer.anchor(renderer.resolveAtRegion(ins, seed, index, canvas))
        }
        fun extents(canvas: CanvasSize): Pair<Double, Double> {
            val (xa, ya) = anchorAt(0, canvas)
            val (xb, yb) = anchorAt(1, canvas)
            val ua = ServerRendererGeometry.hash01(0, seed, "region-x")
            val ub = ServerRendererGeometry.hash01(1, seed, "region-x")
            val va = ServerRendererGeometry.hash01(0, seed, "region-y")
            val vb = ServerRendererGeometry.hash01(1, seed, "region-y")
            assertTrue("the two indices must not draw the same fraction", Math.abs(ua - ub) > 1e-6)
            assertTrue("the two indices must not draw the same fraction", Math.abs(va - vb) > 1e-6)
            return ((xa - xb) / (ua - ub)) to ((ya - yb) / (va - vb))
        }

        val (obanW, obanH) = extents(oban)
        assertEquals(
            "the region's extent must buy the same pixels across as down",
            obanW * oban.width,
            obanH * oban.height,
            1e-6,
        )

        val (squareW, squareH) = extents(square)
        assertEquals("a square canvas leaves the region as stated", 0.4, squareW, 1e-12)
        assertEquals("a square canvas leaves the region as stated", 0.4, squareH, 1e-12)
    }

    /** T-80, second half: the same, on the grid layout's own reading of `at.region`. */
    @Test
    fun testGridRegionExtentIsAxisIndependentInPixels() {
        val renderer = renderer()
        fun anchors(canvas: CanvasSize): List<Pair<Double, Double>> {
            val ins = JSONObject(
                """
                {"primitive":"circle","center":[0.5,0.5],"radius":0.02,
                 "at":{"region":[0.3,0.3,0.7,0.7]},
                 "arrangement":{"layout":"grid","count":16,"rows":4,"cols":4,"jitter":0.0}}
                """.trimIndent()
            )
            return renderer.expandArrangement(ins, seed, canvas, seed).map { renderer.anchor(it) }
        }

        val (obanW, obanH) = pxBounds(anchors(oban), oban)
        assertEquals(
            "the grid's region must buy the same pixels across as down",
            obanW,
            obanH,
            1e-6,
        )
        val (squareW, squareH) = pxBounds(anchors(square), square)
        assertEquals("a square canvas leaves the grid's region as stated", squareW, squareH, 1e-6)
        assertEquals("and that region is 0.4 of the paper, three cells wide", 300.0, squareW, 1e-6)
    }
}
