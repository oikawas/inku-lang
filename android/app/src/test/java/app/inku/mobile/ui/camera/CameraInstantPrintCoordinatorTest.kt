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
        var descriptions = 0
        var interpretations = 0
        var compositions = 0
        var saves = 0
        val coordinator = CameraInstantPrintCoordinator(onPhase = phases::add)

        val outcome = coordinator.run(
            prepare = { prepares += 1; "prepared" },
            load = { loads += 1 },
            analyze = { analyses += 1; "photo observation" },
            writeDescription = { observation ->
                assertEquals("photo observation", observation)
                descriptions += 1
                "poetic description"
            },
            onLocalReady = { assertEquals("poetic description", it) },
            interpret = { local ->
                assertEquals("poetic description", local)
                interpretations += 1
                "$local ddl"
            },
            compose = { _, _, progress ->
                compositions += 1
                progress(CameraInstantPrintPhase.Rendering)
                progress(CameraInstantPrintPhase.Saving)
                saves += 1
                "saved"
            },
        )

        assertEquals("saved", outcome.result)
        assertEquals("poetic description", outcome.local)
        assertEquals(listOf(1, 1, 1, 1, 1, 1, 1), listOf(prepares, loads, analyses, descriptions, interpretations, compositions, saves))
        assertEquals(
            listOf(
                CameraInstantPrintPhase.PreparingImage,
                CameraInstantPrintPhase.LoadingLocalModel,
                CameraInstantPrintPhase.AnalyzingLocally,
                CameraInstantPrintPhase.WritingDescription,
                CameraInstantPrintPhase.InterpretingStage1,
                CameraInstantPrintPhase.Composing,
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
            .filterNot { it == CameraInstantPrintPhase.Completed || it == CameraInstantPrintPhase.WritingDescription }
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
                        writeDescription = { it },
                        onLocalReady = {},
                        interpret = {
                            awaitIf(blockedPhase, CameraInstantPrintPhase.InterpretingStage1, release)
                            "ddl"
                        },
                        compose = { _, _, progress ->
                            awaitIf(blockedPhase, CameraInstantPrintPhase.Composing, release)
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
                    writeDescription = { it },
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
    fun drawingRetryStartsFromTheRetainedPoeticDescription() = runBlocking {
        val phases = mutableListOf<CameraInstantPrintPhase>()
        var stageOneCalls = 0
        val coordinator = CameraInstantPrintCoordinator(onPhase = phases::add)

        val outcome = coordinator.runFromAnalysis(
            local = "retained poetic description",
            interpret = {
                assertEquals("retained poetic description", it)
                stageOneCalls += 1
                "ddl"
            },
            compose = { _, _, progress ->
                progress(CameraInstantPrintPhase.Rendering)
                progress(CameraInstantPrintPhase.Saving)
                "saved"
            },
        )

        assertEquals("saved", outcome.result)
        assertEquals(1, stageOneCalls)
        assertEquals(CameraInstantPrintPhase.InterpretingStage1, phases.first())
        assertTrue(CameraInstantPrintPhase.WritingDescription !in phases)
    }

    @Test
    fun cancellingTheDescriptionCallNeverReachesDrawingOrSave() = runBlocking {
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        var interpretations = 0
        var saves = 0
        val job = launch {
            CameraInstantPrintCoordinator(onPhase = {}).run(
                prepare = { "photo" },
                load = {},
                analyze = { "observation" },
                writeDescription = { entered.complete(Unit); release.await(); "description" },
                onLocalReady = {},
                interpret = { interpretations += 1; "ddl" },
                compose = { _, _, _ -> saves += 1; "saved" },
            )
        }
        entered.await()
        job.cancelAndJoin()
        assertEquals(0, interpretations)
        assertEquals(0, saves)
    }

    private suspend fun awaitIf(
        blocked: CameraInstantPrintPhase,
        current: CameraInstantPrintPhase,
        release: CompletableDeferred<Unit>,
    ) {
        if (blocked == current) release.await()
    }
}
