package app.inku.mobile.llm

import app.inku.mobile.security.DisplaySanitizer
import java.io.InputStream
import java.net.HttpURLConnection
import org.json.JSONObject

interface ModelProvider {
    val providerId: String

    suspend fun generate(request: ModelRequest): ModelResponse
}

data class ModelRequest(
    val modelId: String,
    val prompt: String,
    val temperature: Double,
    val maxTokens: Int,
    val stopSequences: List<String> = emptyList(),
    val systemInstruction: String? = null,
    val tool: ModelTool? = null,
    /** Host-enforced bound for one transport attempt. */
    val timeoutMs: Long? = null,
    /**
     * Shared-pipeline action name (`generate_normalized_ddl`, ...). When set, a
     * remote transport applies the server's per-provider pipeline request shape
     * instead of the generic [temperature].
     */
    val pipelineAction: String? = null,
    /** One normalized JPEG sent with [prompt]; only camera analysis sets it. */
    val imageJpeg: ByteArray? = null,
    /** Gemini `thinkingLevel` for a non-pipeline request; null keeps the model default. */
    val thinkingLevel: String? = null,
    /** Non-secret registration pinned when this shared-pipeline run began. */
    val chatGptSession: ChatGptSessionRef? = null,
)

class ModelProviderHttpException(
    val statusCode: Int,
    message: String,
    /** What the provider said, from [providerRefusal]; empty when it said nothing readable. */
    val refusal: JSONObject = JSONObject(),
    /** The answer's `Retry-After` header, as sent: seconds or an HTTP date. */
    val retryAfter: String? = null,
    /** Gemini's `google.rpc.RetryInfo.retryDelay` in the refusal body, in seconds. */
    val retryDelaySeconds: Double? = null,
) : IllegalStateException(message)

/**
 * A provider answered 2xx without the part that carries the answer: no
 * choices, message, candidates or content, or only empty text. The server reads
 * the same answers with `data["choices"][0]["message"]` and a non-empty text
 * check, whose KeyError/IndexError/TypeError it classifies `malformed_payload`.
 */
class MalformedProviderResponseException(message: String) : IllegalStateException(message)

/**
 * The builtin services that need a key, as the server's builtin definitions
 * mark `requires_api_key` (`model_settings.py`). Local Ollama and connections
 * added by hand do not.
 */
internal fun requiresApiKey(providerId: String): Boolean = providerId in API_KEY_PROVIDER_IDS

private val API_KEY_PROVIDER_IDS = setOf("openai", "anthropic", "gemini", "nvidia", "ollama-cloud")

/** The server's `failure_detail` for a connection whose key is missing. */
internal const val CREDENTIALS_UNAVAILABLE = "credentials_unavailable"

/**
 * The most a provider's 2xx answer may carry: the shared pipeline's
 * `prompt_limits.max_response_bytes`, which the server's transport also reads
 * as its response bound. A larger answer is refused, as the server's
 * "provider response limit exceeded" ValueError is.
 */
internal const val MAX_PROVIDER_RESPONSE_BYTES = 1024 * 1024

/** The server reads a refusal's first 16 KiB to say why (`pipeline_provider.py`). */
internal const val MAX_PROVIDER_ERROR_BYTES = 16_384

/**
 * The body of one provider answer, bounded in bytes as the server bounds it.
 * A non-2xx answer becomes a [ModelProviderHttpException] carrying its first
 * [MAX_PROVIDER_ERROR_BYTES]; a 2xx answer over [MAX_PROVIDER_RESPONSE_BYTES]
 * is an IllegalArgumentException (`provider_rejected`).
 */
internal fun readProviderBody(connection: HttpURLConnection): String {
    val status = connection.responseCode
    val success = status in 200..299
    val limit = if (success) MAX_PROVIDER_RESPONSE_BYTES else MAX_PROVIDER_ERROR_BYTES
    val (bytes, over) = readBounded(if (success) connection.inputStream else connection.errorStream, limit)
    val body = String(bytes, Charsets.UTF_8)
    if (!success) {
        val suffix = if (over) " [truncated]" else ""
        throw ModelProviderHttpException(
            status,
            "HTTP $status from ${connection.url.host.orEmpty()}: ${DisplaySanitizer.redact(body).take(180)}$suffix",
            providerRefusal(body),
            retryAfter = connection.getHeaderField("Retry-After"),
            retryDelaySeconds = retryInfoDelaySeconds(body),
        )
    }
    require(!over) { "Remote response was too large." }
    return body
}

/** At most [limit] bytes, and whether the stream held more. */
private fun readBounded(stream: InputStream?, limit: Int): Pair<ByteArray, Boolean> {
    if (stream == null) return ByteArray(0) to false
    stream.use { input ->
        val buffer = ByteArray(limit + 1)
        var size = 0
        while (size < buffer.size) {
            val read = input.read(buffer, size, buffer.size - size)
            if (read < 0) break
            size += read
        }
        return if (size > limit) buffer.copyOf(limit) to true else buffer.copyOf(size) to false
    }
}

/**
 * What a refusal says, without anything that could carry a key -- the server's
 * `_provider_error` (`pipeline_provider.py`). OpenAI, Anthropic and Gemini all
 * answer `{"error": {...}}`; its code, type, param and status name the reason.
 * The message is kept short and redacted, since a 401 echoes part of the key.
 */
internal fun providerRefusal(body: String): JSONObject {
    val found = JSONObject()
    val error = runCatching { JSONObject(body).optJSONObject("error") }.getOrNull() ?: return found
    for (key in listOf("code", "type", "param", "status")) {
        when (val value = error.opt(key)) {
            is String -> if (value.isNotEmpty()) found.put(key, value)
            is Int, is Long -> found.put(key, value)
        }
    }
    error.optString("message").takeIf { it.isNotEmpty() }?.let {
        found.put("message", DisplaySanitizer.redact(it).take(240))
    }
    return found
}

data class ModelResponse(
    val text: String,
    val modelId: String,
    val promptTokens: Int? = null,
    val completionTokens: Int? = null,
    val elapsedMs: Long? = null,
    /** The transport reported an output-token limit rather than a complete answer. */
    val outputTruncated: Boolean = false,
)

data class ModelTool(
    val name: String,
    val description: String,
    val parametersJson: String,
)
