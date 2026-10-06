package app.inku.mobile.render

import android.graphics.Bitmap
import java.nio.ByteBuffer

/** Test APK only: thresholds and white compositing live in the Rust test module. */
data class NativeDisplayDifference(val passes: Boolean, val worstBlock: Double, val differing: Double)

internal object NativeDisplayChecks {
    init { System.loadLibrary("display_check_android") }
    external fun comparePng(width: Int, height: Int, stride: Int,
        actual: ByteArray, reference: ByteArray): NativeDisplayDifference
    external fun compareRaw(width: Int, height: Int, actualStride: Int,
        actual: ByteArray, referenceStride: Int, reference: ByteArray): NativeDisplayDifference

    fun pixels(bitmap: Bitmap): ByteArray = ByteBuffer.allocate(bitmap.rowBytes * bitmap.height)
        .also(bitmap::copyPixelsToBuffer).array()
}
