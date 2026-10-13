package app.inku.mobile.llm

/**
 * The models Android is verified to draw with on a device: the on-device
 * Gemma 4 E2B, and Gemma 4 31B through the Gemini API, the model the device
 * tests use. These device-verification marks remain separate from the
 * shared ModelCatalog's evaluations, recommendations and labels, which
 * now also appear in the model pickers.
 */
object SupportedModels {
    private val ids = setOf(DefaultModelDownloads.gemma4E2b.modelId, "gemini:gemma-4-31b-it")

    /** [modelId] as a picker lists it: qualified by its provider, or bare under [providerId]. */
    fun isSupported(providerId: String, modelId: String): Boolean =
        (if (modelId.startsWith("$providerId:")) modelId else "$providerId:$modelId") in ids
}
