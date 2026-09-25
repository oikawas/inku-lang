package app.inku.mobile.llm

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class GeminiModelProviderTest {
    @Test
    fun gemmaPipelineUsesNativeEndpointCredentialsAndFunctionArguments() = runBlocking {
        lateinit var connection: GeminiConnection
        val provider = GeminiModelProvider("gemini", "https://generativelanguage.googleapis.com", "test-key") { url ->
            GeminiConnection(url).also { connection = it }
        }
        val response = provider.generate(
            ModelRequest(
                modelId = "gemini:gemma-4-31b-it",
                prompt = "Draw a circle",
                temperature = 0.0,
                maxTokens = 1024,
                systemInstruction = "Submit JSON",
                tool = ModelTool("submit_pipeline_response", "Submit", """{"type":"object","properties":{"normalized_ddl":{"type":"string"}},"required":["normalized_ddl"],"additionalProperties":false}"""),
                timeoutMs = 12_345,
            ),
        )
        assertEquals("https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent", connection.url.toString())
        assertEquals("POST", connection.requestMethod)
        assertEquals("test-key", connection.getRequestProperty("x-goog-api-key"))
        assertNull(connection.getRequestProperty("Authorization"))
        assertFalse(connection.instanceFollowRedirects)
        assertEquals(12_345, connection.readTimeout)
        val payload = JSONObject(connection.body.toString(Charsets.UTF_8.name()))
        assertEquals("Draw a circle", payload.getJSONArray("contents").getJSONObject(0).getJSONArray("parts").getJSONObject(0).getString("text"))
        assertEquals("Submit JSON", payload.getJSONObject("systemInstruction").getJSONArray("parts").getJSONObject(0).getString("text"))
        assertEquals(1024, payload.getJSONObject("generationConfig").getInt("maxOutputTokens"))
        assertEquals("ANY", payload.getJSONObject("toolConfig").getJSONObject("functionCallingConfig").getString("mode"))
        val declaration = payload.getJSONArray("tools").getJSONObject(0).getJSONArray("functionDeclarations").getJSONObject(0)
        assertEquals("submit_pipeline_response", declaration.getString("name"))
        assertFalse(declaration.getJSONObject("parametersJsonSchema").getBoolean("additionalProperties"))
        assertEquals("circle", JSONObject(response.text).getString("normalized_ddl"))
        assertEquals(11, response.promptTokens)
        assertEquals(7, response.completionTokens)
    }
}

private class GeminiConnection(url: URL) : HttpURLConnection(url) {
    val body = ByteArrayOutputStream()
    override fun getOutputStream() = body
    override fun getResponseCode() = 200
    override fun getInputStream() = """{"candidates":[{"content":{"parts":[{"thought":true,"text":"internal thought"},{"functionCall":{"name":"submit_pipeline_response","args":{"normalized_ddl":"circle"}}}]}}],"usageMetadata":{"promptTokenCount":11,"candidatesTokenCount":7}}""".byteInputStream()
    override fun connect() = Unit
    override fun disconnect() = Unit
    override fun usingProxy() = false
}
