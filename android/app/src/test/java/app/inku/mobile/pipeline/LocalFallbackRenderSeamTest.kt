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
