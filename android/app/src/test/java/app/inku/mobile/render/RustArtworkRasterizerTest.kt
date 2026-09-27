package app.inku.mobile.render

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RustArtworkRasterizerTest {
    @Test
    fun rawRasterCallCarriesOnlyOptionalTargetDimensions() {
        val bridge = CapturingRasterBridge()
        val rasterizer = RustArtworkRasterizer(bridge)

        val output = rasterizer.rasterizeRaw("<svg/>", targetWidth = 320)

        assertEquals(1, output.width)
        val options = JSONObject(bridge.lastOptionsJson)
        assertEquals(320, options.getInt("target_width"))
        assertTrue(options.isNull("target_height"))
        assertEquals(setOf("target_width", "target_height"), options.keys().asSequence().toSet())
    }
}

private class CapturingRasterBridge : RenderBridge {
    var lastOptionsJson: String = ""

    override fun coreApiVersion(): String = EXPECTED_CORE_API_VERSION
    override fun rasterApiVersion(): String = EXPECTED_RASTER_API_VERSION
    override fun renderEngineId(): String = "default"
    override fun renderEngineVersion(): String = "41"
    override fun defaultColorMapJson(): String = "{}"
    override fun rendererReferenceJson(): String = "{}"
    override fun render(requestJson: String): NativeRenderOutput = error("not used")

    override fun rasterize(svg: String, rasterOptionsJson: String): NativeRasterOutput {
        lastOptionsJson = rasterOptionsJson
        return NativeRasterOutput(
            width = 1,
            height = 1,
            stride = 4,
            pixelFormat = RustArtworkRasterizer.PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
            pixels = byteArrayOf(255.toByte(), 0, 0, 255.toByte()),
        )
    }
}
