package app.inku.mobile.ui.camera

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraCaptureStateTest {

    @Test
    fun captureStateDistinguishesEveryVisiblePhase() {
        var source = File("src/main/java/app/inku/mobile/ui/camera/CameraCaptureState.kt")
        if (!source.isFile) source = File("app/src/main/java/app/inku/mobile/ui/camera/CameraCaptureState.kt")
        assertTrue("CameraCaptureState.kt must exist", source.isFile)

        val text = source.readText()
        listOf(
            "AwaitingOverwriteConfirmation",
            "Capturing",
            "PreparingImage",
            "LoadingLocalModel",
            "AnalyzingLocally",
            "ReadyToEdit",
            "Failed",
            "Cancelled",
        ).forEach { state ->
            assertTrue("missing camera state $state", text.contains(state))
        }
    }
}
