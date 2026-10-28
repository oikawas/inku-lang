package app.inku.mobile.data

import app.inku.mobile.data.db.ProviderSettingEntity
import org.junit.Assert.assertEquals
import org.junit.Test

class ProviderSettingsKeyGuardTest {
    @Test fun legacyPlaintextIsEncryptedBeforeNormalizationAndSave() {
        val encryptedInputs = mutableListOf<String>()
        val guard = ProviderSettingsKeyGuard { plaintext ->
            encryptedInputs += plaintext
            "enc:v1:fixture:$plaintext"
        }
        val legacy = ProviderSettingEntity("custom", "Custom", "openai-compatible", "https://example.test/v1",
            "legacy-secret", "[\"model\"]", true, false, 1)
        val alreadyEncrypted = legacy.copy(providerId = "other", encryptedApiKey = "enc:v1:unchanged")
        val normalized = guard.normalize(listOf(legacy, alreadyEncrypted), listOf("local-model"), emptyMap(), emptyMap())
        assertEquals("enc:v1:fixture:legacy-secret", normalized.first { it.providerId == "custom" }.encryptedApiKey)
        assertEquals("enc:v1:unchanged", normalized.first { it.providerId == "other" }.encryptedApiKey)
        val saved = guard.save(listOf(legacy, alreadyEncrypted), legacy, listOf("local-model"), emptyMap(), emptyMap(), emptyList())
        assertEquals("enc:v1:fixture:legacy-secret", saved.first { it.providerId == "custom" }.encryptedApiKey)
        assertEquals(listOf("legacy-secret", "legacy-secret", "legacy-secret"), encryptedInputs)
    }
}
