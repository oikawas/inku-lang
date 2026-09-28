package app.inku.mobile.llm

import app.inku.mobile.security.DisplaySanitizer
import org.json.JSONObject

interface ModelProvider {
    val providerId: String

    suspend fun generate(request: ModelRequest): ModelResponse
}

data class ModelRequest(
    val modelId: String,
    val prompt: String,
    val temperature: Double,
    val maxTokens: Int,
    val stopSequences: List<String> = emptyList(),
    val systemInstruction: String? = null,
    val tool: ModelTool? = null,
    /** Host-enforced bound for one transport attempt. */
    val timeoutMs: Long? = null,
    /**
     * Shared-pipeline action name (`generate_normalized_ddl`, ...). When set, a
     * remote transport applies the server's per-provider pipeline request shape
     * instead of the generic [temperature].
     */
    val pipelineAction: String? = null,
    /** One normalized JPEG sent with [prompt]; only camera analysis sets it. */
    val imageJpeg: ByteArray? = null,
    /** Gemini `thinkingLevel` for a non-pipeline request; null keeps the model default. */
    val thinkingLevel: String? = null,
)

class ModelProviderHttpException(
    val statusCode: Int,
    message: String,
    /** What the provider said, from [providerRefusal]; empty when it said nothing readable. */
    val refusal: JSONObject = JSONObject(),
) : IllegalStateException(message)

/**
 * What a refusal says, without anything that could carry a key -- the server's
 * `_provider_error` (`pipeline_provider.py`). OpenAI, Anthropic and Gemini all
 * answer `{"error": {...}}`; its code, type, param and status name the reason.
 * The message is kept short and redacted, since a 401 echoes part of the key.
 */
internal fun providerRefusal(body: String): JSONObject {
    val found = JSONObject()
    val error = runCatching { JSONObject(body).optJSONObject("error") }.getOrNull() ?: return found
    for (key in listOf("code", "type", "param", "status")) {
        when (val value = error.opt(key)) {
            is String -> if (value.isNotEmpty()) found.put(key, value)
            is Int, is Long -> found.put(key, value)
        }
    }
    error.optString("message").takeIf { it.isNotEmpty() }?.let {
        found.put("message", DisplaySanitizer.redact(it).take(240))
    }
    return found
}

data class ModelResponse(
    val text: String,
    val modelId: String,
    val promptTokens: Int? = null,
    val completionTokens: Int? = null,
    val elapsedMs: Long? = null,
)

data class ModelTool(
    val name: String,
    val description: String,
    val parametersJson: String,
)
