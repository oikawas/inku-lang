package app.inku.mobile.ui.camera

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraDevelopmentPresentationTest {
    @Test
    fun realPhasesMapToTheExactJapaneseAndEnglishDevelopmentWords() {
        val cases = listOf(
            CameraCaptureState.PreparingImage to Triple("光を読み取っています", "Reading the light", CameraDevelopmentEffect.PaperExposure),
            CameraCaptureState.LoadingLocalModel to Triple("光を読み取っています", "Reading the light", CameraDevelopmentEffect.PaperExposure),
            CameraCaptureState.AnalyzingLocally to Triple("光を読み取っています", "Reading the light", CameraDevelopmentEffect.PaperExposure),
            CameraCaptureState.InterpretingWithNim to Triple("かたちを起こしています", "Bringing out the forms", CameraDevelopmentEffect.GrainAndForms),
            CameraCaptureState.ComposingWithNim to Triple("色と配置を定着させています", "Fixing color and placement", CameraDevelopmentEffect.VividColorFields),
            CameraCaptureState.Rendering to Triple("現像しています", "Developing", CameraDevelopmentEffect.OutlineSettling),
            CameraCaptureState.Saving to Triple("現像しています", "Developing", CameraDevelopmentEffect.OutlineSettling),
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
    fun animationScaleZeroUsesStaticStagesAndImmediateReveal() {
        val static = cameraDevelopmentPresentation(
            CameraCaptureState.ComposingWithNim,
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
            CameraCaptureState.Failed(CameraFailure.NimFailed, canRetryNim = true),
            isJapanese = false,
            animationsEnabled = true,
        ) ?: error("NIM failure presentation missing")
        val local = cameraDevelopmentPresentation(
            CameraCaptureState.Failed(CameraFailure.AnalysisFailed),
            isJapanese = false,
            animationsEnabled = true,
        ) ?: error("local failure presentation missing")
        val direct = cameraDevelopmentPresentation(
            CameraCaptureState.Failed(CameraFailure.NimFailedDirectDdl, canRetryNim = true),
            isJapanese = false,
            animationsEnabled = true,
        ) ?: error("direct DDL NIM failure presentation missing")

        assertTrue(nim.showRetry)
        assertTrue(direct.showRetry)
        assertEquals(CameraDevelopmentEffect.OutlineSettling, direct.effect)
        assertTrue(nim.showCancel)
        assertFalse(local.showRetry)
        assertTrue(local.showCancel)
    }
}
