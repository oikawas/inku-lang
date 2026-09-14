package app.inku.mobile.llm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalVisionDdlRequestContractTest {
    @Test
    fun descriptionPromptAndVersionRemainTheDefault() {
        assertEquals(VisionOutputMode.DESCRIPTION, CameraVisionModeSetting.decode(null))
        assertEquals("camera-description-v1", VisionPrompts.versionFor(VisionOutputMode.DESCRIPTION))
        assertTrue(VisionPrompts.forLanguage("ja").contains("2〜5文"))
        assertTrue(VisionPrompts.forLanguage("en").contains("two to five"))
    }
}
