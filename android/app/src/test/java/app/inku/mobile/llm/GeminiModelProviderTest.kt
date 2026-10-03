package app.inku.mobile.llm

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

class GeminiModelProviderTest {
    @Test
    fun compositionSchemaKeepsTheThesisFirstAndOrdersNestedObjectsWithoutDroppingProperties() {
        val projected = GeminiJsonSchema.project(JSONObject("""{
            "type":"object","propertyOrdering":["thesis","roles","missing"],
            "properties":{
                "roles":{"type":"array","items":{"type":"object",
                    "propertyOrdering":["kind","detail"],"properties":{
                        "detail":{"type":"string"},"kind":{"const":"focal"}
                    }}},
                "thesis":{"type":"string"},"extra":{"type":"string"}
            }
        }"""))
        // The JVM org.json uses HashMap; Android writes these names in insertion order.
        assertEquals(listOf("thesis", "roles", "extra"), GeminiJsonSchema.orderedPropertyNames(projected))
        val nested = projected.getJSONObject("properties").getJSONObject("roles").getJSONObject("items")
        assertEquals(listOf("kind", "detail"), GeminiJsonSchema.orderedPropertyNames(nested))
        assertEquals("focal", nested.getJSONObject("properties").getJSONObject("kind").getJSONArray("enum").getString(0))
        assertEquals("string", projected.getJSONObject("properties").getJSONObject("extra").getString("type"))
    }

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
                tool = ModelTool("submit_pipeline_response", "Submit", """{"type":"object","properties":{"normalized_ddl":{"type":"string"},"schema":{"const":"v1","examples":["v1"]}},"required":["normalized_ddl"],"additionalProperties":false}"""),
                timeoutMs = 12_345,
                pipelineAction = "generate_normalized_ddl",
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
        // Server pipeline shape: model-default sampling, minimal thinking, one allowed function.
        assertFalse(payload.getJSONObject("generationConfig").has("temperature"))
        assertEquals("minimal", payload.getJSONObject("generationConfig").getJSONObject("thinkingConfig").getString("thinkingLevel"))
        val calling = payload.getJSONObject("toolConfig").getJSONObject("functionCallingConfig")
        assertEquals("ANY", calling.getString("mode"))
        assertEquals("submit_pipeline_response", calling.getJSONArray("allowedFunctionNames").getString(0))
        val declaration = payload.getJSONArray("tools").getJSONObject(0).getJSONArray("functionDeclarations").getJSONObject(0)
        assertEquals("submit_pipeline_response", declaration.getString("name"))
        val schema = declaration.getJSONObject("parametersJsonSchema")
        assertFalse(schema.getBoolean("additionalProperties"))
        val projected = schema.getJSONObject("properties").getJSONObject("schema")
        assertEquals("v1", projected.getJSONArray("enum").getString(0))
        assertFalse(projected.has("const") || projected.has("examples"))
        assertEquals("circle", JSONObject(response.text).getString("normalized_ddl"))
        assertEquals(11, response.promptTokens)
        assertEquals(7, response.completionTokens)
    }

    @Test
    fun duplicateFunctionAnswersAreMalformedInsteadOfChoosingTheLast() {
        val parts = JSONArray("""[{"functionCall":{"name":"submit_pipeline_response","args":{"normalized_ddl":"circle"}}},{"functionCall":{"name":"submit_pipeline_response","args":{"normalized_ddl":"square"}}}]""")
        assertThrows(JSONException::class.java) {
            GeminiModelProvider.responseText(parts, "submit_pipeline_response")
        }
    }
}

class GeminiVisionRequestTest {
    @Test
    fun cameraRequestFollowsTheGeminiKindEvenWithACustomConnectionId() = runBlocking {
        lateinit var connection: GeminiConnection
        val provider = GeminiModelProvider("photo-google", "https://generativelanguage.googleapis.com", "test-key") { url ->
            GeminiConnection(url, answer = """{"candidates":[{"content":{"parts":[{"thought":true,"text":"Internal thought"},{"text":"A red circle."},{"text":"A blue rectangle."}]}}]}""").also { connection = it }
        }
        val response = RemoteVisionAnalyzer(provider).analyze(
            VisionAnalysisRequest(
                modelId = "photo-google:gemma-4-31b-it", languageCode = "en",
                normalizedJpeg = byteArrayOf(1, 2, 3), width = 320, height = 240,
            ),
        )
        val payload = JSONObject(connection.body.toString(Charsets.UTF_8.name()))
        val generation = payload.getJSONObject("generationConfig")
        assertEquals("minimal", generation.getJSONObject("thinkingConfig").getString("thinkingLevel"))
        assertEquals(0.2, generation.getDouble("temperature"), 0.0)
        val parts = payload
            .getJSONArray("contents").getJSONObject(0).getJSONArray("parts")
        assertEquals(VisionPrompts.forLanguage("en"), parts.getJSONObject(0).getString("text"))
        val inline = parts.getJSONObject(1).getJSONObject("inlineData")
        assertEquals("image/jpeg", inline.getString("mimeType"))
        assertEquals("AQID", inline.getString("data"))
        assertEquals("A red circle. A blue rectangle.", response.text)
    }
}

private class GeminiConnection(
    url: URL,
    private val answer: String = """{"candidates":[{"content":{"parts":[{"thought":true,"text":"internal thought"},{"functionCall":{"name":"submit_pipeline_response","args":{"normalized_ddl":"circle"}}}]}}],"usageMetadata":{"promptTokenCount":11,"candidatesTokenCount":7}}""",
) : HttpURLConnection(url) {
    val body = ByteArrayOutputStream()
    override fun getOutputStream() = body
    override fun getResponseCode() = 200
    override fun getInputStream() = answer.byteInputStream()
    override fun connect() = Unit
    override fun disconnect() = Unit
    override fun usingProxy() = false
}
