package app.inku.mobile.data.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class CanvasAspectsTest {
    @Test
    fun injectedRustRegistryOwnsNewPaperRatiosWhilePixel9RemainsReadOnlyLegacy() {
        installCanvasRegistryForJvmTest()

        assertEquals(
            listOf(
                "square",
                "golden",
                "a4",
                "b4",
                "pillar",
                "oban",
                "wide",
                "byobu",
                "vertical",
                "sd_monitor",
                "hd_monitor",
            ),
            CanvasAspects.all.map { it.id },
        )
        assertEquals("809:500", CanvasAspects.all.first { it.id == "golden" }.ratioLabel)
        assertEquals(1.8, CanvasAspects.ratioFor(CanvasAspects.LEGACY_PIXEL9_LANDSCAPE_SAFE_ID), 0.0)
        assertFalse(CanvasAspects.all.any { it.id == CanvasAspects.LEGACY_PIXEL9_LANDSCAPE_SAFE_ID })
        assertEquals(
            CanvasAspects.DEFAULT_ID,
            CanvasAspects.newSelectionOrDefault(CanvasAspects.LEGACY_PIXEL9_LANDSCAPE_SAFE_ID),
        )
    }
}
