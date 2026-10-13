package app.inku.mobile.llm

import android.util.Log
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
        val payload = requestBody(providerId, request, baseUrl)
        val response = postJson(endpoint("/chat/completions"), payload, request.timeoutMs)
        val outputTruncated = response.optJSONArray("choices")?.optJSONObject(0)?.optString("finish_reason") == "length"
        if (request.pipelineAction != null && outputTruncated) {
            Log.w("InkuProvider", outputLimitLine(providerId, request, payload, response))
            throw ProviderOutputLimitException()
        }
        val content = answerText(response, request.tool?.name)
        val usage = response.optJSONObject("usage")
        ModelResponse(
            text = content,
            modelId = request.modelId,
            promptTokens = usage?.optInt("prompt_tokens")?.takeIf { it > 0 },
            completionTokens = usage?.optInt("completion_tokens")?.takeIf { it > 0 },
            outputTruncated = outputTruncated,
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
        /** Bounded output-limit diagnostics, with no answer or reasoning text. */
        internal fun outputLimitLine(providerId: String, request: ModelRequest, payload: JSONObject, response: JSONObject): String {
            val message = response.optJSONArray("choices")?.optJSONObject(0)?.optJSONObject("message")
            val usage = response.optJSONObject("usage")
            val fields = JSONObject()
                .put("action", request.pipelineAction).put("provider", providerId)
                .put("model", modelForRequest(providerId, request.modelId))
                .put("max_tokens", payload.opt("max_tokens") ?: payload.opt("max_completion_tokens") ?: JSONObject.NULL)
                .put("finish_reason", "length")
                .put("output_tokens", usage?.opt("completion_tokens") ?: JSONObject.NULL)
                .put("reasoning_tokens", usage?.optJSONObject("completion_tokens_details")?.opt("reasoning_tokens") ?: JSONObject.NULL)
                .put("has_reasoning", !(message?.opt("reasoning") as? String).isNullOrEmpty() ||
                    !(message?.opt("reasoning_content") as? String).isNullOrEmpty())
                .put("has_text", !(message?.opt("content") as? String).isNullOrEmpty())
                .put("has_tool_call", (message?.optJSONArray("tool_calls")?.length() ?: 0) > 0)
            return "provider_output_limit $fields"
        }

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
         * message text, which [generate] already reads. Every Ollama request
         * uses no reasoning, or gpt-oss's lowest level with room for it. OpenAI's own API
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
                providerId,
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
         * OpenAI-compatible servers keep their fields, except Ollama's gpt-oss
         * gets its lowest thinking level and 8,192 extra tokens for reasoning.
         * NIM's Gemma 4 gets its chat-template thinking switch turned off.
         */
        internal fun putOpenAiSampling(
            payload: JSONObject,
            baseUrl: String,
            model: String,
            providerId: String,
            maxTokens: Int,
            temperature: Double,
        ) {
            val host = runCatching { URL(baseUrl).host }.getOrNull()?.lowercase()
            if (host != OPENAI_HOST) {
                payload.put("temperature", temperature).put("max_tokens", maxTokens)
                if (providerId == "nvidia" && GEMMA4.containsMatchIn(model.substringAfterLast('/'))) {
                    payload.put("chat_template_kwargs", JSONObject().put("enable_thinking", false))
                }
                if (providerId in OLLAMA_PROVIDER_IDS) {
                    if (OLLAMA_LEVELS_ONLY.containsMatchIn(model)) {
                        payload.put("reasoning_effort", "low").put("max_tokens", maxTokens + OLLAMA_THINKING_ROOM_TOKENS)
                    } else {
                        payload.put("reasoning_effort", "none")
                    }
                }
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
        private val GEMMA4 = Regex("^gemma[-_]?4(?:[-_]|$)", RegexOption.IGNORE_CASE)
        private val OLLAMA_PROVIDER_IDS = setOf("ollama", "ollama-cloud")
        private val OLLAMA_LEVELS_ONLY = Regex("^gpt-oss(?:[:-]|$)")
        private const val OLLAMA_THINKING_ROOM_TOKENS = 8192
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
