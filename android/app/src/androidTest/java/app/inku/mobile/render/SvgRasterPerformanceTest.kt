package app.inku.mobile.render

import android.graphics.Bitmap
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.nio.ByteBuffer
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/** Focused timing probe for the filtered preview and a filter-free control. */
@RunWith(AndroidJUnit4::class)
class SvgRasterPerformanceTest {
    @Test
    fun previewRasterAndBitmapTransfer() {
        val assets = InstrumentationRegistry.getInstrumentation().context.assets
        for (name in listOf("A-pen-circle", "C-filter-display-pencil")) {
            val svg = assets.open("render-engine-41/$name.svg").bufferedReader().use { it.readText() }
            repeat(4) { iteration ->
                val started = System.nanoTime()
                val raw = RustArtworkRasterizer().rasterizeRaw(svg, targetWidth = 1080, targetHeight = 1080)
                val rasterMs = (System.nanoTime() - started) / 1_000_000.0
                val transferStarted = System.nanoTime()
                val bitmap = Bitmap.createBitmap(raw.width, raw.height, Bitmap.Config.ARGB_8888)
                val bytes = RustArtworkRasterizer.argb8888RowsForBitmap(raw, bitmap.rowBytes)
                bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(bytes))
                bitmap.setPremultiplied(true)
                val transferMs = (System.nanoTime() - transferStarted) / 1_000_000.0
                bitmap.recycle()
                assertEquals(1080, raw.width)
                assertEquals(1080, raw.height)
                Log.i("InkuRasterPerf", "$name iteration=$iteration raster_ms=$rasterMs transfer_ms=$transferMs")
            }
        }
    }
}
