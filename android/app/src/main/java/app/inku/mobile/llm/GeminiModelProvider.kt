package app.inku.mobile.llm

import app.inku.mobile.security.DisplaySanitizer
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
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
        var arguments: String? = null
        val text = StringBuilder()
        for (index in 0 until parts.length()) {
            val part = parts.optJSONObject(index) ?: continue
            if (part.optBoolean("thought")) continue
            val call = part.optJSONObject("functionCall")
            if (request.tool != null && call?.optString("name") == request.tool.name) {
                arguments = call.optJSONObject("args")?.toString()
            }
            if (part.has("text")) text.append(part.getString("text"))
        }
        val content = arguments ?: text.toString()
        check(content.isNotBlank()) { "Gemini response did not contain text or requested function arguments." }
        val usage = response.optJSONObject("usageMetadata")
        ModelResponse(
            text = content,
            modelId = request.modelId,
            promptTokens = usage?.optInt("promptTokenCount")?.takeIf { it > 0 },
            completionTokens = usage?.optInt("candidatesTokenCount")?.takeIf { it > 0 },
            elapsedMs = System.currentTimeMillis() - started,
        )
    }

    private fun payload(request: ModelRequest): JSONObject {
        val generation = JSONObject()
            .put("temperature", request.temperature)
            .put("maxOutputTokens", request.maxTokens)
        if (request.stopSequences.isNotEmpty()) generation.put("stopSequences", JSONArray(request.stopSequences))
        val payload = JSONObject()
            .put("contents", JSONArray().put(textContent(request.prompt).put("role", "user")))
            .put("generationConfig", generation)
        request.systemInstruction?.takeIf { it.isNotBlank() }?.let {
            payload.put("systemInstruction", textContent(it))
        }
        request.tool?.let { tool ->
            val declaration = JSONObject()
                .put("name", tool.name)
                .put("description", tool.description)
                .put("parametersJsonSchema", JSONObject(tool.parametersJson))
            payload.put("tools", JSONArray().put(JSONObject().put("functionDeclarations", JSONArray().put(declaration))))
            payload.put("toolConfig", JSONObject().put("functionCallingConfig", JSONObject().put("mode", "ANY")))
        }
        return payload
    }

    private fun textContent(text: String): JSONObject =
        JSONObject().put("parts", JSONArray().put(JSONObject().put("text", text)))
}
