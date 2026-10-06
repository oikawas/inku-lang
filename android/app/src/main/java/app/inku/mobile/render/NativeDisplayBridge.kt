package app.inku.mobile.render

import android.graphics.Bitmap
import org.json.JSONArray
import org.json.JSONObject

/** A classified shared-core failure; Bitmap/JNI failures keep their host exception. */
class NativeDisplayException(message: String) : IllegalStateException(message) {
    private val payload = JSONObject(message)
    val kind: String = payload.getString("kind")
    val code: String = payload.getString("code")
}

data class NativeDisplayScene(
    val handle: Long,
    val intrinsicWidth: Double,
    val intrinsicHeight: Double,
    val sourceBytes: Long,
    val pictureBytes: Long,
)

data class DisplayRegion(
    val fullWidth: Int, val fullHeight: Int,
    val x: Int, val y: Int, val width: Int, val height: Int,
) {
    fun json(): String = JSONObject().put("full_width", fullWidth).put("full_height", fullHeight)
        .put("x", x).put("y", y).put("width", width).put("height", height).toString()

    companion object {
        fun fromJson(value: String): DisplayRegion = fromJson(JSONObject(value))
        fun fromJson(value: JSONObject): DisplayRegion = DisplayRegion(
            value.getInt("full_width"), value.getInt("full_height"), value.getInt("x"), value.getInt("y"),
            value.getInt("width"), value.getInt("height"),
        )
        fun list(value: String): List<DisplayRegion> = JSONArray(value).let { array ->
            List(array.length()) { fromJson(array.getJSONObject(it)) }
        }
    }
}

data class DisplayRect(val x: Double, val y: Double, val width: Double, val height: Double) {
    fun json(): String = JSONObject().put("x", x).put("y", y)
        .put("width", width).put("height", height).toString()
}

data class DisplayLayout(
    val coarseSide: Int, val tileSide: Int, val maxWindowSide: Int,
    val maxWindowPixels: Long, val maxCanvasSide: Int,
) {
    fun json(): String = JSONObject().put("coarse_side", coarseSide).put("tile_side", tileSide)
        .put("max_window_side", maxWindowSide).put("max_window_pixels", maxWindowPixels)
        .put("max_canvas_side", maxCanvasSide).toString()

    companion object {
        fun fromJson(value: String): DisplayLayout = JSONObject(value).let {
            DisplayLayout(it.getInt("coarse_side"), it.getInt("tile_side"), it.getInt("max_window_side"),
                it.getLong("max_window_pixels"), it.getInt("max_canvas_side"))
        }
    }
}

/** Synchronous JNI transport. Hosts own threads, cancellation and cache references. */
interface DisplayBridge {
    fun apiVersion(): String
    fun layout(): String
    fun prepare(svg: String): NativeDisplayScene
    fun close(handle: Long)
    fun liveHandles(): Int
    fun whole(handle: Long, width: Int, height: Int): String
    fun detailRegion(zoomed: String, visible: String, pixelScale: Double, limits: String): String?
    fun begin(handle: Long, region: String): Long
    fun tiles(composite: Long): String
    fun renderTile(composite: Long, region: String)
    fun snapshot(composite: Long): Bitmap
    fun finish(composite: Long): Bitmap
    fun rasterize(handle: Long, width: Int, height: Int): Bitmap
}

object NativeDisplayBridge : DisplayBridge {
    init { System.loadLibrary("inku_render_android") }
    external override fun apiVersion(): String
    external override fun layout(): String
    external override fun prepare(svg: String): NativeDisplayScene
    external override fun close(handle: Long)
    external override fun liveHandles(): Int
    external override fun whole(handle: Long, width: Int, height: Int): String
    external override fun detailRegion(zoomed: String, visible: String, pixelScale: Double, limits: String): String?
    external override fun begin(handle: Long, region: String): Long
    external override fun tiles(composite: Long): String
    external override fun renderTile(composite: Long, region: String)
    external override fun snapshot(composite: Long): Bitmap
    external override fun finish(composite: Long): Bitmap
    external override fun rasterize(handle: Long, width: Int, height: Int): Bitmap
}

internal const val EXPECTED_DISPLAY_API_VERSION = "0.1.0"
