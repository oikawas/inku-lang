package app.inku.mobile.llm

import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/** Claude Messages connection; body and answer interpretation come from the shared core. */
class AnthropicModelProvider(
    override val providerId: String,
    private val baseUrl: String,
    private val apiKey: String?,
    private val openConnection: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection },
) : ModelProvider {
    override suspend fun generate(request: ModelRequest): ModelResponse =
        ProviderWireTransport.generate("anthropic", providerId, baseUrl, apiKey, openConnection, request)

    internal fun payload(request: ModelRequest): JSONObject =
        JSONObject(ProviderWireTransport.build("anthropic", providerId, baseUrl, request).getString("body"))

    internal companion object {
        /** Inspection seam for text-image ordering; the core writes the content. */
        internal fun userContent(request: ModelRequest): Any =
            JSONObject(ProviderWireTransport.build("anthropic", "anthropic", "https://api.anthropic.com", request)
                .getString("body")).getJSONArray("messages").getJSONObject(0).get("content")

        /** Test seam: the core validates tool calls and text answers. */
        internal fun responseText(blocks: JSONArray, toolName: String?): String =
            ProviderWireTransport.testAnswer("anthropic", JSONObject().put("content", blocks))

        /** Bounded diagnostic fields are copied from the core's cut record. */
        internal fun outputLimitLine(providerId: String, request: ModelRequest, body: JSONObject,
                                     response: JSONObject): String {
            val answer = SharedProviderWire.call(JSONObject().put("action", "pipeline_response")
                .put("format", "anthropic").put("status", 200).put("body", response.toString()))
            val fields = JSONObject().put("action", request.pipelineAction).put("provider", providerId)
                .put("model", body.optString("model"))
                .put("max_tokens", body.opt("max_tokens") ?: JSONObject.NULL)
            answer.optJSONObject("cut")?.let { cut -> for (key in cut.keys()) fields.put(key, cut.get(key)) }
            return "provider_output_limit $fields"
        }
    }
}
