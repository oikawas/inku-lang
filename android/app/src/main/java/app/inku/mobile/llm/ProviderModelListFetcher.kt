package app.inku.mobile.llm

import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONException
import org.json.JSONObject

internal data class ProviderModelListRequest(
    val url: String,
    val headers: Map<String, String>,
)

/** The three catalog endpoints and credential forms used by the server settings API. */
internal fun providerModelListRequest(kind: String, baseUrl: String, apiKey: String?): ProviderModelListRequest {
    ProviderUrlValidator.validateRemoteBaseUrl(baseUrl)
    val root = baseUrl.trimEnd('/')
    val key = apiKey?.takeIf { it.isNotBlank() }
    return when (kind) {
        "anthropic" -> ProviderModelListRequest(
            "$root/v1/models",
            buildMap {
                key?.let { put("x-api-key", it) }
                put("anthropic-version", "2023-06-01")
            },
        )
        "gemini" -> ProviderModelListRequest(
            "$root/v1beta/models" + (key?.let { "?key=${URLEncoder.encode(it, "UTF-8")}" } ?: ""),
            emptyMap(),
        )
        "openai-compatible", "openai_compatible" -> ProviderModelListRequest(
            "$root/models",
            key?.let { mapOf("Authorization" to "Bearer $it") } ?: emptyMap(),
        )
        else -> error("Model list is unavailable for this connection type.")
    }
}

internal fun parseProviderModelList(body: String): List<String> {
    val payload = try {
        JSONObject(body)
    } catch (_: JSONException) {
        error("Model list response was not JSON.")
    }
    val raw = payload.optJSONArray("data") ?: payload.optJSONArray("models")
        ?: error("Model list response did not contain models.")
    val models = (0 until raw.length()).mapNotNull { index ->
        val item = raw.optJSONObject(index) ?: return@mapNotNull null
        item.optString("id").ifBlank { item.optString("name") }
            .removePrefix("models/")
            .trim()
            .takeIf { it.isNotBlank() }
    }.distinct()
    require(models.isNotEmpty()) { "Model list response was empty." }
    return models
}

internal object ProviderModelListFetcher {
    suspend fun fetchModels(kind: String, baseUrl: String, apiKey: String?): List<String> = withContext(Dispatchers.IO) {
        val request = providerModelListRequest(kind, baseUrl, apiKey)
        val host = URL(request.url).host
        var connection: HttpURLConnection? = null
        try {
            connection = (URL(request.url).openConnection() as HttpURLConnection).also {
                configureRemoteConnection(it, method = "GET", apiKey = null, timeoutMs = 20_000)
                request.headers.forEach { (name, value) -> it.setRequestProperty(name, value) }
            }
            val status = connection.responseCode
            if (status !in 200..299) {
                throw ModelProviderHttpException(status, "HTTP $status from $host.")
            }
            val (body, truncated) = readLimited(connection.inputStream, 2_000_000)
            require(!truncated) { "Model list response was too large." }
            parseProviderModelList(body)
        } catch (_: IOException) {
            error("Model list request failed for $host.")
        } finally {
            connection?.disconnect()
        }
    }

    private fun readLimited(stream: java.io.InputStream?, maxChars: Int): Pair<String, Boolean> {
        if (stream == null) return "" to false
        stream.bufferedReader(Charsets.UTF_8).use { reader ->
            val buffer = CharArray(8192)
            val body = StringBuilder()
            while (true) {
                val count = reader.read(buffer)
                if (count < 0) return body.toString() to false
                val remaining = maxChars - body.length
                if (remaining <= 0) return body.toString() to true
                if (count > remaining) {
                    body.append(buffer, 0, remaining)
                    return body.toString() to true
                }
                body.append(buffer, 0, count)
            }
        }
    }
}
