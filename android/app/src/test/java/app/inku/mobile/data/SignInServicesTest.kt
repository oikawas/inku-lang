package app.inku.mobile.data

import app.inku.mobile.llm.ChatGptPlanView
import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.ui.i18n.InkuStringsEn
import app.inku.mobile.ui.i18n.InkuStringsJa
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class SignInServicesTest {
    private fun canonical(value: Any?): Any? = when (value) {
        is JSONObject -> value.keys().asSequence().associateWith { canonical(value.get(it)) }
        is JSONArray -> (0 until value.length()).map { canonical(value.get(it)) }
        is Number -> java.math.BigDecimal(value.toString()).stripTrailingZeros()
        else -> value
    }

    @Test fun sharedSignInCasesUseTheActualJniCore() {
        val cases = JSONObject(File(System.getProperty("inku.signInCases")).readText()).getJSONArray("cases")
        assertEquals(50, cases.length())
        for (index in 0 until cases.length()) {
            val row = cases.getJSONObject(index)
            val answer = JSONObject(NativePipelineBridge.modelCatalog(row.getJSONObject("request").toString().toByteArray())
                .toString(Charsets.UTF_8))
            assertEquals(row.getString("name"), canonical(row.getJSONObject("answer")), canonical(answer))
        }
    }

    /**
     * The shared view rows Android can state, rebuilt from the host's own
     * values through `chatGptConnectionRequest`: the answer is the row's.
     * Android ties busy to a sign-in in Chrome and cannot open that page
     * again, so a busy row with no attempt and a reopenable attempt are not
     * among them.
     */
    @Test fun theConnectionViewRowsAreAnsweredFromTheHostRequest() {
        val cases = JSONObject(File(System.getProperty("inku.signInCases")).readText()).getJSONArray("cases")
        val skipped = setOf("view: busy", "view: signing in, the page can be opened again", "view: refuses an unknown service")
        var checked = 0
        for (index in 0 until cases.length()) {
            val row = cases.getJSONObject(index)
            val name = row.getString("name")
            if (!name.startsWith("view: ") || name in skipped) continue
            val request = row.getJSONObject("request")
            val connection = request.getJSONObject("connection")
            val profiles = connection.optJSONArray("profiles").objects().map { profile ->
                val scopes = profile.optJSONArray("scopes").strings()
                app.inku.mobile.llm.ChatGptProfileView(profile.getString("id"), profile.getString("label"), profile.getString("state"),
                    planAllowed = "chatgpt.tokens.use.direct" in scopes, scopes = scopes)
            }
            val pending = connection.optJSONArray("pending_registrations").objects().map {
                app.inku.mobile.llm.ChatGptPendingRegistration(it.getString("id"), if (it.isNull("client_id")) null else it.getString("client_id"))
            }
            val unconfirmed = request.optString("last_operation") in setOf("sign_out", "delete") && request.has("revocation_confirmed") &&
                !request.getBoolean("revocation_confirmed")
            val answer = catalogRequest("sign_in_connection_view", app.inku.mobile.llm.chatGptConnectionRequest(profiles, pending,
                if (connection.isNull("active_profile_id")) null else connection.getString("active_profile_id"),
                request.optJSONObject("attempt")?.optBoolean("active") == true,
                if (request.isNull("code")) null else request.optString("code"), unconfirmed))
            assertEquals(name, canonical(row.getJSONObject("answer")), canonical(answer))
            assertEquals(name, row.getJSONObject("answer").getBoolean("guide"), ChatGptPlanView(connection = answer).canUsePlan)
            checked++
        }
        // One connection per device: the rows Android states, including another account signing in.
        assertEquals(14, checked)
    }

    private fun JSONArray?.objects(): List<JSONObject> = if (this == null) emptyList() else (0 until length()).map(::getJSONObject)

    /** Step 5: every shared row of the procedures (a request and its answer) through the JNI core. */
    @Test fun sharedSignInFlowRowsUseTheActualJniCore() {
        val rows = JSONArray(File(System.getProperty("inku.signInFlowCases")).readText())
        assertEquals(122, rows.length())
        for (index in 0 until rows.length()) {
            val row = rows.getJSONObject(index)
            val request = JSONObject(row.getJSONObject("request").toString()).put("schema", "inku.model-catalog-request.v1")
            val answer = JSONObject(NativePipelineBridge.modelCatalog(request.toString().toByteArray()).toString(Charsets.UTF_8))
            assertEquals("[$index] ${row.optString("why")}", canonical(row.getJSONObject("expect")), canonical(answer))
        }
    }

    @Test fun theScreenNamesAreTheCoreLabels() {
        assertEquals("ChatGPT でサインイン", InkuStringsJa.chatGptPlan)
        assertEquals("Sign in with ChatGPT", InkuStringsEn.chatGptPlan)
        assertEquals("Sign in with ChatGPT", SignInServices.chatGptProviderSetting(ChatGptPlanView()).displayName)
    }

    @Test fun aSignedInServiceGoesFirstAndTheOthersKeepTheirOrder() {
        val ids = listOf("local-litert-lm", "anthropic", "ollama", "chatgpt", "gemini")
        assertEquals(listOf("chatgpt", "local-litert-lm", "anthropic", "ollama", "gemini"), SignInServices.order(ids) { it })
        val without = listOf("local-litert-lm", "anthropic", "gemini")
        assertEquals(without, SignInServices.order(without) { it })
        assertEquals(emptyList<String>(), SignInServices.order(emptyList<String>()) { it })
    }

    @Test fun bothProviderRowsAreTheSameRow() {
        val plan = ChatGptPlanView(publishedModels = listOf("gpt-6.1-sol"))
        val row = SignInServices.chatGptProviderSetting(plan)
        assertEquals("chatgpt", row.providerId)
        assertEquals("chatgpt-responses", row.kind)
        assertEquals("https://api.openai.com/v1", row.baseUrl)
        assertEquals("[\"gpt-6.1-sol\"]", row.publishedModelsJson)
        assertEquals(false, row.isEnabled)
    }
}
