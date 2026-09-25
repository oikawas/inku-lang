package app.inku.mobile.ui.camera

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraDevelopmentPresentationTest {
    @Test
    fun realPhasesMapToTheExactJapaneseAndEnglishDevelopmentWords() {
        val cases = listOf(
            CameraCaptureState.PreparingImage to Triple("写真を準備しています", "Preparing your photo", CameraDevelopmentEffect.PhotoPreparing),
            CameraCaptureState.LoadingLocalModel to Triple("写真を見る準備をしています", "Getting ready to examine your photo", CameraDevelopmentEffect.PhotoPreparing),
            CameraCaptureState.AnalyzingLocally to Triple("写真の内容を調べています", "Examining your photo", CameraDevelopmentEffect.PhotoReading),
            CameraCaptureState.InterpretingStage1 to Triple("絵の構図を考えています", "Planning the composition", CameraDevelopmentEffect.GrainAndForms),
            CameraCaptureState.Composing to Triple("色と形を組み立てています", "Building the colors and forms", CameraDevelopmentEffect.VividColorFields),
            CameraCaptureState.Rendering to Triple("絵を仕上げています", "Finishing the work", CameraDevelopmentEffect.OutlineSettling),
            CameraCaptureState.Saving to Triple("作品を保存しています", "Saving your work", CameraDevelopmentEffect.Saving),
            CameraCaptureState.Completed("history-id") to Triple("現像できました", "Developed", CameraDevelopmentEffect.FinalArtwork),
        )

        cases.forEach { (state, expected) ->
            val ja = cameraDevelopmentPresentation(state, isJapanese = true, animationsEnabled = true)
                ?: error("missing Japanese presentation for $state")
            val en = cameraDevelopmentPresentation(state, isJapanese = false, animationsEnabled = true)
                ?: error("missing English presentation for $state")
            assertEquals(expected.first, ja.message)
            assertEquals(expected.second, en.message)
            assertEquals(expected.third, ja.effect)
            assertTrue(ja.politeLiveRegion)
            assertFalse(ja.message.contains('%'))
            assertFalse(en.message.contains("ETA", ignoreCase = true))
        }
    }

    @Test
    fun originalPhotoControlsUseOneSetOfWordsPerLanguage() {
        assertEquals("元の写真", cameraOriginalPhotoWords(isJapanese = true).label)
        assertEquals("元の写真を拡大", cameraOriginalPhotoWords(isJapanese = true).enlarge)
        assertEquals("Original photo", cameraOriginalPhotoWords(isJapanese = false).label)
        assertEquals("Close", cameraOriginalPhotoWords(isJapanese = false).close)
    }

    @Test
    fun animationScaleZeroUsesStaticStagesAndImmediateReveal() {
        val static = cameraDevelopmentPresentation(
            CameraCaptureState.Composing,
            isJapanese = false,
            animationsEnabled = false,
        ) ?: error("presentation missing")

        assertFalse(static.animationsEnabled)
        assertTrue(static.showCancel)
        assertFalse(static.showRetry)
    }

    @Test
    fun onlyNimFailureOffersRetryAndAllFailuresCanBeCancelled() {
        val nim = cameraDevelopmentPresentation(
            CameraCaptureState.Failed(CameraFailure.DrawFailed, canRetryDraw = true),
            isJapanese = false,
            animationsEnabled = true,
        ) ?: error("NIM failure presentation missing")
        val local = cameraDevelopmentPresentation(
            CameraCaptureState.Failed(CameraFailure.AnalysisFailed),
            isJapanese = false,
            animationsEnabled = true,
        ) ?: error("local failure presentation missing")
        assertTrue(nim.showRetry)
        assertEquals(CameraDevelopmentEffect.OutlineSettling, nim.effect)
        assertTrue(nim.showCancel)
        assertFalse(local.showRetry)
        assertTrue(local.showCancel)

        val picker = cameraDevelopmentPresentation(
            CameraCaptureState.Failed(CameraFailure.PhotoPickerUnavailable),
            isJapanese = false,
            animationsEnabled = false,
        ) ?: error("Photo Picker failure presentation missing")
        assertEquals("Image processing failed", picker.message)
        assertFalse(picker.showRetry)
    }
}
