package app.inku.mobile.ui

import java.io.File
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.yield
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelDownloadCancellationGuardTest {
    @Test
    fun cancellingDownloadRemainsInFlightUntilItsCleanupCompletes() = runBlocking {
        val cleanupStarted = CompletableDeferred<Unit>()
        val releaseCleanup = CompletableDeferred<Unit>()
        val job = launch {
            try {
                awaitCancellation()
            } finally {
                withContext(NonCancellable) {
                    cleanupStarted.complete(Unit)
                    releaseCleanup.await()
                }
            }
        }
        yield()

        job.cancel()
        cleanupStarted.await()
        assertTrue(modelDownloadInFlight(job))
        releaseCleanup.complete(Unit)
        job.join()
        assertFalse(modelDownloadInFlight(job))
    }

    @Test
    fun cancelActionKeepsJobOwnershipUntilCompletion() {
        var source = File("src/main/java/app/inku/mobile/ui/InkuViewModel.kt")
        if (!source.isFile) source = File("app/src/main/java/app/inku/mobile/ui/InkuViewModel.kt")
        val cancelBody = source.readText()
            .substringAfter("fun cancelModelDownload() {")
            .substringBefore("\n    fun toggleStar")

        assertFalse(cancelBody.contains("modelDownloadJob = null"))
    }
}
