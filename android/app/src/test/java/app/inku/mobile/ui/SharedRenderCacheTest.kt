package app.inku.mobile.ui

import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test

class SharedRenderCacheTest {
    @Test
    fun cancelledCallerDoesNotCancelAnotherCallerForTheSameRender() = runBlocking {
        val cache = SharedRenderCache<String, String>(64, { it.length.toLong() }, 1)
        val started = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val renders = AtomicInteger()
        val render = {
            renders.incrementAndGet()
            started.complete(Unit)
            runBlocking { release.await() }
            "pixels"
        }

        val first = async { cache.get("same", render) }
        started.await()
        val second = async(start = CoroutineStart.UNDISPATCHED) { cache.get("same", render) }
        first.cancelAndJoin()
        release.complete(Unit)

        assertEquals("pixels", second.await())
        assertEquals("pixels", cache.get("same", render))
        assertEquals(1, renders.get())
    }

    @Test
    fun cancelledQueuedRenderDoesNotStartAfterPermitBecomesAvailable() = runBlocking {
        val cache = SharedRenderCache<String, String>(64, { it.length.toLong() }, 1)
        val started = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val obsoleteRenders = AtomicInteger()
        val current = async {
            cache.get("current") {
                started.complete(Unit)
                runBlocking { release.await() }
                "current"
            }
        }
        started.await()
        val obsolete = async(start = CoroutineStart.UNDISPATCHED) {
            cache.get("obsolete") {
                obsoleteRenders.incrementAndGet()
                "obsolete"
            }
        }
        obsolete.cancelAndJoin()
        release.complete(Unit)

        assertEquals("current", current.await())
        assertEquals(0, obsoleteRenders.get())
    }
}
