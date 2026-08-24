package app.inku.mobile.render

import app.inku.mobile.data.model.WorkColorSnapshot
import app.inku.mobile.pipeline.RenderRequest
import java.math.BigInteger
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AndroidRenderHostTest {
    @Test
    fun requestJsonCarriesRawScoreResolvedHostInputsAndExplicitWild() {
        val bridge = CapturingRenderBridge()
        val host = AndroidRenderHost(bridge)
        val snapshot = WorkColorSnapshot(
            catalogId = "retired-catalog",
            colorMap = linkedMapOf("black" to "#010203", "white" to "#fafafa"),
            catalogName = "Recorded",
            catalogSub = "Snapshot",
        )

        val result = host.render(
            request(
                canvasAspect = "wide",
                renderSeed = 9_007_199_254_740_991L,
                compositionSeed = 0L,
                wild = true,
                workColorSnapshot = snapshot,
            ),
        )

        val wire = JSONObject(bridge.lastRenderRequestJson)
        assertTrue(wire.get("score") is JSONObject)
        val options = wire.getJSONObject("options")
        assertEquals("retired-catalog", options.getString("catalog_id"))
        assertEquals("wide", options.getString("canvas_aspect_id"))
        assertEquals(2350, options.getJSONObject("canvas").getInt("width"))
        assertEquals(1000, options.getJSONObject("canvas").getInt("height"))
        assertEquals("#010203", options.getJSONObject("resolved_color_map").getString("black"))
        assertEquals("9007199254740991", options.get("render_seed").toString())
        assertEquals("0", options.get("composition_seed").toString())
        assertTrue(options.getBoolean("wild"))

        val metadata = JSONObject(result.metadataJson)
        assertEquals("default", metadata.getString("render_engine_id"))
        assertEquals("41", metadata.getString("render_engine_version"))
        assertEquals("wide", metadata.getString("render_canvas_aspect_id"))
        assertEquals("Recorded", metadata.getString("render_color_catalog_name"))
        assertEquals("#010203", metadata.getJSONObject("render_color_map").getString("black"))
        assertTrue(metadata.getBoolean("render_wild"))
        assertEquals(result.renderHash, metadata.getString("render_hash"))
        assertNotEquals("", result.renderHash)
    }

    @Test
    fun seedWirePreservesNullZeroSignedLimitAndUnsigned64BitPattern() {
        val cases = listOf(
            null to null,
            0L to "0",
            9_007_199_254_740_991L to "9007199254740991",
            Long.MAX_VALUE to "9223372036854775807",
            -1L to "18446744073709551615",
        )
        cases.forEach { (seed, expected) ->
            val bridge = CapturingRenderBridge()
            AndroidRenderHost(bridge).render(request(renderSeed = seed))
            val requestText = bridge.lastRenderRequestJson
            val options = JSONObject(requestText).getJSONObject("options")
            if (expected == null) {
                assertTrue(options.isNull("render_seed"))
            } else {
                assertEquals(BigInteger(expected), BigInteger(options.get("render_seed").toString()))
                assertTrue(requestText.contains("\"render_seed\":$expected"))
                assertFalse(requestText.contains("\"render_seed\":\"$expected\""))
            }
        }
    }

    @Test
    fun explicitSeedAndWildOverrideHistoricalScoreOptionsWithoutChangingNullFallback() {
        val score = JSONObject(SCORE)
            .put("render_seed", -2L)
            .put("composition_seed", BigInteger("18446744073709551615"))
            .put("render_wild", true)
            .toString()
        val bridge = CapturingRenderBridge()
        val host = AndroidRenderHost(bridge)

        host.render(request(scoreJson = score))
        var options = JSONObject(bridge.lastRenderRequestJson).getJSONObject("options")
        assertEquals("18446744073709551614", options.get("render_seed").toString())
        assertEquals("18446744073709551615", options.get("composition_seed").toString())
        assertTrue(options.getBoolean("wild"))

        host.render(request(scoreJson = score, renderSeed = 0L, compositionSeed = 0L, wild = false))
        options = JSONObject(bridge.lastRenderRequestJson).getJSONObject("options")
        assertEquals("0", options.get("render_seed").toString())
        assertEquals("0", options.get("composition_seed").toString())
        assertFalse(options.getBoolean("wild"))
    }

    @Test
    fun hostDoesNotOwnScoreMigration() {
        val score = JSONObject(SCORE)
        score.getJSONArray("instructions").put(
            JSONObject()
                .put("primitive", "line")
                .put("weight", "hair")
                .put("from", org.json.JSONArray(listOf(0.1, 0.1)))
                .put("to", org.json.JSONArray(listOf(0.9, 0.9))),
        )
        val bridge = CapturingRenderBridge()

        AndroidRenderHost(bridge).render(request(scoreJson = score.toString()))

        val forwarded = JSONObject(bridge.lastRenderRequestJson)
            .getJSONObject("score")
            .getJSONArray("instructions")
            .getJSONObject(0)
        assertEquals("hair", forwarded.getString("weight"))
    }

    private fun request(
        scoreJson: String = SCORE,
        canvasAspect: String = "square",
        renderSeed: Long? = null,
        compositionSeed: Long? = null,
        wild: Boolean? = null,
        workColorSnapshot: WorkColorSnapshot? = null,
    ) = RenderRequest(
        scoreJson = scoreJson,
        colorCatalogId = "default",
        canvasAspect = canvasAspect,
        svgProfile = "display",
        renderSeed = renderSeed,
        compositionSeed = compositionSeed,
        wild = wild,
        workColorSnapshot = workColorSnapshot,
    )

    companion object {
        private const val SCORE =
            """{"version":"0.1.0","canvas":{"aspect":"square"},"background":"white","instructions":[]}"""
    }
}

private class CapturingRenderBridge : RenderBridge {
    var lastRenderRequestJson: String = ""
    var lastRasterOptionsJson: String = ""

    override fun coreApiVersion(): String = EXPECTED_CORE_API_VERSION
    override fun rasterApiVersion(): String = EXPECTED_RASTER_API_VERSION
    override fun renderEngineId(): String = "default"
    override fun renderEngineVersion(): String = "41"
    override fun defaultColorMapJson(): String = "{}"
    override fun rendererReferenceJson(): String = "{}"

    override fun render(requestJson: String): NativeRenderOutput {
        lastRenderRequestJson = requestJson
        return NativeRenderOutput(
            svg = "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
            metadataJson = """{"render_engine_id":"default","render_engine_version":"41"}""",
        )
    }

    override fun rasterize(svg: String, rasterOptionsJson: String): NativeRasterOutput {
        lastRasterOptionsJson = rasterOptionsJson
        return NativeRasterOutput(
            width = 1,
            height = 1,
            stride = 4,
            pixelFormat = RustArtworkRasterizer.PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
            pixels = byteArrayOf(0, 0, 0, 0),
        )
    }
}
