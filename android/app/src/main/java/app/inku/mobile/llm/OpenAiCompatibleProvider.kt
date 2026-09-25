package app.inku.mobile.llm

import app.inku.mobile.security.DisplaySanitizer
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

class OpenAiCompatibleProvider(
    override val providerId: String,
    private val baseUrl: String,
    private val apiKey: String?,
) : ModelProvider {
    override suspend fun generate(request: ModelRequest): ModelResponse = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        val model = modelForRequest(providerId, request.modelId)
        val payload = JSONObject()
            .put("model", model)
            .put(
                "messages",
                JSONArray().apply {
                    request.systemInstruction?.takeIf { it.isNotBlank() }?.let {
                        put(JSONObject().put("role", "system").put("content", it))
                    }
                    put(JSONObject().put("role", "user").put("content", userContent(request)))
                },
            )
            .put("temperature", pipelineTemperature(request.pipelineAction) ?: request.temperature)
            .put("max_tokens", request.maxTokens)
        request.tool?.let { tool ->
            val function = JSONObject()
                .put("name", tool.name)
                .put("description", tool.description)
                .put("parameters", JSONObject(tool.parametersJson))
            payload
                .put("tools", JSONArray().put(JSONObject().put("type", "function").put("function", function)))
                .put(
                    "tool_choice",
                    JSONObject()
                        .put("type", "function")
                        .put("function", JSONObject().put("name", tool.name)),
                )
        }
        if (request.stopSequences.isNotEmpty()) {
            payload.put("stop", JSONArray(request.stopSequences))
        }
        val response = postJson(endpoint("/chat/completions"), payload, request.timeoutMs)
        val choices = response.optJSONArray("choices") ?: error("Chat Completions response did not contain choices.")
        val first = choices.optJSONObject(0) ?: error("Chat Completions response was empty.")
        val message = first.optJSONObject("message")
        val content = extractToolArguments(message, request.tool?.name)
            ?: message?.optString("content")
            ?: first.optString("text")
        if (content.isBlank()) error("Chat Completions response did not contain text.")
        val usage = response.optJSONObject("usage")
        ModelResponse(
            text = content,
            modelId = request.modelId,
            promptTokens = usage?.optInt("prompt_tokens")?.takeIf { it > 0 },
            completionTokens = usage?.optInt("completion_tokens")?.takeIf { it > 0 },
            elapsedMs = System.currentTimeMillis() - started,
        )
    }

    private fun extractToolArguments(message: JSONObject?, expectedToolName: String?): String? {
        if (message == null || expectedToolName.isNullOrBlank()) return null
        val calls = message.optJSONArray("tool_calls") ?: return null
        for (i in 0 until calls.length()) {
            val call = calls.optJSONObject(i) ?: continue
            val function = call.optJSONObject("function") ?: continue
            if (function.optString("name") == expectedToolName) {
                val args = function.optString("arguments").trim()
                if (args.isNotBlank()) return args
            }
        }
        return null
    }

    private fun postJson(url: String, payload: JSONObject, timeoutMs: Long?): JSONObject {
        val connection = open(url, "POST", timeoutMs)
        try {
            connection.setRequestProperty("Content-Type", "application/json")
            connection.doOutput = true
            OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use { writer ->
                writer.write(payload.toString())
            }
            return readJson(connection)
        } finally {
            connection.disconnect()
        }
    }

    private fun open(url: String, method: String, timeoutMs: Long?): HttpURLConnection {
        val parsedUrl = URL(url)
        ProviderUrlValidator.validateRemoteBaseUrl(parsedUrl.toString())
        return (parsedUrl.openConnection() as HttpURLConnection).also { connection ->
            configureRemoteConnection(connection, method, apiKey, timeoutMs)
        }
    }

    private fun readJson(connection: HttpURLConnection): JSONObject {
        val success = connection.responseCode in 200..299
        val stream = if (success) connection.inputStream else connection.errorStream
        val (body, truncated) = readTextLimited(stream, if (success) MAX_RESPONSE_CHARS else MAX_ERROR_CHARS)
        if (!success) {
            val host = connection.url.host.orEmpty()
            val suffix = if (truncated) " [truncated]" else ""
            throw ModelProviderHttpException(
                connection.responseCode,
                "HTTP ${connection.responseCode} from $host: ${DisplaySanitizer.redact(body).take(180)}$suffix",
            )
        }
        require(!truncated) { "Remote response was too large." }
        return JSONObject(body)
    }

    private fun endpoint(path: String): String {
        return baseUrl.trimEnd('/') + path
    }

    private fun readTextLimited(stream: java.io.InputStream?, maxChars: Int): Pair<String, Boolean> {
        if (stream == null) return "" to false
        stream.bufferedReader(Charsets.UTF_8).use { reader ->
            val buffer = CharArray(8192)
            val builder = StringBuilder()
            while (true) {
                val read = reader.read(buffer)
                if (read < 0) return builder.toString() to false
                val remaining = maxChars - builder.length
                if (remaining <= 0) return builder.toString() to true
                if (read > remaining) {
                    builder.append(buffer, 0, remaining)
                    return builder.toString() to true
                }
                builder.append(buffer, 0, read)
            }
        }
    }

    internal companion object {
        internal fun modelForRequest(providerId: String, modelId: String): String =
            modelId.removePrefix("$providerId:").ifBlank { modelId }

        /** Plain text, or the prompt with one JPEG as an image_url data URI. */
        internal fun userContent(request: ModelRequest): Any {
            val image = request.imageJpeg ?: return request.prompt
            return JSONArray()
                .put(JSONObject().put("type", "text").put("text", request.prompt))
                .put(
                    JSONObject()
                        .put("type", "image_url")
                        .put(
                            "image_url",
                            JSONObject().put(
                                "url",
                                "data:image/jpeg;base64," + java.util.Base64.getEncoder().encodeToString(image),
                            ),
                        ),
                )
        }

        /** The server's OpenAI-compatible pipeline sampling: 0.3 for Stage 1, 0.0 otherwise. */
        internal fun pipelineTemperature(action: String?): Double? = when (action) {
            null -> null
            "generate_normalized_ddl" -> 0.3
            else -> 0.0
        }

        private const val MAX_RESPONSE_CHARS = 2_000_000
        private const val MAX_ERROR_CHARS = 16_384
    }
}

internal fun configureRemoteConnection(
    connection: HttpURLConnection,
    method: String,
    apiKey: String?,
    timeoutMs: Long? = null,
) {
    connection.requestMethod = method
    // A configured provider URL is the credential boundary. Never replay its
    // Authorization header to an automatic redirect target.
    connection.instanceFollowRedirects = false
    val attemptTimeout = (timeoutMs ?: REMOTE_REQUEST_TIMEOUT_MS.toLong())
        .coerceIn(1L, Int.MAX_VALUE.toLong())
        .toInt()
    connection.connectTimeout = attemptTimeout
    connection.readTimeout = attemptTimeout
    connection.setRequestProperty("Accept", "application/json")
    apiKey?.takeIf { it.isNotBlank() }?.let { connection.setRequestProperty("Authorization", "Bearer $it") }
}

private const val REMOTE_REQUEST_TIMEOUT_MS = 600_000
