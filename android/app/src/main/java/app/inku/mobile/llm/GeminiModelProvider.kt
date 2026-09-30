package app.inku.mobile.llm

import app.inku.mobile.security.DisplaySanitizer
import java.net.HttpURLConnection
import java.net.URL
import java.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

class GeminiModelProvider(
    override val providerId: String,
    private val baseUrl: String,
    private val apiKey: String?,
    private val openConnection: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
) : ModelProvider {
    override suspend fun generate(request: ModelRequest): ModelResponse = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        ProviderUrlValidator.validateRemoteBaseUrl(baseUrl)
        val model = request.modelId.removePrefix("$providerId:").removePrefix("models/")
        require(model.matches(Regex("[A-Za-z0-9._-]+"))) { "Invalid Gemini model ID." }
        val url = URL("${baseUrl.trimEnd('/')}/v1beta/models/$model:generateContent")
        val connection = openConnection(url)
        val response = try {
            configureRemoteConnection(connection, "POST", apiKey = null, timeoutMs = request.timeoutMs)
            apiKey?.takeIf { it.isNotBlank() }?.let { connection.setRequestProperty("x-goog-api-key", it) }
            connection.setRequestProperty("Content-Type", "application/json")
            connection.doOutput = true
            connection.outputStream.writer(Charsets.UTF_8).use { it.write(payload(request).toString()) }
            val status = connection.responseCode
            val success = status in 200..299
            val limit = if (success) 2_000_000 else 16_384
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
                    providerRefusal(body),
                )
            }
            require(body.length <= limit) { "Remote response was too large." }
            JSONObject(body)
        } finally {
            connection.disconnect()
        }
        val parts = response.optJSONArray("candidates")?.optJSONObject(0)
            ?.optJSONObject("content")?.optJSONArray("parts")
            ?: error("Gemini response did not contain content.")
        val usage = response.optJSONObject("usageMetadata")
        ModelResponse(
            text = responseText(parts, request.tool?.name),
            modelId = request.modelId,
            promptTokens = usage?.optInt("promptTokenCount")?.takeIf { it > 0 },
            completionTokens = usage?.optInt("candidatesTokenCount")?.takeIf { it > 0 },
            outputTruncated = response.optJSONArray("candidates")?.optJSONObject(0)?.optString("finishReason") == "MAX_TOKENS",
            elapsedMs = System.currentTimeMillis() - started,
        )
    }

    private fun payload(request: ModelRequest): JSONObject {
        val pipelineAction = request.pipelineAction
        val generation = JSONObject().put("maxOutputTokens", request.maxTokens)
        if (pipelineAction == null) {
            generation.put("temperature", request.temperature)
            // Server Vision requests use minimal thinking for the Gemini kind,
            // including a custom connection ID or an unfamiliar model name.
            val thinkingLevel = if (request.imageJpeg != null) "minimal" else request.thinkingLevel
            thinkingLevel?.let { generation.put("thinkingConfig", JSONObject().put("thinkingLevel", it)) }
        } else {
            // Shared-pipeline requests use the server's Gemini request shape:
            // model-default sampling and minimal thinking.
            generation.put("thinkingConfig", JSONObject().put("thinkingLevel", "minimal"))
        }
        if (request.stopSequences.isNotEmpty()) generation.put("stopSequences", JSONArray(request.stopSequences))
        val user = textContent(request.prompt).put("role", "user")
        request.imageJpeg?.let { image ->
            // The server sends Gemini the instruction followed by inline images.
            val parts = JSONArray()
                .put(JSONObject().put("text", request.prompt))
                .put(
                    JSONObject().put(
                        "inlineData",
                        JSONObject()
                            .put("mimeType", "image/jpeg")
                            .put("data", Base64.getEncoder().encodeToString(image)),
                    ),
                )
            user.put("parts", parts)
        }
        val payload = JSONObject()
            .put("contents", JSONArray().put(user))
            .put("generationConfig", generation)
        request.systemInstruction?.takeIf { it.isNotBlank() }?.let {
            payload.put("systemInstruction", textContent(it))
        }
        request.tool?.let { tool ->
            val schema = JSONObject(tool.parametersJson)
            val declaration = JSONObject()
                .put("name", tool.name)
                .put("description", tool.description)
                .put(
                    "parametersJsonSchema",
                    if (pipelineAction == null) {
                        schema
                    } else {
                        GeminiJsonSchema.project(
                            schema,
                            compactHoleEdits = pipelineAction == "complete_visible_ddl_holes",
                        )
                    },
                )
            payload.put("tools", JSONArray().put(JSONObject().put("functionDeclarations", JSONArray().put(declaration))))
            payload.put(
                "toolConfig",
                JSONObject().put(
                    "functionCallingConfig",
                    JSONObject().put("mode", "ANY").put("allowedFunctionNames", JSONArray().put(tool.name)),
                ),
            )
        }
        return payload
    }

    private fun textContent(text: String): JSONObject =
        JSONObject().put("parts", JSONArray().put(JSONObject().put("text", text)))

    internal companion object {
        /** A pipeline answer is exactly one requested function call, as on the server. */
        internal fun responseText(parts: JSONArray, toolName: String?): String {
            val objects = (0 until parts.length()).mapNotNull { parts.optJSONObject(it) }
            if (toolName != null) {
                val calls = objects.filter { it.has("functionCall") }.map { it.optJSONObject("functionCall") }
                if (calls.size != 1 || calls[0]?.optString("name") != toolName) {
                    throw JSONException("Gemini returned an unexpected function call.")
                }
                return calls[0]?.optJSONObject("args")?.toString()
                    ?: throw JSONException("Gemini function call did not contain an arguments object.")
            }
            val text = objects.filter { it.has("text") && !it.optBoolean("thought") }
                .joinToString("\n") { it.getString("text") }
            check(text.isNotBlank()) { "Gemini response did not contain text." }
            return text
        }
    }
}
