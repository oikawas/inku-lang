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

    @Test
    fun pickerResultJoinsTheExistingOneTouchOwnerWithoutPersistingItsUri() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val start = viewModel.indexOf("fun onPhotoPickerResult")
        val end = viewModel.indexOf("fun retryCameraDevelopment", start)
        assertTrue("photo picker result owner must exist", start >= 0)
        assertTrue("photo picker result owner must be bounded", end > start)
        val boundary = viewModel.substring(start, end)

        assertTrue(boundary.contains("selectedImageFiles.importImage"))
        assertTrue(boundary.contains("runCameraInstantPrint"))
        assertTrue(boundary.contains("CameraInputOrigin.PhotoPicker"))
        assertTrue(boundary.contains("val uiLanguageCode = snapshot.uiLanguage.code"))
        assertFalse(boundary.contains("takePersistableUriPermission"))
        assertFalse(boundary.contains("persistSetting("))
    }

    @Test
    fun pickerNullRestoresBeforeAnyImageOrModelWork() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val start = viewModel.indexOf("fun onPhotoPickerResult")
        val nullResult = viewModel.indexOf("if (uri == null)", start)
        val runStart = viewModel.indexOf("cameraRunSerial += 1", nullResult)
        val branch = viewModel.substring(nullResult, runStart)

        assertTrue(branch.contains("restoreCameraComposeSnapshot()"))
        assertTrue(branch.contains("return"))
        assertFalse(branch.contains("importImage"))
        assertFalse(branch.contains("runCameraInstantPrint"))
    }

    @Test
    fun pickerUsesTheSamePreflightAndANonReplayingRequestFlow() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val start = viewModel.indexOf("private fun startCameraCapture()")
        val end = viewModel.indexOf("fun onCameraCaptureResult", start)
        val preflight = viewModel.substring(start, end)

        assertTrue(preflight.indexOf("repository.isLocalVisionModelReady()") < preflight.indexOf("mutablePhotoPickerRequests.emit(Unit)"))
        assertTrue(preflight.indexOf("cameraNimProviderIssue(cameraProviders)") < preflight.indexOf("mutablePhotoPickerRequests.emit(Unit)"))
        assertTrue(viewModel.contains("MutableSharedFlow<Unit>(extraBufferCapacity = 1)"))
        assertFalse(viewModel.contains("MutableSharedFlow<Unit>(replay ="))
    }

    @Test
    fun sourceChooserAndPickerWaitAreExplicitNonProcessingStates() {
        val state = projectFile("app/src/main/java/app/inku/mobile/ui/camera/CameraCaptureState.kt").readText()
        assertTrue(state.contains("ChoosingSource"))
        assertTrue(state.contains("PickingPhoto"))
        val lockBoundary = state.substring(state.indexOf("internal val CameraCaptureState.locksCameraInteraction"))
        assertFalse(lockBoundary.contains("CameraCaptureState.ChoosingSource,"))
        assertFalse(lockBoundary.contains("CameraCaptureState.PickingPhoto,"))
    }

    // SPEC: the camera button goes to the camera without asking for an input
    // source or confirming the overwrite of what is on the studio.
    @Test
    fun cameraRequestGoesStraightToTheCapture() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val request = viewModel.substring(
            viewModel.indexOf("fun requestCameraCapture()"),
            viewModel.indexOf("private fun canRequestCameraInput"),
        )

        assertTrue(request.contains("beginCameraInput(CameraInputSource.Camera, confirmOverwrite = false)"))
        assertFalse(request.contains("CameraCaptureState.ChoosingSource"))
    }
}
