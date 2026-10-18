package app.inku.mobile.ui

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The wiring behind the 2026-10-18 navigation review (ANDROID_SPEC). Each of
 * these was a path the screen could reach that ended somewhere the author did
 * not ask to go; the view model needs a device to run, so the wiring is read.
 */
class NavigationReviewWiringTest {
    private fun projectFile(relative: String): File {
        val candidates = listOf(File(relative), File(relative.removePrefix("app/")), File("android", relative))
        return candidates.firstOrNull(File::isFile) ?: candidates.first()
    }

    private val viewModel by lazy { projectFile("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt").readText() }

    private fun body(start: String, end: String): String {
        val from = viewModel.indexOf(start)
        val to = viewModel.indexOf(end, from)
        assertTrue("$start not found", from >= 0 && to > from)
        return viewModel.substring(from, to)
    }

    @Test
    fun aCandidateIsTheParentOnlyOfADrawingFromTheWorkItWasRefinedOutOf() {
        val swap = body("private suspend fun withPreviewParent", "fun acceptModelLicense()")
        assertTrue(swap.contains("if (!current.refinementOpen) return declaration"))
        assertTrue(swap.contains("if (declaration.parentNodeId != refinedFrom) return declaration"))
        val select = body("private fun applyHistorySelection", "private fun adoptSavedHistory")
        assertTrue(select.contains("refinementPreviewId = null"))
    }

    @Test
    fun movingToAnotherWorkDoesNotStopARunningDrawing() {
        val adjacent = body("private fun selectAdjacentHistory", "private fun showPresentationHistory")
        val guard = adjacent.indexOf("if (viewer.isRunning) return")
        // After the full screen opened from Works, which does not stop the run.
        assertTrue(guard > adjacent.indexOf("showPresentationHistory(viewer.presentationSequence[next])"))
        assertTrue(body("fun selectLatestHistory", "private fun selectAdjacentHistory").contains("if (viewer.isRunning) return"))
        assertTrue(body("fun selectLineageNode", "fun selectPreviousHistory").contains("if (localState.value.isRunning) return"))
    }

    @Test
    fun paintAsksBeforeReplacingInstructionsEditedByHand() {
        val draw = body("fun draw()", "fun cancelDdlOverwrite()")
        val ask = draw.indexOf("confirmDdlOverwrite = true")
        assertTrue(ask >= 0)
        assertTrue(ask < draw.indexOf("runSubmit(current, cameraProvenance)"))
    }

    @Test
    fun aBatchLineOrDemoCycleThePipelineStopsIsAFailureAndTheRunGoesOn() {
        val batch = body("private fun runBatchSnapshot", "private fun rememberBatchPrompt")
        assertFalse(batch.contains("presentPipelineInteraction(error)"))
        assertTrue(batch.contains("abandonPipelineInteraction(error)"))
        val demo = body("fun startDemo()", "fun stopDrawing()")
        assertFalse(demo.contains("presentPipelineInteraction(error)"))
        assertTrue(demo.contains("abandonPipelineInteraction(error)"))
    }

    @Test
    fun aStoppedCameraDrawingKeepsItsRetryAndThePhotoStaysWithItsOwnRun() {
        val camera = body("private suspend fun presentCameraPipelineStop", "private fun failCameraRun")
        assertTrue(camera.contains("failCameraRun(serial, CameraFailure.DrawFailed"))
        val resume = body("private fun continuePipeline", "fun declinePipelinePatch()")
        assertTrue(resume.contains("takeIf { view.executionId == cameraPipelineExecutionId }"))
    }

    @Test
    fun theCameraRefusesAChatGptModelBeforeTheShutter() {
        val start = body("private fun startCameraCapture()", "mutableCameraCaptureRequests.emit(")
        val refuse = start.indexOf("strings().cameraChatGptCannotReadPhoto")
        assertTrue(refuse >= 0)
        assertTrue(refuse < start.indexOf("CameraCaptureState.Capturing"))
    }

    @Test
    fun changeDescriptionOpensAnEditableDescription() {
        assertTrue(body("fun editWorkDescription", "fun editWorkInstructions").contains("descriptionForkRequested = true"))
    }

    @Test
    fun aStoppedChatGptCallIsACancellationNotATransportFailure() {
        val manager = projectFile("app/src/main/java/app/inku/mobile/llm/ChatGptPlanManager.kt").readText()
        val generate = manager.substring(manager.indexOf("override suspend fun generate"), manager.indexOf("private fun reportFailure"))
        assertTrue(generate.indexOf("if (!currentCoroutineContext().isActive) throw CancellationException") < generate.indexOf("reportFailure(ref, safe.code)"))
    }
}
