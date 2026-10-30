package app.inku.mobile.llm

import app.inku.mobile.data.catalogRequest
import java.net.SocketTimeoutException
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.ceil
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject

/** Concurrent slots and the host clock surround core-owned admission decisions. */
class ProviderAdmission(
    private val clockMs: () -> Long = System::currentTimeMillis,
    private val sleepMs: suspend (Long) -> Unit = { delay(it) },
) {
    private var transitions: ProviderRateTransitions = InMemoryProviderRateTransitions()
    private val slots = ConcurrentHashMap<String, Pair<Int, Semaphore>>()

    internal constructor(transitions: ProviderRateTransitions, clockMs: () -> Long = System::currentTimeMillis,
        sleepMs: suspend (Long) -> Unit = { delay(it) }) : this(clockMs, sleepMs) { this.transitions = transitions }

    internal suspend fun pauseFor429(providerId: String, refused: ModelProviderHttpException) {
        val now = clockMs() / 1000.0
        val seconds = SharedProviderAdmission.call(JSONObject().put("action", "retry").put("now", now)
            .put("retry_after", refused.retryAfter ?: JSONObject.NULL).put("raw", refused.retryBody)).getDouble("seconds")
        val result = transitions.transition(providerId, JSONObject().put("action", "pause").put("now", now).put("seconds", seconds))
        if (result.has("error")) throw ProviderRateStateException()
    }

    /** Test seam and unlimited provider path; production supplies the estimated tokens. */
    suspend fun <T> admit(providerId: String, timeoutMs: Long?, send: suspend () -> T): T =
        admit(providerId, "", JSONObject().put("rpm", 0).put("tpm", 0).put("rpd", 0), 0, timeoutMs, send)

    internal suspend fun <T> admit(providerId: String, kind: String, limits: JSONObject, inputTokens: Long,
        timeoutMs: Long?, send: suspend () -> T): T = admit(providerId, kind, limits, timeoutMs, { inputTokens }, send)

    internal suspend fun <T> admit(providerId: String, kind: String, limits: JSONObject, timeoutMs: Long?,
        estimate: suspend () -> Long, send: suspend () -> T): T {
        val deadline = timeoutMs?.let { clockMs() + it }
        val limit = providerConcurrencyLimit(providerId)
        val slot = if (limit <= 0) null else slots.compute(providerId) { _, cached ->
            cached?.takeIf { it.first == limit } ?: (limit to Semaphore(limit))
        }!!.second
        var acquired = false
        if (slot != null) {
            if (timeoutMs == null) { slot.acquire(); acquired = true }
            else try { withTimeout(timeoutMs) { slot.acquire(); acquired = true } }
            catch (_: TimeoutCancellationException) { currentCoroutineContext().ensureActive() }
            if (!acquired) throw ProviderSlotTimeoutException()
        }
        try {
            val inputTokens = try { estimate() } catch (refused: ModelProviderHttpException) {
                if (refused.statusCode == 429) pauseFor429(providerId, refused)
                throw refused
            }
            if (deadline != null && clockMs() >= deadline) throw ProviderRateLimitWaitException()
            val preflight = SharedProviderAdmission.call(JSONObject().put("action", "preflight")
                .put("limits", limits).put("input_tokens", inputTokens))
            if (preflight.optString("decision") == "reject") throw ProviderBudgetRejectedException(preflight.getString("reason"))
            if (preflight.has("error")) throw ProviderRateStateException()
            val id = java.util.UUID.randomUUID().toString()
            while (true) {
                val now = clockMs()
                val answer = transitions.transition(providerId, JSONObject().put("action", "admit").put("kind", kind)
                    .put("limits", limits).put("input_tokens", inputTokens).put("id", id).put("now", now / 1000.0))
                if (answer.has("error")) throw ProviderRateStateException()
                when (answer.optString("decision")) {
                    "admit" -> break
                    "reject" -> throw ProviderBudgetRejectedException(answer.getString("reason"))
                    "wait" -> {
                        val wait = ceil(answer.getDouble("seconds") * 1000.0).toLong().coerceAtLeast(1)
                        if (deadline != null && (now >= deadline || wait > deadline - now)) throw ProviderRateLimitWaitException()
                        sleepMs(wait)
                    }
                    else -> throw ProviderRateStateException()
                }
            }
            var used: Long? = null
            try {
                val result = send()
                used = (result as? ModelResponse)?.promptTokens?.toLong()
                return result
            } catch (refused: ModelProviderHttpException) {
                if (refused.statusCode == 429) {
                    pauseFor429(providerId, refused)
                }
                throw refused
            } catch (error: Throwable) {
                used = (error as? ProviderInputUsage)?.inputTokens
                throw error
            } finally {
                val actual = used ?: if (limits.optLong("tpm") == 0L) 0L else null
                val result = withContext(NonCancellable) { transitions.transition(providerId, JSONObject().put("action", "settle").put("id", id)
                    .put("now", clockMs() / 1000.0).put("input_tokens", actual ?: JSONObject.NULL)) }
                if (result.has("error")) throw ProviderRateStateException()
            }
        } finally { if (acquired) slot?.release() }
    }
}

private class InMemoryProviderRateTransitions : ProviderRateTransitions {
    private val mutex = Mutex()
    private val states = mutableMapOf<String, String>()
    override suspend fun transition(providerId: String, request: JSONObject): JSONObject = mutex.withLock {
        val state = states[providerId]?.let(::JSONObject) ?: JSONObject().put("events", JSONArray())
            .put("day", "").put("daily", 0).put("not_before", 0)
        val answer = SharedProviderAdmission.call(JSONObject(request.toString()).put("state", state))
        answer.optJSONObject("state")?.let { states[providerId] = app.inku.mobile.pipeline.CoreIdentityJson.encode(it) }
        answer
    }
}

class ProviderRateLimitWaitException : IllegalStateException("provider cool-down does not fit the attempt")
class ProviderSlotTimeoutException : SocketTimeoutException("provider slot deadline expired")
internal class ProviderRateStateException : IllegalStateException("provider rate accounting unavailable")
internal class ProviderBudgetRejectedException(val reason: String) : IllegalArgumentException(reason)

internal fun providerConcurrencyLimit(providerId: String): Int =
    catalogRequest("provider_concurrency", JSONObject().put("provider", providerId)).getInt("limit")
