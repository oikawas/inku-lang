package app.inku.mobile.ui

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraModelSelectionTest {
    @Test
    fun cameraAndDrawingHaveOneSelectionAndOnePersistedAuthority() {
        val viewModel = projectFile("ui/InkuViewModel.kt").readText()
        val app = projectFile("ui/InkuApp.kt").readText()
        val headless = projectFile("HeadlessRenderActivity.kt").readText()

        assertFalse(viewModel.contains("cameraVisionModelId"))
        assertFalse(viewModel.contains("CameraVisionModelSetting"))
        assertFalse(app.contains("setCameraVisionModel"))
        assertFalse(app.contains("selectCameraVisionModelForCapture"))
        assertFalse(headless.contains("CameraVisionModelSetting"))
        assertTrue(viewModel.contains("modelId = snapshot.selectedModelId"))
        assertTrue(viewModel.contains("modelId = observed.drawSettings.stage1ModelId"))
        assertTrue(viewModel.contains("cameraComposeSnapshot = cameraComposeSnapshot?.copy("))
        assertTrue(headless.contains("analyzeHeadlessImage(repository, outputDir, runId, stage1Model)"))
        assertFalse(viewModel.contains("camera_vision_output_mode"))
    }

    private fun projectFile(relative: String): File {
        val path = "src/main/java/app/inku/mobile/$relative"
        return listOf(File("app", path), File(path), File("android/app", path)).first(File::isFile)
    }
}
