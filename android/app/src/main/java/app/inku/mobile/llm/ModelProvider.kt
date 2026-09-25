package app.inku.mobile.llm

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
) : IllegalStateException(message)

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
