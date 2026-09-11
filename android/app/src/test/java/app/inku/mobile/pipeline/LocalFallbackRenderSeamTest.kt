package app.inku.mobile.pipeline

import app.inku.mobile.render.RenderResult
import app.inku.mobile.render.SvgRenderer
import java.math.BigInteger
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class LocalFallbackRenderSeamTest {
    @Test
    fun rendererGetsMigratedScoreWhileSavedResultKeepsOriginalScore() {
        val score =
            """{"canvas":"square","background":"white","instructions":[{"primitive":"line","weight":"hair"}]}"""
        val renderer = CapturingSvgRenderer()
        val pipeline = LocalFallbackPipeline(renderer)

        val result = pipeline.renderFromScore(
            scoreJson = score,
            request = PaintRequest(
                description = "legacy replay",
                stage1Model = "test",
                stage2Model = "test",
                colorCatalogId = "default",
                canvasAspect = "square",
                autoRepair = true,
                renderSeed = -1L,
            ),
        )

        val renderedWeight = JSONObject(renderer.request.scoreJson)
            .getJSONArray("instructions")
            .getJSONObject(0)
            .getString("weight")
        val savedWeight = JSONObject(result.scoreJson)
            .getJSONArray("instructions")
            .getJSONObject(0)
            .getString("weight")
        assertEquals("silverpoint", renderedWeight)
        assertEquals("hair", savedWeight)
        assertEquals(
            "18446744073709551615",
            JSONObject(result.renderMetadataJson).get("render_seed").toString(),
        )
    }

    @Test
    fun normalizationKeepsScoreEditionAndAcceptedSurfaceIntensity() {
        val pipeline = LocalFallbackPipeline(CapturingSvgRenderer())
        for (edition in listOf("0.1.0", "0.2.0", "0.3.0")) {
            val source = JSONObject("""{"version":"$edition","instructions":[{"primitive":"circle","filled":true}]}""")
            if (edition == "0.3.0") source.getJSONArray("instructions")
                .getJSONObject(0).put("surface_intensity", "dense")
            val normalized = pipeline.normalizeServerScoreWithLang(source, "", "square", null)
            assertEquals(edition, normalized.getString("version"))
            val instruction = normalized.getJSONArray("instructions").getJSONObject(0)
            assertEquals(if (edition == "0.3.0") "dense" else "",
                instruction.optString("surface_intensity"))
        }
        val versionless = JSONObject("""{"instructions":[{"primitive":"circle"}]}""")
        assertEquals("0.1.0", pipeline.normalizeServerScoreWithLang(versionless, "", "square", null)
            .getString("version"))
    }

    @Test
    fun canonicalSeedDoesNotNarrowUnsignedOrBigIntegerValues() {
        val pipeline = LocalFallbackPipeline(CapturingSvgRenderer())
        val unsignedMax = BigInteger("18446744073709551615")

        assertEquals(unsignedMax, pipeline.canonicalSeed(-1L))
        assertEquals(unsignedMax, pipeline.canonicalSeed(unsignedMax))
        assertEquals(BigInteger("9223372036854775807"), pipeline.canonicalSeed(Long.MAX_VALUE))
        assertEquals(0, pipeline.canonicalSeed(0L))
    }
}

private class CapturingSvgRenderer : SvgRenderer {
    lateinit var request: RenderRequest

    override fun render(request: RenderRequest): RenderResult {
        this.request = request
        return RenderResult(
            svg = "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
            metadataJson = """{"render_engine_id":"default","render_engine_version":"35","render_wild":false}""",
            renderHash = "renderer-projection",
        )
    }
}
