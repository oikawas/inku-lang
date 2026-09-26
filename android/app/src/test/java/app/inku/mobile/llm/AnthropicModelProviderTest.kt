package app.inku.mobile.llm

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AnthropicModelProviderTest {
    @Test
    fun pipelineRequestUsesTheMessagesApiAndReturnsTheForcedToolInput() = runBlocking {
        lateinit var connection: AnthropicConnection
        val provider = AnthropicModelProvider("anthropic", "https://api.anthropic.com/", "test-key") { url ->
            AnthropicConnection(url).also { connection = it }
        }
        val schema = """{"type":"object","properties":{"normalized_ddl":{"type":"string"}},"required":["normalized_ddl"]}"""
        val response = provider.generate(
            ModelRequest(
                modelId = "anthropic:claude-sonnet-4-6",
                prompt = "Draw a circle",
                temperature = 0.3,
                maxTokens = 2048,
                systemInstruction = "Submit JSON",
                tool = ModelTool("submit_pipeline_response", "Submit", schema),
                timeoutMs = 12_345,
                pipelineAction = "generate_normalized_ddl",
            ),
        )
        assertEquals("https://api.anthropic.com/v1/messages", connection.url.toString())
        assertEquals("test-key", connection.getRequestProperty("x-api-key"))
        assertEquals("2023-06-01", connection.getRequestProperty("anthropic-version"))
        assertNull(connection.getRequestProperty("Authorization"))
        assertFalse(connection.instanceFollowRedirects)
        assertEquals(12_345, connection.readTimeout)
        val payload = JSONObject(connection.body.toString(Charsets.UTF_8.name()))
        assertEquals("claude-sonnet-4-6", payload.getString("model"))
        assertEquals(2048, payload.getInt("max_tokens"))
        assertEquals("Submit JSON", payload.getString("system"))
        assertEquals("Draw a circle", payload.getJSONArray("messages").getJSONObject(0).getString("content"))
        // The server's pipeline shape leaves sampling to the model.
        assertFalse(payload.has("temperature"))
        val tool = payload.getJSONArray("tools").getJSONObject(0)
        assertEquals("submit_pipeline_response", tool.getString("name"))
        assertEquals(JSONObject(schema).toString(), tool.getJSONObject("input_schema").toString())
        assertEquals("tool", payload.getJSONObject("tool_choice").getString("type"))
        assertEquals("submit_pipeline_response", payload.getJSONObject("tool_choice").getString("name"))
        assertEquals("circle", JSONObject(response.text).getString("normalized_ddl"))
        assertEquals(11, response.promptTokens)
        assertEquals(7, response.completionTokens)
    }

    @Test
    fun photoDescriptionSendsTheJpegBeforeThePromptAndReadsText() = runBlocking {
        lateinit var connection: AnthropicConnection
        val provider = AnthropicModelProvider("anthropic", "https://api.anthropic.com", "test-key") { url ->
            AnthropicConnection(url, answer = """{"content":[{"type":"text","text":"A red chair."}]}""").also { connection = it }
        }
        val response = provider.generate(
            ModelRequest(
                modelId = "anthropic:claude-haiku-4-5-20251001",
                prompt = "Describe the photo",
                temperature = 0.2,
                maxTokens = 512,
                imageJpeg = byteArrayOf(1, 2, 3),
            ),
        )
        val payload = JSONObject(connection.body.toString(Charsets.UTF_8.name()))
        assertEquals(0.2, payload.getDouble("temperature"), 0.0)
        val content = payload.getJSONArray("messages").getJSONObject(0).getJSONArray("content")
        val source = content.getJSONObject(0).getJSONObject("source")
        assertEquals("image", content.getJSONObject(0).getString("type"))
        assertEquals("image/jpeg", source.getString("media_type"))
        assertEquals("AQID", source.getString("data"))
        assertEquals("Describe the photo", content.getJSONObject(1).getString("text"))
        assertTrue(payload.optJSONArray("tools") == null)
        assertEquals("A red chair.", response.text)
    }
}

private class AnthropicConnection(
    url: URL,
    private val answer: String = """{"content":[{"type":"text","text":"Submitting."},{"type":"tool_use","id":"t1","name":"submit_pipeline_response","input":{"normalized_ddl":"circle"}}],"usage":{"input_tokens":11,"output_tokens":7}}""",
) : HttpURLConnection(url) {
    val body = ByteArrayOutputStream()
    override fun getOutputStream() = body
    override fun getResponseCode() = 200
    override fun getInputStream() = answer.byteInputStream()
    override fun connect() = Unit
    override fun disconnect() = Unit
    override fun usingProxy() = false
}
