package app.inku.mobile.render

import android.graphics.Bitmap
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DisplayScenePoolTest {
    @Test
    fun evictionKeepsRequestReferencesAndLastCloseReleasesTheHandle() {
        val bridge = FakeBridge()
        val pool = DisplayScenePool(bridge, 100)
        val first = pool.acquire("a", "a")
        val shared = pool.acquire("a", "a")
        assertEquals(first.scene.handle, shared.scene.handle)
        val next = pool.acquire("b", "b")
        assertTrue(bridge.closed.isEmpty())
        first.close()
        assertTrue(bridge.closed.isEmpty())
        shared.close()
        assertEquals(listOf(first.scene.handle), bridge.closed)
        pool.purge()
        assertEquals(listOf(first.scene.handle), bridge.closed)
        next.close()
        next.close()
        assertEquals(listOf(first.scene.handle, next.scene.handle), bridge.closed)
        assertEquals(2L, bridge.created)
    }

    private class FakeBridge : DisplayBridge {
        var created = 0L
        val closed = mutableListOf<Long>()
        override fun prepare(svg: String) = NativeDisplayScene(++created, 10.0, 10.0, 10, 10)
        override fun close(handle: Long) { closed.add(handle) }
        override fun apiVersion(): String = error("unused")
        override fun layout(): String = error("unused")
        override fun liveHandles(): Int = error("unused")
        override fun whole(handle: Long, width: Int, height: Int): String = error("unused")
        override fun detailRegion(zoomed: String, visible: String, pixelScale: Double, limits: String): String? = error("unused")
        override fun begin(handle: Long, region: String): Long = error("unused")
        override fun tiles(composite: Long): String = error("unused")
        override fun renderTile(composite: Long, region: String) = error("unused")
        override fun snapshot(composite: Long): Bitmap = error("unused")
        override fun finish(composite: Long): Bitmap = error("unused")
        override fun rasterize(handle: Long, width: Int, height: Int): Bitmap = error("unused")
    }
}
