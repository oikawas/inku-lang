package app.inku.mobile.llm

import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/** An explicit, one-token check of one Ollama Cloud model with the author's key. */
internal object ModelAccessProbe {
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
            when (connection.responseCode) { 200 -> true; 402, 403 -> false; else -> null }
        } finally {
            connection.disconnect()
        }
    }
}
