package app.inku.mobile.llm

import android.graphics.Bitmap
import android.graphics.Canvas
import app.inku.mobile.render.RustArtworkRasterizer
import java.io.ByteArrayOutputStream

/** The square, transparent PNG observed by autonomous refinement. */
internal object RefinementVisionImage {
    const val SIZE = 768

    fun fromSvg(svg: String, rasterizer: RustArtworkRasterizer = RustArtworkRasterizer()): ByteArray {
        val artwork = rasterizer.rasterize(svg, targetWidth = SIZE, targetHeight = SIZE)
        try {
            require(artwork.width in 1..SIZE && artwork.height in 1..SIZE) {
                "Refinement raster dimensions exceed the 768-pixel canvas"
            }
            val square = if (artwork.width == SIZE && artwork.height == SIZE) artwork else
                Bitmap.createBitmap(SIZE, SIZE, Bitmap.Config.ARGB_8888).also { canvasBitmap ->
                    Canvas(canvasBitmap).drawBitmap(
                        artwork, (SIZE - artwork.width) / 2f, (SIZE - artwork.height) / 2f, null,
                    )
                }
            try {
                return ByteArrayOutputStream().use { output ->
                    check(square.compress(Bitmap.CompressFormat.PNG, 100, output))
                    output.toByteArray().also(::requirePng768)
                }
            } finally {
                if (square !== artwork) square.recycle()
            }
        } finally {
            artwork.recycle()
        }
    }

    /** Read only PNG signature and IHDR dimensions; useful before provider transport. */
    fun requirePng768(bytes: ByteArray) {
        require(bytes.size >= 24 && bytes.copyOfRange(0, 8).contentEquals(PNG_SIGNATURE) &&
            bytes[12] == 'I'.code.toByte() && bytes[13] == 'H'.code.toByte() &&
            bytes[14] == 'D'.code.toByte() && bytes[15] == 'R'.code.toByte() &&
            dimension(bytes, 16) == SIZE && dimension(bytes, 20) == SIZE) {
            "Refinement image must be a 768×768 PNG"
        }
    }

    private fun dimension(bytes: ByteArray, offset: Int): Int =
        ((bytes[offset].toInt() and 0xff) shl 24) or
            ((bytes[offset + 1].toInt() and 0xff) shl 16) or
            ((bytes[offset + 2].toInt() and 0xff) shl 8) or
            (bytes[offset + 3].toInt() and 0xff)

    private val PNG_SIGNATURE = byteArrayOf(137.toByte(), 80, 78, 71, 13, 10, 26, 10)
}
