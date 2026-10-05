package app.inku.mobile.pipeline

import app.inku.mobile.llm.AnthropicModelProvider
import app.inku.mobile.llm.GeminiModelProvider
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.llm.OpenAiCompatibleProvider
import app.inku.mobile.ui.i18n.InkuFailure
import app.inku.mobile.ui.i18n.inkuError
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

/** The failure class the core receives decides whether it retries (server `pipeline_provider.py`). */
class ProviderFailureCodeTest {
    @Test
    fun aChatCompletionWithNullContentIsMalformedNotTheTextNull() = runBlocking {
        val provider = OpenAiCompatibleProvider("nvidia", NVIDIA_URL, "test-key") { url ->
            FixedConnection(url, """{"choices":[{"message":{"content":null}}]}""")
        }
        assertEquals("malformed_payload", failureOf(provider))
    }

    @Test
    fun geminiWithoutCandidatesIsMalformed() = runBlocking {
        val provider = GeminiModelProvider("gemini", GEMINI_URL, "test-key") { url ->
            FixedConnection(url, """{"candidates":[]}""")
        }
        assertEquals("malformed_payload", failureOf(provider))
    }

    @Test
    fun aConfigurationFailureIsRejectedSoTheCoreDoesNotRetryIt() = runBlocking {
        val provider = object : ModelProvider {
            override val providerId = "fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse = inkuError { it.errorBaseUrlInsecure }
        }
        assertEquals("provider_rejected", failureOf(provider))
    }

    @Test
    fun anUnparseableOpenAiCompatibleBaseUrlIsRejectedBeforeAnyConnection() = runBlocking {
        val provider = OpenAiCompatibleProvider("custom", "not a url", "test-key") { error("no connection expected") }
        assertEquals("provider_rejected", failureOf(provider))
    }

    @Test
    fun theObserverHearsTheCredentialsDetailOfAMissingKey() = runBlocking {
        val missing = InkuFailure("credentials_unavailable") { it.errorProviderApiKeyMissing("Gemini") }
        val provider = object : ModelProvider {
            override val providerId = "fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse = throw missing
        }
        val heard = mutableListOf<List<Any?>>()
        val adapter = SingleAttemptModelEffectProvider(provider) { actionId, failure, detail, cause ->
            heard += listOf(actionId, failure, detail, cause)
        }
        val result = JSONObject(adapter.perform(ACTION.toString(), MODELS))
        assertEquals("provider_rejected", result.getString("failure"))
        assertEquals(1, heard.size)
        assertEquals(listOf("provider-1", "provider_rejected", "credentials_unavailable"), heard.single().take(3))
        assertSame(missing, heard.single()[3])
    }

    @Test
    fun aSuccessBodyOneByteOverOneMebibyteIsRejectedByEveryTransport() = runBlocking {
        val answers = mapOf(
            "openai" to """{"choices":[{"message":{"tool_calls":[{"function":{"name":"submit_pipeline_response","arguments":"{}"}}]}}]}""",
            "gemini" to """{"candidates":[{"content":{"parts":[{"functionCall":{"name":"submit_pipeline_response","args":{}}}]}}]}""",
            "anthropic" to """{"content":[{"type":"tool_use","name":"submit_pipeline_response","input":{}}]}""",
        )
        fun transport(kind: String, size: Int): ModelProvider {
            val answer = answers.getValue(kind)
            val body = answer + " ".repeat(size - answer.length)
            val open = { url: URL -> FixedConnection(url, body) }
            return when (kind) {
                "openai" -> OpenAiCompatibleProvider("nvidia", NVIDIA_URL, "test-key", open)
                "gemini" -> GeminiModelProvider("gemini", GEMINI_URL, "test-key", open)
                else -> AnthropicModelProvider("anthropic", "https://api.anthropic.com", "test-key", open)
            }
        }
        for (kind in answers.keys) {
            assertEquals(kind, "sketch_generated", tagOf(transport(kind, 1_048_576)))
            assertEquals(kind, "provider_rejected", failureOf(transport(kind, 1_048_577)))
        }
    }

    private suspend fun tagOf(provider: ModelProvider): String =
        JSONObject(SingleAttemptModelEffectProvider(provider).perform(ACTION.toString(), MODELS)).getString("tag")

    private suspend fun failureOf(provider: ModelProvider): String =
        JSONObject(SingleAttemptModelEffectProvider(provider).perform(ACTION.toString(), MODELS)).getString("failure")

    private companion object {
        const val NVIDIA_URL = "https://integrate.api.nvidia.com/v1"
        const val GEMINI_URL = "https://generativelanguage.googleapis.com"
        val MODELS = PipelineModelSelection("stage1", "stage2")
        val ACTION: JSONObject = JSONObject()
            .put("tag", "generate_sketch")
            .put("identity", JSONObject().put("action_id", "provider-1").put("attempt", 1).put("request_digest", "digest"))
            .put("timeout_ms", "5000")
            .put(
                "payload",
                JSONObject().put(
                    "prompt",
                    JSONObject()
                        .put("action_name", "generate_sketch")
                        .put("system", "system")
                        .put("message", "message")
                        .put("response_schema", JSONObject().put("type", "object")),
                ),
            )
    }
}

private class FixedConnection(url: URL, private val answer: String, private val status: Int = 200) : HttpURLConnection(url) {
    private val sent = ByteArrayOutputStream()
    override fun getOutputStream() = sent
    override fun getResponseCode() = status
    override fun getInputStream() = answer.byteInputStream()
    override fun getErrorStream() = answer.byteInputStream()
    override fun connect() = Unit
    override fun disconnect() = Unit
    override fun usingProxy() = false
}
