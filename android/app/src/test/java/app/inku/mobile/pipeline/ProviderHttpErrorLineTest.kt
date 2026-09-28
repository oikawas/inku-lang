package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelProviderHttpException
import app.inku.mobile.llm.providerRefusal
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The refusal the server's `provider_http_error` line keeps, kept the same way on Android. */
class ProviderHttpErrorLineTest {

    @Test
    fun aRefusalKeepsItsReasonFieldsAndARedactedMessage() {
        val body = """{"error":{"message":"Function tools with reasoning_effort are not supported for gpt-5.6-terra in /v1/chat/completions. Key sk-abcdef123456.","type":"invalid_request_error","param":"reasoning_effort","code":null}}"""
        val error = ModelProviderHttpException(400, "HTTP 400 from api.openai.com", providerRefusal(body))

        val line = providerHttpErrorLine("generate_normalized_ddl", "openai:gpt-5.6-terra", error)

        assertTrue(line.startsWith("provider_http_error "))
        val fields = JSONObject(line.removePrefix("provider_http_error "))
        assertEquals("generate_normalized_ddl", fields.getString("action"))
        assertEquals("openai:gpt-5.6-terra", fields.getString("model"))
        assertEquals(400, fields.getInt("status"))
        assertEquals("invalid_request_error", fields.getString("type"))
        assertEquals("reasoning_effort", fields.getString("param"))
        assertFalse("a null code is not a reason", fields.has("code"))
        val message = fields.getString("message")
        assertTrue(message.startsWith("Function tools with reasoning_effort"))
        assertFalse("the key is masked", message.contains("abcdef123456"))
    }

    @Test
    fun aBodyThatIsNotAProviderErrorAddsNothing() {
        assertEquals(0, providerRefusal("<html>Bad Gateway</html>").length())
        assertEquals(0, providerRefusal("""{"error":"quota"}""").length())
        val gemini = providerRefusal("""{"error":{"code":403,"message":"denied","status":"PERMISSION_DENIED"}}""")
        assertEquals(403, gemini.getInt("code"))
        assertEquals("PERMISSION_DENIED", gemini.getString("status"))
    }
}
