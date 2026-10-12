package app.inku.mobile.llm

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import app.inku.mobile.pipeline.SingleAttemptModelEffectProvider
import app.inku.mobile.pipeline.PipelineModelSelection
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
    fun aCutOffFunctionCallBecomesAPipelineFailureInsteadOfAnAnswer() = runBlocking {
        val action = """{"tag":"generate_normalized_ddl","identity":{"action_id":"draw"},"timeout_ms":"1000",
            "payload":{"prompt":{"action_name":"generate_normalized_ddl","message":"draw","system":"submit",
            "response_schema":{"type":"object"}}}}"""
        val models = PipelineModelSelection("custom-google:gemini-3.1-pro-preview", "custom-google:gemini-3.1-pro-preview")
        val details = mutableListOf<String?>()
        for (finish in listOf("MAX_TOKENS", "STOP")) {
            val provider = GeminiModelProvider("custom-google", "https://generativelanguage.invalid", "test-only") { url ->
                GeminiConnection(url, """{"candidates":[{"finishReason":"$finish","content":{"parts":[
                    {"functionCall":{"name":"submit_pipeline_response","args":{"normalized_ddl":"circle"}}}]}}]}""")
            }
            val effect = SingleAttemptModelEffectProvider(provider) { _, _, detail, _ -> details += detail }
            val result = JSONObject(effect.perform(action, models))
            if (finish == "MAX_TOKENS") {
                assertEquals("provider_failed", result.getString("tag"))
                assertEquals("malformed_payload", result.getString("failure"))
                assertFalse(result.has("response"))
                assertEquals(listOf("output_limit_reached"), details)
            } else {
                assertEquals("normalized_ddl_generated", result.getString("tag"))
                assertEquals("circle", JSONObject(result.getString("response")).getString("normalized_ddl"))
            }
        }
    }

    @Test
    fun pipelineModelsSendTheServersLowestThinkingLevel() = runBlocking {
        for ((model, expected) in THINKING_CASES) {
            lateinit var connection: GeminiConnection
            val provider = GeminiModelProvider("custom-google", "https://generativelanguage.invalid", "test-only") { url ->
                GeminiConnection(url).also { connection = it }
            }
            provider.generate(ModelRequest("custom-google:$model", "draw", 0.0, 1024,
                tool = ModelTool("submit_pipeline_response", "Submit", """{"type":"object"}"""),
                pipelineAction = "generate_normalized_ddl"))
            val payload = JSONObject(connection.body.toString(Charsets.UTF_8.name()))
            assertThinking(model, expected, payload)
            assertFalse(payload.getJSONObject("generationConfig").has("temperature"))
            assertEquals("ANY", payload.getJSONObject("toolConfig").getJSONObject("functionCallingConfig").getString("mode"))
        }
    }

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
        assertEquals(1024 + 8192, payload.getJSONObject("generationConfig").getInt("maxOutputTokens"))
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

    /** Server `quote(model, safe="")`: only A-Z a-z 0-9 _ . - ~ stay as they are. */
    @Test
    fun aModelIdIsPercentEncodedAsThePythonServerQuotesIt() = runBlocking {
        val urls = mutableListOf<String>()
        val provider = GeminiModelProvider("gemini", "https://generativelanguage.googleapis.com", "test-key") { url ->
            urls += url.toString()
            GeminiConnection(url)
        }
        for (model in listOf("gemini:models/gemma~4/it", "gemini:a b+c:d")) {
            provider.generate(
                ModelRequest(
                    modelId = model,
                    prompt = "Draw a circle",
                    temperature = 0.0,
                    maxTokens = 1024,
                    tool = ModelTool("submit_pipeline_response", "Submit", """{"type":"object"}"""),
                    pipelineAction = "generate_normalized_ddl",
                ),
            )
        }
        assertEquals(
            listOf(
                "https://generativelanguage.googleapis.com/v1beta/models/gemma~4%2Fit:generateContent",
                "https://generativelanguage.googleapis.com/v1beta/models/a%20b%2Bc%3Ad:generateContent",
            ),
            urls,
        )
    }
}

class GeminiVisionRequestTest {
    @Test
    fun demoUsesTheNewBudgetAndKeepsGemmasThoughtsOutOfTheInstruction() = runBlocking {
        for ((model, expected) in listOf("gemma-4-31b-it" to "minimal", "gemini-flash-latest" to "low",
            "gemini-2.5-flash-image" to null)) {
            lateinit var connection: GeminiConnection
            val provider = GeminiModelProvider("custom-google", "https://generativelanguage.invalid", "test-only") { url ->
                GeminiConnection(url, """{"candidates":[{"content":{"parts":[
                    {"thought":true,"text":"The user wants a scene..."},{"text":"a pond at dusk"}]}}]}""")
                    .also { connection = it }
            }
            assertEquals("a pond at dusk", DemoInstructionWriter(provider).write("pond", "custom-google:$model"))
            val payload = JSONObject(connection.body.toString(Charsets.UTF_8.name()))
            assertThinking(model, expected, payload, 256)
            assertFalse(payload.getJSONObject("generationConfig").has("temperature"))
        }
    }

    @Test
    fun imageModelsSendTheServersLowestThinkingLevel() = runBlocking {
        for ((model, expected) in THINKING_CASES) {
            lateinit var connection: GeminiConnection
            val provider = GeminiModelProvider("custom-google", "https://generativelanguage.invalid", "test-only") { url ->
                GeminiConnection(url, TEXT_ANSWER).also { connection = it }
            }
            RemoteVisionAnalyzer(provider).analyze(VisionAnalysisRequest(modelId = "custom-google:$model",
                languageCode = "en", normalizedJpeg = byteArrayOf(1, 2, 3), width = 320, height = 240))
            val payload = JSONObject(connection.body.toString(Charsets.UTF_8.name()))
            assertThinking(model, expected, payload)
            assertFalse(payload.getJSONObject("generationConfig").has("temperature"))
            assertEquals("AQID", payload.getJSONArray("contents").getJSONObject(0).getJSONArray("parts")
                .getJSONObject(1).getJSONObject("inlineData").getString("data"))
        }
    }

    @Test
    fun cameraDescriptionModelsSendTheServersLowestThinkingLevel() = runBlocking {
        for ((model, expected) in THINKING_CASES) {
            lateinit var connection: GeminiConnection
            val provider = GeminiModelProvider("custom-google", "https://generativelanguage.invalid", "test-only") { url ->
                GeminiConnection(url, TEXT_ANSWER).also { connection = it }
            }
            CameraDescriptionWriter(provider).write(CameraDescriptionRequest("a red circle", "custom-google:$model", "en"))
            val payload = JSONObject(connection.body.toString(Charsets.UTF_8.name()))
            assertThinking(model, expected, payload)
            assertFalse(payload.getJSONObject("generationConfig").has("temperature"))
            assertFalse(payload.has("tools"))
        }
    }

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
        assertFalse(generation.has("temperature"))
        val parts = payload
            .getJSONArray("contents").getJSONObject(0).getJSONArray("parts")
        assertEquals(VisionPrompts.forLanguage("en"), parts.getJSONObject(0).getString("text"))
        val inline = parts.getJSONObject(1).getJSONObject("inlineData")
        assertEquals("image/jpeg", inline.getString("mimeType"))
        assertEquals("AQID", inline.getString("data"))
        assertEquals("A red circle. A blue rectangle.", response.text)
    }
}

private val THINKING_CASES = listOf(
    "gemini-3.8-flash" to "low",
    "gemini-3.7-flash" to "low",
    "gemini-flash-latest" to "low",
    "gemini-pro-latest" to "low",
    "gemini-3.6-flash" to "minimal",
    "gemini-3.5-flash-lite" to "minimal",
    "gemini-flash-lite-latest" to "minimal",
    "gemini-3.1-flash-lite-image" to "minimal",
    "models/gemini-3.6-flash" to "minimal",
    "gemini-3.1-pro-preview" to "low",
    "gemini-3-flash-preview" to "minimal",
    "gemini-3-pro-preview" to "low",
    "gemini-2.5-pro" to "low",
    "gemini-2.5-flash" to "low",
    "gemini-2.5-flash-lite" to null,
    "gemini-2.5-flash-image" to null,
    "gemma-4-31b-it" to "minimal",
    "models/gemini-4.1-pro-preview" to "low",
    "gemini-2.5-flash-lite-preview" to null,
    "gemini-2.5-flashlight" to "low",
    "gemini-3.5-flash" to "minimal",
    "gemini-3.1-flash-lite" to "minimal",
    "gemini-3.1-flash-lite-preview" to "minimal",
    "gemini-3.1-flash-image" to "minimal",
    "gemini-3.1-flash-image-preview" to "minimal",
    "gemini-robotics-er-2-preview" to "minimal",
    "nano-banana-pro-preview" to "minimal",
    "gemini-nano-banana-2.1" to "minimal",
    "antigravity-any" to null,
    "models/gemini-2.5-flash-image-preview" to null,
    "gemini-3.6-flash-preview" to "low",
)
private const val TEXT_ANSWER = """{"candidates":[{"content":{"parts":[{"text":"A red circle."}]}}]}"""

private fun assertThinking(model: String, expected: String?, payload: JSONObject, answerTokens: Int? = null) {
    val generation = payload.getJSONObject("generationConfig")
    if (expected == null) assertFalse(model, generation.has("thinkingConfig"))
    else assertEquals(model, expected, generation.getJSONObject("thinkingConfig").getString("thinkingLevel"))
    val base = answerTokens ?: if (payload.has("tools")) 1024 else 2048
    assertEquals(model, base + if (expected == null) 0 else 8192, generation.getInt("maxOutputTokens"))
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
