package app.inku.mobile.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RefinementProgressLaneTest {

    @Test
    fun testFourCandidatesStartWithOneRunningLane() {
        assertEquals(
            listOf(
                RefinementProgressLaneState.Running,
                RefinementProgressLaneState.Waiting,
                RefinementProgressLaneState.Waiting,
                RefinementProgressLaneState.Waiting,
            ),
            refinementProgressLanes(candidateCount = 4, completedCount = 0, busy = true),
        )
    }

    @Test
    fun testCompletedCandidatesAdvanceTheSingleRunningLane() {
        assertEquals(
            listOf(
                RefinementProgressLaneState.Done,
                RefinementProgressLaneState.Done,
                RefinementProgressLaneState.Running,
                RefinementProgressLaneState.Waiting,
            ),
            refinementProgressLanes(candidateCount = 4, completedCount = 2, busy = true),
        )
    }

    @Test
    fun testOneCandidateOrIdleHasNoLaneRow() {
        assertTrue(
            refinementProgressLanes(candidateCount = 1, completedCount = 0, busy = true).isEmpty(),
        )
        assertTrue(
            refinementProgressLanes(candidateCount = 4, completedCount = 2, busy = false).isEmpty(),
        )
    }
}
