package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The server_reference fixture drives the tempering functions directly through reflection, so it
 * stays green even when the production chain calls none of them. This test goes through
 * normalizeServerScore instead, and pins where the filled-shape tempering has to sit.
 *
 * Server runs it as a standalone pass in coerce/__init__.py, between the presence repair and the
 * density governor. Inside the density governor it can never fire: the single-shape tempering runs
 * first and always brings the area below the filled threshold (0.14 < 0.20). Wiring it only into
 * the density governor would therefore ship a mechanism that never runs, and the fixture could not
 * tell the difference.
 */
class FilledShapeTemperingWiringTest {

    private val normalizeServerScore = LocalFallbackPipeline::class.java.getDeclaredMethod(
        "normalizeServerScore",
        JSONObject::class.java,
        String::class.java,
        String::class.java,
    ).apply { isAccessible = true }

    @Test
    fun testFilledShapeTemperingRunsAsItsOwnPassBeforeTheDensityGovernor() {
        val instruction = JSONObject()
            .put("primitive", "square")
            .put("center", JSONArray(listOf(0.5, 0.5)))
            .put("size", JSONArray(listOf(0.6, 0.5)))
            .put("filled", true)
            .put("style", "solid")
            .put("weight", "pen")
            .put("mode", "additive")
            .put("color", "black")
        val score = JSONObject()
            .put("version", "0.1.0")
            .put("canvas", "square")
            .put("background", "white")
            .put("instructions", JSONArray().put(instruction))

        val result = normalizeServerScore.invoke(
            LocalFallbackPipeline(), score, "四角を描く", "square",
        ) as JSONObject

        val size = result.getJSONArray("instructions").getJSONObject(0).getJSONArray("size")
        // The standalone pass caps to 0.42 x 0.30 first, which leaves the area under the
        // single-shape threshold. Without it the single-shape pass caps to 0.34 x 0.24 instead,
        // and the size reads [0.288, 0.24].
        assertEquals("filled tempering did not run before the density governor", 0.36, size.getDouble(0), 0.001)
        assertEquals("filled tempering did not run before the density governor", 0.30, size.getDouble(1), 0.001)
    }
}
