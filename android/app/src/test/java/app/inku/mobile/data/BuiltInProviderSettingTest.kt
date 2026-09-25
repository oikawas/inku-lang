package app.inku.mobile.data

import app.inku.mobile.data.db.ProviderSettingEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class BuiltInProviderSettingTest {
    @Test
    fun anEditedBuiltInKeepsItsNameAndUrlButNotItsKindOrSwitch() {
        val catalog = setting("ollama", "Ollama", "http://127.0.0.1:11434/v1")
        val edited = setting("ollama", "Home Ollama", "https://ollama.example.com/v1", kind = "gemini", enabled = false)

        val stored = builtInProviderSetting(catalog, edited)

        assertEquals("Home Ollama", stored.displayName)
        assertEquals("https://ollama.example.com/v1", stored.baseUrl)
        assertEquals("openai-compatible", stored.kind)
        assertEquals(true, stored.isEnabled)
        assertSame(catalog, builtInProviderSetting(catalog, null))
        // A blank edit and the local marker URL fall back to the catalog.
        assertEquals(catalog.baseUrl, builtInProviderSetting(catalog, edited.copy(baseUrl = " ")).baseUrl)
        val local = setting("local-litert-lm", "LiteRT-LM / Local", "local://litert-lm", local = true)
        assertEquals("local://litert-lm", builtInProviderSetting(local, local.copy(baseUrl = "https://x.example")).baseUrl)
    }

    private fun setting(
        id: String,
        name: String,
        url: String?,
        kind: String = "openai-compatible",
        enabled: Boolean = true,
        local: Boolean = false,
    ) = ProviderSettingEntity(
        providerId = id,
        displayName = name,
        kind = kind,
        baseUrl = url,
        encryptedApiKey = null,
        publishedModelsJson = "[]",
        isEnabled = enabled,
        isDefaultLocal = local,
        updatedAt = 0,
    )
}
