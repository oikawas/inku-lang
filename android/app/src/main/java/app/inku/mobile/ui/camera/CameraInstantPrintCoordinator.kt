package app.inku.mobile.ui.camera

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

internal enum class CameraInstantPrintPhase {
    PreparingImage,
    LoadingLocalModel,
    AnalyzingLocally,
    InterpretingStage1,
    Composing,
    Rendering,
    Saving,
    Completed,
}

internal data class CameraInstantPrintOutcome<Local, Result>(
    val local: Local,
    val result: Result,
)

/** Runs one capture through real processing boundaries without owning UI or persistence. */
internal class CameraInstantPrintCoordinator(
    /** False once a newer capture has replaced this one; the run then stops at its next step. */
    private val isCurrent: () -> Boolean = { true },
    private val onPhase: (CameraInstantPrintPhase) -> Unit,
) {
    suspend fun <Prepared, Local, Interpreted, Result> run(
        prepare: suspend () -> Prepared,
        load: suspend () -> Unit,
        analyze: suspend (Prepared) -> Local,
        onLocalReady: suspend (Local) -> Unit,
        interpret: suspend (Local) -> Interpreted,
        compose: suspend (
            Local,
            Interpreted,
            suspend (CameraInstantPrintPhase) -> Unit,
        ) -> Result,
    ): CameraInstantPrintOutcome<Local, Result> {
        emit(CameraInstantPrintPhase.PreparingImage)
        val prepared = prepare()
        ensureCurrent()
        emit(CameraInstantPrintPhase.LoadingLocalModel)
        load()
        ensureCurrent()
        emit(CameraInstantPrintPhase.AnalyzingLocally)
        val local = analyze(prepared)
        ensureCurrent()
        onLocalReady(local)
        ensureCurrent()
        return runFromAnalysis(local, interpret, compose)
    }

    suspend fun <Local, Interpreted, Result> runFromAnalysis(
        local: Local,
        interpret: suspend (Local) -> Interpreted,
        compose: suspend (
            Local,
            Interpreted,
            suspend (CameraInstantPrintPhase) -> Unit,
        ) -> Result,
    ): CameraInstantPrintOutcome<Local, Result> {
        emit(CameraInstantPrintPhase.InterpretingStage1)
        val interpreted = interpret(local)
        ensureCurrent()
        emit(CameraInstantPrintPhase.Composing)
        val result = compose(local, interpreted) { phase ->
            require(
                phase == CameraInstantPrintPhase.Rendering ||
                    phase == CameraInstantPrintPhase.Saving,
            ) { "Compose may report only rendering or saving." }
            emit(phase)
        }
        ensureCurrent()
        emit(CameraInstantPrintPhase.Completed)
        return CameraInstantPrintOutcome(local, result)
    }

    private suspend fun emit(phase: CameraInstantPrintPhase) {
        ensureCurrent()
        onPhase(phase)
        ensureCurrent()
    }

    private suspend fun ensureCurrent() {
        currentCoroutineContext().ensureActive()
        if (!isCurrent()) throw CancellationException("Camera run is stale.")
    }
}
