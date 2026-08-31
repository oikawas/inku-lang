package app.inku.mobile

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HeadlessFailureLogTest {
    @Test
    fun headlessLogSummaryRedactsSecretsAndPrivatePaths() {
        val secret = "headless-review-secret"
        val summary = headlessFailureLogMessage(
            runId = "review-run",
            error = IllegalStateException("Bearer $secret at /data/user/0/app.inku.mobile/files/model"),
        )

        assertFalse(summary.contains(secret))
        assertFalse(summary.contains("/data/user/0"))
        assertTrue(summary.contains("review-run"))
        assertTrue(summary.contains("IllegalStateException"))
    }
}
