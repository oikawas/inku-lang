package app.inku.mobile.llm

import java.net.HttpURLConnection
import java.net.URL
import java.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/**
 * Claude API through Anthropic's own Messages API.
 *
 * This is the request the server makes for the `anthropic` provider kind
 * (`pipeline_provider.py` `_request`): `POST /v1/messages` with `x-api-key` and
 * `anthropic-version`, and one answer tool offered with `tool_choice: auto`.
 * Its `input`, or the response object in a text answer, is the response.
 * The kind used to fall through to the
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
            JSONObject(readProviderBody(connection))
        } finally {
            connection.disconnect()
        }
        val blocks = response.optJSONArray("content")
            ?: throw MalformedProviderResponseException("Claude response did not contain content.")
        val usage = response.optJSONObject("usage")
        ModelResponse(
            text = responseText(blocks, request.tool?.name),
            modelId = request.modelId,
            promptTokens = usage?.optInt("input_tokens")?.takeIf { it > 0 },
            completionTokens = usage?.optInt("output_tokens")?.takeIf { it > 0 },
            outputTruncated = response.optString("stop_reason") == "max_tokens",
            elapsedMs = System.currentTimeMillis() - started,
        )
    }

    private fun payload(request: ModelRequest): JSONObject {
        val model = request.modelId.removePrefix("$providerId:")
        val payload = JSONObject()
            .put("model", model)
            .put("max_tokens", request.maxTokens)
            .put("messages", JSONArray().put(JSONObject().put("role", "user").put("content", userContent(request))))
        // Both server transports (pipeline_provider.py and vision_client.py)
        // omit temperature for this kind. Sonnet 5.5 refuses it on photo
        // descriptions too; the rule follows the transport, not a model name.
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
                // "auto" for every model, as the server sends it: Claude Opus 5.5
                // refuses a forced tool ("tool_choice: type \"tool\" and \"any\" are
                // not supported for this model"). The answer's tool stays the only one.
                .put("tool_choice", JSONObject().put("type", "auto"))
        }
        return payload
    }

    internal companion object {
        const val ANTHROPIC_VERSION = "2023-06-01"

        /** Plain text, or one base64 JPEG ahead of the instruction, as the server sends Anthropic. */
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
         * The answer, read as the server's `pipeline_provider.py` reads it. When a
         * tool was offered, a call of it is the answer: exactly one call of that
         * tool, anything else malformed. With `tool_choice` "auto" the model may
         * answer in text instead; then the object in the text blocks is the
         * answer (see [jsonObjectIn]). Thinking blocks are never read. Without a
         * tool, the text blocks are the answer.
         */
        internal fun responseText(blocks: JSONArray, toolName: String?): String {
            val objects = (0 until blocks.length()).mapNotNull { blocks.optJSONObject(it) }
            val texts = objects.filter { it.optString("type") == "text" }.map { it.optString("text") }
            if (toolName != null) {
                val calls = objects.filter { it.optString("type") == "tool_use" }
                if (calls.isEmpty()) return jsonObjectIn(texts.joinToString("\n")).toString()
                if (calls.size != 1 || calls[0].optString("name") != toolName) {
                    throw JSONException("Claude returned an unexpected tool call.")
                }
                val input = calls[0].optJSONObject("input")
                    ?: throw JSONException("Claude tool call did not contain an input object.")
                return input.toString()
            }
            val text = texts.joinToString("\n")
            if (text.isBlank()) throw MalformedProviderResponseException("Claude response did not contain text.")
            return text
        }

        /**
         * The object an answer given as text carries, fenced or not: from the
         * first `{` to the last `}` (the server's `_json_object_in`). The shared
         * core checks its shape; no object is a malformed answer.
         */
        internal fun jsonObjectIn(text: String): JSONObject {
            val start = text.indexOf('{')
            val end = text.lastIndexOf('}')
            if (start == -1 || end <= start) throw JSONException("Claude answered without the response object.")
            return JSONObject(text.substring(start, end + 1))
        }
    }
}
