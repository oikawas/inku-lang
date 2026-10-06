package app.inku.mobile.render

import android.graphics.Color
import android.os.Debug
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.nio.ByteBuffer
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.last
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Public fixtures only; no Room writes, author corpus reads, or provider calls. */
@RunWith(AndroidJUnit4::class)
class NativeDisplayDeviceTest {
    private val assets get() = InstrumentationRegistry.getInstrumentation().context.assets

    @Test
    fun publicWholesAndZoomedWindowsUseTheSharedComparison() = runBlocking {
        val handlesBefore = NativeDisplayBridge.liveHandles()
        val renderer = AndroidDisplayRenderer()
        try {
            assertEquals(EXPECTED_DISPLAY_API_VERSION, NativeDisplayBridge.apiVersion())
            listOf("p00", "p02", "p07", "p11").forEach { name ->
                val reference = assets.open("display/$name-chrome.png").use { it.readBytes() }
                val dimensions = ByteBuffer.wrap(reference, 16, 8)
                val width = dimensions.int
                val height = dimensions.int
                val start = System.nanoTime()
                var firstMillis: Long? = null
                val final = renderer.whole(svg(name), width, height).onEach {
                    if (firstMillis == null) firstMillis = elapsed(start)
                }.filter { it.complete && !it.coarse }.last()
                assertEquals(AndroidDisplayRenderer.Painter.Skia, final.painter)
                // Record memory before the development comparator allocates its working pixels.
                Log.i(TAG, "$name whole first_ms=$firstMillis complete_ms=${elapsed(start)} " +
                    "native_heap=${Debug.getNativeHeapAllocatedSize()}")
                val difference = NativeDisplayChecks.comparePng(width, height, final.bitmap.rowBytes,
                    NativeDisplayChecks.pixels(final.bitmap), reference)
                assertTrue("$name: $difference", difference.passes)
                Log.i(TAG, "$name comparison=$difference")
            }
            val source = svg("p07")
            listOf(4, 10).forEach { zoom ->
                // Same 1800x1400 viewport, drawn from the original SVG at each zoom.
                val region = renderer.detailRegion(DisplayRect(0.0, 0.0, 2000.0 * zoom, 2000.0 * zoom),
                    DisplayRect(600.0 * zoom, 700.0 * zoom, 1800.0, 1400.0))!!
                assertEquals(1800, region.width)
                assertEquals(1400, region.height)
                val start = System.nanoTime()
                var firstMillis: Long? = null
                val final = renderer.window(source, region, 0).onEach {
                    if (firstMillis == null) firstMillis = elapsed(start)
                }.filter { it.complete }.last()
                Log.i(TAG, "p07 zoom=$zoom first_ms=$firstMillis complete_ms=${elapsed(start)} " +
                    "native_heap=${Debug.getNativeHeapAllocatedSize()}")
                // One-piece native drawing of this window avoids an enormous full-canvas allocation.
                val scene = NativeDisplayBridge.prepare(source)
                val single = NativeDisplayBridge.begin(scene.handle, region.json())
                try {
                    NativeDisplayBridge.renderTile(single, region.json())
                    val reference = NativeDisplayBridge.finish(single)
                    val difference = NativeDisplayChecks.compareRaw(region.width, region.height,
                        final.bitmap.rowBytes, NativeDisplayChecks.pixels(final.bitmap),
                        reference.rowBytes, NativeDisplayChecks.pixels(reference))
                    assertTrue("zoom=$zoom: $difference", difference.passes)
                    reference.recycle()
                } finally {
                    NativeDisplayBridge.close(single)
                    NativeDisplayBridge.close(scene.handle)
                }
            }
            assertTrue(renderer.diagnostics().fallbacks.isEmpty())
        } finally {
            renderer.purgeScenes()
        }
        assertEquals(handlesBefore, NativeDisplayBridge.liveHandles())
    }

    @Test
    fun cancellationAndFallbackKeepTheNewWorkAndNativeOwnership() = runBlocking {
        val handlesBefore = NativeDisplayBridge.liveHandles()
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val started = AtomicInteger()
        val sceneHandle = AtomicLong()
        val sceneReleased = CompletableDeferred<Unit>()
        val gated = object : DisplayBridge by NativeDisplayBridge {
            override fun prepare(svg: String): NativeDisplayScene = NativeDisplayBridge.prepare(svg).also {
                sceneHandle.set(it.handle)
            }
            override fun close(handle: Long) {
                NativeDisplayBridge.close(handle)
                if (sceneHandle.get() == handle) sceneReleased.complete(Unit)
            }
            override fun renderTile(composite: Long, region: String) {
                started.incrementAndGet()
                entered.countDown()
                check(release.await(5, TimeUnit.SECONDS)) { "tile gate timed out" }
                NativeDisplayBridge.renderTile(composite, region)
            }
        }
        val oldRenderer = AndroidDisplayRenderer(gated)
        val renderer = AndroidDisplayRenderer()
        val oldFrames = AtomicInteger()
        val old = launch {
            oldRenderer.window(svg("p07"), DisplayRegion(8000, 8000, 1600, 1600, 1800, 1400), 0)
                .collect { oldFrames.incrementAndGet() }
        }
        try {
            assertTrue(withContext(Dispatchers.IO) { entered.await(5, TimeUnit.SECONDS) })
            old.cancel()
            release.countDown()
            val newest = renderer.whole(COLOR_ROWS, 3, 2).filter { !it.coarse }.last()
            old.cancelAndJoin()
            assertEquals(0, oldFrames.get())
            assertTrue("canceled work started ${started.get()} tiles", started.get() <= 2)
            assertEquals(Color.RED, newest.bitmap.getPixel(0, 0))
            assertEquals(Color.BLUE, newest.bitmap.getPixel(2, 0))
            assertEquals(Color.BLUE, newest.bitmap.getPixel(0, 1))
            assertEquals(Color.GREEN, newest.bitmap.getPixel(2, 1))
            assertEquals(128, Color.alpha(newest.bitmap.getPixel(1, 0)))
            assertArrayEquals(byteArrayOf(0, 128.toByte(), 0, 128.toByte()),
                NativeDisplayChecks.pixels(newest.bitmap).copyOfRange(4, 8))

            val unsupported = """<svg xmlns="http://www.w3.org/2000/svg" width="3" height="2"><defs>
                <linearGradient id="g"><stop stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient>
                </defs><rect width="3" height="2" fill="url(#g)"/></svg>""".trimIndent()
            assertEquals(AndroidDisplayRenderer.Painter.Resvg,
                renderer.whole(unsupported, 3, 2).last().painter)
            assertEquals(1, renderer.diagnostics().fallbacks.values.sum())
            try {
                renderer.whole(COLOR_ROWS, 0, 2).collect()
                throw AssertionError("invalid dimensions were accepted")
            } catch (failure: NativeDisplayException) {
                assertEquals("refused", failure.kind)
            }
            assertEquals(1, renderer.diagnostics().fallbacks.values.sum())
            Log.i(TAG, "cancel started_tiles=${started.get()} old_frames=${oldFrames.get()} " +
                "diagnostics=${renderer.diagnostics()}")
        } finally {
            release.countDown()
            old.cancelAndJoin()
            oldRenderer.purgeScenes()
            renderer.purgeScenes()
            // A canceled collector returns before its independent cache flight's
            // synchronous JNI call. That call retains the scene until it unwinds.
            if (sceneHandle.get() != 0L) withTimeout(10_000) { sceneReleased.await() }
        }
        assertEquals(handlesBefore, NativeDisplayBridge.liveHandles())
    }

    /** One cold p07 window separates native drawing from host snapshot/Bitmap costs. */
    @Test
    fun heavyWindowStageCostsAreRecordedOnce() = runBlocking {
        val handlesBefore = NativeDisplayBridge.liveHandles()
        val prepareNanos = AtomicLong()
        val tileNanos = AtomicLong()
        val longestTile = AtomicLong()
        val snapshotNanos = AtomicLong()
        val finishNanos = AtomicLong()
        val snapshots = AtomicInteger()
        val measured = object : DisplayBridge by NativeDisplayBridge {
            override fun prepare(svg: String): NativeDisplayScene {
                val start = System.nanoTime()
                return NativeDisplayBridge.prepare(svg).also { prepareNanos.addAndGet(System.nanoTime() - start) }
            }
            override fun renderTile(composite: Long, region: String) {
                val start = System.nanoTime()
                NativeDisplayBridge.renderTile(composite, region)
                val duration = System.nanoTime() - start
                tileNanos.addAndGet(duration)
                longestTile.accumulateAndGet(duration, ::maxOf)
            }
            override fun snapshot(composite: Long): android.graphics.Bitmap {
                val start = System.nanoTime()
                return NativeDisplayBridge.snapshot(composite).also {
                    snapshotNanos.addAndGet(System.nanoTime() - start)
                    snapshots.incrementAndGet()
                }
            }
            override fun finish(composite: Long): android.graphics.Bitmap {
                val start = System.nanoTime()
                return NativeDisplayBridge.finish(composite).also { finishNanos.addAndGet(System.nanoTime() - start) }
            }
        }
        val renderer = AndroidDisplayRenderer(measured)
        val source = svg("p07")
        val region = DisplayRegion(8000, 8000, 2400, 2800, 1800, 1400)
        try {
            val start = System.nanoTime()
            var firstMillis: Long? = null
            val final = renderer.window(source, region, 0).onEach {
                if (firstMillis == null) firstMillis = elapsed(start)
            }.filter { it.complete }.last()
            assertEquals(1800, final.bitmap.width)
            assertEquals(1400, final.bitmap.height)
            assertEquals(AndroidDisplayRenderer.Painter.Skia, final.painter)
            Log.i(TAG, "p07 cold_window first_ms=$firstMillis complete_ms=${elapsed(start)} " +
                "prepare_ms=${prepareNanos.get() / 1_000_000} tile_sum_ms=${tileNanos.get() / 1_000_000} " +
                "longest_tile_ms=${longestTile.get() / 1_000_000} snapshots=${snapshots.get()} " +
                "snapshot_sum_ms=${snapshotNanos.get() / 1_000_000} finish_ms=${finishNanos.get() / 1_000_000} " +
                "native_heap=${Debug.getNativeHeapAllocatedSize()} diagnostics=${renderer.diagnostics()}")
            // The existing pixel check passed. Time a single replay to distinguish
            // per-tile work from the cost of the same large viewport drawn at once.
            val scene = NativeDisplayBridge.prepare(source)
            val single = NativeDisplayBridge.begin(scene.handle, region.json())
            try {
                val singleStart = System.nanoTime()
                NativeDisplayBridge.renderTile(single, region.json())
                val image = NativeDisplayBridge.finish(single)
                Log.i(TAG, "p07 single_window complete_ms=${elapsed(singleStart)}")
                image.recycle()
            } finally {
                NativeDisplayBridge.close(single)
                NativeDisplayBridge.close(scene.handle)
            }
        } finally { renderer.purgeScenes() }
        assertEquals(handlesBefore, NativeDisplayBridge.liveHandles())
    }

    private fun svg(name: String) = assets.open("display/$name.svg").bufferedReader().use { it.readText() }
    private fun elapsed(start: Long) = (System.nanoTime() - start) / 1_000_000

    companion object {
        private const val TAG = "InkuDisplayCheck"
        private val COLOR_ROWS = """<svg xmlns="http://www.w3.org/2000/svg" width="3" height="2">
            <path d="M0 0h1v1H0z" fill="#ff0000"/><path d="M1 0h1v1H1z" fill="#00ff00" fill-opacity="0.5"/>
            <path d="M2 0h1v1H2z" fill="#0000ff"/><path d="M0 1h1v1H0z" fill="#0000ff"/>
            <path d="M1 1h1v1H1z" fill="#ff0000"/><path d="M2 1h1v1H2z" fill="#00ff00"/>
            </svg>""".trimIndent()
    }
}
