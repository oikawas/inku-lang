package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MascotSettingsRemovalStage3Test {

    @Test
    fun t7_inkuUiStateReflectionVerification() {
        val fields = InkuUiState::class.java.declaredFields.map { it.name }

        assertFalse("showKiwi should be removed from InkuUiState", fields.contains("showKiwi"))
        assertFalse("showCrab should be removed from InkuUiState", fields.contains("showCrab"))
        assertTrue("mascotKind should exist in InkuUiState", fields.contains("mascotKind"))
    }

    @Test
    fun t8_mascotPersistenceKeyUniqueness() {
        assertEquals("mascot_kind", SETTING_KEY_MASCOT_KIND)
    }
}
