package app.inku.mobile.llm

import app.inku.mobile.pipeline.PipelineModelSelection
import app.inku.mobile.pipeline.SingleAttemptModelEffectProvider
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/** Ports the 429 cool-down and slot cases of server `test_provider_rate_limits.py` / `provider_limits.py`. */
class ProviderAdmissionTest {
    private val start = 1_790_000_000_000L
    private var now = start
    private val waits = mutableListOf<Long>()
    private val admission = ProviderAdmission(clockMs = { now }, sleepMs = { waits += it; now += it })

    private fun gemini(status: Int, headers: Map<String, String> = emptyMap(), body: String = OK) =
        GeminiModelProvider("gemini", "https://generativelanguage.googleapis.com", "test-key") { url ->
            Answer(url, status, body, headers)
        }

    private suspend fun send(provider: ModelProvider, timeoutMs: Long = 120_000): ModelResponse =
        admission.admit(provider.providerId, timeoutMs) { provider.generate(REQUEST) }

    @Test
    fun retryAfterAndRetryInfoMakeTheNextRequestWaitTheLongerOfThem() = runBlocking {
        val refused = gemini(429, mapOf("Retry-After" to "65"), RETRY_INFO_90S)
        val error = assertThrows(ModelProviderHttpException::class.java) { runBlocking { send(refused) } }
        assertEquals("65", error.retryAfter)
        assertEquals(90.0, error.retryDelaySeconds!!, 0.0)
        assertEquals(emptyList<Long>(), waits)

        send(gemini(200))
        assertEquals(listOf(90_000L), waits)
        assertEquals(start + 90_000L, now)
        // The refusal's wait is spent; the next request goes at once.
        send(gemini(200))
        assertEquals(listOf(90_000L), waits)
    }

    @Test
    fun anHttpDateRetryAfterAndTheSixtyTwoSecondFloorAreBothHonoured() = runBlocking {
        val date = DateTimeFormatter.RFC_1123_DATE_TIME.format(Instant.ofEpochMilli(start + 100_000L).atOffset(ZoneOffset.UTC))
        assertThrows(ModelProviderHttpException::class.java) { runBlocking { send(gemini(429, mapOf("Retry-After" to date))) } }
        send(gemini(200))
        assertEquals(listOf(100_000L), waits)

        // A shorter Retry-After, or none at all, still waits the 62-second window.
        assertThrows(ModelProviderHttpException::class.java) { runBlocking { send(gemini(429, mapOf("Retry-After" to "30"))) } }
        send(gemini(200))
        assertThrows(ModelProviderHttpException::class.java) { runBlocking { send(gemini(429)) } }
        send(gemini(200))
        assertEquals(listOf(100_000L, 62_000L, 62_000L), waits)
    }

    @Test
    fun withoutARefusalNothingWaitsAndAnotherProvidersCoolDownIsNotShared() = runBlocking {
        send(gemini(200))
        assertThrows(ModelProviderHttpException::class.java) { runBlocking { send(gemini(429)) } }
        val other = object : ModelProvider {
            override val providerId = "nvidia"
            override suspend fun generate(request: ModelRequest) = ModelResponse("{}", request.modelId)
        }
        send(other)
        assertEquals(emptyList<Long>(), waits)
    }

    @Test
    fun aCoolDownLongerThanTheAttemptFailsRateLimitedWithoutSending() = runBlocking {
        assertThrows(ModelProviderHttpException::class.java) { runBlocking { send(gemini(429, mapOf("Retry-After" to "65"))) } }
        var sent = 0
        val provider = object : ModelProvider {
            override val providerId = "gemini"
            override suspend fun generate(request: ModelRequest): ModelResponse =
                admission.admit(providerId, request.timeoutMs) { sent++; ModelResponse("{}", request.modelId) }
        }
        val details = mutableListOf<String?>()
        val result = JSONObject(
            SingleAttemptModelEffectProvider(provider) { _, _, detail, _ -> details += detail }
                .perform(action(timeoutMs = 60_000).toString(), PipelineModelSelection("gemini:m", "gemini:m")),
        )
        assertEquals("rate_limited", result.getString("failure"))
        assertEquals(listOf<String?>("rate_limit_wait"), details)
        assertEquals(0, sent)
        assertEquals(emptyList<Long>(), waits)
    }

    @Test
    fun ollamaCloudTakesTwoRequestsAtOnceAndOthersAreNotHeld() = runBlocking {
        val real = ProviderAdmission()
        for ((providerId, expected) in listOf("ollama-cloud" to 2, "nvidia" to 3)) {
            var inFlight = 0
            var most = 0
            val gate = CompletableDeferred<Unit>()
            val calls = List(3) {
                async {
                    real.admit(providerId, 5_000) {
                        inFlight++
                        most = maxOf(most, inFlight)
                        gate.await()
                        inFlight--
                    }
                }
            }
            withTimeout(2_000) { while (inFlight < expected) delay(5) }
            delay(50)
            assertEquals(providerId, expected, inFlight)
            gate.complete(Unit)
            calls.awaitAll()
            assertEquals(providerId, expected, most)
        }
    }

    @Test
    fun waitingForAnOllamaCloudSlotPastTheAttemptIsATransportTimeout() = runBlocking {
        val real = ProviderAdmission()
        val gate = CompletableDeferred<Unit>()
        val held = List(2) { async { real.admit("ollama-cloud", 5_000) { gate.await() } } }
        delay(50)
        val started = System.nanoTime()
        val error = runCatching { real.admit("ollama-cloud", 100) { error("must not be sent") } }.exceptionOrNull()
        assertTrue(error.toString(), error is SocketTimeoutException)
        assertTrue((System.nanoTime() - started) / 1_000_000 >= 100)
        gate.complete(Unit)
        held.awaitAll()
        // The released slots are free again.
        assertEquals("sent", real.admit("ollama-cloud", 100) { "sent" })
    }

    private fun action(timeoutMs: Long) = JSONObject()
        .put("tag", "generate_normalized_ddl")
        .put("identity", JSONObject().put("action_id", "provider-1").put("attempt", 1).put("request_digest", "digest"))
        .put("timeout_ms", timeoutMs.toString())
        .put(
            "payload",
            JSONObject().put(
                "prompt",
                JSONObject()
                    .put("action_name", "generate_normalized_ddl")
                    .put("system", "system")
                    .put("message", "message")
                    .put("response_schema", JSONObject().put("type", "object")),
            ),
        )

    private companion object {
        const val OK = """{"candidates":[{"content":{"parts":[{"functionCall":{"name":"submit_pipeline_response","args":{"normalized_ddl":"same bytes"}}}]}}]}"""
        const val RETRY_INFO_90S = """{"error":{"status":"RESOURCE_EXHAUSTED","details":[{"@type":"type.googleapis.com/google.rpc.RetryInfo","retryDelay":"90s"}]}}"""
        val REQUEST = ModelRequest(
            modelId = "gemini:gemma-4-31b-it",
            prompt = "message",
            temperature = 0.0,
            maxTokens = 2048,
            systemInstruction = "system",
            tool = ModelTool("submit_pipeline_response", "Submit", """{"type":"object"}"""),
            pipelineAction = "generate_normalized_ddl",
        )
    }
}

private class Answer(
    url: URL,
    private val status: Int,
    private val answer: String,
    private val headers: Map<String, String>,
) : HttpURLConnection(url) {
    private val sent = ByteArrayOutputStream()
    override fun getOutputStream() = sent
    override fun getResponseCode() = status
    override fun getInputStream() = answer.byteInputStream()
    override fun getErrorStream() = answer.byteInputStream()
    override fun getHeaderField(name: String?): String? =
        headers.entries.firstOrNull { it.key.equals(name, ignoreCase = true) }?.value
    override fun connect() = Unit
    override fun disconnect() = Unit
    override fun usingProxy() = false
}
