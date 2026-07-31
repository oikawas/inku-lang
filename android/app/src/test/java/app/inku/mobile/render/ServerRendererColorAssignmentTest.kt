package app.inku.mobile.render

import app.inku.mobile.pipeline.RenderRequest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * engine 17: the catalog palette reaches the drawing.
 *
 * Nothing else in the suite looks at a color. The SVG corpus compares paths,
 * points and dashes, and every case in it renders through the bare default map
 * with `black`, so the assignment could be missing entirely and the suite would
 * still be green. This class renders through the renderer's own entry point —
 * it names no internal function, so the port is free to shape the mechanism as
 * it likes, as long as the ink comes out the color the server chose.
 */
class ServerRendererColorAssignmentTest {

    private val fixture: JSONObject by lazy {
        val stream = javaClass.getResourceAsStream("/server_reference/renderer_color_assignment.json")
            ?: error("renderer_color_assignment.json not found")
        JSONObject(stream.bufferedReader().use { it.readText() })
    }

    private fun colorKeys(): List<String> {
        val constants = fixture.getJSONObject("constants")
        val out = mutableListOf<String>()
        for (key in listOf("achromatic_colors", "chromatic_colors")) {
            val array = constants.getJSONArray(key)
            for (i in 0 until array.length()) out.add(array.getString(i))
        }
        return out
    }

    private fun renderStrokeColor(
        catalogId: String,
        color: String,
        seed: Long,
        colorHint: String? = null,
    ): String {
        val instruction = JSONObject()
            .put("primitive", "circle")
            .put("center", org.json.JSONArray(listOf(0.5, 0.5)))
            .put("radius", 0.2)
            .put("weight", "pen")
            .put("color", color)
        if (colorHint != null) instruction.put("color_hint", colorHint)
        val score = JSONObject()
            .put("render_seed", seed)
            .put("instructions", org.json.JSONArray(listOf(instruction)))
        val svg = DefaultSvgRenderer().render(
            RenderRequest(
                scoreJson = score.toString(),
                colorCatalogId = catalogId,
                canvasAspect = "square",
                svgProfile = "editable",
            )
        ).svg
        val strokes = Regex("""stroke="(#[0-9a-fA-F]{6})"""").findAll(svg)
            .map { it.groupValues[1].lowercase() }
            .toSet()
        assertEquals("$catalogId/$color drew more than one stroke color", 1, strokes.size)
        return strokes.first()
    }

    private fun renderBackgroundColor(catalogId: String, background: String): String {
        val score = JSONObject()
            .put("render_seed", 12345L)
            .put("background", background)
            .put(
                "instructions",
                org.json.JSONArray(
                    listOf(
                        JSONObject()
                            .put("primitive", "line")
                            .put("from", org.json.JSONArray(listOf(0.1, 0.5)))
                            .put("to", org.json.JSONArray(listOf(0.9, 0.5)))
                            .put("weight", "pen")
                    )
                )
            )
        val svg = DefaultSvgRenderer().render(
            RenderRequest(
                scoreJson = score.toString(),
                colorCatalogId = catalogId,
                canvasAspect = "square",
                svgProfile = "editable",
            )
        ).svg
        val rect = Regex("""<rect[^>]*fill="(#[0-9a-fA-F]{6})"""").find(svg)
            ?: error("no background rect in $catalogId/$background")
        return rect.groupValues[1].lowercase()
    }

    /** The whole answer: 11 catalogs x 9 abstract colors, at the corpus seed. */
    @Test
    fun testEveryCatalogAssignsEveryAbstractColorTheWayTheServerDoes() {
        val assignment = fixture.getJSONObject("assignment")
        val seed = fixture.getJSONArray("seeds").getString(0)
        val failures = mutableListOf<String>()
        for (catalogId in assignment.keys()) {
            val expected = assignment.getJSONObject(catalogId).getJSONObject(seed)
            for (color in colorKeys()) {
                val want = expected.getString(color).lowercase()
                val got = renderStrokeColor(catalogId, color, seed.toLong())
                if (want != got) failures.add("$catalogId.$color expected $want but drew $got")
            }
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
    }

    /**
     * The seed only reaches a band holding more than one color, so most of the
     * table is the same under any seed. A port that never wires the seed in
     * would pass the test above; it fails here.
     */
    @Test
    fun testTheSeedMovesExactlyThePairsTheServerMoves() {
        val assignment = fixture.getJSONObject("assignment")
        val seeds = fixture.getJSONArray("seeds")
        val first = seeds.getString(0)
        val second = seeds.getString(1)
        val expectedMoved = mutableSetOf<String>()
        val declared = fixture.getJSONArray("seed_sensitive")
        for (i in 0 until declared.length()) expectedMoved.add(declared.getString(i))
        assertTrue("the fixture declares no seed-sensitive pair", expectedMoved.isNotEmpty())

        val moved = mutableSetOf<String>()
        for (catalogId in assignment.keys()) {
            for (color in colorKeys()) {
                val a = renderStrokeColor(catalogId, color, first.toLong())
                val b = renderStrokeColor(catalogId, color, second.toLong())
                if (a != b) moved.add("$catalogId.$color")
            }
        }
        assertEquals(expectedMoved.sorted(), moved.sorted())
    }

    /**
     * The written color and the hint are separate channels: the hint chooses a
     * slot, the assignment fills it. The pairs in the fixture include hints
     * whose token sits inside a longer word, which engine 17 no longer matches.
     */
    @Test
    fun testHintsResolveThroughTheAssignment() {
        val cases = fixture.getJSONArray("hint_resolution")
        val failures = mutableListOf<String>()
        for (i in 0 until cases.length()) {
            val case = cases.getJSONObject(i)
            val hint = case.getString("color_hint")
            val got = renderStrokeColor(
                case.getString("catalog_id"),
                case.getString("color"),
                case.getLong("render_seed"),
                colorHint = hint,
            )
            val want = case.getString("expected").lowercase()
            if (want != got) {
                failures.add("${case.getString("catalog_id")} '$hint' expected $want but drew $got")
            }
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
    }

    /** The background is assigned too, not looked up in the raw map. */
    @Test
    fun testBackgroundsAreAssignedNotLookedUp() {
        val assignment = fixture.getJSONObject("assignment")
        val seed = fixture.getJSONArray("seeds").getString(0)
        val failures = mutableListOf<String>()
        for (catalogId in assignment.keys()) {
            val expected = assignment.getJSONObject(catalogId).getJSONObject(seed)
            for (color in colorKeys()) {
                val want = expected.getString(color).lowercase()
                val got = renderBackgroundColor(catalogId, color)
                if (want != got) failures.add("$catalogId background=$color expected $want but drew $got")
            }
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
    }

    /**
     * The three colors the catalogs never name. Without the nine-word default
     * map underneath, `yellow`, `orange` and `purple` fall to the renderer's
     * last-resort ink and every catalog answers the same.
     */
    @Test
    fun testTheCatalogsDoNotAgreeOnTheThreeColorsTheyDoNotName() {
        val assignment = fixture.getJSONObject("assignment")
        val seed = fixture.getJSONArray("seeds").getString(0)
        for (color in listOf("yellow", "orange", "purple")) {
            val drawn = assignment.keys().asSequence()
                .map { renderStrokeColor(it, color, seed.toLong()) }
                .toSet()
            assertTrue(
                "every catalog drew $color as the same ink: $drawn",
                drawn.size > 1,
            )
        }
    }
}
