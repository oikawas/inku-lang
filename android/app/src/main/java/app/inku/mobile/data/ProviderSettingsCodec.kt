package app.inku.mobile.data

import app.inku.mobile.data.db.ProviderSettingEntity
import org.json.JSONArray
import org.json.JSONObject

/** The only conversion between Room provider rows and the shared settings format. */
internal object ProviderSettingsCodec {
    private val catalogInfo by lazy { catalogRequest("catalog") }
    private val catalogProviders by lazy { catalogInfo.getJSONObject("catalog").getJSONObject("providers") }
    private val catalogModels by lazy {
        catalogProviders.keys().asSequence().associateWith { provider ->
            val models = catalogProviders.getJSONObject(provider).optJSONArray("models") ?: JSONArray()
            (0 until models.length()).associate { index ->
                val row = models.getJSONObject(index)
                val internal = JSONObject(row.toString())
                val storedKeys = catalogInfo.getJSONObject("stored_label_keys")
                internal.optJSONArray("labels").strings().forEach { label ->
                    if (storedKeys.has(label)) internal.put(storedKeys.getString(label), true)
                }
                internal.remove("labels")
                row.getString("id") to internal
            }
        }
    }
    fun catalogIds(provider: String): List<String> = catalogProviders.optJSONObject(provider)?.optJSONArray("models")?.let { models ->
        (0 until models.length()).map { models.getJSONObject(it).getString("id") }
    }.orEmpty()
    private val definitions by lazy {
        val list = catalogRequest("providers", JSONObject().put("host", "android")).getJSONArray("providers")
        (0 until list.length()).associate { list.getJSONObject(it).getString("id") to list.getJSONObject(it) }
    }
    fun parseModelIds(value: String): List<String> = runCatching {
        val array = JSONArray(value)
        (0 until array.length()).map { array.optString(it).trim() }.filter(String::isNotEmpty)
    }.getOrElse { value.lines().map(String::trim).filter(String::isNotEmpty) }

    fun toCore(row: ProviderSettingEntity, available: List<String> = parseModelIds(row.publishedModelsJson),
        observed: Map<String, JSONObject> = emptyMap(), access: Map<String, Boolean> = emptyMap(),
        seen: List<String> = emptyList()): JSONObject {
        val ids = parseModelIds(row.publishedModelsJson)
        val allModels = (if (row.isDefaultLocal) available else available + ids).distinct()
        // Core can merge its built-in NVIDIA models even when the host's
        // candidates omit them. Every known but unpublished id must be false.
        val builtins = definitions[row.providerId]?.optJSONArray("models") ?: JSONArray()
        val known = (allModels + ids + catalogIds(row.providerId) + observed.keys + access.keys + seen +
            (0 until builtins.length()).map { builtins.getJSONObject(it).getString("id") }).distinct()
        val models = JSONArray(allModels.map { id ->
            (observed[id] ?: catalogModels[row.providerId]?.get(id))?.let { JSONObject(it.toString()) }
                ?: JSONObject().put("id", id).put("label", id)
        })
        val applied = if (access.isEmpty()) models else {
            val answers = JSONArray((0 until models.length()).map { models.getJSONObject(it) }.filterNot { it.optBoolean("eol") }
                .map { model -> access[model.getString("id")]?.let { JSONObject().put("subscription", !it) } ?: JSONObject() })
            catalogRequest("access_apply", JSONObject().put("models", models).put("answers", answers)).getJSONArray("models")
        }
        return JSONObject().put("id", row.providerId).put("label", row.displayName)
            .put("kind", row.kind.replace('-', '_')).put("base_url", row.baseUrl ?: "")
            .put("active", row.isEnabled).put("api_key", row.encryptedApiKey ?: "")
            .put("models", applied)
            .put("enabled_models", JSONObject().also { enabled -> known.forEach { enabled.put(it, it in ids) } })
            .put("rate_limits", JSONObject().put("rpm", 0).put("tpm", 0).put("rpd", 0)).put("memo", "")
    }

    fun fromCore(value: JSONObject, previous: ProviderSettingEntity? = null): ProviderSettingEntity {
        val id = value.getString("id")
        val enabled = value.optJSONObject("enabled_models") ?: JSONObject()
        val models = value.optJSONArray("models") ?: JSONArray()
        val enabledModels = (0 until models.length()).mapNotNull { index ->
            models.optJSONObject(index)?.optString("id")?.takeIf { it.isNotBlank() && enabled.optBoolean(it) }
        }
        val previousOrder = previous?.let { parseModelIds(it.publishedModelsJson) }.orEmpty()
        val published = previousOrder.filter { it in enabledModels } + enabledModels.filter { it !in previousOrder }
        val key = value.optString("api_key").takeIf(String::isNotEmpty)
        return ProviderSettingEntity(id, value.optString("label", id), value.optString("kind", "openai_compatible").replace('_', '-'),
            value.optString("base_url").takeIf(String::isNotBlank), key, JSONArray(published).toString(),
            value.optBoolean("active", true), previous?.isDefaultLocal ?: (id == "local-litert-lm"), previous?.updatedAt ?: 0)
    }

    private fun input(rows: List<ProviderSettingEntity>, localModels: List<String>, available: Map<String, List<String>>,
        observations: Map<String, ModelCatalogObservation>): JSONObject {
        val input = JSONObject()
        rows.filter { it.providerId != "chatgpt" }.forEach { row ->
            val known = definitions[row.providerId]?.optJSONArray("models") ?: JSONArray()
            val defaultIds = (0 until known.length()).map { known.getJSONObject(it).getString("id") }
            input.put(row.providerId, toCore(row, if (row.isDefaultLocal) localModels else available[row.providerId] ?: defaultIds,
                observations[row.providerId]?.records.orEmpty(), observations[row.providerId]?.access.orEmpty(),
                observations[row.providerId]?.seen.orEmpty()))
        }
        if (!input.has("local-litert-lm")) {
            val local = definitions.getValue("local-litert-lm")
            val row = ProviderSettingEntity("local-litert-lm", local.getString("label"), "litert-lm", local.getString("default_base_url"),
                null, JSONArray(localModels).toString(), true, true, 0)
            input.put(row.providerId, toCore(row, localModels))
        }
        return input
    }

    private fun settings(input: JSONObject) = JSONObject()
        .put("model_catalog_version", catalogInfo.getString("version")).put("providers", input)

    private fun rows(result: JSONObject, previous: List<ProviderSettingEntity>): List<ProviderSettingEntity> {
        val old = previous.associateBy { it.providerId }
        val values = result.getJSONObject("settings").getJSONObject("providers")
        return values.keys().asSequence().map { id -> fromCore(values.getJSONObject(id), old[id]) }.toList()
    }

    fun normalize(previous: List<ProviderSettingEntity>, localModels: List<String>, available: Map<String, List<String>> = emptyMap(),
        observations: Map<String, ModelCatalogObservation> = emptyMap()): List<ProviderSettingEntity> {
        val input = input(previous, localModels, available, observations)
        val result = catalogRequest("normalize_settings", JSONObject().put("host", "android").put("settings", settings(input))
            .put("order", JSONArray(input.keys().asSequence().toList())).put("env", JSONObject()))
        return rows(result, previous)
    }

    fun update(previous: List<ProviderSettingEntity>, localModels: List<String>, id: String, patch: JSONObject,
        available: Map<String, List<String>> = emptyMap(), observations: Map<String, ModelCatalogObservation> = emptyMap()): List<ProviderSettingEntity> {
        val input = input(previous, localModels, available, observations)
        val result = catalogRequest("update_settings", JSONObject().put("host", "android").put("settings", settings(input))
            .put("order", JSONArray(input.keys().asSequence().toList())).put("env", JSONObject())
            .put("patch", JSONObject().put("providers", JSONObject().put(id, patch)))
            .put("patch_order", JSONArray().put(id)))
        return rows(result, previous)
    }

    fun refresh(provider: String, fetched: JSONArray, previous: JSONObject, today: String,
        access: Map<String, Boolean> = emptyMap()): JSONObject {
        val prepared = catalogRequest("refresh_prepare", JSONObject().put("provider", provider)
            .put("models", fetched).put("previous", previous)).getJSONArray("models")
        val answers = JSONArray((0 until prepared.length()).map { index ->
            val id = prepared.getJSONObject(index).getString("id")
            access[id]?.let { JSONObject().put("subscription", !it) } ?: JSONObject()
        })
        val checked = catalogRequest("access_apply", JSONObject().put("models", prepared).put("answers", answers)).getJSONArray("models")
        return catalogRequest("refresh_finish", JSONObject().put("models", checked).put("previous", previous).put("today", today))
    }
}
