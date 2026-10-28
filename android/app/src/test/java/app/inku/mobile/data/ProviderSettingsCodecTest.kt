package app.inku.mobile.data

import app.inku.mobile.data.db.ProviderSettingEntity
import org.junit.Assert.assertEquals
import org.junit.Test
import org.json.JSONObject
import org.json.JSONArray
import app.inku.mobile.llm.DefaultModelDownloads

class ProviderSettingsCodecTest {
    @Test fun roomCoreRoomPreservesTheStoredRowAndEncryptedKey() {
        val row = ProviderSettingEntity("custom", "Custom", "openai-compatible", "https://example.test/v1",
            "enc:v1:synthetic", "[\"one\",\"two\"]", true, false, 123)
        assertEquals(row, ProviderSettingsCodec.fromCore(ProviderSettingsCodec.toCore(row), row))
        val local = ProviderSettingEntity("local-litert-lm", "LiteRT", "litert-lm", "local://litert-lm",
            null, "[\"gemma\"]", true, true, 456)
        assertEquals(local, ProviderSettingsCodec.fromCore(ProviderSettingsCodec.toCore(local), local))
    }

    @Test fun normalizationPreservesSixConfiguredRowsAndOpaqueKeys() {
        val localModels = DefaultModelDownloads.all.map { it.modelId }
        fun models(vararg ids: String) = JSONArray(ids.toList()).toString()
        val rows = listOf(
            ProviderSettingEntity("local-litert-lm", "LiteRT-LM / Local", "litert-lm", "local://litert-lm", null, models("local-litert-lm:gemma-4-e2b"), true, true, 1),
            ProviderSettingEntity("openai", "OpenAI API Platform", "openai-compatible", "https://api.openai.com/v1", "enc:synthetic-\\\"-日本語", models("gpt-5.6-luna", "gpt-5.6-terra"), true, false, 2),
            ProviderSettingEntity("nvidia", "NVIDIA NIM", "openai-compatible", "https://integrate.api.nvidia.com/v1", "enc:nvidia", models("google/gemma-4-31b-it", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"), true, false, 3),
            ProviderSettingEntity("anthropic", "Claude API", "anthropic", "https://api.anthropic.com", "enc:anthropic", models("claude-opus-5-5", "claude-haiku-5-5", "claude-sonnet-5-5"), true, false, 4),
            ProviderSettingEntity("gemini", "Gemini API", "gemini", "https://generativelanguage.googleapis.com", "enc:gemini", models("gemma-4-31b-it", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.6-flash"), true, false, 5),
            ProviderSettingEntity("ollama-cloud", "Ollama Cloud (ollama.com)", "openai-compatible", "https://ollama.com/v1", "enc:ollama", models(), true, false, 6),
        )
        val normalized = ProviderSettingsCodec.normalize(rows, localModels).associateBy { it.providerId }
        rows.forEach { assertEquals(it, normalized.getValue(it.providerId)) }
    }

    @Test fun updateTransportsOpaqueKeyAndRetainsLocalSelection() {
        val local = ProviderSettingEntity("local-litert-lm", "LiteRT-LM / Local", "litert-lm", "local://litert-lm", null,
            "[\"gemma-4\"]", true, true, 1)
        val custom = ProviderSettingEntity("custom", "Custom", "openai-compatible", "https://example.test/v1",
            "synthetic:before", "[\"model\"]", true, false, 2)
        val patch = ProviderSettingsCodec.toCore(custom.copy(encryptedApiKey = "synthetic:after/+=\\\""))
        val result = ProviderSettingsCodec.update(listOf(local, custom), listOf("gemma-3", "gemma-4"), "custom", patch)
            .associateBy { it.providerId }
        assertEquals("synthetic:after/+=\\\"", result.getValue("custom").encryptedApiKey)
        assertEquals(local, result.getValue("local-litert-lm"))
        val cleared = ProviderSettingsCodec.update(result.values.toList(), listOf("gemma-3", "gemma-4"), "custom", JSONObject().put("clear_api_key", true))
        assertEquals(null, cleared.first { it.providerId == "custom" }.encryptedApiKey)
        val deleted = ProviderSettingsCodec.update(result.values.toList(), listOf("gemma-3", "gemma-4"), "custom", JSONObject().put("delete", true))
        assertEquals(false, deleted.any { it.providerId == "custom" })
    }

    @Test fun updateDoesNotPublishAnObservedRetiredModel() {
        val row = ProviderSettingEntity("openai", "OpenAI API Platform", "openai-compatible", "https://api.openai.com/v1",
            null, "[\"gpt-6-luna\"]", true, false, 1)
        val retired = JSONObject().put("id", "gpt-6-luna").put("label", "gpt-6-luna").put("eol", true)
        val patch = ProviderSettingsCodec.toCore(row, listOf("gpt-6-luna"), mapOf("gpt-6-luna" to retired))
        val updated = ProviderSettingsCodec.update(listOf(row), listOf("local-model"), "openai", patch)
            .first { it.providerId == "openai" }
        assertEquals(emptyList<String>(), ProviderSettingsCodec.parseModelIds(updated.publishedModelsJson))
    }
}
