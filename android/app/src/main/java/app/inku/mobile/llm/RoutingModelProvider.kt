package app.inku.mobile.llm

import app.inku.mobile.ui.i18n.inkuError
import app.inku.mobile.data.AndroidSecretBox
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.ProviderSettingEntity
import org.json.JSONArray

class RoutingModelProvider(
    private val database: InkuDatabase,
    private val localProvider: LocalLiteRtLmProvider,
) : ModelProvider {
    override val providerId: String = "routing"

    override suspend fun generate(request: ModelRequest): ModelResponse {
        val provider = resolveProvider(request.modelId)
        if (!canGenerateWith(provider)) {
            inkuError { it.errorProviderNotFoundForModel(request.modelId) }
        }
        if (provider.providerId == "local-litert-lm") {
            return localProvider.generate(request)
        }
        val remote = remoteProvider(provider)
        return remote.generate(request)
    }

    suspend fun fetchModels(providerId: String): List<String> {
        val provider = database.providerSettingDao().get(providerId) ?: inkuError { it.errorServiceNotFound(providerId) }
        if (provider.kind !in setOf("openai-compatible", "openai_compatible", "anthropic", "gemini")) {
            inkuError { it.errorProviderModelsUnsupported(provider.displayName) }
        }
        val baseUrl = provider.baseUrl?.trim()?.ifBlank { null } ?: inkuError { it.errorProviderBaseUrlMissing(provider.displayName) }
        val apiKey = provider.encryptedApiKey?.let(AndroidSecretBox::decryptOrPlain)
        if (provider.providerId in setOf("openai", "nvidia", "ollama-cloud") && apiKey.isNullOrBlank()) {
            inkuError { it.errorProviderApiKeyMissing(provider.displayName) }
        }
        return ProviderModelListFetcher.fetchModels(provider.kind, baseUrl, apiKey)
    }

    private suspend fun resolveProvider(modelId: String): ProviderSettingEntity {
        return resolveProviderForRouting(database.providerSettingDao().listAll(), modelId)
            ?: inkuError { it.errorProviderNotFoundForModel(modelId) }
    }

    private fun remoteProvider(provider: ProviderSettingEntity): ModelProvider {
        val baseUrl = provider.baseUrl?.trim()?.ifBlank { null } ?: inkuError { it.errorProviderBaseUrlMissing(provider.displayName) }
        val apiKey = provider.encryptedApiKey?.let(AndroidSecretBox::decryptOrPlain)
        if (provider.providerId in setOf("openai", "nvidia", "ollama-cloud") && apiKey.isNullOrBlank()) {
            inkuError { it.errorProviderApiKeyMissing(provider.displayName) }
        }
        // One transport per connection kind, as the server's `_request` has.
        return when (provider.kind) {
            "gemini" -> GeminiModelProvider(provider.providerId, baseUrl, apiKey)
            "anthropic" -> AnthropicModelProvider(provider.providerId, baseUrl, apiKey)
            else -> OpenAiCompatibleProvider(provider.providerId, baseUrl, apiKey)
        }
    }

    internal companion object {
        /**
         * The service a model id belongs to: the one it names with a
         * `provider:` prefix, else the one enabled service that publishes it.
         * An id no enabled service publishes, or that two publish, goes to
         * the device's own model.
         */
        internal fun resolveProviderForRouting(
            providers: List<ProviderSettingEntity>,
            modelId: String,
        ): ProviderSettingEntity? {
            providers.firstOrNull { modelId.startsWith("${it.providerId}:") }?.let { return it }
            val owners = providers.filter { provider ->
                provider.isEnabled && parsePublishedModelIds(provider.publishedModelsJson).contains(modelId)
            }
            return owners.singleOrNull() ?: providers.firstOrNull { it.isDefaultLocal }
        }

        internal fun canGenerateWith(provider: ProviderSettingEntity): Boolean = provider.isEnabled

        private fun parsePublishedModelIds(value: String): List<String> = runCatching {
            val array = JSONArray(value)
            (0 until array.length()).mapNotNull { array.optString(it).takeIf { id -> id.isNotBlank() } }
        }.getOrElse {
            value.lines().map { it.trim() }.filter { it.isNotBlank() }
        }
    }
}
