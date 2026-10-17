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
        val responses = request.pipelineAction != null && isOpenAiApi(baseUrl)
        val payload = requestBody(providerId, request, baseUrl)
        val response = postJson(endpoint(if (responses) "/responses" else "/chat/completions"), payload, request.timeoutMs)
        val outputTruncated = if (responses) {
            response.optString("status") == "incomplete" &&
                response.optJSONObject("incomplete_details")?.optString("reason") == "max_output_tokens"
        } else response.optJSONArray("choices")?.optJSONObject(0)?.optString("finish_reason") == "length"
        if (request.pipelineAction != null && outputTruncated) {
            Log.w("InkuProvider", outputLimitLine(providerId, request, payload, response))
            throw ProviderOutputLimitException()
        }
        val content = if (responses) responsesAnswerText(response, request.tool?.name) else answerText(response, request.tool?.name)
        val usage = response.optJSONObject("usage")
        ModelResponse(
            text = content,
            modelId = request.modelId,
            promptTokens = usage?.optInt(if (responses) "input_tokens" else "prompt_tokens")?.takeIf { it > 0 },
            completionTokens = usage?.optInt(if (responses) "output_tokens" else "completion_tokens")?.takeIf { it > 0 },
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
                writer.write(OrderedSchemaJson.encode(payload))
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
            val usage = response.optJSONObject("usage")
            val fields = JSONObject()
                .put("action", request.pipelineAction).put("provider", providerId)
                .put("model", modelForRequest(providerId, request.modelId))
                .put("max_tokens", payload.opt("max_output_tokens") ?: payload.opt("max_tokens") ?:
                    payload.opt("max_completion_tokens") ?: JSONObject.NULL)
            if (payload.has("max_output_tokens")) {
                val output = responsesOutput(response)
                fields.put("incomplete_reason", "max_output_tokens")
                    .put("output_tokens", usage?.opt("output_tokens") ?: JSONObject.NULL)
                    .put("reasoning_tokens", usage?.optJSONObject("output_tokens_details")?.opt("reasoning_tokens") ?: JSONObject.NULL)
                    .put("has_text", output.any { it.optString("type") == "message" })
                    .put("has_function_call", output.any { it.optString("type") == "function_call" })
            } else {
                val message = response.optJSONArray("choices")?.optJSONObject(0)?.optJSONObject("message")
                fields.put("finish_reason", "length")
                    .put("output_tokens", usage?.opt("completion_tokens") ?: JSONObject.NULL)
                    .put("reasoning_tokens", usage?.optJSONObject("completion_tokens_details")?.opt("reasoning_tokens") ?: JSONObject.NULL)
                    .put("has_reasoning", !(message?.opt("reasoning") as? String).isNullOrEmpty() ||
                        !(message?.opt("reasoning_content") as? String).isNullOrEmpty())
                    .put("has_text", !(message?.opt("content") as? String).isNullOrEmpty())
                    .put("has_tool_call", (message?.optJSONArray("tool_calls")?.length() ?: 0) > 0)
            }
            return "provider_output_limit $fields"
        }

        private fun responsesOutput(response: JSONObject): List<JSONObject> = response.optJSONArray("output")?.let { output ->
            (0 until output.length()).mapNotNull { output.optJSONObject(it) }
        }.orEmpty()

        /** Only a completed response's one offered function, or its output text, is an answer. */
        internal fun responsesAnswerText(response: JSONObject, toolName: String?): String {
            if (response.optString("status") != "completed" || response.optJSONArray("output") == null) {
                throw MalformedProviderResponseException("Responses answer did not complete.")
            }
            val output = responsesOutput(response)
            val calls = output.filter { it.optString("type") == "function_call" }
            val text = if (calls.isNotEmpty()) {
                if (calls.size != 1 || calls.single().optString("name") != toolName || calls.single().opt("arguments") !is String) {
                    throw MalformedProviderResponseException("Responses returned an unexpected function call.")
                }
                calls.single().getString("arguments")
            } else {
                buildString {
                    output.filter { it.optString("type") == "message" }.forEach { item ->
                        val content = item.optJSONArray("content") ?: return@forEach
                        for (index in 0 until content.length()) {
                            val part = content.optJSONObject(index) ?: continue
                            if (part.optString("type") == "output_text") append(part.opt("text") as? String ?: "")
                        }
                    }
                }
            }
            return text.takeIf { it.isNotBlank() }
                ?: throw MalformedProviderResponseException("Responses answer did not contain text.")
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
         * The request body, in the server's per-connection shape. OpenAI's
         * pipeline uses Responses; auxiliary calls and other hosts use Chat Completions
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
            if (request.pipelineAction != null && isOpenAiApi(baseUrl)) {
                return responsesRequestBody(providerId, request, baseUrl, model)
            }
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

        private fun isOpenAiApi(baseUrl: String): Boolean = runCatching { URL(baseUrl).host.lowercase() }.getOrNull() == OPENAI_HOST

        private fun responsesRequestBody(providerId: String, request: ModelRequest, baseUrl: String, model: String): JSONObject {
            val tool = requireNotNull(request.tool) { "A pipeline Responses request needs its answer function." }
            val sampling = JSONObject()
            putOpenAiSampling(sampling, baseUrl, model, providerId, request.maxTokens,
                pipelineTemperature(request.pipelineAction) ?: request.temperature)
            val inputContent: Any = if (request.pipelineAction == REFINEMENT_VISION_ACTION) {
                val image = requireNotNull(request.imageJpeg) { "Refinement advice needs a JPEG." }
                require(image.isNotEmpty()) { "Refinement advice needs a JPEG." }
                JSONArray()
                    .put(JSONObject().put("type", "input_text").put("text", request.prompt))
                    .put(JSONObject().put("type", "input_image")
                        .put("image_url", "data:image/jpeg;base64," + java.util.Base64.getEncoder().encodeToString(image)))
            } else request.prompt
            val payload = JSONObject().put("model", model).put("store", false)
                .put("instructions", request.systemInstruction.orEmpty())
                .put("input", JSONArray().put(JSONObject().put("role", "user").put("content", inputContent)))
                .put("tools", JSONArray().put(JSONObject().put("type", "function").put("name", tool.name)
                    .put("description", tool.description).put("parameters", JSONObject(tool.parametersJson)).put("strict", false)))
                .put("tool_choice", "required").put("parallel_tool_calls", false)
                .put("max_output_tokens", sampling.getInt("max_completion_tokens"))
            if (sampling.has("reasoning_effort")) payload.put("reasoning", JSONObject().put("effort", sampling.getString("reasoning_effort")))
            if (sampling.has("temperature")) payload.put("temperature", sampling.getDouble("temperature"))
            return payload
        }

        /** Server's sampling: stop reasoning where supported, otherwise low with room for it. */
        internal fun putOpenAiSampling(
            payload: JSONObject,
            baseUrl: String,
            model: String,
            providerId: String,
            maxTokens: Int,
            temperature: Double,
        ) {
            if (!isOpenAiApi(baseUrl)) {
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
            if (!OPENAI_REASONING.containsMatchIn(model)) {
                payload.put("temperature", temperature)
            } else if (OPENAI_REASONING_OFF.containsMatchIn(model)) {
                payload.put("reasoning_effort", "none")
            } else {
                payload.put("reasoning_effort", "low").put("max_completion_tokens", maxTokens + OPENAI_REASONING_ROOM_TOKENS)
            }
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
         * 0.0 for other drawing actions; refinement Vision keeps its 0.35 request.
         */
        internal fun pipelineTemperature(action: String?): Double? = when (action) {
            null, REFINEMENT_VISION_ACTION -> null
            "generate_normalized_ddl", "read_composition" -> 0.3
            else -> 0.0
        }

        private const val OLLAMA_PROVIDER_ID = "ollama"
        private const val OPENAI_HOST = "api.openai.com"
        private val OPENAI_REASONING = Regex("^(gpt-5|gpt-6|o\\d)")
        private val OPENAI_REASONING_OFF = Regex("^(gpt-5\\.\\d|gpt-6-(?:sol|luna)(?:-|$))")
        private const val OPENAI_REASONING_ROOM_TOKENS = 25000
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
