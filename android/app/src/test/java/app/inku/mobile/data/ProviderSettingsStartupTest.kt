package app.inku.mobile.data

import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.llm.DefaultModelDownloads
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProviderSettingsStartupTest {
    @Test fun backupSelectionsSurviveStartupWithCandidatesAndObservations() {
        val fixture = JSONObject(requireNotNull(javaClass.getResourceAsStream("/provider-settings-pixel9-20261028.json"))
            .bufferedReader().use { it.readText() })
        val source = fixture.getJSONArray("providers")
        val rows = (0 until source.length()).map { index -> source.getJSONObject(index).let { row ->
            ProviderSettingEntity(row.getString("id"), row.getString("name"), row.getString("kind"), row.getString("url"),
                if (row.isNull("key")) null else row.getString("key"), row.getJSONArray("published").toString(),
                row.getBoolean("enabled"), row.getBoolean("local"), 0)
        } }
        val settings = fixture.getJSONObject("settings")
        val candidates = settings.keys().asSequence().filter { it.startsWith("provider_model_candidates:") }
            .associate { key -> key.substringAfter(':') to settings.getJSONArray(key).strings() }
        val observations = settings.keys().asSequence().filter { it.startsWith("model_catalog_observations:") }
            .associate { key -> key.substringAfter(':') to ModelCatalogObservation.read(settings.getJSONObject(key).toString()) }
        val guard = ProviderSettingsKeyGuard()
        val localModels = DefaultModelDownloads.all.map { it.modelId }
        val normalized = guard.normalize(rows, localModels, candidates, observations).associateBy { it.providerId }
        rows.forEach { row ->
            val result = normalized.getValue(row.providerId)
            assertEquals("${row.providerId} published", ProviderSettingsCodec.parseModelIds(row.publishedModelsJson),
                ProviderSettingsCodec.parseModelIds(result.publishedModelsJson))
            assertEquals("${row.providerId} fields", row, result)
        }
        val nvidia = rows.first { it.providerId == "nvidia" }
        val selected = ProviderSettingsCodec.parseModelIds(nvidia.publishedModelsJson)
        val observation = observations.getValue("nvidia")
        val encoded = ProviderSettingsCodec.toCore(nvidia, candidates.getValue("nvidia"), observation.records,
            observation.access, observation.seen).getJSONObject("enabled_models")
        val definitions = catalogRequest("providers", JSONObject().put("host", "android")).getJSONArray("providers")
        val builtin = (0 until definitions.length()).map(definitions::getJSONObject).first { it.getString("id") == "nvidia" }
            .getJSONArray("models")
        val known = ProviderSettingsCodec.catalogIds("nvidia") + candidates.getValue("nvidia") + observation.seen +
            observation.access.keys + observation.records.keys + (0 until builtin.length()).map { builtin.getJSONObject(it).getString("id") }
        known.forEach { id ->
            assertTrue("missing enabled flag for $id", encoded.has(id))
            assertEquals("enabled flag for $id", id in selected, encoded.getBoolean(id))
        }
        fun assertNvidiaUnchanged(label: String, result: List<ProviderSettingEntity>) = assertEquals(label, selected,
            ProviderSettingsCodec.parseModelIds(result.first { it.providerId == "nvidia" }.publishedModelsJson))
        assertNvidiaUnchanged("save", guard.save(rows, nvidia, localModels, candidates, observations,
            ProviderSettingsCodec.catalogIds("nvidia")))
        assertNvidiaUnchanged("clear key", guard.update(rows, localModels, "openai", JSONObject().put("clear_api_key", true), candidates, observations))
        assertNvidiaUnchanged("delete", guard.update(rows, localModels, "anthropic", JSONObject().put("delete", true), candidates, observations))
        val nvidiaCandidates = candidates.getValue("nvidia")
        val modelRows = JSONArray(nvidiaCandidates.map { JSONObject().put("id", it).put("label", it) })
        val enabled = JSONObject().also { flags -> nvidiaCandidates.forEach { flags.put(it, it in selected) } }
        val refreshed = ProviderSettingsCodec.refresh("nvidia", modelRows, JSONObject().put("models", modelRows)
            .put("enabled_models", enabled), "2026-10-28").getJSONObject("enabled_models")
        assertEquals("refresh", selected.toSet(), refreshed.keys().asSequence().filter { refreshed.getBoolean(it) }.toSet())
    }
}
