package app.inku.mobile.llm

class LocalLiteRtLmProvider : ModelProvider {
    override val providerId: String = "local-litert-lm"

    override suspend fun generate(request: ModelRequest): ModelResponse {
        error("LiteRT-LM integration is not wired yet")
    }
}
