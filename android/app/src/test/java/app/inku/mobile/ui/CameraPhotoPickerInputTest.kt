package app.inku.mobile.ui

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraPhotoPickerInputTest {
    private fun projectFile(relative: String): File {
        val candidates = listOf(File(relative), File(relative.removePrefix("app/")), File("android", relative))
        return candidates.firstOrNull(File::isFile) ?: candidates.first()
    }

    // SPEC 2026-09-30: the only image input is a camera capture; neither the
    // Photo Picker nor the dialog that chose between the two is shown.
    @Test
    fun cameraEntryTakesAPhotoWithoutASourceChooserOrStoragePermission() {
        val app = projectFile("app/src/main/java/app/inku/mobile/ui/InkuApp.kt").readText()
        val manifest = projectFile("app/src/main/AndroidManifest.xml").readText()

        assertTrue(app.contains("ActivityResultContracts.TakePicture"))
        assertFalse(app.contains("CameraInputSourceDialog"))
        assertFalse(app.contains("ActivityResultContracts.PickVisualMedia"))
        assertFalse(app.contains("photoPickerRequests"))
        assertFalse(manifest.contains("READ_MEDIA_IMAGES"))
        assertFalse(manifest.contains("READ_EXTERNAL_STORAGE"))
        assertFalse(manifest.contains("WRITE_EXTERNAL_STORAGE"))
    }

    // SPEC: the camera button goes to the camera without asking for an input
    // source or confirming the overwrite of what is on the studio.
    @Test
    fun cameraRequestGoesStraightToTheCapture() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val begin = viewModel.substring(
            viewModel.indexOf("private fun beginCameraInput()"),
            viewModel.indexOf("private fun startCameraCapture()"),
        )

        assertTrue(begin.contains("startCameraCapture()"))
        // The picker, the source chooser and the overwrite question were
        // removed with their screens; nothing in the view model waits on them.
        for (gone in listOf("onPhotoPickerResult", "photoPickerRequests", "ChoosingSource", "PickingPhoto", "AwaitingOverwriteConfirmation")) {
            assertFalse("$gone is still in the view model", viewModel.contains(gone))
        }
    }
}
