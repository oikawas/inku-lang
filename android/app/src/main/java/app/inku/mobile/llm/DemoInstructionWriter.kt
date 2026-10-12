package app.inku.mobile.llm

import app.inku.mobile.ui.i18n.inkuError

/** The repository's demo call, kept independent of Room so its actual provider request is checkable. */
internal class DemoInstructionWriter(private val provider: ModelProvider) {
    suspend fun write(seedPhrase: String, modelId: String): String {
        val seed = seedPhrase.trim().ifBlank { "96文字以内の短い描画指示文を1つ作って。" }
        val response = provider.generate(ModelRequest(
            modelId = modelId, prompt = seed, temperature = 0.85, maxTokens = 256,
            systemInstruction = "あなたはinkuのデモ用短文を作る。回答は日本語の短文1つだけ。前置き、箇条書き、番号、引用符、説明、Markdownを出さない。",
            demoInstruction = true,
        ))
        return response.text.trim().trim('"', '“', '”', '\'', '「', '」')
            .lineSequence().map { it.trim().removePrefix("-").trim() }
            .firstOrNull { it.isNotBlank() } ?: inkuError { it.demoPromptGenerationEmpty }
    }
}
