package app.inku.mobile.llm

import app.inku.mobile.pipeline.CoreIdentityJson
import app.inku.mobile.pipeline.NativePipelineBridge
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ChatGptPolicyCoreTest {
    private fun canonical(value: Any?): Any? = when (value) {
        is JSONObject -> value.keys().asSequence().associateWith { canonical(value.get(it)) }
        is JSONArray -> (0 until value.length()).map { canonical(value.get(it)) }
        is Number -> java.math.BigDecimal(value.toString()).stripTrailingZeros()
        else -> value
    }

    @Test fun sharedPolicyCasesUseTheActualJniCore() {
        val directory = requireNotNull(File(requireNotNull(System.getProperty("inku.identityCases"))).parentFile)
        val wire = JSONObject(directory.resolve("provider-wire-cases.json").readText()).getJSONArray("chatgpt")
        val addendum = JSONArray(directory.resolve("chatgpt-auth-addendum-cases.json").readText())
        val rules = JSONArray(directory.resolve("chatgpt-auth-11-15-cases.json").readText())
        val rows = (0 until wire.length()).map { wire.getJSONObject(it) }
            .filter { it.getJSONObject("request").optString("schema") == "inku.model-catalog-request.v1" }
        assertEquals(21, rows.size)
        assertEquals(4, addendum.length())
        for (row in rows + (0 until addendum.length()).map { addendum.getJSONObject(it) } + (0 until rules.length()).map { rules.getJSONObject(it) }) {
            val request = row.getJSONObject("request").put("schema", "inku.model-catalog-request.v1")
            val result = JSONObject(NativePipelineBridge.modelCatalog(CoreIdentityJson.encode(request).toByteArray()).toString(Charsets.UTF_8))
            val expected = row.getJSONObject("expect")
            for (key in expected.keys()) {
                assertEquals(row.optString("why", row.optString("name")) + ": " + key,
                    canonical(expected.get(key)), canonical(result.get(key)))
            }
        }
    }

    @Test fun profileRoundTripPreservesAndroidTimeAndSecrets() {
        val profile = JSONObject().put("id", "fixture").put("generation", 7).put("state", "connected")
            .put("access_token", "test-access").put("refresh_token", "test-refresh")
            .put("expires_at", 1800000000001L).put("earliest_refresh_at", 123450000L)
            .put("catalog", JSONObject().put("expires_at", 123999000L).put("models", JSONArray()))
        val purposes = JSONObject().put("model", JSONArray().put("llm"))
        val core = ChatGptCore.toCore(profile, purposes)
        assertEquals("runtime", core.getString("refresh_owner"))
        assertEquals("1800000000.001", core.get("expires_at").toString())
        assertEquals(canonical(purposes), canonical(core.getJSONObject("model_purposes")))
        val restored = ChatGptCore.fromCore(core).apply { remove("model_purposes") }
        // Step 5: what the core is given is kept as saved. A registration saved
        // before step 5 had neither field; it is given Android's own (the runtime refreshes, at the core's issuer).
        val legacy = JSONObject(profile.toString()).put("refresh_owner", "runtime").put("issuer", "https://auth.openai.com")
        assertEquals(canonical(legacy), canonical(restored))
        assertEquals("exported", ChatGptCore.toCore(JSONObject(profile.toString()).put("refresh_owner", "exported")).getString("refresh_owner"))
        // The id token kept for `id_token_hint` after sign-out goes through both ways and the store's shape.
        val signedOut = JSONObject(profile.toString()).put("sub", "person").put("retained_id_token", "kept-token")
        assertEquals("kept-token", ChatGptCore.fromCore(ChatGptCore.toCore(signedOut)).getString("retained_id_token"))
        val store = JSONObject().put("profiles", JSONObject().put("fixture", signedOut))
        assertEquals("kept-token", hostStore(coreStore(store)).getJSONObject("profiles").getJSONObject("fixture").getString("retained_id_token"))
    }

    @Test fun directScopeAloneAllowsThePlan() {
        val profile = JSONObject().put("generation", 1).put("state", "connected")
            .put("scopes", JSONArray().put("chatgpt.tokens.use.direct"))
        assertTrue(profile.planAllowed())
        profile.put("scopes", JSONArray().put("resource.invoke"))
        assertFalse(profile.planAllowed())
    }

    @Test fun androidPolicyBridgeMatchesBothFixtureSets() {
        val directory = requireNotNull(File(requireNotNull(System.getProperty("inku.identityCases"))).parentFile)
        val wire = JSONObject(directory.resolve("provider-wire-cases.json").readText()).getJSONArray("chatgpt")
        val addendum = JSONArray(directory.resolve("chatgpt-auth-addendum-cases.json").readText())
        val rows = (0 until wire.length()).map { wire.getJSONObject(it) }
            .filter { it.getJSONObject("request").optString("schema") == "inku.model-catalog-request.v1" } +
            (0 until addendum.length()).map { addendum.getJSONObject(it) }
        for (row in rows) {
            val request = row.getJSONObject("request")
            val result = try { ChatGptCore.call(request.getString("action"), request) }
                catch (error: ChatGptException) { JSONObject().put("error", error.code) }
            val expected = row.getJSONObject("expect")
            for (key in expected.keys()) assertEquals(row.optString("why", row.optString("name")) + ": " + key,
                canonical(expected.get(key)), canonical(result.get(key)))
        }
    }
}
