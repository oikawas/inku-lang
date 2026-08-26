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
    fun cameraResultHandsTheLocalDescriptionToTheOneTouchOwner() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val cameraStart = viewModel.indexOf("fun onCameraCaptureResult")
        val cameraEnd = viewModel.indexOf("fun onCameraCaptureLaunchFailed", cameraStart)
        assertTrue("camera result owner must exist", cameraStart >= 0)
        assertTrue("camera result owner must be bounded", cameraEnd > cameraStart)
        val cameraBoundary = viewModel.substring(cameraStart, cameraEnd)

        assertTrue(cameraBoundary.contains("runCameraInstantPrint"))
        assertTrue(cameraBoundary.contains("analyzeLocalVision"))
        assertTrue(cameraBoundary.contains("val request = VisionAnalysisRequest("))
        assertTrue(cameraBoundary.contains("CameraInputProvenance.fromAnalysis(request, result)"))
        assertTrue(cameraBoundary.contains("description = result.text.trim()"))
        assertTrue(cameraBoundary.contains("prompt = input.description"))
        assertTrue(cameraBoundary.contains("repository.interpret("))
        assertTrue(cameraBoundary.contains("repository.composeFromDdl("))
        assertTrue(cameraBoundary.contains("beforeSave ="))
        assertTrue(cameraBoundary.contains("serial != cameraRunSerial"))
        assertFalse(cameraBoundary.contains("CameraCaptureState.ReadyToEdit"))
        assertFalse(cameraBoundary.contains("saveHistory("))
    }

    @Test
    fun cameraPreflightsLocalVisionAndFixedNimBeforeEmittingTheCaptureRequest() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val start = section(viewModel, "private fun startCameraCapture()", "fun onCameraCaptureResult")
        val localReady = start.indexOf("repository.isLocalVisionModelReady()")
        val providerReady = start.indexOf("cameraNimProviderIssue(cameraProviders)")
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

        assertTrue(draw.contains("CameraNimDrawRouting.forState(current.cameraCaptureState)"))
        assertTrue(draw.contains("validateModelsForRun(current, route)"))
        assertTrue(draw.contains("runSubmit(current, route)"))
        assertTrue(submit.contains("route?.stage1ModelId ?: current.selectedModelId"))
        assertTrue(submit.contains("route?.stage2ModelId ?: current.selectedStage2ModelId"))
        assertTrue(submit.contains("route?.catalogId ?:"))
        assertTrue(submit.contains("route?.autoRepair ?: current.ddlAutoRepairEnabled"))
        assertTrue(submit.contains("inputProvenance = route?.inputProvenance"))
        assertTrue(submit.contains("if (route == null) describeLineage(current) else LineageDeclaration()"))
        assertTrue(submit.contains("if (route == null) describeSketchInput(current) else SketchInput()"))
        assertFalse("camera snapshot must not persist or mutate normal selections", submit.contains("persistSetting("))
        listOf("selectedModelId", "selectedStage2ModelId", "selectedCatalogId", "sketchMode").forEach { field ->
            assertFalse("$field must not be assigned", Regex("$field\\s*=(?!=)").containsMatchIn(submit))
        }
    }

    @Test
    fun cameraOriginLifecyclePreservesRetryAndClearsAtExplicitBoundaries() {
        val viewModel = projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText()
        val setPrompt = section(viewModel, "fun setPrompt", "fun requestCameraCapture()")
        val clearPrompt = section(viewModel, "fun clearPrompt()", "fun setDdl")
        val history = section(viewModel, "private fun applyHistorySelection", "fun selectHistory(item: HistoryListItem)")
        val submit = section(viewModel, "private fun runSubmit", "fun drawFromDdl()")
        val success = section(submit, ".onSuccess", ".onFailure")
        val failure = submit.substring(submit.indexOf(".onFailure"))

        assertFalse("ordinary edits preserve camera origin", setPrompt.contains("cameraCaptureState ="))
        assertTrue(clearPrompt.contains("cameraCaptureState = localState.value.cameraCaptureState.clearCameraOrigin()"))
        assertTrue(history.contains("cameraCaptureState = localState.value.cameraCaptureState.clearCameraOrigin()"))
        assertTrue(success.contains("cameraCaptureState = if (route != null) CameraCaptureState.Idle"))
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
