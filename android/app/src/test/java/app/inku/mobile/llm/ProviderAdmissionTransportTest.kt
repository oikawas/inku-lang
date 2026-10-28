package app.inku.mobile.llm

import app.inku.mobile.data.catalogRequest
import app.inku.mobile.data.db.ProviderSettingEntity
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.assertThrows
import org.junit.Test

class ProviderAdmissionTransportTest {
    @Test fun stored429PauseSurvivesANewAdmissionInstance() = runBlocking {
        var raw: String? = null
        var now = 1_790_000_000_000L
        val waits = mutableListOf<Long>()
        val store = ProviderRateTransitions { _, request ->
            transitionStoredProviderRateState(raw, request).also { answer ->
                answer.optJSONObject("state")?.let { raw = encodeProviderRateState(it) }
            }
        }
        fun admission() = ProviderAdmission(store, { now }, { duration -> waits += duration; now += duration })
        assertThrows(ModelProviderHttpException::class.java) {
            runBlocking { admission().admit("openai", 120_000) { throw ModelProviderHttpException(429, "fixture") } }
        }
        assertEquals("sent", admission().admit("openai", 120_000) { "sent" })
        assertEquals(listOf(62_000L), waits)
    }

    @Test fun geminiTextRequestsAlsoGetTheCoreCountRequest() {
        val request = ModelRequest("gemini:model", "message", 0.3, 256, systemInstruction = "system")
        val built = ProviderWireTransport.build("gemini", "gemini", "https://example.test", request)
        val count = built.getJSONObject("count_tokens")
        assertTrue(count.getString("url").endsWith(":countTokens"))
        val body = JSONObject(built.getString("body"))
        val countBody = JSONObject(count.getString("body")).getJSONObject("generateContentRequest")
        assertEquals("models/model", countBody.getString("model"))
        assertEquals(body.getJSONArray("contents").toString(), countBody.getJSONArray("contents").toString())
        assertEquals(body.getJSONObject("systemInstruction").toString(), countBody.getJSONObject("systemInstruction").toString())
    }

    @Test fun geminiTextResponseCarriesItsUsageForSettlement() = runBlocking {
        val request = ModelRequest("gemini:model", "message", 0.3, 256)
        val response = ProviderWireTransport.generate("gemini", "gemini", "https://example.test", "fixture-key", { url ->
            object : HttpURLConnection(url) {
                override fun getOutputStream() = ByteArrayOutputStream()
                override fun getResponseCode() = 200
                override fun getInputStream() = """{"candidates":[{"content":{"parts":[{"text":"ok"}]}}],"usageMetadata":{"promptTokenCount":75}}""".byteInputStream()
                override fun connect() = Unit
                override fun disconnect() = Unit
                override fun usingProxy() = false
            }
        }, request)
        assertEquals("ok", response.text)
        assertEquals(75, response.promptTokens)
    }

    @Test fun limitsRejectOversizeAndCorruptStateWithoutSending() = runBlocking {
        val limits = catalogRequest("rate_limits", JSONObject().put("provider", "gemini")).getJSONObject("rate_limits")
        val effective = SharedProviderAdmission.call(JSONObject().put("action", "limits").put("limits", limits))
        assertEquals(27, effective.getInt("rpm"))
        assertEquals(14400, effective.getInt("tpm"))
        assertEquals(14400, limits.getInt("rpd"))
        var sent = false
        val transitions = ProviderRateTransitions { _, _ -> JSONObject().put("error", "corrupt_state") }
        val admission = ProviderAdmission(transitions)
        assertThrows(ProviderBudgetRejectedException::class.java) {
            runBlocking { admission.admit("gemini", "gemini", limits, 14401, 30_000) { sent = true } }
        }
        assertThrows(ProviderRateStateException::class.java) {
            runBlocking { admission.admit("gemini", "gemini", limits, 1, 30_000) { sent = true } }
        }
        assertEquals(false, sent)
    }

    @Test fun geminiCountPreservesJsonTypesForTheCore() = runBlocking {
        val provider = ProviderSettingEntity("gemini", "Gemini", "gemini", "https://example.test", "fixture-key", "[]", true, false, 0)
        val request = ModelRequest("gemini:model", "message", 0.0, 256, tool = ModelTool("submit", "Submit", """{"type":"object"}"""),
            pipelineAction = "generate_normalized_ddl")
        val limits = catalogRequest("rate_limits", JSONObject().put("provider", "gemini")).getJSONObject("rate_limits")
        fun open(body: String): (URL) -> HttpURLConnection = { url -> object : HttpURLConnection(url) {
            override fun getOutputStream() = ByteArrayOutputStream()
            override fun getResponseCode() = 200
            override fun getInputStream() = body.byteInputStream()
            override fun connect() = Unit
            override fun disconnect() = Unit
            override fun usingProxy() = false
        } }
        assertThrows(ProviderBudgetRejectedException::class.java) {
            runBlocking { ProviderWireTransport.estimate(provider, request, limits, open("""{"totalTokens":1.0}""")) }
        }
        assertThrows(ProviderBudgetRejectedException::class.java) {
            runBlocking { ProviderWireTransport.estimate(provider, request, limits, open("""{"totalTokens":true}""")) }
        }
        val large = assertThrows(ProviderBudgetRejectedException::class.java) {
            runBlocking { ProviderWireTransport.estimate(provider, request, limits, open("""{"totalTokens":18446744073709551615}""")) }
        }
        assertEquals("request exceeds the configured input-token budget", large.reason)
        assertThrows(MalformedProviderResponseException::class.java) {
            runBlocking { ProviderWireTransport.estimate(provider, request, limits, open("[]")) }
        }
        Unit
    }

    @Test fun geminiCountsThenSendsAndSettlesActualUsage() = runBlocking {
        val calls = mutableListOf<String>()
        var state = JSONObject().put("events", JSONArray()).put("day", "").put("daily", 0).put("not_before", 0)
        val transitions = ProviderRateTransitions { _, input ->
            calls += input.getString("action")
            SharedProviderAdmission.call(JSONObject(input.toString()).put("state", state)).also { answer ->
                answer.optJSONObject("state")?.let { state = it }
            }
        }
        val provider = ProviderSettingEntity("gemini", "Gemini", "gemini", "https://example.test", "fixture-key", "[]", true, false, 0)
        val request = ModelRequest("gemini:gemma-4-31b-it", "message", 0.0, 256, systemInstruction = "system",
            tool = ModelTool("submit_pipeline_response", "Submit", """{"type":"object"}"""), pipelineAction = "generate_normalized_ddl")
        val limits = catalogRequest("rate_limits", JSONObject().put("provider", "gemini")).getJSONObject("rate_limits")
        val open: (URL) -> HttpURLConnection = { url ->
            object : HttpURLConnection(url) {
                private val output = ByteArrayOutputStream()
                override fun getOutputStream() = output
                override fun getResponseCode() = 200
                override fun getInputStream(): java.io.InputStream {
                    calls += if (url.path.endsWith(":countTokens")) "count" else "send"
                    val response = if (url.path.endsWith(":countTokens")) """{"totalTokens":100}""" else
                        """{"candidates":[{"content":{"parts":[{"functionCall":{"name":"submit_pipeline_response","args":{"normalized_ddl":"ok"}}}]}}],"usageMetadata":{"promptTokenCount":75}}"""
                    return response.byteInputStream()
                }
                override fun connect() = Unit
                override fun disconnect() = Unit
                override fun usingProxy() = false
            }
        }
        val result = ProviderAdmission(transitions).admit("gemini", "gemini", limits, 30_000, {
            ProviderWireTransport.estimate(provider, request, limits, open).also { assertEquals(110L, it) }
        }) {
            ProviderWireTransport.generate("gemini", "gemini", "https://example.test", "fixture-key", open, request)
        }
        assertEquals(75, result.promptTokens)
        assertEquals(listOf("count", "admit", "send", "settle"), calls)
        assertEquals(75, state.getJSONArray("events").getJSONObject(0).getInt("tokens"))
        assertTrue(state.getInt("daily") == 1)
    }
}
