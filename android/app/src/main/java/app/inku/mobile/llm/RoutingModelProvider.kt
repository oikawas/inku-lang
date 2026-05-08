package app.inku.mobile.llm

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
        val provider = database.providerSettingDao().get(providerId) ?: error("サービスが見つかりません: $providerId")
        if (provider.kind != "openai-compatible" && provider.kind != "openai_compatible") {
            error("${provider.displayName} のモデル取得はAndroid版では未対応です。")
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
        error("モデルに対応する接続先が見つかりません: $modelId")
    }

    private fun remoteProvider(provider: ProviderSettingEntity): OpenAiCompatibleProvider {
        val baseUrl = provider.baseUrl?.trim()?.ifBlank { null } ?: error("${provider.displayName} のBase URLが未設定です。")
        val apiKey = provider.encryptedApiKey?.let(AndroidSecretBox::decryptOrPlain)
        if (provider.providerId in setOf("openai", "nvidia") && apiKey.isNullOrBlank()) {
            error("${provider.displayName} のAPIキーが未設定です。")
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
