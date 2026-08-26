package app.inku.mobile.ui.camera

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraInstantPrintCoordinatorTest {
    @Test
    fun successRunsEveryRealStageOnceAndSavesOnce() = runBlocking {
        val phases = mutableListOf<CameraInstantPrintPhase>()
        var prepares = 0
        var loads = 0
        var analyses = 0
        var interpretations = 0
        var compositions = 0
        var saves = 0
        val coordinator = CameraInstantPrintCoordinator(onPhase = phases::add)

        val outcome = coordinator.run(
            prepare = { prepares += 1; "prepared" },
            load = { loads += 1 },
            analyze = { analyses += 1; "local description" },
            onLocalReady = {},
            interpret = { local -> interpretations += 1; "$local ddl" },
            compose = { _, _, progress ->
                compositions += 1
                progress(CameraInstantPrintPhase.Rendering)
                progress(CameraInstantPrintPhase.Saving)
                saves += 1
                "saved"
            },
        )

        assertEquals("saved", outcome.result)
        assertEquals(listOf(1, 1, 1, 1, 1, 1), listOf(prepares, loads, analyses, interpretations, compositions, saves))
        assertEquals(
            listOf(
                CameraInstantPrintPhase.PreparingImage,
                CameraInstantPrintPhase.LoadingLocalModel,
                CameraInstantPrintPhase.AnalyzingLocally,
                CameraInstantPrintPhase.InterpretingWithNim,
                CameraInstantPrintPhase.ComposingWithNim,
                CameraInstantPrintPhase.Rendering,
                CameraInstantPrintPhase.Saving,
                CameraInstantPrintPhase.Completed,
            ),
            phases,
        )
    }

    @Test
    fun cancellationAtEveryBlockingStagePreventsSave() = runBlocking {
        CameraInstantPrintPhase.entries
            .filterNot { it == CameraInstantPrintPhase.Completed }
            .forEach { blockedPhase ->
                val entered = CompletableDeferred<Unit>()
                val release = CompletableDeferred<Unit>()
                var saves = 0
                val coordinator = CameraInstantPrintCoordinator(
                    onPhase = { phase -> if (phase == blockedPhase) entered.complete(Unit) },
                )
                val job = launch {
                    coordinator.run(
                        prepare = { awaitIf(blockedPhase, CameraInstantPrintPhase.PreparingImage, release); "prepared" },
                        load = { awaitIf(blockedPhase, CameraInstantPrintPhase.LoadingLocalModel, release) },
                        analyze = { awaitIf(blockedPhase, CameraInstantPrintPhase.AnalyzingLocally, release); "local" },
                        onLocalReady = {},
                        interpret = {
                            awaitIf(blockedPhase, CameraInstantPrintPhase.InterpretingWithNim, release)
                            "ddl"
                        },
                        compose = { _, _, progress ->
                            awaitIf(blockedPhase, CameraInstantPrintPhase.ComposingWithNim, release)
                            progress(CameraInstantPrintPhase.Rendering)
                            awaitIf(blockedPhase, CameraInstantPrintPhase.Rendering, release)
                            progress(CameraInstantPrintPhase.Saving)
                            awaitIf(blockedPhase, CameraInstantPrintPhase.Saving, release)
                            saves += 1
                            "saved"
                        },
                    )
                }

                entered.await()
                job.cancelAndJoin()
                assertEquals("$blockedPhase must save nothing", 0, saves)
            }
    }

    @Test
    fun staleRunCannotAdvanceOrReturnAResult() = runBlocking {
        var current = true
        val phases = mutableListOf<CameraInstantPrintPhase>()
        val coordinator = CameraInstantPrintCoordinator(isCurrent = { current }, onPhase = phases::add)

        val failure = async {
            runCatching {
                coordinator.run(
                    prepare = { current = false; "prepared" },
                    load = {},
                    analyze = { "local" },
                    onLocalReady = {},
                    interpret = { "ddl" },
                    compose = { _, _, _ -> "saved" },
                )
            }.exceptionOrNull()
        }.await()

        assertTrue(failure is CancellationException)
        assertEquals(listOf(CameraInstantPrintPhase.PreparingImage), phases)
    }

    @Test
    fun nimRetryStartsAtStageOneWithoutRepeatingLocalVision() = runBlocking {
        val phases = mutableListOf<CameraInstantPrintPhase>()
        var localCalls = 0
        var stageOneCalls = 0
        val coordinator = CameraInstantPrintCoordinator(onPhase = phases::add)

        val outcome = coordinator.runFromNim(
            local = "retained local description",
            interpret = { stageOneCalls += 1; "ddl" },
            compose = { _, _, progress ->
                progress(CameraInstantPrintPhase.Rendering)
                progress(CameraInstantPrintPhase.Saving)
                "saved"
            },
        )

        assertEquals("saved", outcome.result)
        assertEquals(0, localCalls)
        assertEquals(1, stageOneCalls)
        assertEquals(CameraInstantPrintPhase.InterpretingWithNim, phases.first())
    }

    private suspend fun awaitIf(
        blocked: CameraInstantPrintPhase,
        current: CameraInstantPrintPhase,
        release: CompletableDeferred<Unit>,
    ) {
        if (blocked == current) release.await()
    }
}
