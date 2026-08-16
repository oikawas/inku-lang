package app.inku.mobile.render

import app.inku.mobile.ReferenceCorpus
import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The engines a corpus of circles could not see.
 *
 * Every arrangement case here was a `circle` until engine 26, and both seeds
 * handed to the expansion were the same number, so three engines reached no
 * fixture at all -- not for want of a mechanism but for want of a case. These
 * are the cases the corpus gained, and this is what they are for.
 */
class GroupMembersReachEachEngineTest {

    private val renderer = DefaultSvgRenderer()

    private fun index(): JSONObject = JSONObject(ReferenceCorpus.text("svg_index.json"))

    private fun render(name: String): String {
        val entry = index().getJSONObject(name)
        val compositionSeed = if (entry.has("composition_seed") && !entry.isNull("composition_seed")) {
            entry.getLong("composition_seed")
        } else {
            null
        }
        return renderer.render(
            RenderRequest(
                scoreJson = entry.getJSONObject("score").toString(),
                colorCatalogId = ReferenceRendering.catalogId(entry),
                canvasAspect = "square",
                svgProfile = "editable",
                renderSeed = entry.getLong("render_seed"),
                compositionSeed = compositionSeed,
            )
        ).svg
    }

    private fun expand(name: String): List<JSONObject> {
        val entry = index().getJSONObject(name)
        val score = entry.getJSONObject("score")
        val ins = score.getJSONArray("instructions").getJSONObject(0)
        val renderSeed = entry.getLong("render_seed")
        val placementSeed = if (entry.has("composition_seed") && !entry.isNull("composition_seed")) {
            entry.getLong("composition_seed")
        } else {
            renderSeed
        }
        return renderer.expandArrangement(ins, placementSeed, null, renderSeed)
    }

    private fun fadeLevels(name: String): List<Double?> =
        expand(name).map {
            ServerRendererFade.levelFromHint(
                if (it.has("color_hint") && !it.isNull("color_hint")) it.optString("color_hint") else null
            )
        }

    private fun rotations(name: String): List<Double?> =
        expand(name).map { if (it.has("rotation") && !it.isNull("rotation")) it.optDouble("rotation") else null }

    // A hand stroke is drawn as a filled contour, so the ceiling arrives as
    // `fill-opacity`; the only `stroke-opacity` in a group like this belongs to
    // the material layer's specks and is one constant for the drawing.
    private fun fillOpacities(svg: String): List<String> =
        Regex("""fill-opacity="([^"]*)"""").findAll(svg).map { it.groupValues[1] }.toList()

    /**
     * T-7: the fade reaches every member of a group, and leaves alone the two
     * groups that cannot fade.
     *
     * The scatter is the positive half and the only one that can carry it: a
     * ring is equidistant from its own centre and so is a pair, so 48 and 49
     * come out with no ceiling at all and a port that never fades matches them.
     */
    @Test
    fun testTheFadeReachesEveryMemberAndSkipsTheTwoThatCannotFade() {
        val levels = fadeLevels("51_arrangement_scatter_fade_edge")
        assertEquals("every member carries a ceiling", levels.size, levels.count { it != null })
        assertTrue("the group is worth measuring", levels.size >= 2)
        assertTrue(
            "the ceilings differ by position, not one constant for the group",
            levels.filterNotNull().toSet().size > 1
        )
        // The ramp runs 0.62 -> 0.18 outward, so the extremes are the ends.
        assertEquals(0.62, levels.filterNotNull().max(), 1e-9)
        assertEquals(0.18, levels.filterNotNull().min(), 1e-9)
        // And the drawing reads them. Not "more than one value" -- the ends of
        // the ramp have to be in the picture by name, or a port that ramped by
        // some other rule would pass on the spread alone.
        val drawn = fillOpacities(render("51_arrangement_scatter_fade_edge")).toSet()
        assertTrue("the drawing carries the near end of the ramp", "0.620000" in drawn)
        assertTrue("the drawing carries the far end of the ramp", "0.180000" in drawn)
        assertTrue("the drawing is not one flat tone", drawn.size > 2)

        for (degenerate in listOf("48_arrangement_fade_radial_edge", "49_arrangement_fade_count2_edge")) {
            assertEquals(
                "$degenerate must not be ramped",
                0,
                fadeLevels(degenerate).count { it != null }
            )
        }
    }

    /**
     * T-8: the placement follows the composition seed, and nothing else does.
     *
     * Both halves are needed. Moving the composition seed has to move the
     * anchors, or the split is not wired; moving the performance seed must not,
     * or the placement is reading the wrong one.
     */
    @Test
    fun testThePlacementFollowsTheCompositionSeedAndNotThePerformanceSeed() {
        val fixture = JSONObject(ReferenceCorpus.text("renderer_arrangement.json"))
        val split = fixture.getJSONObject("composition_seed_split")
        val ins = split.getJSONObject("instruction")
        val renderSeed = split.getLong("render_seed")
        val compositionSeed = split.getLong("composition_seed")
        val otherPerformanceSeed = split.getLong("other_performance_seed")

        fun anchorsOf(placement: Long, performance: Long): List<List<Double>> =
            renderer.expandArrangement(JSONObject(ins.toString()), placement, null, performance)
                .map { val (x, y) = renderer.anchor(it); listOf(x, y) }

        fun expected(key: String): List<List<Double>> {
            val arr = split.getJSONArray(key)
            return (0 until arr.length()).map {
                val pt = arr.getJSONArray(it)
                listOf(pt.getDouble(0), pt.getDouble(1))
            }
        }

        val plain = anchorsOf(renderSeed, renderSeed)
        val moved = anchorsOf(compositionSeed, renderSeed)
        val otherHand = anchorsOf(renderSeed, otherPerformanceSeed)

        assertEquals("no composition seed", expected("anchors_no_composition_seed"), plain)
        assertEquals("with a composition seed", expected("anchors_with_composition_seed"), moved)
        assertEquals("another performance seed", expected("anchors_other_performance_seed"), otherHand)

        assertNotEquals("the composition seed has to move the placement", plain, moved)
        assertEquals("the performance seed must not move the placement", plain, otherHand)
    }

    /**
     * T-9: each member of a group finds its own angle.
     *
     * `arc` and `cloudform` are the two shapes the rule turns that the corpus
     * had never carried; the drawings pin that the turn reaches the picture and
     * not only the expansion.
     */
    @Test
    fun testEachMemberOfATurningGroupFindsItsOwnAngle() {
        for (name in listOf("43_arrangement_angle_arc_edge", "44_arrangement_angle_cloudform_edge")) {
            val turns = rotations(name)
            assertTrue("$name is worth measuring", turns.size >= 2)
            assertEquals("$name: every member states an angle", turns.size, turns.count { it != null })
            assertEquals(
                "$name: the members do not share one angle",
                turns.size,
                turns.filterNotNull().toSet().size
            )
            // +/-27 degrees since engine 27, and nothing outside it. The literal
            // is written out here and bound to production on the next line, the
            // way the server's `test_the_amplitude_is_the_one_that_was_ruled_on`
            // does it: a check that only reads the constant would follow the
            // constant anywhere it went.
            val amplitude = 27.0
            assertEquals("the ruled band is the one production swings", amplitude, HAND_GROUP_ROT, 0.0)
            assertTrue("$name: within the ruled band", turns.filterNotNull().all { kotlin.math.abs(it) <= amplitude })
            assertEquals(
                "$name: the drawing turns each member",
                turns.size,
                Regex("""transform="rotate\(""").findAll(render(name)).count()
            )
        }
    }

    /**
     * T-10: a group that states its own angle is left alone -- and "states" is
     * not "states something non-zero".
     *
     * `rotation: 0` says "do not tilt these", which is an answer and not a
     * missing one; 141 groups in production give exactly that answer and a
     * truthy test would silently turn every one of them. The thirty is here
     * beside the zero because only the zero moves under the wrong reading, and
     * a pair that both moved would not tell the two readings apart.
     */
    @Test
    fun testAGroupThatStatesItsAngleIsLeftAloneIncludingAStatedZero() {
        val stated = mapOf(
            "45_arrangement_angle_stated_zero_edge" to 0.0,
            "46_arrangement_angle_stated_30_edge" to 30.0,
        )
        for ((name, angle) in stated) {
            val turns = rotations(name)
            assertTrue("$name is worth measuring", turns.size >= 2)
            assertEquals(
                "$name: every member keeps the stated angle",
                listOf(angle),
                turns.filterNotNull().toSet().toList()
            )
        }
    }

    /**
     * T-12: the eight cases the corpus gained are actually walked.
     *
     * Without this the three tests above are claims about fixtures nothing
     * reads. The walk over `svg_index.json` is what reaches them, and it has to
     * reach every one by name -- a count alone would pass if the eight arrived
     * and eight others left.
     */
    @Test
    fun testTheWalkReachesEveryDrawingIncludingTheOnesAddedForTheseEngines() {
        val names = index().keys().asSequence().toList()
        assertEquals("every drawing in the corpus", 51, names.size)
        val added = listOf(
            "43_arrangement_angle_arc_edge",
            "44_arrangement_angle_cloudform_edge",
            "45_arrangement_angle_stated_zero_edge",
            "46_arrangement_angle_stated_30_edge",
            "47_arrangement_size_square_edge",
            "48_arrangement_fade_radial_edge",
            "49_arrangement_fade_count2_edge",
            "50_arrangement_composition_scatter_edge",
            "51_arrangement_scatter_fade_edge",
        )
        for (name in added) {
            assertTrue("$name is in the index", name in names)
            assertTrue("$name has a resource", ReferenceCorpus.text("$name.svg").isNotEmpty())
        }
        // And the one that states a composition seed carries it, or the walk
        // would draw it at the performance seed's placement.
        assertEquals(
            777L,
            index().getJSONObject("50_arrangement_composition_scatter_edge").getLong("composition_seed")
        )
    }
}
