package app.inku.mobile.ui

import app.inku.mobile.llm.CameraVisionModeSetting
import app.inku.mobile.llm.VisionOutputMode
import app.inku.mobile.ui.camera.CameraCaptureState
import app.inku.mobile.ui.camera.CameraFailure
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraVisionModeSettingTest {
    @Test
    fun settingRoundTripsAndFailsSafeToDescription() {
        assertEquals("{\"value\":\"ddl\"}", CameraVisionModeSetting.encode(VisionOutputMode.DDL))
        assertEquals(VisionOutputMode.DDL, CameraVisionModeSetting.decode("{\"value\":\"ddl\"}"))
        assertEquals(VisionOutputMode.DESCRIPTION, CameraVisionModeSetting.decode(null))
        assertEquals(VisionOutputMode.DESCRIPTION, CameraVisionModeSetting.decode(""))
        assertEquals(VisionOutputMode.DESCRIPTION, CameraVisionModeSetting.decode("{broken"))
        assertEquals(VisionOutputMode.DESCRIPTION, CameraVisionModeSetting.decode("{\"value\":\"future\"}"))
    }

    @Test
    fun settingsExposeBothModesAndRejectChangesDuringACameraRun() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val app = projectFile("app/src/main/java/app/inku/mobile/ui/InkuApp.kt").readText()
        val stringsJa = projectFile("app/src/main/java/app/inku/mobile/ui/i18n/InkuStringsJa.kt").readText()
        val stringsEn = projectFile("app/src/main/java/app/inku/mobile/ui/i18n/InkuStringsEn.kt").readText()

        assertTrue(viewModel.contains("fun setCameraVisionOutputMode"))
        assertTrue(viewModel.contains("cameraVisionModeChangeLocked"))
        assertTrue(app.contains("viewModel.setCameraVisionOutputMode"))
        assertTrue(stringsJa.contains("記述（推奨）"))
        assertTrue(stringsJa.contains("DDL直接（上級）"))
        assertTrue(stringsEn.contains("Description (recommended)"))
        assertTrue(stringsEn.contains("Direct DDL (advanced)"))

        assertTrue(cameraVisionModeChangeLocked(CameraCaptureState.AwaitingOverwriteConfirmation))
        assertTrue(cameraVisionModeChangeLocked(CameraCaptureState.Capturing))
        assertTrue(cameraVisionModeChangeLocked(CameraCaptureState.AnalyzingLocally))
        assertEquals(false, cameraVisionModeChangeLocked(CameraCaptureState.Idle))
        assertEquals(false, cameraVisionModeChangeLocked(CameraCaptureState.Completed("history")))
        assertEquals(false, cameraVisionModeChangeLocked(CameraCaptureState.Failed(CameraFailure.InvalidDdl)))
    }

    private fun projectFile(relative: String): File {
        val candidates = listOf(File(relative), File(relative.removePrefix("app/")), File("android", relative))
        return candidates.firstOrNull(File::isFile) ?: candidates.first()
    }
}
