package app.inku.mobile.llm

import java.net.HttpURLConnection
import java.net.URL
import java.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONException
import org.json.JSONObject
import org.json.JSONArray

/** An OpenAI-compatible connection. The shared core writes and reads its wire format. */
class OpenAiCompatibleProvider(
    override val providerId: String,
    private val baseUrl: String,
    private val apiKey: String?,
    private val openConnection: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
) : ModelProvider {
    override suspend fun generate(request: ModelRequest): ModelResponse =
        ProviderWireTransport.generate("openai_compatible", providerId, baseUrl, apiKey, openConnection, request)

    internal companion object {
        /** Used by routing's qualified model identifiers; provider policy stays in core. */
        internal fun modelForRequest(providerId: String, modelId: String): String =
            modelId.removePrefix("$providerId:").ifBlank { modelId }

        /** Inspection seam for focused tests; production sends the returned body string unchanged. */
        internal fun requestBody(providerId: String, request: ModelRequest, baseUrl: String): JSONObject =
            JSONObject(ProviderWireTransport.build("openai_compatible", providerId, baseUrl, request).getString("body"))

        /** Legacy test seam; extraction is delegated to the same core response reader. */
        internal fun answerText(response: JSONObject, toolName: String?): String =
            try { ProviderWireTransport.testAnswer("openai_chat", response) }
            catch (error: JSONException) { throw MalformedProviderResponseException(error.message.orEmpty()) }

        /** Legacy test seam; extraction is delegated to the same core response reader. */
        internal fun responsesAnswerText(response: JSONObject, toolName: String?): String =
            try { ProviderWireTransport.testAnswer("openai_responses", response) }
            catch (error: JSONException) { throw MalformedProviderResponseException(error.message.orEmpty()) }

        /** Legacy test seam for a message already known to contain a tool call. */
        internal fun extractToolArguments(message: JSONObject?, expectedToolName: String?): String? {
            if (message == null || expectedToolName == null || !message.has("tool_calls")) return null
            val response = JSONObject().put("choices", JSONArray().put(JSONObject().put("message", message)))
            return ProviderWireTransport.testAnswer("openai_chat", response)
        }

        /** Diagnostic fields come from the core's cut record. */
        internal fun outputLimitLine(providerId: String, request: ModelRequest, payload: JSONObject,
                                     response: JSONObject): String =
            ProviderWireTransport.outputLimitLine("openai_compatible", providerId, request, payload, response)
    }
}

/** HTTP is local to Android; the request and answer interpretation belong to the core. */
internal object ProviderWireTransport {
    fun build(kind: String, providerId: String, baseUrl: String, request: ModelRequest): JSONObject {
        ProviderUrlValidator.validateRemoteBaseUrl(baseUrl)
        val textRequest = request.pipelineAction == null || request.pipelineAction == REFINEMENT_VISION_ACTION
        val model = OpenAiCompatibleProvider.modelForRequest(providerId, request.modelId)
            .let { if (kind == "gemini") it.removePrefix("models/") else it }
        val connection = JSONObject()
            .put("id", providerId)
            .put("kind", kind)
            .put("api_profile", "")
            .put("base_url", baseUrl)
        val input = JSONObject()
            .put("action", if (textRequest) "text_request" else "pipeline_request")
            .put("connection", connection)
            .put("model", model)
            .put("max_tokens", request.maxTokens)
        if (textRequest) {
            val images = JSONArray()
            request.imagePayload()?.let { image ->
                images.put("data:${image.mimeType};base64,${Base64.getEncoder().encodeToString(image.bytes)}")
            }
            input.put("system", request.systemInstruction.orEmpty())
                .put("text", request.prompt)
                .put("images", images)
                .put("temperature", request.temperature)
        } else {
            val tool = requireNotNull(request.tool) { "A pipeline request needs its answer function." }
            // The schema's original member order matters when it has no propertyOrdering.
            // Keep that object raw on the trip to the core.
            val raw = "{\"action\":\"pipeline_request\",\"connection\":${app.inku.mobile.pipeline.CoreIdentityJson.encode(connection)}," +
                "\"model\":${JSONObject.quote(model)},\"max_tokens\":${request.maxTokens}," +
                "\"prompt\":{\"system\":${JSONObject.quote(request.systemInstruction.orEmpty())}," +
                "\"message\":${JSONObject.quote(request.prompt)}," +
                "\"action_name\":${JSONObject.quote(request.pipelineAction)}," +
                "\"response_schema\":${tool.parametersJson}}}"
            return requestAnswer(SharedProviderWire.call(raw))
        }
        return requestAnswer(SharedProviderWire.call(input))
    }

    private fun requestAnswer(built: JSONObject): JSONObject {
        if (built.optString("outcome") == "refused") throw IllegalArgumentException(built.getString("detail"))
        check(built.optString("outcome") == "ok") { "provider wire request outcome missing" }
        return built
    }

    suspend fun generate(kind: String, providerId: String, baseUrl: String, apiKey: String?,
                         openConnection: (URL) -> HttpURLConnection, request: ModelRequest): ModelResponse =
        withContext(Dispatchers.IO) {
            val started = System.currentTimeMillis()
            val built = build(kind, providerId, baseUrl, request)
            val url = URL(built.getString("url"))
            val connection = openConnection(url)
            val http = try {
                configureRemoteConnection(connection, "POST", apiKey = null, timeoutMs = request.timeoutMs)
                val headers = built.getJSONObject("headers")
                for (name in headers.keys()) connection.setRequestProperty(name, headers.getString(name))
                val auth = built.getJSONObject("auth")
                val key = apiKey?.takeIf(String::isNotBlank) ?: auth.getString("missing")
                connection.setRequestProperty(auth.getString("header"), auth.getString("prefix") + key)
                connection.doOutput = true
                connection.outputStream.writer(Charsets.UTF_8).use { it.write(built.getString("body")) }
                readProviderHttpBody(connection)
            } finally {
                connection.disconnect()
            }
            val response = SharedProviderWire.call(JSONObject()
                .put("action", if (request.pipelineAction == null || request.pipelineAction == REFINEMENT_VISION_ACTION)
                    "text_response" else "pipeline_response")
                .put("format", built.getString("format"))
                .put("status", http.status)
                .put("body", http.body))
            providerWireModelResponse(response, request, http, System.currentTimeMillis() - started, url.host)
        }

    internal fun testAnswer(format: String, response: JSONObject): String {
        val answer = SharedProviderWire.call(JSONObject().put("action", "pipeline_response")
            .put("format", format).put("status", 200).put("body", response.toString()))
        if (answer.optString("outcome") != "answer") throw JSONException("Provider returned an unexpected answer.")
        return answer.getString("text")
    }

    internal fun outputLimitLine(kind: String, providerId: String, request: ModelRequest,
                                 payload: JSONObject, response: JSONObject): String {
        val answer = SharedProviderWire.call(JSONObject().put("action", "pipeline_response")
            .put("format", if (payload.has("max_output_tokens")) "openai_responses" else "openai_chat")
            .put("status", 200).put("body", response.toString()))
        val fields = JSONObject().put("action", request.pipelineAction).put("provider", providerId)
            .put("model", payload.optString("model"))
            .put("max_tokens", payload.opt("max_output_tokens") ?: payload.opt("max_tokens") ?:
                payload.opt("max_completion_tokens") ?: JSONObject.NULL)
        answer.optJSONObject("cut")?.let { cut ->
            for (key in cut.keys()) fields.put(key, cut.get(key))
        }
        return "provider_output_limit $fields"
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
