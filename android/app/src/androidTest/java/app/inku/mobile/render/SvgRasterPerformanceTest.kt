package app.inku.mobile.render

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
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
                val rawMs = (System.nanoTime() - started) / 1_000_000.0
                val bitmapStarted = System.nanoTime()
                val bitmap = RustArtworkRasterizer().rasterize(svg, targetWidth = 1080, targetHeight = 1080)
                val bitmapTotalMs = (System.nanoTime() - bitmapStarted) / 1_000_000.0
                assertEquals(1080, raw.width)
                assertEquals(1080, raw.height)
                assertEquals(1080, bitmap.width)
                assertEquals(1080, bitmap.height)
                bitmap.recycle()
                Log.i("InkuRasterPerf", "$name iteration=$iteration warmup=${iteration == 0} raw_ms=$rawMs bitmap_total_ms=$bitmapTotalMs")
            }
        }
    }
}
