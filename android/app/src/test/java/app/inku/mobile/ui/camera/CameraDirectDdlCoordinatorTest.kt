package app.inku.mobile.ui.camera

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class CameraDirectDdlCoordinatorTest {
    @Test
    fun directDdlSkipsInterpretationAndStartsComposition() = runBlocking {
        val phases = mutableListOf<CameraInstantPrintPhase>()
        var interpretations = 0
        var compositions = 0
        val coordinator = CameraInstantPrintCoordinator(onPhase = phases::add)

        val outcome = coordinator.run(
            route = CameraInstantPrintRoute.DirectDdl,
            prepare = { "prepared" },
            load = {},
            analyze = { "青い円を右上に置く。" },
            onLocalReady = {},
            interpret = { interpretations += 1; "must not run" },
            compose = { local, interpreted, progress ->
                compositions += 1
                assertEquals(null, interpreted)
                progress(CameraInstantPrintPhase.Rendering)
                progress(CameraInstantPrintPhase.Saving)
                local
            },
        )

        assertEquals("青い円を右上に置く。", outcome.result)
        assertEquals(0, interpretations)
        assertEquals(1, compositions)
        assertFalse(phases.contains(CameraInstantPrintPhase.InterpretingWithNim))
        assertEquals(CameraInstantPrintPhase.ComposingWithNim, phases[3])
    }

    @Test
    fun directDdlRetryStartsAtStageTwoWithoutLocalOrStageOne() = runBlocking {
        val phases = mutableListOf<CameraInstantPrintPhase>()
        var localCalls = 0
        var stageOneCalls = 0
        var stageTwoCalls = 0
        val coordinator = CameraInstantPrintCoordinator(onPhase = phases::add)

        val outcome = coordinator.runFromNim(
            route = CameraInstantPrintRoute.DirectDdl,
            local = "retained ddl",
            interpret = { stageOneCalls += 1; "must not run" },
            compose = { _, interpreted, _ ->
                stageTwoCalls += 1
                assertEquals(null, interpreted)
                "saved"
            },
        )

        assertEquals("saved", outcome.result)
        assertEquals(0, localCalls)
        assertEquals(0, stageOneCalls)
        assertEquals(1, stageTwoCalls)
        assertEquals(CameraInstantPrintPhase.ComposingWithNim, phases.first())
    }
}
