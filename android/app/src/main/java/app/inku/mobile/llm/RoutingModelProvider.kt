package app.inku.mobile.llm

import app.inku.mobile.ui.i18n.InkuFailure
import app.inku.mobile.ui.i18n.inkuError
import app.inku.mobile.data.AndroidSecretBox
import app.inku.mobile.data.ProviderSettingsCodec
import app.inku.mobile.data.catalogRequest
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.model.CompatibilityConstants
import org.json.JSONArray
import org.json.JSONObject

class RoutingModelProvider(
    private val database: InkuDatabase,
    private val localProvider: LocalLiteRtLmProvider,
    private val chatGptPlan: (() -> ChatGptPlanManager)? = null,
    private val admission: ProviderAdmission = ProviderAdmission.shared,
    private val observeAccess: suspend (ProviderSettingEntity, String, Boolean) -> Unit = { _, _, _ -> },
) : ModelProvider {
    override val providerId: String = "routing"

    override suspend fun generate(request: ModelRequest): ModelResponse {
        if (request.modelId.startsWith("chatgpt:")) {
            return (chatGptPlan?.invoke() ?: throw ChatGptException("chatgpt_not_connected")).generate(request)
        }
        val provider = resolveProvider(request)
        if (!canGenerateWith(provider)) {
            inkuError { it.errorProviderNotFoundForModel(request.modelId) }
        }
        if (provider.providerId == "chatgpt") {
            val qualified = request.copy(modelId = "chatgpt:" + request.modelId)
            return (chatGptPlan?.invoke() ?: throw ChatGptException("chatgpt_not_connected")).generate(qualified)
        }
        if (provider.providerId == "local-litert-lm") {
            return localProvider.generate(request)
        }
        val remote = remoteProvider(provider)
        try {
            val result = if (request.pipelineAction == null) remote.generate(request) else
                admission.admit(provider.providerId, request.timeoutMs) { remote.generate(request) }
            observeAccess(provider, request.modelId, true)
            return result
        } catch (error: ModelProviderHttpException) {
            if (error.statusCode == 402 || error.statusCode == 403) observeAccess(provider, request.modelId, false)
            throw error
        }
    }

    suspend fun fetchModels(providerId: String): List<String> {
        val rows = fetchModelRows(providerId)
        return (0 until rows.length()).map { rows.getJSONObject(it).getString("id") }
    }

    suspend fun fetchModelRows(providerId: String): JSONArray {
        val provider = database.providerSettingDao().get(providerId) ?: inkuError { it.errorServiceNotFound(providerId) }
        if (provider.kind !in setOf("openai-compatible", "openai_compatible", "anthropic", "gemini")) {
            inkuError { it.errorProviderModelsUnsupported(provider.displayName) }
        }
        val baseUrl = provider.baseUrl?.trim()?.ifBlank { null } ?: inkuError { it.errorProviderBaseUrlMissing(provider.displayName) }
        val apiKey = provider.encryptedApiKey?.let(AndroidSecretBox::decryptOrPlain)
        if (requiresApiKey(provider.providerId) && apiKey.isNullOrBlank()) {
            throw InkuFailure(CREDENTIALS_UNAVAILABLE) { it.errorProviderApiKeyMissing(provider.displayName) }
        }
        return ProviderModelListFetcher.fetchRows(provider.kind, baseUrl, apiKey)
    }

    private suspend fun resolveProvider(request: ModelRequest): ProviderSettingEntity {
        val providers = database.providerSettingDao().listAll().toMutableList()
        // Plan connections are owned by their manager, outside provider_settings.
        chatGptPlan?.invoke()?.state?.value?.let { plan ->
            providers.removeAll { it.providerId == "chatgpt" }
            providers += ProviderSettingEntity(
                providerId = "chatgpt", displayName = "ChatGPT", kind = "chatgpt-responses",
                baseUrl = null, encryptedApiKey = null, publishedModelsJson = JSONArray(plan.publishedModels).toString(),
                isEnabled = plan.canUsePlan, isDefaultLocal = false, updatedAt = 0,
            )
        }
        val available = providers.associate { provider ->
            provider.providerId to if (provider.isDefaultLocal) ProviderSettingsCodec.parseModelIds(provider.publishedModelsJson) else database.settingsDao().get("provider_model_candidates:${provider.providerId}")
                ?.valueJson?.takeUnless { it == "null" }?.let(ProviderSettingsCodec::parseModelIds)
                .let { it ?: ProviderSettingsCodec.catalogIds(provider.providerId) }
        }
        resolveProviderForRouting(providers, request.modelId, null, available)?.let { return it }
        val selection = database.settingsDao().get("model_selection")?.valueJson?.let(::JSONObject)
        val fallback = configuredStageProvider(providers, selection, request.pipelineAction)
        return resolveProviderForRouting(providers, request.modelId, fallback, available)
            ?: inkuError { it.errorProviderNotFoundForModel(request.modelId) }
    }

    internal companion object {
        /**
         * The service a model id belongs to: the one it names with a
         * `provider:` prefix, else the one enabled service that publishes it.
         * An id no enabled service publishes, or that two publish, goes to
         * the user's provider for the request's stage.
         */
        internal fun resolveProviderForRouting(
            providers: List<ProviderSettingEntity>,
            modelId: String,
            stageDefaultProviderId: String?,
            available: Map<String, List<String>> = emptyMap(),
        ): ProviderSettingEntity? {
            // The ChatGPT plan is owned outside provider_settings (step 4).
            val plan = providers.firstOrNull { it.providerId == "chatgpt" && it.isEnabled &&
                modelId in ProviderSettingsCodec.parseModelIds(it.publishedModelsJson) }
            if (plan != null && providers.none { it.providerId != "chatgpt" && it.isEnabled &&
                    modelId in ProviderSettingsCodec.parseModelIds(it.publishedModelsJson) }) return plan
            val rows = JSONObject()
            providers.forEach { provider -> rows.put(provider.providerId,
                ProviderSettingsCodec.toCore(provider.copy(encryptedApiKey = null), available[provider.providerId] ?: ProviderSettingsCodec.parseModelIds(provider.publishedModelsJson))) }
            val answer = catalogRequest("resolve_ref", JSONObject().put("providers", rows).put("ref", modelId)
                .put("default_provider", stageDefaultProviderId ?: "__missing__"))
            val resolved = answer.getString("provider")
            providers.firstOrNull { it.providerId == resolved }?.let { return it }
            val retired = catalogRequest("retired_providers").getJSONArray("providers")
            return (0 until retired.length()).map(retired::getJSONObject).firstOrNull { it.optString("id") == resolved }
                ?.let { ProviderSettingsCodec.fromCore(it).copy(isEnabled = false) }
        }

        /** Older selections carry qualified models, so no Room migration is needed. */
        internal fun configuredStageProvider(
            providers: List<ProviderSettingEntity>,
            selection: JSONObject?,
            pipelineAction: String?,
        ): String? {
            val stage2 = pipelineAction == "complete_visible_ddl_holes"
            val stage = if (stage2) "stage2" else "stage1"
            val rows = JSONObject()
            providers.forEach { rows.put(it.providerId, ProviderSettingsCodec.toCore(it.copy(encryptedApiKey = null))) }
            val configuredProvider = selection?.optString("${stage}_provider")?.takeIf { it.isNotBlank() }
            val selectedModel = selection?.optString("${stage}_model")?.takeIf { it.isNotBlank() }
                ?: if (stage2) CompatibilityConstants.defaultStage2Model else CompatibilityConstants.defaultStage1Model
            val model = if (configuredProvider != null) catalogRequest("split_ref", JSONObject()
                .put("providers", rows).put("ref", selectedModel)).getString("model") else selectedModel
            val settings = JSONObject().put("stage1_model", model)
            configuredProvider?.let { settings.put("stage1_provider", it) }
            val reference = catalogRequest("resolve_stage_default", JSONObject().put("providers", rows)
                .put("stage", "stage1").put("user_settings", settings)).getString("ref")
            val answer = catalogRequest("split_ref", JSONObject().put("providers", rows).put("ref", reference))
            return answer.optString("provider").takeUnless { it.isBlank() || it == "null" }
        }

        internal fun remoteProvider(provider: ProviderSettingEntity): ModelProvider {
            val baseUrl = provider.baseUrl?.trim()?.ifBlank { null } ?: inkuError { it.errorProviderBaseUrlMissing(provider.displayName) }
            val apiKey = provider.encryptedApiKey?.let(AndroidSecretBox::decryptOrPlain)
            if (requiresApiKey(provider.providerId) && apiKey.isNullOrBlank()) {
                // The server's `failure_detail`, so a screen can name the cause.
                throw InkuFailure(CREDENTIALS_UNAVAILABLE) { it.errorProviderApiKeyMissing(provider.displayName) }
            }
            // One transport per connection kind, as the server's `_request` has.
            return when (provider.kind) {
                "gemini" -> GeminiModelProvider(provider.providerId, baseUrl, apiKey)
                "anthropic" -> AnthropicModelProvider(provider.providerId, baseUrl, apiKey)
                else -> OpenAiCompatibleProvider(provider.providerId, baseUrl, apiKey)
            }
        }

        internal fun canGenerateWith(provider: ProviderSettingEntity): Boolean = provider.isEnabled

    }
}
