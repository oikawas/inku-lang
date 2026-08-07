package app.inku.mobile.pipeline

import app.inku.mobile.render.DefaultSvgRenderer
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Saved works on the device carry `weight: "hair"`, the name v2.7.9 retired.
 *
 * Two things have to hold, and a check for only the first passes even when nothing was
 * replaced: the old work must still load, and the replacement must actually reach the
 * drawing. `weight` is in the instruction seed key, so a migrated Score cannot draw the
 * same marks as an unmigrated one.
 */
class ServerScoreCompatTest {

    private val renderer = DefaultSvgRenderer()

    private fun scoreWith(weight: String): String = JSONObject()
        .put("canvas", "square")
        .put("background", "white")
        .put(
            "instructions",
            JSONArray().put(
                JSONObject()
                    .put("primitive", "circle")
                    .put("weight", weight)
                    .put("color", "black")
                    .put("center", JSONArray(listOf(0.5, 0.5)))
                    .put("radius", 0.20)
            )
        ).toString()

    private fun renderOf(weight: String): String = renderer.render(
        RenderRequest(
            scoreJson = scoreWith(weight),
            colorCatalogId = "default",
            canvasAspect = "square",
            svgProfile = "editable",
            renderSeed = 12345L,
        )
    ).svg

    @Test
    fun testLegacyHairScoreStillLoads() {
        val svg = renderOf("hair")
        assertTrue("A saved hair Score must still render", svg.startsWith("<svg"))
        assertTrue("It must carry the tool's own id, not the default's", svg.contains("_silverpoint"))
    }

    @Test
    fun testLegacyHairRendersAsSilverpointAndNotAsTheDefault() {
        val fromLegacy = renderOf("hair")
        val fromCurrent = renderOf("silverpoint")
        val fromDefault = renderOf("pen")

        // Replaced: the old name draws exactly what the new name draws.
        assertEquals("hair must render byte-identically to silverpoint", fromCurrent, fromLegacy)
        // Not dropped: silverpoint is 0.5px and pen is 2.0px, so falling back would be visible.
        assertNotEquals("hair must not fall back to the default pen", fromDefault, fromLegacy)
    }

    @Test
    fun testTheReplacementMovesTheDrawing() {
        // weight is in the seed key allowlist, so the same figure under the old name and
        // under an unmigrated reading cannot produce the same marks. This is what a
        // "does it still load" check on its own would miss.
        val migrated = ServerScoreCompat.migrateWeight("hair")
        assertEquals("silverpoint", migrated)

        val unmigratedIsADifferentDrawing = renderOf("pen") != renderOf("silverpoint")
        assertTrue("silverpoint must not draw what any other tool draws", unmigratedIsADifferentDrawing)
    }

    @Test
    fun testMigrationReachesEveryInstructionOfAScore() {
        val score = JSONObject(
            """{"instructions":[{"primitive":"line","weight":"hair"},
                                {"primitive":"circle","weight":"pencil"},
                                {"primitive":"square","weight":"hair"}]}"""
        )
        ServerScoreCompat.migrateScore(score)
        val weights = (0 until score.getJSONArray("instructions").length()).map {
            score.getJSONArray("instructions").getJSONObject(it).getString("weight")
        }
        assertEquals(listOf("silverpoint", "pencil", "silverpoint"), weights)
    }
}
