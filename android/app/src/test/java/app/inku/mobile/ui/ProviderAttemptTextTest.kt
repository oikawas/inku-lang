package app.inku.mobile.ui

import app.inku.mobile.pipeline.ProviderAttempt
import app.inku.mobile.ui.i18n.InkuStringsEn
import app.inku.mobile.ui.i18n.InkuStringsJa
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** What the running row makes of the core's attempt report (the Server review's W4). */
class ProviderAttemptTextTest {

    private fun report(json: String): ProviderAttempt? =
        ProviderAttempt.fromReport("run-1", json.encodeToByteArray())

    private fun attempt(number: Int): String =
        """{"provider_attempt":{"action":"generate_normalized_ddl","attempt":$number,""" +
            """"max_attempts":4,"delay_ms":"2000","timeout_ms":"120000"}}"""

    @Test
    fun aFirstAttemptIsAWaitAndALaterOneARetry() {
        val first = report(attempt(1))
        val second = report(attempt(2))

        assertEquals("応答待ち（1/4回目）", providerAttemptText(first, InkuStringsJa))
        assertEquals("再試行中（2/4回目）", providerAttemptText(second, InkuStringsJa))
        assertEquals("Retrying (try 2/4)", providerAttemptText(second, InkuStringsEn))
        assertEquals("the run it belongs to", "run-1", second?.executionId)
    }

    @Test
    fun noCallABrokenSnapshotOrAnUnreadableAnswerShowNothing() {
        assertNull(report("""{"provider_attempt":null}"""))
        assertNull(report("""{"error":"invalid_snapshot"}"""))
        assertNull(report("not json"))
        assertEquals("", providerAttemptText(null, InkuStringsJa))
    }
}
