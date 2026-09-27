package app.inku.mobile.llm

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SupportedModelsTest {
    @Test
    fun marksTheTwoVerifiedModelsWhetherOrNotTheIdNamesItsProvider() {
        assertTrue(SupportedModels.isSupported("local-litert-lm", "local-litert-lm:gemma-4-e2b"))
        assertTrue(SupportedModels.isSupported("gemini", "gemini:gemma-4-31b-it"))
        assertTrue(SupportedModels.isSupported("gemini", "gemma-4-31b-it"))
        assertFalse(SupportedModels.isSupported("gemini", "gemini-3.5-flash-lite"))
        assertFalse(SupportedModels.isSupported("nvidia", "google/gemma-4-31b-it"))
    }
}
