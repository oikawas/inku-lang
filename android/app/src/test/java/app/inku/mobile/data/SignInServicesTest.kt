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
        assertEquals(21, cases.length())
        for (index in 0 until cases.length()) {
            val row = cases.getJSONObject(index)
            val answer = JSONObject(NativePipelineBridge.modelCatalog(row.getJSONObject("request").toString().toByteArray())
                .toString(Charsets.UTF_8))
            assertEquals(row.getString("name"), canonical(row.getJSONObject("answer")), canonical(answer))
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
