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
        val providers = database.providerSettingDao().listAll().filter { it.isEnabled }
        providers.firstOrNull { modelId.startsWith("${it.providerId}:") }?.let { return it }
        providers.firstOrNull { it.providerId == "local-litert-lm" && modelId.startsWith("local-litert-lm:") }?.let { return it }
        providers.firstOrNull { provider ->
            parsePublishedModelIds(provider.publishedModelsJson).contains(modelId)
        }?.let { return it }
        inkuError { it.errorProviderNotFoundForModel(modelId) }
    }

    private fun remoteProvider(provider: ProviderSettingEntity): OpenAiCompatibleProvider {
        val baseUrl = provider.baseUrl?.trim()?.ifBlank { null } ?: inkuError { it.errorProviderBaseUrlMissing(provider.displayName) }
        val apiKey = provider.encryptedApiKey?.let(AndroidSecretBox::decryptOrPlain)
        if (provider.providerId in setOf("openai", "nvidia") && apiKey.isNullOrBlank()) {
            inkuError { it.errorProviderApiKeyMissing(provider.displayName) }
        }
        return OpenAiCompatibleProvider(provider.providerId, baseUrl, apiKey)
    }

    private fun parsePublishedModelIds(value: String): List<String> {
        return runCatching {
            val array = JSONArray(value)
            (0 until array.length()).mapNotNull { array.optString(it).takeIf { id -> id.isNotBlank() } }
        }.getOrElse {
            value.lines().map { it.trim() }.filter { it.isNotBlank() }
        }
    }
}
