package app.inku.mobile.llm

import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.CoreIdentityJson
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class ProviderAdmissionCoreTest {
    private fun canonical(value: Any?): Any? = when (value) {
        is JSONObject -> value.keys().asSequence().associateWith { canonical(value.get(it)) }
        is JSONArray -> (0 until value.length()).map { canonical(value.get(it)) }
        is Number -> java.math.BigDecimal(value.toString()).stripTrailingZeros()
        else -> value
    }

    @Test fun sharedCasesUseTheActualJniCore() {
        val cases = JSONObject(File(System.getProperty("inku.providerAdmissionCases")).readText()).getJSONArray("cases")
        assertEquals(50, cases.length())
        for (index in 0 until cases.length()) {
            val row = cases.getJSONObject(index)
            val result = JSONObject(NativePipelineBridge.providerAdmission(CoreIdentityJson.encode(row.getJSONObject("request")).toByteArray())
                .toString(Charsets.UTF_8))
            assertEquals(row.getString("name"), canonical(row.getJSONObject("expected")), canonical(result))
        }
    }

    @Test fun sharedSequenceRetainsTheStateAcrossOperations() {
        val fixture = JSONObject(File(System.getProperty("inku.providerAdmissionSequence")).readText())
        val steps = fixture.getJSONArray("steps")
        var state = JSONObject().put("events", JSONArray()).put("day", "").put("daily", 0).put("not_before", 0)
        for (index in 0 until steps.length()) {
            val step = steps.getJSONObject(index)
            val action = step.getString("action")
            if (action != "advance") {
                val input = JSONObject().put("action", if (action == "reserve") "admit" else action)
                    .put("state", state).put("now", step.get("now")).put("kind", "gemini")
                    .put("limits", fixture.getJSONObject("limits"))
                when (action) {
                    "reserve" -> input.put("id", step.getString("id")).put("input_tokens", step.get("value"))
                    "settle" -> input.put("id", "id0").put("input_tokens", step.get("value"))
                    "pause" -> input.put("seconds", step.get("value"))
                }
                val answer = SharedProviderAdmission.call(input)
                val status = if (answer.optString("decision") == "wait") "wait:${answer.getDouble("seconds")}" else "ok"
                assertEquals("step $index", step.getString("status"), status)
                state = answer.getJSONObject("state")
            }
            val expected = JSONObject(step.getString("json"))
            assertEquals("state $index", canonical(expected), canonical(state))
            val encoded = CoreIdentityJson.encode(state)
            assertEquals("round trip $index", encoded, CoreIdentityJson.encode(JSONObject(encoded)))
            assertEquals("server bytes $index", step.getString("json"), encodeProviderRateState(state))
        }
    }

    @Test fun storedStateRoundTripsAndCorruptionIsRefused() {
        val request = JSONObject().put("action", "admit").put("now", 1790917200.0).put("kind", "gemini")
            .put("limits", JSONObject().put("rpm", 30).put("tpm", 16000).put("rpd", 14400))
            .put("input_tokens", 100).put("id", "fixture")
        val first = transitionStoredProviderRateState(null, request).getJSONObject("state")
        val stored = encodeProviderRateState(first)
        val second = transitionStoredProviderRateState(stored, JSONObject().put("action", "settle")
            .put("now", 1790917200.0).put("id", "fixture").put("input_tokens", 75))
        assertEquals(75, second.getJSONObject("state").getJSONArray("events").getJSONObject(0).getInt("tokens"))
        assertEquals("corrupt_state", transitionStoredProviderRateState("not-json", request).getString("error"))
        assertEquals("corrupt_state", transitionStoredProviderRateState("""{"events":"bad"}""", request).getString("error"))
    }
}
