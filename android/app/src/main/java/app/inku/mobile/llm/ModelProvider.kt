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
