package app.inku.mobile.data

import app.inku.mobile.data.db.ProviderSettingEntity
import org.json.JSONObject

/** Migrate legacy plaintext before any provider settings are passed to core. */
internal class ProviderSettingsKeyGuard(
    private val encrypt: (String) -> String = AndroidSecretBox::encrypt,
) {
    private fun protect(row: ProviderSettingEntity): ProviderSettingEntity {
        val key = row.encryptedApiKey
        val protected = when {
            key == null || AndroidSecretBox.isEncrypted(key) -> key
            else -> AndroidSecretBox.decryptOrPlain(key)?.let(encrypt)
        }
        return row.copy(encryptedApiKey = protected)
    }

    private fun protect(rows: List<ProviderSettingEntity>): List<ProviderSettingEntity> =
        rows.filter { it.providerId != "chatgpt" }.map(::protect)

    fun normalize(rows: List<ProviderSettingEntity>, localModels: List<String>, candidates: Map<String, List<String>>,
        observations: Map<String, ModelCatalogObservation>): List<ProviderSettingEntity> =
        ProviderSettingsCodec.normalize(protect(rows), localModels, candidates, observations)

    fun save(rows: List<ProviderSettingEntity>, next: ProviderSettingEntity, localModels: List<String>,
        candidates: Map<String, List<String>>, observations: Map<String, ModelCatalogObservation>,
        catalogModels: List<String>): List<ProviderSettingEntity> {
        val safe = protect(next)
        val patch = ProviderSettingsCodec.toCore(safe,
            if (safe.isDefaultLocal) localModels else candidates[safe.providerId] ?: catalogModels,
            observations[safe.providerId]?.records.orEmpty(), observations[safe.providerId]?.access.orEmpty())
        return ProviderSettingsCodec.update(protect(rows), localModels, safe.providerId, patch, candidates, observations)
    }

    fun update(rows: List<ProviderSettingEntity>, localModels: List<String>, id: String, patch: JSONObject,
        candidates: Map<String, List<String>>, observations: Map<String, ModelCatalogObservation>): List<ProviderSettingEntity> =
        ProviderSettingsCodec.update(protect(rows), localModels, id, patch, candidates, observations)
}
