package app.inku.mobile.llm

import app.inku.mobile.data.catalogRequest
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/** An explicit, one-token check of one Ollama Cloud model with the author's key. */
internal object ModelAccessProbe {
    suspend fun checkDetailed(baseUrl: String, apiKey: String, model: String,
        today: String = java.time.LocalDate.now(java.time.ZoneOffset.UTC).toString(),
        openConnection: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
    ): JSONObject = withContext(Dispatchers.IO) {
        ProviderUrlValidator.validateRemoteBaseUrl(baseUrl)
        val origin = baseUrl.trimEnd('/').removeSuffix("/v1")
        val show = runCatching {
            val connection = openConnection(URL("$origin/api/show"))
            try {
                configureRemoteConnection(connection, "POST", null, 20_000)
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.setRequestProperty("Accept", "application/json")
                connection.outputStream.use { it.write(JSONObject().put("model", model).toString().toByteArray(Charsets.UTF_8)) }
                val status = connection.responseCode
                val body = if (status == 410) connection.errorStream?.bufferedReader()?.use { reader ->
                    val buffer = CharArray(2048)
                    val count = reader.read(buffer)
                    if (count > 0) String(buffer, 0, count) else ""
                }.orEmpty() else ""
                catalogRequest("access_probe", JSONObject().put("stage", "show").put("status", status).put("text", body)
                    .put("today", today)).getJSONObject("answer")
            } finally { connection.disconnect() }
        }.getOrDefault(JSONObject())
        if (show.length() != 0 || apiKey.isBlank()) return@withContext show
        val available = check(baseUrl, apiKey, model, openConnection)
        if (available == null) JSONObject() else JSONObject().put("subscription", !available)
    }

    suspend fun check(baseUrl: String, apiKey: String, model: String,
        openConnection: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
    ): Boolean? = withContext(Dispatchers.IO) {
        ProviderUrlValidator.validateRemoteBaseUrl(baseUrl)
        val connection = openConnection(URL(baseUrl.trimEnd('/') + "/chat/completions"))
        try {
            configureRemoteConnection(connection, "POST", apiKey, 20_000)
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            val body = JSONObject().put("model", model).put("max_tokens", 1).put("messages", JSONArray().put(
                JSONObject().put("role", "user").put("content", "."),
            )).toString()
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val answer = catalogRequest("access_probe", JSONObject().put("stage", "call")
                .put("status", connection.responseCode)).getJSONObject("answer")
            if (answer.has("subscription")) !answer.getBoolean("subscription") else null
        } finally {
            connection.disconnect()
        }
    }
}
