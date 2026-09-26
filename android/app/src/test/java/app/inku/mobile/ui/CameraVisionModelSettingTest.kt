package app.inku.mobile.ui

import app.inku.mobile.llm.CameraVisionModelSetting
import app.inku.mobile.llm.LOCAL_VISION_MODEL_ID
import app.inku.mobile.ui.camera.CameraCaptureState
import app.inku.mobile.ui.camera.CameraFailure
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraVisionModelSettingTest {
    @Test
    fun settingRoundTripsAndFailsSafeToTheLocalModel() {
        val remote = "gemini:gemma-4-31b-it"
        assertEquals(remote, CameraVisionModelSetting.decode(CameraVisionModelSetting.encode(remote)))
        assertEquals(LOCAL_VISION_MODEL_ID, CameraVisionModelSetting.decode(null))
        assertEquals(LOCAL_VISION_MODEL_ID, CameraVisionModelSetting.decode(""))
        assertEquals(LOCAL_VISION_MODEL_ID, CameraVisionModelSetting.decode("{broken"))
        assertEquals(LOCAL_VISION_MODEL_ID, CameraVisionModelSetting.decode("{\"value\":\"no-provider\"}"))
        // Gemma 4 E4B is no longer offered; a device that chose it describes with E2B.
        assertEquals(LOCAL_VISION_MODEL_ID, CameraVisionModelSetting.decode(CameraVisionModelSetting.encode("local-litert-lm:gemma-4-e4b")))
    }

    /**
     * A photo always becomes a description. The direct-DDL mode and its stored
     * `camera_vision_output_mode` are no longer read, so a device that chose it
     * draws through the description route.
     */
    @Test
    fun settingsOfferNoDirectDdlModeAndRejectModelChangesDuringACameraRun() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val app = projectFile("app/src/main/java/app/inku/mobile/ui/InkuApp.kt").readText()
        val stringsJa = projectFile("app/src/main/java/app/inku/mobile/ui/i18n/InkuStringsJa.kt").readText()
        val stringsEn = projectFile("app/src/main/java/app/inku/mobile/ui/i18n/InkuStringsEn.kt").readText()

        assertFalse(viewModel.contains("camera_vision_output_mode"))
        assertFalse(viewModel.contains("setCameraVisionOutputMode"))
        assertFalse(app.contains("setCameraVisionOutputMode"))
        assertFalse(stringsJa.contains("DDL直接"))
        assertFalse(stringsEn.contains("Direct DDL"))
        assertTrue(viewModel.contains("cameraVisionModelChangeLocked"))

        assertTrue(cameraVisionModelChangeLocked(CameraCaptureState.AwaitingOverwriteConfirmation))
        assertTrue(cameraVisionModelChangeLocked(CameraCaptureState.Capturing))
        assertTrue(cameraVisionModelChangeLocked(CameraCaptureState.PickingPhoto))
        assertTrue(cameraVisionModelChangeLocked(CameraCaptureState.AnalyzingLocally))
        assertEquals(false, cameraVisionModelChangeLocked(CameraCaptureState.Idle))
        assertEquals(false, cameraVisionModelChangeLocked(CameraCaptureState.Completed("history")))
        assertEquals(false, cameraVisionModelChangeLocked(CameraCaptureState.Failed(CameraFailure.AnalysisFailed)))
    }

    private fun projectFile(relative: String): File {
        val candidates = listOf(File(relative), File(relative.removePrefix("app/")), File("android", relative))
        return candidates.firstOrNull(File::isFile) ?: candidates.first()
    }
}
