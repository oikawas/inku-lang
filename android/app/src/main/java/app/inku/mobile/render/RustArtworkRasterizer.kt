package app.inku.mobile.render

import android.graphics.Bitmap
import java.nio.ByteBuffer
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
        val output = rasterizeRaw(svg, targetWidth, targetHeight)
        val bitmap = Bitmap.createBitmap(output.width, output.height, Bitmap.Config.ARGB_8888)
        val bytes = argb8888RowsForBitmap(output, bitmap.rowBytes)
        bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(bytes))
        bitmap.setPremultiplied(true)
        return bitmap
    }

    /** Raw output remains available for exact host/device parity tests. */
    fun rasterizeRaw(
        svg: String,
        targetWidth: Int? = null,
        targetHeight: Int? = null,
    ): NativeRasterOutput {
        require(svg.isNotEmpty()) { "SVG must not be empty" }
        require(targetWidth == null || targetWidth > 0) { "targetWidth must be positive" }
        require(targetHeight == null || targetHeight > 0) { "targetHeight must be positive" }
        bridge.requireCompatibleNativePackage()
        val options = JSONObject()
            .put("target_width", targetWidth ?: JSONObject.NULL)
            .put("target_height", targetHeight ?: JSONObject.NULL)
        return bridge.rasterize(svg, options.toString()).also(::validateRasterOutput)
    }

    companion object {
        internal const val PIXEL_FORMAT_RGBA8_PREMULTIPLIED = "rgba8-premultiplied"

        internal fun argb8888RowsForBitmap(
            output: NativeRasterOutput,
            destinationStride: Int,
        ): ByteArray {
            validateRasterOutput(output)
            val tightStride = Math.multiplyExact(output.width, RGBA_BYTES_PER_PIXEL)
            require(destinationStride >= tightStride) {
                "Bitmap stride $destinationStride is smaller than $tightStride"
            }
            val destinationSize = Math.multiplyExact(destinationStride, output.height)
            val bytes = ByteArray(destinationSize)
            for (row in 0 until output.height) {
                for (column in 0 until output.width) {
                    val source = row * output.stride + column * RGBA_BYTES_PER_PIXEL
                    val destination = row * destinationStride + column * RGBA_BYTES_PER_PIXEL
                    // Rust returns premultiplied RGBA. ARGB_8888's arm64
                    // little-endian backing bytes are BGRA, so swap red/blue;
                    // keep the already-premultiplied color and alpha untouched.
                    bytes[destination] = output.pixels[source + 2]
                    bytes[destination + 1] = output.pixels[source + 1]
                    bytes[destination + 2] = output.pixels[source]
                    bytes[destination + 3] = output.pixels[source + 3]
                }
            }
            return bytes
        }

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
