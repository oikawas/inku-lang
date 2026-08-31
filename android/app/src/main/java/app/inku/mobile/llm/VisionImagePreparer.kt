package app.inku.mobile.llm

import android.graphics.Bitmap
import android.graphics.ImageDecoder
import java.io.ByteArrayOutputStream
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlin.math.roundToInt

data class PreparedVisionImage(
    val jpegBytes: ByteArray,
    val width: Int,
    val height: Int,
)

/** Maximum app-owned image payload accepted before ImageDecoder touches it. */
internal const val MAX_VISION_SOURCE_IMAGE_BYTES = 64L * 1024L * 1024L

object VisionImagePreparer {
    internal const val MAX_LONG_EDGE = 1280
    internal const val JPEG_QUALITY = 85

    internal fun boundedSize(width: Int, height: Int): Pair<Int, Int> {
        require(width > 0 && height > 0) { "Image dimensions must be positive." }
        val longEdge = maxOf(width, height)
        if (longEdge <= MAX_LONG_EDGE) return width to height
        val scale = MAX_LONG_EDGE.toDouble() / longEdge.toDouble()
        return maxOf(1, (width * scale).roundToInt()) to maxOf(1, (height * scale).roundToInt())
    }

    suspend fun prepare(file: File): PreparedVisionImage = withContext(Dispatchers.IO) {
        validateSourceFile(file)
        val source = ImageDecoder.createSource(file)
        val bitmap = ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
            val (width, height) = boundedSize(info.size.width, info.size.height)
            decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
            decoder.setTargetSize(width, height)
        }
        try {
            val bytes = ByteArrayOutputStream().use { output ->
                check(bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, output)) {
                    "The normalized camera image could not be encoded."
                }
                output.toByteArray()
            }
            check(bytes.isNotEmpty()) { "The normalized camera image is empty." }
            PreparedVisionImage(bytes, bitmap.width, bitmap.height)
        } finally {
            bitmap.recycle()
        }
    }

    internal fun validateSourceFile(file: File, maxBytes: Long = MAX_VISION_SOURCE_IMAGE_BYTES) {
        require(maxBytes > 0L) { "Image byte limit must be positive." }
        val length = file.takeIf { it.isFile }?.length() ?: 0L
        require(length > 0L) { "The camera returned an empty image." }
        require(length <= maxBytes) { "The image is too large." }
    }
}
