package app.inku.mobile.render

import android.graphics.Bitmap
import android.graphics.Matrix
import app.inku.mobile.ui.SharedRenderCache
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.buffer
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/** Display requests own cancellation. Two native calls at most; obsolete jobs stop between tiles. */
internal class AndroidDisplayRenderer(
    private val bridge: DisplayBridge = NativeDisplayBridge,
    private val dispatcher: CoroutineDispatcher = Executors.newFixedThreadPool(2) { runnable ->
        Thread(runnable, "inku-display").apply { isDaemon = true }
    }.asCoroutineDispatcher(),
) {
    enum class Painter { Skia, Resvg }
    data class Frame(val bitmap: Bitmap, val painter: Painter, val coarse: Boolean = false,
        val complete: Boolean = true, val region: DisplayRegion? = null)

    private val scenes = DisplayScenePool(bridge, 16L * 1024 * 1024)
    private val completed = SharedRenderCache<String, Frame>(
        64L * 1024 * 1024, { it.bitmap.allocationByteCount.toLong() }, 2, dispatcher,
    )
    private val snapshotIntervalNanos = 150_000_000L
    private val fallback = RustArtworkRasterizer()
    private val skiaWholes = AtomicInteger()
    private val skiaWindows = AtomicInteger()
    private val tilesDrawn = AtomicInteger()
    private val densityLimitedWindows = AtomicInteger()
    private val fallbackCodes = ConcurrentHashMap<String, AtomicInteger>()
    private val layout: DisplayLayout by lazy {
        check(bridge.apiVersion() == EXPECTED_DISPLAY_API_VERSION) { "Rust display API mismatch" }
        DisplayLayout.fromJson(bridge.layout())
    }

    fun whole(svg: String, width: Int, height: Int, rotationDegrees: Int = 0): Flow<Frame> = channelFlow {
        val rotation = normalizedRotation(rotationDegrees)
        val digest = withContext(dispatcher) { digest(svg) }
        val key = "display:$drawsWithSkia:$EXPECTED_DISPLAY_API_VERSION:$digest:whole:$width:$height:$rotation"
        completed.peek(key)?.let { send(it); return@channelFlow }
        val sourceWidth = if (rotation == 90 || rotation == 270) height else width
        val sourceHeight = if (rotation == 90 || rotation == 270) width else height
        var fallbackCode = "disabled"
        val coarse = if (drawsWithSkia) try {
            completed.getSuspending("display:$EXPECTED_DISPLAY_API_VERSION:$digest:coarse:$rotation") {
                withScene(digest, svg) { scene ->
                    Frame(rotate(bridge.rasterize(scene.handle, layout.coarseSide, layout.coarseSide), rotation),
                        Painter.Skia, coarse = true)
                }
            }
        } catch (failure: NativeDisplayException) {
            if (failure.kind != "unsupported") throw failure
            fallbackCode = failure.code
            null
        } else null
        if (coarse != null) send(coarse)
        val full = completed.getSuspending(key) {
            if (coarse == null) {
                fallbackCodes.computeIfAbsent(fallbackCode) { AtomicInteger() }.incrementAndGet()
                Frame(rotate(fallback.rasterize(svg, sourceWidth, sourceHeight), rotation), Painter.Resvg)
            } else {
                withScene(digest, svg) { scene ->
                    val region = DisplayRegion.fromJson(bridge.whole(scene.handle, sourceWidth, sourceHeight))
                    tiled(scene, region, rotation, null).also { skiaWholes.incrementAndGet() }
                }
            }
        }
        if (full != null) send(full)
    }.buffer(Channel.CONFLATED)

    fun window(svg: String, region: DisplayRegion, rotationDegrees: Int): Flow<Frame> = channelFlow {
        val rotation = normalizedRotation(rotationDegrees)
        val digest = withContext(dispatcher) { digest(svg) }
        val key = "skia:$EXPECTED_DISPLAY_API_VERSION:$digest:window:${region.json()}:$rotation"
        completed.peek(key)?.let { send(it); return@channelFlow }
        val full = completed.getSuspending(key) {
            withScene(digest, svg) { scene ->
                tiled(scene, region, rotation) { trySend(it) }.also { skiaWindows.incrementAndGet() }
            }
        }
        if (full != null) send(full)
    }.buffer(Channel.CONFLATED)

    suspend fun detailRegion(zoomed: DisplayRect, visible: DisplayRect): DisplayRegion? = withContext(dispatcher) {
        val limits = layout.copy(maxWindowPixels = minOf(layout.maxWindowPixels, 4L * 1024 * 1024))
        bridge.detailRegion(zoomed.json(), visible.json(), 1.0, limits.json())?.let(DisplayRegion::fromJson)?.also {
            if (it.fullWidth + 1 < zoomed.width || it.fullHeight + 1 < zoomed.height) {
                densityLimitedWindows.incrementAndGet()
            }
        }
    }

    private suspend fun <T> withScene(digest: String, svg: String, action: suspend (NativeDisplayScene) -> T): T =
        withContext(dispatcher) {
            check(layout.tileSide > 0) { "Invalid Rust display layout" }
            val lease = scenes.acquire(digest, svg)
            try {
                currentCoroutineContext().ensureActive()
                action(lease.scene)
            } finally { lease.close() }
        }

    private suspend fun tiled(scene: NativeDisplayScene, region: DisplayRegion, rotation: Int,
        progress: ((Frame) -> Unit)?): Frame = coroutineScope {
        val composite = bridge.begin(scene.handle, region.json())
        try {
            val tiles = DisplayRegion.list(bridge.tiles(composite))
            val next = AtomicInteger()
            val finished = AtomicInteger()
            val snapshot = Mutex()
            var handedOver = System.nanoTime()
            List(minOf(2, tiles.size)) {
                async(dispatcher) {
                    while (true) {
                        currentCoroutineContext().ensureActive()
                        val index = next.getAndIncrement()
                        if (index >= tiles.size) break
                        bridge.renderTile(composite, tiles[index].json())
                        tilesDrawn.incrementAndGet()
                        val count = finished.incrementAndGet()
                        currentCoroutineContext().ensureActive()
                        if (progress != null && count < tiles.size) snapshot.withLock {
                            val now = System.nanoTime()
                            if (now - handedOver >= snapshotIntervalNanos) {
                                handedOver = now
                                progress(Frame(rotate(bridge.snapshot(composite), rotation), Painter.Skia,
                                    complete = false, region = region))
                            }
                        }
                    }
                }
            }.awaitAll()
            currentCoroutineContext().ensureActive()
            Frame(rotate(bridge.finish(composite), rotation), Painter.Skia, region = region)
        } finally { bridge.close(composite) }
    }

    suspend fun purgeScenes() = withContext(dispatcher) { scenes.purge() }

    data class Diagnostics(val skiaWholes: Int, val skiaWindows: Int, val tilesDrawn: Int,
        val densityLimitedWindows: Int, val fallbacks: Map<String, Int>)

    fun diagnostics() = Diagnostics(skiaWholes.get(), skiaWindows.get(), tilesDrawn.get(),
        densityLimitedWindows.get(), fallbackCodes.mapValues { it.value.get() })

    companion object {
        // One display-only switch for rollback; export and thumbnails use resvg independently.
        internal const val drawsWithSkia = true
        private fun digest(svg: String): String = MessageDigest.getInstance("SHA-256")
            .digest(svg.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

        internal fun normalizedRotation(value: Int): Int = ((value % 360) + 360) % 360

        private fun rotate(bitmap: Bitmap, degrees: Int): Bitmap {
            if (degrees == 0) return bitmap
            val matrix = Matrix().apply { postRotate(degrees.toFloat()) }
            return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        }
    }
}
