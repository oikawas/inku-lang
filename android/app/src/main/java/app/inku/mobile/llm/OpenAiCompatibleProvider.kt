package app.inku.mobile.llm

import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

class OpenAiCompatibleProvider(
    override val providerId: String,
    private val baseUrl: String,
    private val apiKey: String?,
    private val openConnection: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
) : ModelProvider {
    override suspend fun generate(request: ModelRequest): ModelResponse = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        val response = postJson(endpoint("/chat/completions"), requestBody(providerId, request, baseUrl), request.timeoutMs)
        val content = answerText(response, request.tool?.name)
        val usage = response.optJSONObject("usage")
        ModelResponse(
            text = content,
            modelId = request.modelId,
            promptTokens = usage?.optInt("prompt_tokens")?.takeIf { it > 0 },
            completionTokens = usage?.optInt("completion_tokens")?.takeIf { it > 0 },
            outputTruncated = response.optJSONArray("choices")?.optJSONObject(0)?.optString("finish_reason") == "length",
            elapsedMs = System.currentTimeMillis() - started,
        )
    }

    private fun postJson(url: String, payload: JSONObject, timeoutMs: Long?): JSONObject {
        val connection = open(url, "POST", timeoutMs)
        try {
            connection.setRequestProperty("Content-Type", "application/json")
            connection.doOutput = true
            OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use { writer ->
                writer.write(payload.toString())
            }
            return JSONObject(readProviderBody(connection))
        } finally {
            connection.disconnect()
        }
    }

    private fun open(url: String, method: String, timeoutMs: Long?): HttpURLConnection {
        // Validated before `URL(url)`, so an unparseable address is the
        // reader's configuration failure rather than a transport one.
        ProviderUrlValidator.validateRemoteBaseUrl(url)
        return openConnection(URL(url)).also { connection ->
            configureRemoteConnection(connection, method, apiKey = null, timeoutMs = timeoutMs)
            // The server sends `"Bearer " + (key or "none")` to every
            // OpenAI-compatible connection, keyed or not.
            connection.setRequestProperty("Authorization", "Bearer ${apiKey?.takeIf { it.isNotBlank() } ?: "none"}")
        }
    }

    private fun endpoint(path: String): String {
        return baseUrl.trimEnd('/') + path
    }

    internal companion object {
        /**
         * The answer in a Chat Completions response, read as the server reads
         * `data["choices"][0]["message"]`: the offered tool's arguments, else
         * the message's own text. No choice, no message, or no text in it is a
         * [MalformedProviderResponseException]; a JSON null content is not the
         * text "null".
         */
        internal fun answerText(response: JSONObject, toolName: String?): String {
            val first = response.optJSONArray("choices")?.optJSONObject(0)
                ?: throw MalformedProviderResponseException("Chat Completions response did not contain a choice.")
            val message = first.optJSONObject("message")
                ?: throw MalformedProviderResponseException("Chat Completions response did not contain a message.")
            val content = extractToolArguments(message, toolName) ?: message.opt("content") as? String
            if (content.isNullOrBlank()) {
                throw MalformedProviderResponseException("Chat Completions response did not contain text.")
            }
            return content
        }

        /** An offered tool may answer once, or the server reads the message text. */
        internal fun extractToolArguments(message: JSONObject?, expectedToolName: String?): String? {
            if (message == null || expectedToolName.isNullOrBlank()) return null
            val calls = message.optJSONArray("tool_calls") ?: return null
            if (calls.length() == 0) return null
            val function = calls.optJSONObject(0)?.optJSONObject("function")
            if (calls.length() != 1 || function?.optString("name") != expectedToolName) {
                throw JSONException("Chat Completions returned an unexpected tool call.")
            }
            return (function?.opt("arguments") as? String)?.takeIf { it.isNotBlank() }
                ?: throw JSONException("Chat Completions tool call did not contain arguments text.")
        }

        internal fun modelForRequest(providerId: String, modelId: String): String =
            modelId.removePrefix("$providerId:").ifBlank { modelId }

        /**
         * The Chat Completions body, in the server's per-connection shape
         * (`pipeline_provider.py`). A requested answer is a forced function
         * call, except on `ollama`, whose structured output goes as a strict
         * JSON-schema `response_format` -- the answer then comes back as the
         * message text, which [generate] already reads. A pipeline request to
         * either Ollama connection also turns reasoning off. OpenAI's own API
         * takes its length, temperature and reasoning fields differently; see
         * [putOpenAiSampling].
         */
        internal fun requestBody(providerId: String, request: ModelRequest, baseUrl: String): JSONObject {
            val model = modelForRequest(providerId, request.modelId)
            val payload = JSONObject()
                .put("model", model)
                .put("stream", false)
                .put(
                    "messages",
                    JSONArray().apply {
                        request.systemInstruction?.takeIf { it.isNotBlank() }?.let {
                            put(JSONObject().put("role", "system").put("content", it))
                        }
                        put(JSONObject().put("role", "user").put("content", userContent(request)))
                    },
                )
            putOpenAiSampling(
                payload,
                baseUrl,
                model,
                maxTokens = request.maxTokens,
                temperature = pipelineTemperature(request.pipelineAction) ?: request.temperature,
            )
            request.tool?.let { tool ->
                if (providerId == OLLAMA_PROVIDER_ID) {
                    payload.put(
                        "response_format",
                        JSONObject()
                            .put("type", "json_schema")
                            .put(
                                "json_schema",
                                JSONObject()
                                    .put("name", tool.name)
                                    .put("schema", JSONObject(tool.parametersJson))
                                    .put("strict", true),
                            ),
                    )
                } else {
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
            }
            if (request.pipelineAction != null && providerId in REASONING_OFF_PROVIDER_IDS) {
                payload.put("reasoning_effort", "none")
            }
            if (request.stopSequences.isNotEmpty()) {
                payload.put("stop", JSONArray(request.stopSequences))
            }
            return payload
        }

        /**
         * The length and temperature fields, as the server's `openai_sampling()`
         * (`openai_request.py`) sends them. OpenAI's own API refuses `max_tokens`
         * for the gpt-5 and o-series models and asks for `max_completion_tokens`,
         * which every chat model there accepts; the reasoning families refuse a
         * temperature other than the default; and gpt-5.1 and later refuse
         * function tools in /v1/chat/completions while they reason, so they are
         * asked not to (gpt-5 itself and the o-series do not take "none"). Other
         * OpenAI-compatible servers (NVIDIA, Ollama Cloud and the like) keep the
         * fields they have always been sent.
         */
        internal fun putOpenAiSampling(
            payload: JSONObject,
            baseUrl: String,
            model: String,
            maxTokens: Int,
            temperature: Double,
        ) {
            val host = runCatching { URL(baseUrl).host }.getOrNull()?.lowercase()
            if (host != OPENAI_HOST) {
                payload.put("temperature", temperature).put("max_tokens", maxTokens)
                return
            }
            payload.put("max_completion_tokens", maxTokens)
            if (!OPENAI_FIXED_TEMPERATURE.containsMatchIn(model)) payload.put("temperature", temperature)
            if (OPENAI_REASONING_OFF.containsMatchIn(model)) payload.put("reasoning_effort", "none")
        }

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

        /**
         * The server's OpenAI-compatible pipeline sampling
         * (`_STAGE1_SAMPLED_ACTIONS`): 0.3 for Stage 1 and for the composition
         * reading, which is sent with Stage 1's model, limits and sampling;
         * 0.0 for every other action.
         */
        internal fun pipelineTemperature(action: String?): Double? = when (action) {
            null -> null
            "generate_normalized_ddl", "read_composition" -> 0.3
            else -> 0.0
        }

        private const val OLLAMA_PROVIDER_ID = "ollama"
        private const val OPENAI_HOST = "api.openai.com"
        private val OPENAI_FIXED_TEMPERATURE = Regex("^(gpt-5|o\\d)")
        private val OPENAI_REASONING_OFF = Regex("^gpt-5\\.\\d")
        private val REASONING_OFF_PROVIDER_IDS = setOf("ollama", "ollama-cloud")
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
