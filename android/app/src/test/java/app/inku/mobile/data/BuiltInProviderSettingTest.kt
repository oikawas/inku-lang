package app.inku.mobile.data

import app.inku.mobile.data.db.ProviderSettingEntity
import org.junit.Assert.assertEquals
import org.junit.Test

class BuiltInProviderSettingTest {
    @Test fun corePreservesAnEditedBuiltInAndEnforcesLocalIdentity() {
        val local = ProviderSettingEntity("local-litert-lm", "Local", "litert-lm", "https://example.test",
            null, "[\"local-model\"]", false, true, 1)
        val edited = ProviderSettingEntity("openai", "Edited", "gemini", "https://example.test/v1",
            "synthetic-key", "[\"custom-model\"]", false, false, 2)
        val result = ProviderSettingsCodec.normalize(listOf(local, edited), listOf("local-model"))
            .associateBy { it.providerId }
        assertEquals(edited, result.getValue("openai"))
        assertEquals("local://litert-lm", result.getValue("local-litert-lm").baseUrl)
        assertEquals(true, result.getValue("local-litert-lm").isEnabled)
    }
}
