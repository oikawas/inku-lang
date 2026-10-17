package app.inku.mobile.llm

import android.util.Log
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
    /** One normalized JPEG sent with [prompt] for camera/local Vision. */
    val imageJpeg: ByteArray? = null,
    /** Non-secret registration pinned when this shared-pipeline run began. */
    val chatGptSession: ChatGptSessionRef? = null,
    /** The demo's free-text instruction, whose Claude budget follows Server's demo route. */
    val demoInstruction: Boolean = false,
    /** A square PNG for autonomous refinement Vision only. */
    val imagePng: ByteArray? = null,
)

internal data class ModelImage(val bytes: ByteArray, val mimeType: String)

/** Select one image with its actual wire type; camera JPEG remains unchanged. */
internal fun ModelRequest.imagePayload(): ModelImage? {
    require(imageJpeg == null || imagePng == null) { "Only one model image is allowed" }
    if (pipelineAction == REFINEMENT_VISION_ACTION) {
        val png = requireNotNull(imagePng) { "Refinement advice needs a PNG." }
        RefinementVisionImage.requirePng768(png)
        return ModelImage(png, "image/png")
    }
    require(imagePng == null) { "PNG images are reserved for refinement advice" }
    return imageJpeg?.let { ModelImage(it, "image/jpeg") }
}

class ModelProviderHttpException(
    val statusCode: Int,
    message: String,
    /** What the provider said, from [providerRefusal]; empty when it said nothing readable. */
    val refusal: JSONObject = JSONObject(),
    /** The answer's `Retry-After` header, as sent: seconds or an HTTP date. */
    val retryAfter: String? = null,
    /** Gemini's `google.rpc.RetryInfo.retryDelay` in the refusal body, in seconds. */
    val retryDelaySeconds: Double? = null,
    /** The shared core's failure class, when this answer crossed provider_wire. */
    val failure: String? = null,
) : IllegalStateException(message)

/**
 * A provider answered 2xx without the part that carries the answer: no
 * choices, message, candidates or content, or only empty text. The server reads
 * the same answers with `data["choices"][0]["message"]` and a non-empty text
 * check, whose KeyError/IndexError/TypeError it classifies `malformed_payload`.
 */
class MalformedProviderResponseException(message: String) : IllegalStateException(message)

/** A cut-off tool input cannot become a complete pipeline answer. */
class ProviderOutputLimitException : IllegalStateException("Provider output reached its token limit.")

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

internal data class ProviderHttpBody(
    val status: Int,
    val body: String,
    val retryAfter: String?,
    val retryDelaySeconds: Double?,
)

/** HTTP framing and bounded I/O stay in the host; the core judges the response. */
internal fun readProviderHttpBody(connection: HttpURLConnection): ProviderHttpBody {
    val status = connection.responseCode
    val success = status in 200..299
    val limit = if (success) MAX_PROVIDER_RESPONSE_BYTES else MAX_PROVIDER_ERROR_BYTES
    val (bytes, over) = readBounded(if (success) connection.inputStream else connection.errorStream, limit)
    require(!success || !over) { "Remote response was too large." }
    val body = try {
        Charsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(bytes)).toString().removePrefix("\uFEFF")
    } catch (error: java.nio.charset.CharacterCodingException) {
        if (success) throw MalformedProviderResponseException("Provider response was not UTF-8.")
        ""
    }
    return ProviderHttpBody(status, body, connection.getHeaderField("Retry-After"), retryInfoDelaySeconds(body))
}

/** Map the core's decision to the host's existing effect and observation types. */
internal fun providerWireModelResponse(
    answer: JSONObject,
    request: ModelRequest,
    http: ProviderHttpBody,
    elapsedMs: Long,
    host: String,
): ModelResponse = when (answer.getString("outcome")) {
    "answer" -> ModelResponse(
        text = answer.getString("text"), modelId = request.modelId,
        promptTokens = (answer.opt("input_tokens") as? Number)?.toInt(),
        outputTruncated = answer.optJSONObject("cut") != null,
        elapsedMs = elapsedMs,
    )
    "cut" -> {
        Log.w("InkuProvider", "provider_output_limit " + JSONObject()
            .put("action", request.pipelineAction).put("model", request.modelId)
            .put("cut", answer.getJSONObject("cut")))
        throw ProviderOutputLimitException()
    }
    "malformed" -> throw MalformedProviderResponseException(answer.getString("detail"))
    "http_error" -> throw ModelProviderHttpException(
        http.status, "HTTP ${http.status} from $host: ${answer.getString("failure")}",
        answer.getJSONObject("refusal"), http.retryAfter, http.retryDelaySeconds,
        failure = answer.getString("failure"),
    )
    "refused" -> throw IllegalArgumentException(answer.getString("detail"))
    else -> error("unknown provider wire outcome")
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

/** Diagnostics use the same redacted refusal as the core's HTTP-response action. */
internal fun providerRefusal(body: String): JSONObject = SharedProviderWire.call(JSONObject()
    .put("action", "pipeline_response").put("format", "openai_chat")
    .put("status", 400).put("body", body)).getJSONObject("refusal")

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
