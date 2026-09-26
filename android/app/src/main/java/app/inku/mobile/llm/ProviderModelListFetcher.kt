package app.inku.mobile.llm

import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

internal data class ProviderModelListRequest(
    val url: String,
    val headers: Map<String, String>,
    /** Sent with every page: the largest page the API allows. */
    val firstQuery: Map<String, String> = emptyMap(),
)

/**
 * The three catalog endpoints and credential forms used by the server settings
 * API (`routers/settings.py`). Every key rides in a header: in the query
 * string it would be written into each proxy and access log the URL passes.
 */
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
            mapOf("limit" to MODEL_LIST_PAGE_SIZE),
        )
        "gemini" -> ProviderModelListRequest(
            "$root/v1beta/models",
            key?.let { mapOf("x-goog-api-key" to it) } ?: emptyMap(),
            mapOf("pageSize" to MODEL_LIST_PAGE_SIZE),
        )
        "openai-compatible", "openai_compatible" -> ProviderModelListRequest(
            "$root/models",
            key?.let { mapOf("Authorization" to "Bearer $it") } ?: emptyMap(),
        )
        else -> error("Model list is unavailable for this connection type.")
    }
}

/** The query for the page after [page], or null when [page] was the last one. */
internal fun nextModelListQuery(kind: String, page: JSONObject): Map<String, String>? = when (kind) {
    "anthropic" -> page.optString("last_id").takeIf { page.optBoolean("has_more") && it.isNotEmpty() }
        ?.let { mapOf("after_id" to it) }
    "gemini" -> page.optString("nextPageToken").takeIf { it.isNotEmpty() }?.let { mapOf("pageToken" to it) }
    else -> null
}

internal fun parseProviderModelList(body: String): List<String> = providerModelIds(modelListItems(parseModelListPage(body)))

private fun parseModelListPage(body: String): JSONObject = try {
    JSONObject(body)
} catch (_: JSONException) {
    error("Model list response was not JSON.")
}

private fun modelListItems(page: JSONObject): JSONArray =
    page.optJSONArray("data") ?: page.optJSONArray("models")
        ?: error("Model list response did not contain models.")

private fun providerModelIds(raw: JSONArray): List<String> {
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
    /**
     * Reads every page, as the server does. The page cap only stops a provider
     * that never says it is done; a list cut short there is an error rather
     * than a partial answer.
     */
    suspend fun fetchModels(kind: String, baseUrl: String, apiKey: String?): List<String> = withContext(Dispatchers.IO) {
        val request = providerModelListRequest(kind, baseUrl, apiKey)
        val collected = JSONArray()
        var query = request.firstQuery
        repeat(MODEL_LIST_PAGE_LIMIT) {
            val page = parseModelListPage(fetchPage(pageUrl(request.url, query), request.headers))
            val items = modelListItems(page)
            for (index in 0 until items.length()) collected.put(items.get(index))
            val following = nextModelListQuery(kind, page) ?: return@withContext providerModelIds(collected)
            query = request.firstQuery + following
        }
        error("Model list response did not end.")
    }

    private fun pageUrl(url: String, query: Map<String, String>): String =
        if (query.isEmpty()) {
            url
        } else {
            url + "?" + query.entries.joinToString("&") { (name, value) ->
                "${URLEncoder.encode(name, "UTF-8")}=${URLEncoder.encode(value, "UTF-8")}"
            }
        }

    private fun fetchPage(url: String, headers: Map<String, String>): String {
        val host = URL(url).host
        var connection: HttpURLConnection? = null
        try {
            connection = (URL(url).openConnection() as HttpURLConnection).also {
                configureRemoteConnection(it, method = "GET", apiKey = null, timeoutMs = 20_000)
                headers.forEach { (name, value) -> it.setRequestProperty(name, value) }
            }
            val status = connection.responseCode
            if (status !in 200..299) {
                throw ModelProviderHttpException(status, "HTTP $status from $host.")
            }
            val (body, truncated) = readLimited(connection.inputStream, 2_000_000)
            require(!truncated) { "Model list response was too large." }
            return body
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

// The server's page size and page cap (`_MODEL_LIST_PAGE_SIZE`, `_MODEL_LIST_PAGE_LIMIT`).
private const val MODEL_LIST_PAGE_SIZE = "1000"
private const val MODEL_LIST_PAGE_LIMIT = 20
