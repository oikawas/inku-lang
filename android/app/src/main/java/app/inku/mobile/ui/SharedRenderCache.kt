package app.inku.mobile.ui

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit

/** Bounded LRU with one render per key while at least one caller still needs it. */
internal class SharedRenderCache<K : Any, V : Any>(
    private val maxWeight: Long,
    private val weightOf: (V) -> Long,
    maxConcurrentRenders: Int,
) {
    private class Flight<V>(val result: CompletableDeferred<V?> = CompletableDeferred()) {
        var waiters = 1
        lateinit var job: Job
    }

    private val lock = Any()
    private val cache = LinkedHashMap<K, V>(16, 0.75f, true)
    private val flights = mutableMapOf<K, Flight<V>>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val permits = Semaphore(maxConcurrentRenders)
    private var weight = 0L

    init {
        require(maxWeight > 0L)
        require(maxConcurrentRenders > 0)
    }

    fun peek(key: K): V? = synchronized(lock) { cache[key] }

    suspend fun get(key: K, render: () -> V?): V? {
        currentCoroutineContext().ensureActive()
        val flight = synchronized(lock) {
            cache[key]?.let { return it }
            flights[key]?.also { it.waiters++ } ?: Flight<V>().also { created ->
                flights[key] = created
                created.job = scope.launch(start = CoroutineStart.LAZY) {
                    try {
                        permits.withPermit {
                            currentCoroutineContext().ensureActive()
                            val value = render()
                            currentCoroutineContext().ensureActive()
                            synchronized(lock) {
                                if (flights[key] === created) {
                                    if (value != null) putLocked(key, value)
                                    flights.remove(key)
                                }
                            }
                            created.result.complete(value)
                        }
                    } catch (cancelled: CancellationException) {
                        created.result.cancel(cancelled)
                    } catch (failure: Throwable) {
                        created.result.completeExceptionally(failure)
                    } finally {
                        synchronized(lock) {
                            if (flights[key] === created) flights.remove(key)
                        }
                    }
                }
            }
        }
        try {
            currentCoroutineContext().ensureActive()
            flight.job.start()
            return flight.result.await()
        } finally {
            synchronized(lock) {
                flight.waiters--
                if (flight.waiters == 0 && flights[key] === flight) {
                    flights.remove(key)
                    // A queued render will not enter JNI. A synchronous render already in JNI
                    // may still finish, but its orphaned result will not enter the cache.
                    flight.job.cancel()
                }
            }
        }
    }

    private fun putLocked(key: K, value: V) {
        val entryWeight = weightOf(value).coerceAtLeast(1L)
        if (entryWeight > maxWeight) return
        cache.put(key, value)?.let { previous -> weight -= weightOf(previous).coerceAtLeast(1L) }
        weight += entryWeight
        val entries = cache.entries.iterator()
        while (weight > maxWeight && entries.hasNext()) {
            val eldest = entries.next()
            weight -= weightOf(eldest.value).coerceAtLeast(1L)
            entries.remove()
        }
    }
}
