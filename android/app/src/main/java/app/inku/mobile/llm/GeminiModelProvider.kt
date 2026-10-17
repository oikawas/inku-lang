package app.inku.mobile.llm

import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONArray
import org.json.JSONObject

/** Gemini connection; the core owns the model path, schema, thinking and answer. */
class GeminiModelProvider(
    override val providerId: String,
    private val baseUrl: String,
    private val apiKey: String?,
    private val openConnection: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
) : ModelProvider {
    override suspend fun generate(request: ModelRequest): ModelResponse =
        ProviderWireTransport.generate("gemini", providerId, baseUrl, apiKey, openConnection, request)

    internal companion object {
        /** Test seam: one function call is parsed by the shared core. */
        internal fun responseText(parts: JSONArray, toolName: String?): String =
            ProviderWireTransport.testAnswer("gemini", JSONObject().put("candidates", JSONArray()
                .put(JSONObject().put("content", JSONObject().put("parts", parts)))))
    }
}
