package app.inku.mobile.ui

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraLocalDescriptionWiringTest {

    private fun projectFile(relative: String): File {
        val candidates = listOf(
            File(relative),
            File(relative.removePrefix("app/")),
            File("android", relative),
        )
        return candidates.firstOrNull(File::isFile) ?: candidates.first()
    }

    @Test
    fun cameraUsesTakePictureAndARestrictedCachePath() {
        val app = projectFile("app/src/main/java/app/inku/mobile/ui/InkuApp.kt").readText()
        val paths = projectFile("app/src/main/res/xml/file_paths.xml").readText()
        val manifest = projectFile("app/src/main/AndroidManifest.xml").readText()

        assertTrue(app.contains("ActivityResultContracts.TakePicture"))
        assertTrue(app.contains("rememberLauncherForActivityResult"))
        assertFalse(app.contains("MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA"))
        assertTrue(paths.contains("name=\"camera\""))
        assertTrue(paths.contains("path=\"camera/\""))
        assertFalse(manifest.contains("android.permission.CAMERA"))
        assertFalse(manifest.contains("READ_MEDIA_IMAGES"))
        assertFalse(manifest.contains("WRITE_EXTERNAL_STORAGE"))
    }

    @Test
    fun cameraResultStopsAtTheEditableDescriptionBoundary() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val cameraStart = viewModel.indexOf("fun onCameraCaptureResult")
        val cameraEnd = viewModel.indexOf("fun onCameraCaptureLaunchFailed", cameraStart)
        assertTrue("camera result owner must exist", cameraStart >= 0)
        assertTrue("camera result owner must be bounded", cameraEnd > cameraStart)
        val cameraBoundary = viewModel.substring(cameraStart, cameraEnd)

        assertTrue(cameraBoundary.contains("analyzeLocalVision"))
        assertTrue(cameraBoundary.contains("prompt = result.text"))
        assertFalse(cameraBoundary.contains("repository.interpret("))
        assertFalse(cameraBoundary.contains("composeFromDdl("))
        assertFalse(cameraBoundary.contains("saveHistory("))
    }
}
