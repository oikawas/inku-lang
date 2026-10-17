package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BatchRetryStateTest {
    private val conditions = BatchConditions(
        catalogId = "night",
        canvasAspect = "portrait",
        modelId = "provider:stage1",
        stage2ModelId = "provider:stage2",
        languageCode = "ja",
        renderWild = true,
    )
    private val snapshot = BatchSnapshot(
        text = "first\nsecond\nthird",
        lines = listOf(NumberedBatchLine(2, "first"), NumberedBatchLine(4, "second"), NumberedBatchLine(7, "third")),
        conditions = conditions,
    )

    @Test fun retryKeepsOriginalNumbersAndFrozenConditionsWhileExcludingSuccesses() {
        val retry = failedBatchLines(snapshot, listOf(
            BatchFailure(7, "third", "failed"),
            BatchFailure(4, "changed after the run", "stale"),
        ))
        assertEquals(listOf(NumberedBatchLine(7, "third")), retry)
        assertEquals(conditions, snapshot.conditions)
        assertEquals(listOf(2, 4, 7), snapshot.lines.map(NumberedBatchLine::number))
    }

    @Test fun automaticRetryStopsAtTheConfiguredBoundOrOnInterruption() {
        val failures = listOf(BatchFailure(7, "third", "failed"))
        assertFalse(batchRetryAllowed(failures, completedRounds = 0, limit = 0, interrupted = false))
        assertTrue(batchRetryAllowed(failures, completedRounds = 0, limit = 2, interrupted = false))
        assertTrue(batchRetryAllowed(failures, completedRounds = 1, limit = 2, interrupted = false))
        assertFalse(batchRetryAllowed(failures, completedRounds = 2, limit = 2, interrupted = false))
        assertFalse(batchRetryAllowed(failures, completedRounds = 0, limit = 2, interrupted = true))
        assertFalse(batchRetryAllowed(emptyList(), completedRounds = 0, limit = 5, interrupted = false))
        assertTrue(batchRetryAllowed(failures, completedRounds = 4, limit = 99, interrupted = false))
        assertFalse(batchRetryAllowed(failures, completedRounds = 5, limit = 99, interrupted = false))
        assertFalse(batchRetryAllowed(failures, completedRounds = 0, limit = -1, interrupted = false))
    }
}
