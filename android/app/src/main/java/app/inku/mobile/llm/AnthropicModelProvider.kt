package app.inku.mobile.llm

import app.inku.mobile.security.DisplaySanitizer
import java.net.HttpURLConnection
import java.net.URL
import java.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * Claude API through Anthropic's own Messages API.
 *
 * This is the request the server makes for the `anthropic` provider kind
 * (`pipeline_provider.py` `_request`): `POST /v1/messages` with `x-api-key` and
 * `anthropic-version`, and a structured answer as one forced tool call whose
 * `input` is the response. The kind used to fall through to the
 * OpenAI-compatible transport, which posted `/chat/completions` with a Bearer
 * header, so the default Claude API base URL answered every drawing with 404.
 */
class AnthropicModelProvider(
    override val providerId: String,
    private val baseUrl: String,
    private val apiKey: String?,
    private val openConnection: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
) : ModelProvider {
    override suspend fun generate(request: ModelRequest): ModelResponse = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        ProviderUrlValidator.validateRemoteBaseUrl(baseUrl)
        val url = URL("${baseUrl.trimEnd('/')}/v1/messages")
        val connection = openConnection(url)
        val response = try {
            configureRemoteConnection(connection, "POST", apiKey = null, timeoutMs = request.timeoutMs)
            apiKey?.takeIf { it.isNotBlank() }?.let { connection.setRequestProperty("x-api-key", it) }
            connection.setRequestProperty("anthropic-version", ANTHROPIC_VERSION)
            connection.setRequestProperty("Content-Type", "application/json")
            connection.doOutput = true
            connection.outputStream.writer(Charsets.UTF_8).use { it.write(payload(request).toString()) }
            val status = connection.responseCode
            val success = status in 200..299
            val limit = if (success) MAX_RESPONSE_CHARS else MAX_ERROR_CHARS
            val stream = if (success) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader(Charsets.UTF_8)?.use { reader ->
                val result = StringBuilder()
                val buffer = CharArray(8192)
                while (result.length <= limit) {
                    val count = reader.read(buffer, 0, minOf(buffer.size, limit + 1 - result.length))
                    if (count < 0) break
                    result.append(buffer, 0, count)
                }
                result.toString()
            }.orEmpty()
            if (!success) {
                throw ModelProviderHttpException(
                    status,
                    "HTTP $status from ${url.host}: ${DisplaySanitizer.redact(body).take(180)}",
                )
            }
            require(body.length <= limit) { "Remote response was too large." }
            JSONObject(body)
        } finally {
            connection.disconnect()
        }
        val blocks = response.optJSONArray("content") ?: error("Claude response did not contain content.")
        val usage = response.optJSONObject("usage")
        ModelResponse(
            text = responseText(blocks, request.tool?.name),
            modelId = request.modelId,
            promptTokens = usage?.optInt("input_tokens")?.takeIf { it > 0 },
            completionTokens = usage?.optInt("output_tokens")?.takeIf { it > 0 },
            elapsedMs = System.currentTimeMillis() - started,
        )
    }

    private fun payload(request: ModelRequest): JSONObject {
        val payload = JSONObject()
            .put("model", request.modelId.removePrefix("$providerId:"))
            .put("max_tokens", request.maxTokens)
            .put("messages", JSONArray().put(JSONObject().put("role", "user").put("content", userContent(request))))
        // The server leaves pipeline sampling to the model default for this
        // kind; only the free-text requests (demo prompt, photo description)
        // say how warm to be. Claude accepts 0..1.
        if (request.pipelineAction == null) payload.put("temperature", request.temperature.coerceIn(0.0, 1.0))
        request.systemInstruction?.takeIf { it.isNotBlank() }?.let { payload.put("system", it) }
        if (request.stopSequences.isNotEmpty()) payload.put("stop_sequences", JSONArray(request.stopSequences))
        request.tool?.let { tool ->
            payload
                .put(
                    "tools",
                    JSONArray().put(
                        JSONObject()
                            .put("name", tool.name)
                            .put("description", tool.description)
                            .put("input_schema", JSONObject(tool.parametersJson)),
                    ),
                )
                .put("tool_choice", JSONObject().put("type", "tool").put("name", tool.name))
        }
        return payload
    }

    internal companion object {
        const val ANTHROPIC_VERSION = "2023-06-01"
        private const val MAX_RESPONSE_CHARS = 2_000_000
        private const val MAX_ERROR_CHARS = 16_384

        /** Plain text, or one base64 JPEG block ahead of the instruction, as the other transports order it. */
        internal fun userContent(request: ModelRequest): Any {
            val image = request.imageJpeg ?: return request.prompt
            return JSONArray()
                .put(
                    JSONObject()
                        .put("type", "image")
                        .put(
                            "source",
                            JSONObject()
                                .put("type", "base64")
                                .put("media_type", "image/jpeg")
                                .put("data", Base64.getEncoder().encodeToString(image)),
                        ),
                )
                .put(JSONObject().put("type", "text").put("text", request.prompt))
        }

        /**
         * The forced tool call's input when a tool was asked for, the text blocks
         * otherwise. Like the server, exactly one call of the requested tool is
         * an answer; anything else is a malformed response.
         */
        internal fun responseText(blocks: JSONArray, toolName: String?): String {
            val objects = (0 until blocks.length()).mapNotNull { blocks.optJSONObject(it) }
            if (toolName != null) {
                val calls = objects.filter { it.optString("type") == "tool_use" }
                check(calls.size == 1 && calls[0].optString("name") == toolName) {
                    "Claude response did not contain the requested tool call."
                }
                val input = calls[0].optJSONObject("input") ?: error("Claude tool call did not contain an input object.")
                return input.toString()
            }
            val text = objects
                .filter { it.optString("type") == "text" }
                .joinToString("") { it.optString("text") }
            check(text.isNotBlank()) { "Claude response did not contain text." }
            return text
        }
    }
}
