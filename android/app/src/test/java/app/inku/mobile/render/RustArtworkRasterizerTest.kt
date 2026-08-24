package app.inku.mobile.render

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RustArtworkRasterizerTest {
    @Test
    fun premultipliedRgbaMapsToLittleEndianArgb8888WithBothStrides() {
        val output = NativeRasterOutput(
            width = 2,
            height = 2,
            stride = 12,
            pixelFormat = RustArtworkRasterizer.PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
            pixels = byteArrayOf(
                255.toByte(), 0, 0, 255.toByte(),
                0, 128.toByte(), 0, 128.toByte(),
                91, 92, 93, 94,
                0, 0, 255.toByte(), 255.toByte(),
                64, 64, 64, 64,
                95, 96, 97, 98,
            ),
        )

        val mapped = RustArtworkRasterizer.argb8888RowsForBitmap(output, destinationStride = 12)

        assertArrayEquals(
            byteArrayOf(
                0, 0, 255.toByte(), 255.toByte(),
                0, 128.toByte(), 0, 128.toByte(),
                0, 0, 0, 0,
                255.toByte(), 0, 0, 255.toByte(),
                64, 64, 64, 64,
                0, 0, 0, 0,
            ),
            mapped,
        )
    }

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
