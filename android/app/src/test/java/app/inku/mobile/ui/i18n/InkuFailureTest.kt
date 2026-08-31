package app.inku.mobile.ui.i18n

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InkuFailureTest {
    @Test
    fun platformFailureTextIsRedactedBeforeDisplay() {
        val secret = "sk-review-secret"
        val message = safeErrorMessage(
            IllegalStateException("request failed with $secret at /data/user/0/app.inku.mobile/files/model"),
            fallback = "fallback",
        )

        assertFalse(message.contains(secret))
        assertFalse(message.contains("/data/user/0"))
        assertTrue(message.contains("[redacted]"))
    }

    @Test
    fun deferredWordingStillUsesTheSelectedLanguage() {
        val failure = InkuFailure { strings -> strings.errorBaseUrlInvalid }
        assertEquals(InkuStringsEn.errorBaseUrlInvalid, messageFor(failure, InkuStringsEn, "fallback"))
    }
}
