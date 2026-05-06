package app.inku.mobile.llm

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
        val model = request.modelId.removePrefix("$providerId:").ifBlank { request.modelId }
        val payload = JSONObject()
            .put("model", model)
            .put(
                "messages",
                JSONArray().apply {
                    request.systemInstruction?.takeIf { it.isNotBlank() }?.let {
                        put(JSONObject().put("role", "system").put("content", it))
                    }
                    put(JSONObject().put("role", "user").put("content", request.prompt))
                },
            )
            .put("temperature", request.temperature)
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
        val response = postJson("${baseUrl.trimEnd('/')}/chat/completions", payload)
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

    suspend fun fetchModels(): List<String> = withContext(Dispatchers.IO) {
        val payload = getJson("${baseUrl.trimEnd('/')}/models")
        val rawModels = payload.optJSONArray("data") ?: payload.optJSONArray("models")
            ?: error("Model list response did not contain models.")
        (0 until rawModels.length()).mapNotNull { index ->
            val item = rawModels.optJSONObject(index) ?: return@mapNotNull null
            val id = (item.optString("id").ifBlank { item.optString("name") })
                .removePrefix("models/")
                .trim()
            id.takeIf { it.isNotBlank() }
        }.distinct()
    }

    private fun postJson(url: String, payload: JSONObject): JSONObject {
        val connection = open(url, "POST")
        connection.setRequestProperty("Content-Type", "application/json")
        connection.doOutput = true
        OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use { writer ->
            writer.write(payload.toString())
        }
        return readJson(connection)
    }

    private fun getJson(url: String): JSONObject {
        return readJson(open(url, "GET"))
    }

    private fun open(url: String, method: String): HttpURLConnection {
        val connection = (URL(url).openConnection() as HttpURLConnection)
        connection.requestMethod = method
        connection.connectTimeout = REQUEST_TIMEOUT_MS
        connection.readTimeout = REQUEST_TIMEOUT_MS
        connection.setRequestProperty("Accept", "application/json")
        apiKey?.takeIf { it.isNotBlank() }?.let { connection.setRequestProperty("Authorization", "Bearer $it") }
        return connection
    }

    private fun readJson(connection: HttpURLConnection): JSONObject {
        val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
        val body = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
        if (connection.responseCode !in 200..299) {
            error("HTTP ${connection.responseCode}: ${body.take(240)}")
        }
        return JSONObject(body)
    }

    private companion object {
        private const val REQUEST_TIMEOUT_MS = 600_000
    }
}
