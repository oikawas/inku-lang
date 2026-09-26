package app.inku.mobile.llm

data class ModelDownloadSpec(
    val modelId: String,
    val displayName: String,
    val qualityTier: String,
    val downloadUrl: String,
    val licenseUrl: String,
    val expectedSha256: String?,
    val fileName: String,
    val maxDownloadBytes: Long = 10L * 1024L * 1024L * 1024L,
)

object DefaultModelDownloads {
    val gemma4E2b = ModelDownloadSpec(
        modelId = "local-litert-lm:gemma-4-e2b",
        displayName = "Gemma 4 E2B",
        qualityTier = "standard",
        downloadUrl = "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it.litertlm",
        licenseUrl = "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm",
        expectedSha256 = "181938105e0eefd105961417e8da75903eacda102c4fce9ce90f50b97139a63c",
        fileName = "gemma-4-E2B-it.litertlm",
    )

    // Gemma 4 E4B was offered as the high-quality option until 2026-09-26.
    // A Pixel 9 ran short of memory with it: its first engine start in May
    // ended the process, and describing a photo got the app killed.
    val all = listOf(gemma4E2b)

    /**
     * [modelId], or the standard model in place of an on-device model the
     * catalog no longer offers. A choice stored while Gemma 4 E4B was offered
     * still names it, and nothing on the device can run it now.
     */
    fun offeredOrStandard(modelId: String): String =
        if (modelId.startsWith("local-litert-lm:") && all.none { it.modelId == modelId }) gemma4E2b.modelId else modelId
}
