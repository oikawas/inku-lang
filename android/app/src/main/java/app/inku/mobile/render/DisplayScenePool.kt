package app.inku.mobile.render

import java.io.Closeable
import java.util.concurrent.atomic.AtomicBoolean

/** One cache reference plus independent request references; eviction never closes a request. */
internal class DisplayScenePool(private val bridge: DisplayBridge, private val maxBytes: Long) {
    private class Entry(val digest: String, val scene: NativeDisplayScene, var references: Int)
    private val lock = Any()
    private var kept: Entry? = null

    class Lease internal constructor(val scene: NativeDisplayScene, private val release: () -> Unit) : Closeable {
        private val closed = AtomicBoolean()
        override fun close() { if (closed.compareAndSet(false, true)) release() }
    }

    fun acquire(digest: String, svg: String): Lease {
        synchronized(lock) {
            kept?.takeIf { it.digest == digest }?.let {
                it.references++
                return lease(it)
            }
        }
        // Preparation can be slow: it never holds the cache lock.
        val prepared = bridge.prepare(svg)
        var unused: Long? = null
        var evicted: Long? = null
        val chosen = synchronized(lock) {
            val current = kept
            if (current != null && current.digest == digest) {
                unused = prepared.handle
                current.references++
                current
            } else {
                val cost = prepared.sourceBytes + prepared.pictureBytes
                val cacheable = cost >= 0 && cost <= maxBytes
                val entry = Entry(digest, prepared, if (cacheable) 2 else 1)
                if (cacheable) {
                    kept = entry
                    if (current != null && --current.references == 0) evicted = current.scene.handle
                }
                entry
            }
        }
        unused?.let(bridge::close)
        evicted?.let(bridge::close)
        return lease(chosen)
    }

    private fun lease(entry: Entry): Lease = Lease(entry.scene) {
        val close = synchronized(lock) { --entry.references == 0 }
        if (close) bridge.close(entry.scene.handle)
    }

    fun purge() {
        val close = synchronized(lock) {
            kept?.let { kept = null; if (--it.references == 0) it.scene.handle else null }
        }
        close?.let(bridge::close)
    }
}
