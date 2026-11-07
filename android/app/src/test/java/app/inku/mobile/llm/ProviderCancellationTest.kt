package app.inku.mobile.llm

import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A stopped drawing cancels the provider call; the blocked read must end with
 * it rather than wait for the provider's answer or the read timeout.
 */
class ProviderCancellationTest {
    @Test
    fun cancellingAGenerateDisconnectsTheBlockedConnection() = runBlocking {
        val connection = BlockingConnection(URL("https://api.openai.com/v1/responses"))
        val provider = OpenAiCompatibleProvider("openai", "https://api.openai.com/v1", "test-only") { connection }
        val request = SchemaOrderFixtures.request("openai:fixture-model", "read_composition", SchemaOrderFixtures.reading)
        val call = async(Dispatchers.Default) { provider.generate(request) }
        assertTrue("the request reached the blocking read", connection.reading.await(5, TimeUnit.SECONDS))
        call.cancel()
        val ended = withTimeoutOrNull(5_000) { runCatching { call.await() } }
        connection.release()
        assertTrue("the cancelled call ended", ended != null)
        assertTrue("it ended as a cancellation", ended!!.exceptionOrNull() is CancellationException)
        assertTrue("the socket was disconnected", connection.disconnected)
    }
}

private class BlockingConnection(url: URL) : HttpURLConnection(url) {
    val reading = CountDownLatch(1)
    private val unblock = CountDownLatch(1)
    @Volatile var disconnected = false
    override fun getOutputStream() = ByteArrayOutputStream()
    override fun getResponseCode(): Int {
        reading.countDown()
        unblock.await(30, TimeUnit.SECONDS)
        throw IOException("socket closed")
    }
    fun release() = unblock.countDown()
    override fun connect() = Unit
    override fun disconnect() {
        disconnected = true
        unblock.countDown()
    }
    override fun usingProxy() = false
}
