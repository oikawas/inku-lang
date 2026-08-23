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
        if (provider.kind != "openai-compatible" && provider.kind != "openai_compatible") {
            inkuError { it.errorProviderModelsUnsupported(provider.displayName) }
        }
        return remoteProvider(provider).fetchModels()
    }

    private suspend fun resolveProvider(modelId: String): ProviderSettingEntity {
        return resolveProviderForRouting(database.providerSettingDao().listAll(), modelId)
            ?: inkuError { it.errorProviderNotFoundForModel(modelId) }
    }

    private fun remoteProvider(provider: ProviderSettingEntity): OpenAiCompatibleProvider {
        val baseUrl = provider.baseUrl?.trim()?.ifBlank { null } ?: inkuError { it.errorProviderBaseUrlMissing(provider.displayName) }
        val apiKey = provider.encryptedApiKey?.let(AndroidSecretBox::decryptOrPlain)
        if (provider.providerId in setOf("openai", "nvidia") && apiKey.isNullOrBlank()) {
            inkuError { it.errorProviderApiKeyMissing(provider.displayName) }
        }
        return OpenAiCompatibleProvider(provider.providerId, baseUrl, apiKey)
    }

    internal companion object {
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
