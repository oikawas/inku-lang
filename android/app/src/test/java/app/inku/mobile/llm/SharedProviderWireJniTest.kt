package app.inku.mobile.llm

import app.inku.mobile.pipeline.CoreIdentityJson
import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Every Server wire case reaches the same core through Android's real host JNI. */
class SharedProviderWireJniTest {
    private data class WireCase(val row: JSONObject, val requestJson: String)

    private val fixture: File by lazy {
        val identityCases = File(requireNotNull(System.getProperty("inku.identityCases")))
        identityCases.resolveSibling("provider-wire-cases.json")
    }

    /** Each generated fixture row occupies one line; retain its request's original member order. */
    private val cases: Map<String, List<WireCase>> by lazy {
        val groups = mutableMapOf<String, MutableList<WireCase>>()
        var section = ""
        for (line in fixture.readLines()) {
            val text = line.trim().removeSuffix(",")
            if (text.startsWith("\"requests\": [")) section = "requests"
            if (text.startsWith("\"text_requests\": [")) section = "text_requests"
            if (text.startsWith("\"responses\": [")) section = "responses"
            if (!text.startsWith("{\"why\":")) continue
            val start = text.indexOf(",\"request\":") + ",\"request\":".length
            val end = text.lastIndexOf(",\"expect\":")
            require(start >= ",\"request\":".length && end > start) { "fixture row shape changed" }
            groups.getOrPut(section) { mutableListOf() } += WireCase(JSONObject(text), text.substring(start, end))
        }
        groups
    }

    private fun sameJson(label: String, expected: Any, actual: Any) {
        assertEquals(label, CoreIdentityJson.canonical(expected), CoreIdentityJson.canonical(actual))
    }

    private fun requests(section: String, count: Int) {
        val rows = requireNotNull(cases[section])
        assertEquals(count, rows.size)
        for ((index, item) in rows.withIndex()) {
            val row = item.row
            val why = "$section[$index] ${row.getString("why")}"
            val request = row.getJSONObject("request")
            val expected = row.getJSONObject("expect")
            val answer = SharedProviderWire.call(item.requestJson)
            assertEquals(why, SharedProviderWire.SCHEMA, answer.getString("schema"))
            assertEquals(why, expected.getString("outcome"), answer.getString("outcome"))
            if (expected.getString("outcome") == "refused") {
                assertEquals(why, expected.getString("reason"), answer.getString("reason"))
                assertEquals(why, expected.getString("detail"), answer.getString("detail"))
                continue
            }
            assertEquals("$why url", expected.getString("url"), answer.getString("url"))
            assertEquals("$why exact body bytes", expected.getString("body"), answer.getString("body"))

            val headers = JSONObject(answer.getJSONObject("headers").toString())
            val auth = answer.getJSONObject("auth")
            val authHeader = auth.getString("header")
            assertFalse("$why auth header", authHeader.isBlank())
            val keyValue = auth.getString("prefix") + "KEY"
            headers.put(authHeader, keyValue)
            val lowered = JSONObject()
            for (name in headers.keys().asSequence()) lowered.put(name.lowercase(), headers.getString(name))
            sameJson("$why sent headers with KEY", expected.getJSONObject("headers"), lowered)
            if (authHeader.equals("authorization", ignoreCase = true)) {
                assertEquals("$why auth prefix", "Bearer ", auth.getString("prefix"))
                assertEquals("$why missing key", "none", auth.getString("missing"))
            } else {
                assertEquals("$why auth prefix", "", auth.getString("prefix"))
                assertEquals("$why missing key", "", auth.getString("missing"))
            }

            val body = JSONObject(expected.getString("body"))
            val budget: Any = if (answer.getString("format") == "gemini") {
                body.getJSONObject("generationConfig").get("maxOutputTokens")
            } else {
                listOf("max_tokens", "max_completion_tokens", "max_output_tokens")
                    .firstNotNullOfOrNull { key -> body.opt(key) }
                    ?: JSONObject.NULL
            }
            sameJson("$why output budget", budget, answer.get("output_budget"))

            if (request.getString("action") == "pipeline_request" && answer.getString("format") == "gemini") {
                val counter = answer.getJSONObject("count_tokens")
                assertEquals("$why countTokens URL", answer.getString("url").removeSuffix(":generateContent") + ":countTokens",
                    counter.getString("url"))
                val bodyText = expected.getString("body")
                val model = JSONObject.quote("models/${request.getString("model")}")
                val fields = bodyText.substring(1, bodyText.length - 1)
                val countBody = "{\"generateContentRequest\":{\"model\":$model" +
                    (if (fields.isEmpty()) "" else ",$fields") + "}}"
                assertEquals("$why countTokens exact body", countBody, counter.getString("body"))
            } else {
                assertFalse("$why no countTokens", answer.has("count_tokens"))
            }
        }
    }

    @Test
    fun allPipelineRequestsMatchServerWireBytes() = requests("requests", 246)

    @Test
    fun allTextRequestsMatchServerWireBytes() = requests("text_requests", 81)

    /** Server passes a `models/` Gemini name to the core unchanged; Android's send path must too. */
    @Test
    fun androidSendsModelsPrefixedGeminiNamesUnchanged() {
        val rows = requireNotNull(cases["requests"]).filter { item ->
            val request = item.row.getJSONObject("request")
            request.getJSONObject("connection").getString("kind") == "gemini" &&
                request.getString("model").startsWith("models/")
        }
        assertEquals(2, rows.size)
        for (item in rows) {
            val request = item.row.getJSONObject("request")
            val prompt = request.getJSONObject("prompt")
            val expected = item.row.getJSONObject("expect")
            val why = item.row.getString("why")
            val start = item.requestJson.indexOf("\"response_schema\":") + "\"response_schema\":".length
            val end = item.requestJson.indexOf(",\"system\":", start)
            require(start >= "\"response_schema\":".length && end > start) { "fixture prompt shape changed" }
            val modelRequest = ModelRequest(
                modelId = "gemini:${request.getString("model")}",
                prompt = prompt.getString("message"),
                temperature = 0.0,
                maxTokens = request.getInt("max_tokens"),
                systemInstruction = prompt.getString("system"),
                tool = ModelTool("submit_pipeline_response", "Submit the requested pipeline response.",
                    item.requestJson.substring(start, end)),
                pipelineAction = prompt.getString("action_name"),
            )
            val built = ProviderWireTransport.build("gemini", "gemini",
                request.getJSONObject("connection").getString("base_url"), modelRequest)
            assertEquals("$why url", expected.getString("url"), built.getString("url"))
            assertEquals("$why exact body bytes", expected.getString("body"), built.getString("body"))
        }
    }

    @Test
    fun allResponsesMatchServerOutcomes() {
        val rows = requireNotNull(cases["responses"])
        assertEquals(97, rows.size)
        for ((index, item) in rows.withIndex()) {
            val row = item.row
            val why = "responses[$index] ${row.getString("why")}"
            val expected = row.getJSONObject("expect")
            val answer = SharedProviderWire.call(item.requestJson)
            assertEquals(why, SharedProviderWire.SCHEMA, answer.getString("schema"))
            for (key in expected.keys().asSequence()) {
                assertTrue("$why missing $key", answer.has(key))
                sameJson("$why $key", expected.get(key), answer.get(key))
            }
        }
    }

    @Test
    fun malformedBoundaryFailsClosedWithoutInventingAnHttpRequest() {
        val invalid = SharedProviderWire.call(JSONObject().put("action", "send"))
        assertEquals("refused", invalid.getString("outcome"))
        assertEquals("invalid_request", invalid.getString("reason"))
        assertNotNull(invalid.getString("detail"))
    }
}
