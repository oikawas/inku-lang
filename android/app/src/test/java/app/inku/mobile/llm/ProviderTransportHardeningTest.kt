package app.inku.mobile.llm

import app.inku.mobile.ui.i18n.InkuFailure
import java.net.HttpURLConnection
import java.net.URL
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Test

class ProviderTransportHardeningTest {
    @Test
    fun remoteBaseUrlRejectsCredentialsQueryFragmentsAndMissingHosts() {
        listOf(
            "https://identity@example.invalid/v1",
            "https://example.invalid/v1?mode=test",
            "https://example.invalid/v1#section",
            "https:///v1",
        ).forEach { baseUrl ->
            assertThrows(baseUrl, InkuFailure::class.java) {
                ProviderUrlValidator.validateRemoteBaseUrl(baseUrl)
            }
        }
    }

    @Test
    fun remoteBaseUrlStillAcceptsHttpsAndExactLoopbackHttp() {
        ProviderUrlValidator.validateRemoteBaseUrl("https://example.invalid/v1")
        ProviderUrlValidator.validateRemoteBaseUrl("http://localhost:11434/v1")
        ProviderUrlValidator.validateRemoteBaseUrl("http://127.0.0.1:8101/v3")
        ProviderUrlValidator.validateRemoteBaseUrl("http://[::1]:8101/v3")
    }

    @Test
    fun providerConnectionNeverFollowsRedirects() {
        val connection = StubHttpURLConnection()

        configureRemoteConnection(connection, method = "POST", apiKey = null)

        assertFalse(connection.instanceFollowRedirects)
    }
}

private class StubHttpURLConnection : HttpURLConnection(URL("https://example.invalid")) {
    override fun connect() = Unit
    override fun disconnect() = Unit
    override fun usingProxy(): Boolean = false
}
