package app.inku.mobile.llm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class LocalModelDownloaderHardeningTest {
    @Test
    fun storageReservationCreditsOnlyTheCurrentPartialDownload() {
        assertEquals(4_000L, requiredAdditionalDownloadBytes(totalBytes = 5_000L, retainedPartBytes = 1_000L))
        assertEquals(5_000L, requiredAdditionalDownloadBytes(totalBytes = 5_000L, retainedPartBytes = 0L))
        assertEquals(0L, requiredAdditionalDownloadBytes(totalBytes = 5_000L, retainedPartBytes = 6_000L))
    }

    @Test
    fun partialResponseMustBeginAtTheRequestedResumeOffset() {
        assertEquals(10_000L, validatedPartialContentTotal("bytes 1000-9999/10000", expectedStart = 1_000L))
        assertThrows(IllegalStateException::class.java) {
            validatedPartialContentTotal("bytes 0-9999/10000", expectedStart = 1_000L)
        }
        assertThrows(IllegalStateException::class.java) {
            validatedPartialContentTotal(null, expectedStart = 1_000L)
        }
    }

    @Test
    fun responseMustFinishAtTheDeclaredTotalLength() {
        validateCompletedDownloadLength(expectedTotalBytes = 10_000L, actualDownloadedBytes = 10_000L)
        validateCompletedDownloadLength(expectedTotalBytes = null, actualDownloadedBytes = 9_000L)
        assertThrows(IllegalStateException::class.java) {
            validateCompletedDownloadLength(expectedTotalBytes = 10_000L, actualDownloadedBytes = 9_999L)
        }
        assertThrows(IllegalStateException::class.java) {
            validateCompletedDownloadLength(expectedTotalBytes = 10_000L, actualDownloadedBytes = 10_001L)
        }
    }
}
