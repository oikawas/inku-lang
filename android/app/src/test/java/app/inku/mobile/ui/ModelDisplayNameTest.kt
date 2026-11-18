package app.inku.mobile.ui

import app.inku.mobile.data.ProviderSettingsCodec
import app.inku.mobile.data.catalogRequest
import app.inku.mobile.data.db.ProviderSettingEntity
import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class ModelDisplayNameTest {
    @Test fun screenNamesFollowCoreForSharedCases() {
        val fixture = File(System.getProperty("inku.modelCatalogSource")).resolveSibling("model-display-cases.json")
        val cases = JSONObject(fixture.readText()).getJSONArray("cases")
        for (index in 0 until cases.length()) {
            val row = cases.getJSONObject(index)
            val id = row.getString("name")
            if (id.isEmpty()) continue
            val provider = ProviderSettingEntity("fixture", row.getString("owner"), "openai-compatible",
                null, null, "[]", true, false, 0)
            val state = InkuUiState(providerSettings = listOf(provider),
                providerModelCandidates = mapOf("fixture" to listOf(id)))
            val reference = "fixture:$id"
            val answer = catalogRequest("resolve_display", JSONObject()
                .put("providers", JSONObject().put("fixture", ProviderSettingsCodec.toCore(provider, listOf(id))))
                .put("ref", reference).put("default_provider", "local-litert-lm")
                .put("language", state.uiLanguage.code))
            assertEquals("case $index: $reference", answer.getString("display_name"), modelLabelFor(state, reference))
            assertEquals(id, modelDisplayName(reference, "fixture"))
        }
        val chatGpt = ProviderSettingEntity("chatgpt", "old label", "openai-compatible",
            null, null, "[]", true, false, 0)
        assertEquals("SIWC / gpt-6.1-sol", modelLabelFor(InkuUiState(providerSettings = listOf(chatGpt)),
            "chatgpt:gpt-6.1-sol"))
        assertEquals("qwen3.5:4b-q4_K_M", modelDisplayName("qwen3.5:4b-q4_K_M", "ollama"))
        assertEquals("google/gemma-4-31b-it", modelDisplayName("nvidia:google/gemma-4-31b-it", "nvidia"))
    }
}
