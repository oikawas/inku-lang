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
    fun cameraCapturesInAppWithTheSystemCameraAsFallbackInARestrictedCachePath() {
        val app = projectFile("app/src/main/java/app/inku/mobile/ui/InkuApp.kt").readText()
        val paths = projectFile("app/src/main/res/xml/file_paths.xml").readText()
        val manifest = projectFile("app/src/main/AndroidManifest.xml").readText()

        assertTrue(app.contains("InAppCameraCapture("))
        assertTrue(app.contains("ActivityResultContracts.RequestPermission()"))
        assertTrue(app.contains("ActivityResultContracts.TakePicture"))
        assertFalse(app.contains("MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA"))
        assertTrue(paths.contains("name=\"camera\""))
        assertTrue(paths.contains("path=\"camera/\""))
        assertTrue(manifest.contains("android.permission.CAMERA"))
        assertFalse(manifest.contains("READ_MEDIA_IMAGES"))
        assertFalse(manifest.contains("WRITE_EXTERNAL_STORAGE"))
    }

    @Test
    fun cameraResultHandsTheLocalDescriptionToTheOneTouchOwner() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val cameraStart = viewModel.indexOf("fun onCameraCaptureResult")
        val cameraEnd = viewModel.indexOf("fun onCameraCaptureLaunchFailed", cameraStart)
        assertTrue("camera result owner must exist", cameraStart >= 0)
        assertTrue("camera result owner must be bounded", cameraEnd > cameraStart)
        val cameraBoundary = viewModel.substring(cameraStart, cameraEnd)

        assertTrue(cameraBoundary.contains("runCameraInstantPrint"))
        assertTrue(cameraBoundary.contains("repository.analyzeVision(request)"))
        assertTrue(cameraBoundary.contains("val request = VisionAnalysisRequest("))
        assertTrue(cameraBoundary.contains("CameraInputProvenance.fromAnalysis(request, result, origin)"))
        // A photo always becomes a description that the normal Stage 1 plans from.
        assertFalse(cameraBoundary.contains("outputMode"))
        assertFalse(cameraBoundary.contains("directDdl"))
        assertTrue(cameraBoundary.contains("description = result.text.trim()"))
        assertTrue(cameraBoundary.contains("prompt = input.description"))
        assertTrue(cameraBoundary.contains("repository.interpret("))
        assertTrue(cameraBoundary.contains("repository.composeFromDdl("))
        assertTrue(cameraBoundary.contains("interpreted.ddlForDisplay"))
        assertTrue(cameraBoundary.contains("beforeSave ="))
        assertTrue(cameraBoundary.contains("serial != cameraRunSerial"))
        assertFalse(cameraBoundary.contains("CameraCaptureState.ReadyToEdit"))
        assertFalse(cameraBoundary.contains("saveHistory("))
    }

    @Test
    fun cameraPreflightsTheVisionAndDrawingModelsBeforeEmittingTheCaptureRequest() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val start = section(viewModel, "private fun startCameraCapture()", "fun onCameraCaptureResult")
        val localReady = start.indexOf("modelReadinessIssue(visionModelId, cameraProviders, cameraAssets)")
        val providerReady = start.indexOf("cameraDrawReadiness(snapshot, cameraProviders, cameraAssets)")
        val createFile = start.indexOf("cameraFiles.createPendingCapture()")
        val emit = start.indexOf("mutableCameraCaptureRequests.emit")

        assertTrue(localReady >= 0)
        assertTrue(providerReady > localReady)
        assertTrue(createFile > providerReady)
        assertTrue(emit > createFile)
    }

    @Test
    fun savingPhaseIsReportedBeforeTheFinalCancellationFenceAndTransaction() {
        val repository = projectFile("app/src/main/java/app/inku/mobile/data/InkuRepository.kt").readText()
        val compose = section(repository, "suspend fun composeFromDdl", "suspend fun generateDemoPrompt")
        val saving = compose.indexOf("onProgress(ComposeFromDdlProgress.Saving)")
        val fence = compose.indexOf("beforeSave()")
        val save = compose.indexOf("return saveResult(")

        assertTrue(saving >= 0)
        assertTrue(fence > saving)
        assertTrue(save > fence)
    }

    @Test
    fun developmentOverlayLetsChildControlsHandleInputBeforeBlockingBackground() {
        val app = projectFile("app/src/main/java/app/inku/mobile/ui/InkuApp.kt").readText()
        val surface = section(app, "private fun CameraDevelopmentSurface", "private fun CameraDevelopmentEffectCanvas")

        assertTrue(surface.contains("awaitPointerEvent(PointerEventPass.Final)"))
        assertFalse(surface.contains("awaitPointerEvent(PointerEventPass.Initial)"))
        assertTrue(surface.contains("onClick = viewModel::cancelCameraDevelopment"))
    }

    @Test
    fun cameraOriginOwnsOnlyTheExplicitDrawSnapshot() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val draw = section(viewModel, "fun draw()", "fun cancelDdlOverwrite()")
        val submit = section(viewModel, "private fun runSubmit", "fun drawFromDdl()")

        assertTrue(draw.contains("CameraDrawRouting.provenanceFor(current.cameraCaptureState)"))
        assertTrue(draw.contains("validateModelsForRun(current)"))
        assertTrue(draw.contains("runSubmit(current, cameraProvenance)"))
        assertTrue(submit.contains("val stage1ModelId = current.selectedModelId"))
        assertTrue(submit.contains("val stage2ModelId = current.selectedStage2ModelId"))
        assertTrue(submit.contains("inputProvenance = cameraProvenance"))
        assertTrue(submit.contains("cameraProvenance == null -> describeLineage(current)"))
        assertTrue(submit.contains("cameraProvenance == null -> describeSketchInput(current"))
        assertFalse("camera snapshot must not persist or mutate normal selections", submit.contains("persistSetting("))
        listOf("selectedModelId", "selectedStage2ModelId", "selectedCatalogId", "sketchMode").forEach { field ->
            assertFalse("$field must not be assigned", Regex("$field\\s*=(?!=)").containsMatchIn(submit))
        }
    }

    @Test
    fun cameraOriginLifecyclePreservesRetryAndClearsAtExplicitBoundaries() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val setPrompt = section(viewModel, "fun setPrompt", "fun startDescriptionVariation()")
        val clearPrompt = section(viewModel, "fun clearPrompt()", "fun setDdl")
        val history = section(viewModel, "private fun applyHistorySelection", "fun selectHistory(item: HistoryListItem)")
        val submit = section(viewModel, "private fun runSubmit", "fun drawFromDdl()")
        val success = section(submit, ".onSuccess", ".onFailure")
        val failure = submit.substring(submit.indexOf(".onFailure"))

        assertFalse("ordinary edits preserve camera origin", setPrompt.contains("cameraCaptureState ="))
        assertTrue(clearPrompt.contains("cameraCaptureState = localState.value.cameraCaptureState.clearCameraOrigin()"))
        assertTrue(history.contains("cameraCaptureState = current.cameraCaptureState.clearCameraOrigin()"))
        assertTrue(success.contains("cameraCaptureState = if (cameraProvenance != null) CameraCaptureState.Idle"))
        assertFalse("failure must preserve camera origin for retry", failure.contains("cameraCaptureState ="))
    }

    private fun section(source: String, start: String, end: String): String {
        val from = source.indexOf(start)
        assertTrue("missing source section beginning $start", from >= 0)
        val until = source.indexOf(end, from + start.length)
        assertTrue("missing source section ending $end", until > from)
        return source.substring(from, until)
    }
}
