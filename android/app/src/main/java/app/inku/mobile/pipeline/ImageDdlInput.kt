package app.inku.mobile.pipeline

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ImageDecoder
import app.inku.mobile.llm.VisionImagePreparer
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.MessageDigest
import java.util.Base64
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * The core's rule for the image a work is written from
 * (`inku.image-input-policy.v1`, SPEC §12.6.6). The numbers are the core's;
 * Android does not keep its own.
 */
data class ImageDdlPolicy(
    val maxLongSide: Int,
    val jpegQuality: Int,
    val maxBytes: Long,
    val reviewLongSide: Int,
    val drawingMediaType: String,
) {
    companion object {
        fun from(binding: SharedPipelineBinding): ImageDdlPolicy {
            val report = JSONObject(binding.imageInputPolicy())
            val policy = report.requiredObject("policy")
            return ImageDdlPolicy(
                maxLongSide = policy.getInt("max_long_side"),
                jpegQuality = policy.getInt("jpeg_quality"),
                maxBytes = policy.getLong("max_bytes"),
                reviewLongSide = policy.getInt("review_long_side"),
                drawingMediaType = report.requiredString("drawing_media_type"),
            )
        }
    }
}

/** `inku.image-canvas.v1`: the size to send an image at and the paper nearest its ratio. */
data class ImageDdlCanvas(val sentWidth: Int, val sentHeight: Int, val nearestFormatId: String) {
    companion object {
        fun of(binding: SharedPipelineBinding, originalWidth: Int, originalHeight: Int): ImageDdlCanvas {
            val request = JSONObject().put("original", JSONArray().put(originalWidth).put(originalHeight))
            val answer = JSONObject(binding.imageCanvas(request.toString().encodeToByteArray()).toString(Charsets.UTF_8))
            if (answer.has("error")) throw PipelineHostException("image_invalid")
            val sent = answer.getJSONArray("sent")
            return ImageDdlCanvas(sent.getInt(0), sent.getInt(1), answer.requiredString("nearest_format_id"))
        }
    }
}

/** One image as a pipeline prompt names it: type, size, SHA-256 and length. */
data class PipelineImageReference(
    val mediaType: String,
    val width: Int,
    val height: Int,
    val sha256: String,
    val byteLength: Int,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("media_type", mediaType)
        .put("width", width)
        .put("height", height)
        .put("sha256", sha256)
        .put("byte_len", byteLength)

    companion object {
        fun of(bytes: ByteArray, mediaType: String, width: Int, height: Int) = PipelineImageReference(
            mediaType = mediaType,
            width = width,
            height = height,
            sha256 = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) },
            byteLength = bytes.size,
        )
    }
}

/** The photo a work is written from, as sent, with the size it was taken at. */
class PreparedImageDdlInput(
    val jpeg: ByteArray,
    val reference: PipelineImageReference,
    val originalWidth: Int,
    val originalHeight: Int,
    val nearestFormatId: String,
) {
    /** The core's `ImageInput`. */
    fun authoringJson(): JSONObject = JSONObject()
        .put("sent", reference.toJson())
        .put("original_width", originalWidth)
        .put("original_height", originalHeight)
}

/**
 * Prepares a photo as the server's `prepare_image` does: oriented, any
 * transparency set on white, scaled to the core's sent size and encoded as
 * JPEG at the core's quality. A photo past the core's byte limit is refused.
 */
object ImageDdlInputs {
    suspend fun prepare(file: File, binding: SharedPipelineBinding = NativePipelineBridge): PreparedImageDdlInput =
        withContext(Dispatchers.IO) {
            VisionImagePreparer.validateSourceFile(file)
            val policy = ImageDdlPolicy.from(binding)
            var headerSize: Pair<Int, Int>? = null
            var headerCanvas: ImageDdlCanvas? = null
            val decoded = ImageDecoder.decodeBitmap(ImageDecoder.createSource(file)) { decoder, info, _ ->
                val canvas = ImageDdlCanvas.of(binding, info.size.width, info.size.height)
                headerSize = info.size.width to info.size.height
                headerCanvas = canvas
                decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                decoder.setTargetSize(canvas.sentWidth, canvas.sentHeight)
            }
            try {
                val header = requireNotNull(headerCanvas)
                // The decoder applies the photo's orientation; should a rotated
                // photo come out with its sides swapped from the header's size,
                // the photo's own size is the swapped one.
                val swapped = header.sentWidth != header.sentHeight &&
                    decoded.width == header.sentHeight && decoded.height == header.sentWidth
                val (originalWidth, originalHeight) = requireNotNull(headerSize).let { (width, height) ->
                    if (swapped) height to width else width to height
                }
                val canvas = if (swapped) ImageDdlCanvas.of(binding, originalWidth, originalHeight) else header
                val jpeg = onWhite(decoded, canvas.sentWidth, canvas.sentHeight).let { sent ->
                    try {
                        ByteArrayOutputStream().use { output ->
                            check(sent.compress(Bitmap.CompressFormat.JPEG, policy.jpegQuality, output)) {
                                "The photo could not be encoded."
                            }
                            output.toByteArray()
                        }
                    } finally {
                        sent.recycle()
                    }
                }
                if (jpeg.isEmpty() || jpeg.size > policy.maxBytes) throw PipelineHostException("image_too_large")
                PreparedImageDdlInput(
                    jpeg = jpeg,
                    reference = PipelineImageReference.of(jpeg, "image/jpeg", canvas.sentWidth, canvas.sentHeight),
                    originalWidth = originalWidth,
                    originalHeight = originalHeight,
                    nearestFormatId = canvas.nearestFormatId,
                )
            } finally {
                decoded.recycle()
            }
        }

    private fun onWhite(source: Bitmap, width: Int, height: Int): Bitmap =
        Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888).also { output ->
            Canvas(output).apply {
                drawColor(Color.WHITE)
                drawBitmap(
                    source,
                    null,
                    android.graphics.Rect(0, 0, width, height),
                    android.graphics.Paint(android.graphics.Paint.FILTER_BITMAP_FLAG),
                )
            }
        }
}

/**
 * The review drawing as a PNG of exactly [width]×[height] (server
 * `review_drawing`); null when the raster comes out another size.
 */
internal fun reviewDrawingPng(svg: String, width: Int, height: Int): ByteArray? {
    val raster = app.inku.mobile.render.RustArtworkRasterizer().rasterize(svg, targetWidth = width, targetHeight = height)
    try {
        if (raster.width != width || raster.height != height) return null
        return ByteArrayOutputStream().use { output ->
            check(raster.compress(Bitmap.CompressFormat.PNG, 100, output)) { "The review drawing could not be encoded." }
            output.toByteArray()
        }
    } finally {
        raster.recycle()
    }
}

/**
 * The images of the runs written from an image, by SHA-256, for as long as a
 * run needs them: the photo and the drawing reviewed beside it. Only their
 * references reach the snapshot, Room and the logs; a run that finds its image
 * gone stops rather than sending without it (server `image_missing`).
 */
class PipelineImageStore {
    private class Held(val bytes: ByteArray, val mediaType: String)

    private val images = ConcurrentHashMap<String, Held>()

    fun put(bytes: ByteArray, reference: PipelineImageReference) {
        images[reference.sha256] = Held(bytes.copyOf(), reference.mediaType)
    }

    fun has(sha256: String): Boolean = images.containsKey(sha256)

    /** The `data:` URL provider_wire takes, or null when the image is gone. */
    fun dataUrl(sha256: String): String? = images[sha256]?.let { held ->
        "data:${held.mediaType};base64," + Base64.getEncoder().encodeToString(held.bytes)
    }

    fun remove(sha256: String) {
        images.remove(sha256)
    }

    /** Releases the photo and drawing a finished run's record names. */
    fun release(imageDdlRecord: JSONObject?) {
        if (imageDdlRecord == null) return
        imageDdlRecord.optJSONObject("image")?.optJSONObject("sent")?.optString("sha256")?.let(::remove)
        imageDdlRecord.optJSONObject("drawing")?.optString("sha256")?.let(::remove)
    }
}
