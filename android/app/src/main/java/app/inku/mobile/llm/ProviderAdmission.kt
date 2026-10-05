package app.inku.mobile.llm

import java.net.SocketTimeoutException
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.ceil
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.withTimeout
import org.json.JSONObject

/**
 * Provider-wide admission of shared-pipeline requests, without retries: the
 * two parts of the server's admission that do not need a quota setting.
 *
 * - After a 429, the provider is not sent to again until the longest of 62
 *   seconds, the answer's `Retry-After` and Gemini's `RetryInfo.retryDelay`
 *   has passed (`provider_rate_limits.py` `retry_after_seconds` / `cool_down`).
 *   A wait that does not fit in what is left of the attempt is not sent at
 *   all: [ProviderRateLimitWaitException], `rate_limited`.
 * - A provider limited by concurrency rather than volume holds its requests
 *   to that many at once (`provider_limits.py`). Waiting for a slot past the
 *   attempt's time is [ProviderSlotTimeoutException], `transport_timeout`.
 *
 * The state is in memory and shared by the process through [shared]; the
 * server keeps the cool-down in its database for several workers, which one
 * app process does not need.
 */
class ProviderAdmission(
    private val clockMs: () -> Long = System::currentTimeMillis,
    private val sleepMs: suspend (Long) -> Unit = { delay(it) },
) {
    private val notBeforeMs = ConcurrentHashMap<String, Long>()
    private val slots = ConcurrentHashMap<String, Pair<Int, Semaphore>>()

    /** Sends [send] for [providerId] once admitted, within [timeoutMs] of this call. */
    suspend fun <T> admit(providerId: String, timeoutMs: Long?, send: suspend () -> T): T {
        val deadline = timeoutMs?.let { clockMs() + it }
        val limit = providerConcurrencyLimit(providerId)
        if (limit <= 0) return paced(providerId, deadline, send)
        // Released on the same object it was taken from, as the server does.
        val slot = slots.compute(providerId) { _, cached ->
            cached?.takeIf { it.first == limit } ?: (limit to Semaphore(limit))
        }!!.second
        var acquired = false
        if (timeoutMs == null) {
            slot.acquire()
            acquired = true
        } else {
            try {
                withTimeout(timeoutMs) {
                    slot.acquire()
                    acquired = true
                }
            } catch (_: TimeoutCancellationException) {
                // A permit taken just as the time ran out is still held below;
                // a caller's own cancellation is not this wait's timeout.
                currentCoroutineContext().ensureActive()
            }
        }
        if (!acquired) throw ProviderSlotTimeoutException()
        try {
            return paced(providerId, deadline, send)
        } finally {
            slot.release()
        }
    }

    private suspend fun <T> paced(providerId: String, deadline: Long?, send: suspend () -> T): T {
        while (true) {
            val now = clockMs()
            val wait = (notBeforeMs[providerId] ?: 0L) - now
            if (wait <= 0L) break
            if (deadline != null && now + wait > deadline) throw ProviderRateLimitWaitException()
            sleepMs(wait)
        }
        try {
            return send()
        } catch (refused: ModelProviderHttpException) {
            if (refused.statusCode == 429) {
                coolDown(providerId, retryAfterSeconds(refused.retryAfter, refused.retryDelaySeconds, clockMs() / 1000.0))
            }
            throw refused
        }
    }

    private fun coolDown(providerId: String, seconds: Double) {
        val until = clockMs() + ceil(seconds * 1000.0).toLong()
        notBeforeMs.merge(providerId, until, ::maxOf)
    }

    companion object {
        /** The process's one admission, as the server's is one per database. */
        val shared = ProviderAdmission()
    }
}

/** A 429's cool-down would end after the attempt's deadline; nothing was sent. */
class ProviderRateLimitWaitException : IllegalStateException("provider cool-down does not fit the attempt")

/** No slot on a concurrency-limited provider freed within the attempt. */
class ProviderSlotTimeoutException : SocketTimeoutException("provider slot deadline expired")

/**
 * How many requests this provider takes at once; 0 means no limit. The
 * server's builtin `max_concurrency` (`model_settings.py`): Ollama Cloud's free
 * tier answered 429 above two simultaneous requests.
 */
internal fun providerConcurrencyLimit(providerId: String): Int = if (providerId == "ollama-cloud") 2 else 0

/** The server's `WINDOW_SECONDS`: no provider is sent to sooner than this after a 429. */
private const val RATE_WINDOW_SECONDS = 62.0

/**
 * The server's `retry_after_seconds`: the longest finite one of 62 seconds,
 * `Retry-After` as seconds or as an HTTP date from [nowSeconds], and the
 * refusal's RetryInfo delay.
 */
internal fun retryAfterSeconds(retryAfter: String?, retryDelaySeconds: Double?, nowSeconds: Double): Double {
    val values = mutableListOf(RATE_WINDOW_SECONDS)
    if (!retryAfter.isNullOrEmpty()) {
        val seconds = pythonFloat(retryAfter)
        if (seconds != null) {
            values += seconds
        } else {
            httpDateSeconds(retryAfter)?.let { values += it - nowSeconds }
        }
    }
    retryDelaySeconds?.let { values += it }
    return values.filter { it.isFinite() }.max()
}

/**
 * The longest `retryDelay` ("90s") among the `google.rpc.RetryInfo` details of
 * a refusal body, read as the server reads it; null when there is none.
 */
internal fun retryInfoDelaySeconds(body: String): Double? {
    val details = runCatching { JSONObject(body).optJSONObject("error")?.optJSONArray("details") }.getOrNull()
        ?: return null
    val found = mutableListOf<Double>()
    for (index in 0 until details.length()) {
        val detail = details.optJSONObject(index) ?: continue
        if (detail.optString("@type") != RETRY_INFO_TYPE) continue
        val delay = detail.opt("retryDelay") as? String ?: continue
        if (!delay.endsWith("s")) continue
        // The server's loop stops at the first value float() refuses.
        found += pythonFloat(delay.dropLast(1)) ?: break
    }
    return found.filter { it.isFinite() }.maxOrNull()
}

private const val RETRY_INFO_TYPE = "type.googleapis.com/google.rpc.RetryInfo"

private val PYTHON_FLOAT = Regex("[+-]?((\\d+(\\.\\d*)?|\\.\\d+)([eE][+-]?\\d+)?|inf|infinity|nan)", RegexOption.IGNORE_CASE)

/** Python's `float(text)` for the forms a header or a delay can take; null where it raises. */
private fun pythonFloat(text: String): Double? {
    val value = text.trim()
    if (!PYTHON_FLOAT.matches(value)) return null
    val negative = value.startsWith("-")
    return when (value.trimStart('+', '-').lowercase()) {
        "inf", "infinity" -> if (negative) Double.NEGATIVE_INFINITY else Double.POSITIVE_INFINITY
        "nan" -> Double.NaN
        else -> value.toDouble()
    }
}

/** Seconds since the epoch of an RFC 1123 date, as `parsedate_to_datetime` reads one. */
private fun httpDateSeconds(text: String): Double? =
    runCatching { ZonedDateTime.parse(text.trim(), DateTimeFormatter.RFC_1123_DATE_TIME).toEpochSecond().toDouble() }
        .getOrNull()
