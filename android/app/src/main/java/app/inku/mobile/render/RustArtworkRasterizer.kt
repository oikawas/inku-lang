package app.inku.mobile.render

import android.graphics.Bitmap
import org.json.JSONObject

/** Synchronous SVG-to-Bitmap adapter. Callers must invoke it off the UI thread. */
class RustArtworkRasterizer(
    private val bridge: RenderBridge = NativeRenderBridge,
) {
    fun rasterize(
        svg: String,
        targetWidth: Int? = null,
        targetHeight: Int? = null,
    ): Bitmap {
        validateRequest(svg, targetWidth, targetHeight)
        bridge.requireCompatibleNativePackage()
        return bridge.rasterizeBitmap(svg, optionsJson(targetWidth, targetHeight))
    }

    /** Raw output remains available for exact host/device parity tests. */
    fun rasterizeRaw(
        svg: String,
        targetWidth: Int? = null,
        targetHeight: Int? = null,
    ): NativeRasterOutput {
        validateRequest(svg, targetWidth, targetHeight)
        bridge.requireCompatibleNativePackage()
        return bridge.rasterize(svg, optionsJson(targetWidth, targetHeight)).also(::validateRasterOutput)
    }

    companion object {
        internal const val PIXEL_FORMAT_RGBA8_PREMULTIPLIED = "rgba8-premultiplied"

        private fun validateRequest(svg: String, targetWidth: Int?, targetHeight: Int?) {
            require(svg.isNotEmpty()) { "SVG must not be empty" }
            require(targetWidth == null || targetWidth > 0) { "targetWidth must be positive" }
            require(targetHeight == null || targetHeight > 0) { "targetHeight must be positive" }
        }

        private fun optionsJson(targetWidth: Int?, targetHeight: Int?): String = JSONObject()
            .put("target_width", targetWidth ?: JSONObject.NULL)
            .put("target_height", targetHeight ?: JSONObject.NULL)
            .toString()

        private fun validateRasterOutput(output: NativeRasterOutput) {
            require(output.pixelFormat == PIXEL_FORMAT_RGBA8_PREMULTIPLIED) {
                "Unsupported Rust raster pixel format: ${output.pixelFormat}"
            }
            require(output.width > 0 && output.height > 0) {
                "Rust raster dimensions must be positive"
            }
            val tightStride = Math.multiplyExact(output.width, RGBA_BYTES_PER_PIXEL)
            require(output.stride >= tightStride) { "Rust raster stride is too small" }
            val requiredBytes = Math.multiplyExact(output.stride, output.height)
            require(output.pixels.size >= requiredBytes) { "Rust raster payload is truncated" }
        }

        private const val RGBA_BYTES_PER_PIXEL = 4
    }
}
