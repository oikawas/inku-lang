package app.inku.mobile.llm

data class ModelDownloadSpec(
    val modelId: String,
    val displayName: String,
    val qualityTier: String,
    val downloadUrl: String,
    val licenseUrl: String,
    val expectedSha256: String?,
    val fileName: String,
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

    val gemma4E4b = ModelDownloadSpec(
        modelId = "local-litert-lm:gemma-4-e4b",
        displayName = "Gemma 4 E4B",
        qualityTier = "high",
        downloadUrl = "https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/main/gemma-4-E4B-it.litertlm",
        licenseUrl = "https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm",
        expectedSha256 = "0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0",
        fileName = "gemma-4-E4B-it.litertlm",
    )

    val all = listOf(gemma4E2b, gemma4E4b)
}
