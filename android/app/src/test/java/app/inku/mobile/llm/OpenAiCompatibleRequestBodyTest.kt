package app.inku.mobile.llm

import app.inku.mobile.pipeline.PipelineModelSelection
import app.inku.mobile.pipeline.SingleAttemptModelEffectProvider
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class OpenAiCompatibleRequestBodyTest {
    private val schema = """{"type":"object","properties":{"normalized_ddl":{"type":"string"}},"required":["normalized_ddl"]}"""

    private fun pipelineRequest(modelId: String) = ModelRequest(
        modelId = modelId,
        prompt = "Draw a circle",
        temperature = 0.7,
        maxTokens = 2048,
        systemInstruction = "Submit JSON",
        tool = ModelTool("submit_pipeline_response", "Submit", schema),
        pipelineAction = "generate_normalized_ddl",
    )

    @Test
    fun openAiToolCallsMustContainOnlyTheRequestedAnswer() {
        val toolName = "submit_pipeline_response"
        val function = JSONObject().put("name", toolName).put("arguments", """{"normalized_ddl":"circle"}""")
        val calls = JSONArray().put(JSONObject().put("function", function))
        val message = JSONObject().put("content", "Fallback text").put("tool_calls", calls)
        assertEquals("circle", JSONObject(OpenAiCompatibleProvider.extractToolArguments(message, toolName)!!).getString("normalized_ddl"))
        calls.put(JSONObject().put("function", JSONObject().put("name", toolName).put("arguments", """{"normalized_ddl":"square"}""")))
        assertThrows(JSONException::class.java) {
            OpenAiCompatibleProvider.extractToolArguments(message, toolName)
        }
        val payload = OpenAiCompatibleProvider.requestBody("openai", pipelineRequest("openai:gpt-5.6-luna"), OPENAI_URL)
        assertFalse(payload.getBoolean("stream"))
    }

    /** The server's `pipeline_provider.py` shapes: Ollama answers through `response_format`. */
    @Test
    fun ollamaAnswersThroughAJsonSchemaAndOthersThroughAForcedCall() {
        val ollama = OpenAiCompatibleProvider.requestBody("ollama", pipelineRequest("ollama:gemma4:31b"), OLLAMA_URL)
        assertEquals("gemma4:31b", ollama.getString("model"))
        val format = ollama.getJSONObject("response_format")
        assertEquals("json_schema", format.getString("type"))
        val jsonSchema = format.getJSONObject("json_schema")
        assertEquals("submit_pipeline_response", jsonSchema.getString("name"))
        assertTrue(jsonSchema.getBoolean("strict"))
        assertEquals("string", jsonSchema.getJSONObject("schema").getJSONObject("properties").getJSONObject("normalized_ddl").getString("type"))
        assertFalse(ollama.has("tools"))
        assertFalse(ollama.has("tool_choice"))
        assertEquals("none", ollama.getString("reasoning_effort"))
        assertEquals(0.3, ollama.getDouble("temperature"), 0.0)

        val cloud = OpenAiCompatibleProvider.requestBody("ollama-cloud", pipelineRequest("ollama-cloud:gpt-oss:120b"), OLLAMA_CLOUD_URL)
        assertEquals("submit_pipeline_response", cloud.getJSONObject("tool_choice").getJSONObject("function").getString("name"))
        assertEquals("low", cloud.getString("reasoning_effort"))
        assertEquals(10240, cloud.getInt("max_tokens"))
        for (id in listOf("ollama", "ollama-cloud")) {
            val url = if (id == "ollama") OLLAMA_URL else OLLAMA_CLOUD_URL
            for (model in listOf("gpt-oss", "gpt-oss:20b", "gpt-oss-20b")) {
                val body = OpenAiCompatibleProvider.requestBody(id, pipelineRequest("$id:$model"), url)
                assertEquals(model, body.getString("model"))
                assertEquals("low", body.getString("reasoning_effort"))
                assertEquals(10240, body.getInt("max_tokens"))
            }
            val other = OpenAiCompatibleProvider.requestBody(id, pipelineRequest("$id:gpt-ossary"), url)
            assertEquals("none", other.getString("reasoning_effort"))
            assertEquals(2048, other.getInt("max_tokens"))
        }

        val nvidia = OpenAiCompatibleProvider.requestBody("nvidia", pipelineRequest("nvidia:google/gemma-4-31b-it"), NVIDIA_URL)
        assertEquals(1, nvidia.getJSONArray("tools").length())
        assertFalse(nvidia.has("response_format"))
        assertFalse(nvidia.has("reasoning_effort"))
        val nvidiaGptOss = OpenAiCompatibleProvider.requestBody("nvidia", pipelineRequest("nvidia:openai/gpt-oss-120b"), NVIDIA_URL)
        assertFalse(nvidiaGptOss.has("reasoning_effort"))
        assertEquals(2048, nvidiaGptOss.getInt("max_tokens"))

        // Plain requests keep the same reasoning policy without a drawing schema.
        val plain = OpenAiCompatibleProvider.requestBody(
            "ollama",
            ModelRequest(modelId = "ollama:gemma4:31b", prompt = "Describe", temperature = 0.2, maxTokens = 256),
            OLLAMA_URL,
        )
        assertFalse(plain.has("response_format"))
        assertEquals("none", plain.getString("reasoning_effort"))
        assertEquals(256, plain.getInt("max_tokens"))
        assertEquals(0.2, plain.getDouble("temperature"), 0.0)
    }

    @Test
    fun nimTurnsOffThinkingOnlyForGemmaFourWithoutChangingItsBudgetOrSampling() {
        for (model in listOf("google/gemma-4-31b-it", "gemma4", "org/nested/GEMMA_4_IT")) {
            val body = OpenAiCompatibleProvider.requestBody("nvidia", pipelineRequest("nvidia:$model"), NVIDIA_URL)
            assertEquals(model, body.getString("model"))
            val kwargs = body.getJSONObject("chat_template_kwargs")
            assertEquals(1, kwargs.length())
            assertFalse(kwargs.getBoolean("enable_thinking"))
            assertEquals(2048, body.getInt("max_tokens"))
            assertEquals(0.3, body.getDouble("temperature"), 0.0)
            assertEquals("submit_pipeline_response", body.getJSONObject("tool_choice").getJSONObject("function").getString("name"))
            assertFalse(body.has("reasoning_effort"))
        }
        for (model in listOf("meta/llama-3.2-90b-vision-instruct", "google/gemma-3n-e4b-it", "google/gemma42")) {
            val body = OpenAiCompatibleProvider.requestBody("nvidia", pipelineRequest("nvidia:$model"), NVIDIA_URL)
            assertFalse(body.has("chat_template_kwargs"))
            assertEquals(2048, body.getInt("max_tokens"))
            assertEquals(0.3, body.getDouble("temperature"), 0.0)
        }
        val elsewhere = OpenAiCompatibleProvider.requestBody("custom", pipelineRequest("custom:google/gemma-4-31b-it"), NVIDIA_URL)
        assertFalse(elsewhere.has("chat_template_kwargs"))
    }

    @Test
    fun nimVisionPhotoDescriptionAndDemoSendTheSwitchInTheirActualJsonBodies() = runBlocking {
        val sent = mutableListOf<RecordingConnection>()
        val provider = OpenAiCompatibleProvider("nvidia", NVIDIA_URL, "test-only") { url ->
            RecordingConnection(url, """{"choices":[{"finish_reason":"stop","message":{"content":"A red circle."}}]}""")
                .also { sent += it }
        }
        val model = "nvidia:google/gemma-4-31b-it"
        RemoteVisionAnalyzer(provider).analyze(VisionAnalysisRequest(byteArrayOf(1, 2, 3), 1, 1, "en", model))
        CameraDescriptionWriter(provider).write(CameraDescriptionRequest("A red circle", model, "en"))
        assertEquals("A red circle.", DemoInstructionWriter(provider).write("circle", model))
        val bodies = sent.map { JSONObject(it.sent.toString(Charsets.UTF_8.name())) }
        assertEquals(listOf(2048, 2048, 256), bodies.map { it.getInt("max_tokens") })
        assertEquals(listOf(0.2, 0.7, 0.85), bodies.map { it.getDouble("temperature") })
        for (body in bodies) {
            assertEquals("google/gemma-4-31b-it", body.getString("model"))
            assertFalse(body.getJSONObject("chat_template_kwargs").getBoolean("enable_thinking"))
            assertFalse(body.has("extra_body"))
            assertFalse(body.has("reasoning_effort"))
        }
        val image = bodies.first().getJSONArray("messages").getJSONObject(0).getJSONArray("content")
        assertEquals("data:image/jpeg;base64,AQID", image.getJSONObject(1).getJSONObject("image_url").getString("url"))
        assertFalse(bodies.last().has("tools"))
    }

    @Test
    fun ollamaAuxiliaryRequestsUseTheSameReasoningAndTokenRoom() = runBlocking {
        for (id in listOf("ollama", "ollama-cloud")) {
            val sent = mutableListOf<RecordingConnection>()
            val provider = OpenAiCompatibleProvider(id, if (id == "ollama") OLLAMA_URL else OLLAMA_CLOUD_URL, "test-only") { url ->
                RecordingConnection(url, """{"choices":[{"finish_reason":"stop","message":{"content":"A red circle."}}]}""")
                    .also { sent += it }
            }
            val model = "$id:gpt-oss:20b"
            RemoteVisionAnalyzer(provider).analyze(VisionAnalysisRequest(byteArrayOf(1, 2, 3), 1, 1, "en", model))
            CameraDescriptionWriter(provider).write(CameraDescriptionRequest("A red circle", model, "en"))
            assertEquals("A red circle.", DemoInstructionWriter(provider).write("circle", model))
            val bodies = sent.map { JSONObject(it.sent.toString(Charsets.UTF_8.name())) }
            assertEquals(listOf(10240, 10240, 8448), bodies.map { it.getInt("max_tokens") })
            assertEquals(listOf("low", "low", "low"), bodies.map { it.getString("reasoning_effort") })
            assertEquals(listOf(0.2, 0.7, 0.85), bodies.map { it.getDouble("temperature") })
            val image = bodies.first().getJSONArray("messages").getJSONObject(0).getJSONArray("content")
            assertEquals("data:image/jpeg;base64,AQID", image.getJSONObject(1).getJSONObject("image_url").getString("url"))
            assertFalse(bodies.last().has("tools"))
            RemoteVisionAnalyzer(provider).analyze(VisionAnalysisRequest(byteArrayOf(1), 1, 1, "en", "$id:gemma4:31b"))
            val gemma = JSONObject(sent.last().sent.toString(Charsets.UTF_8.name()))
            assertEquals("none", gemma.getString("reasoning_effort"))
            assertEquals(2048, gemma.getInt("max_tokens"))
        }
    }

    @Test
    fun cutOffChatCompletionsFailBeforeTheirReasoningToolOrTextBecomesAnAnswer() = runBlocking {
        val action = """{"tag":"generate_normalized_ddl","identity":{"action_id":"draw"},"timeout_ms":"1000",
            "payload":{"prompt":{"action_name":"generate_normalized_ddl","message":"draw","system":"submit",
            "response_schema":{"type":"object"}}}}"""
        val tool = JSONObject().put("tool_calls", JSONArray().put(JSONObject().put("function", JSONObject()
            .put("name", "submit_pipeline_response").put("arguments", """{"normalized_ddl":"circle"}"""))))
        val text = JSONObject().put("content", """{"normalized_ddl":"circle"}""")
        val reasoning = JSONObject().put("content", "").put("reasoning", "Private reasoning must not be logged")
        val cases = listOf(Triple("ollama-cloud", "length", reasoning), Triple("nvidia", "length", tool),
            Triple("ollama", "length", text), Triple("ollama-cloud", "stop", tool))
        for ((id, finish, message) in cases) {
            val response = JSONObject().put("choices", JSONArray().put(JSONObject().put("finish_reason", finish).put("message", message)))
                .put("usage", JSONObject().put("completion_tokens", 10240))
            lateinit var connection: RecordingConnection
            val provider = OpenAiCompatibleProvider(id, if (id == "ollama") OLLAMA_URL else OLLAMA_CLOUD_URL, "test-only") { url ->
                RecordingConnection(url, response.toString()).also { connection = it }
            }
            val details = mutableListOf<String?>()
            val effect = SingleAttemptModelEffectProvider(provider) { _, _, detail, _ -> details += detail }
            val model = "$id:gpt-oss:20b"
            val result = JSONObject(effect.perform(action, PipelineModelSelection(model, model)))
            if (finish == "length") {
                assertEquals("provider_failed", result.getString("tag"))
                assertEquals("malformed_payload", result.getString("failure"))
                assertFalse(result.has("response"))
                assertEquals(listOf("output_limit_reached"), details)
                if (id == "ollama-cloud") {
                    val payload = JSONObject(connection.sent.toString(Charsets.UTF_8.name()))
                    val line = OpenAiCompatibleProvider.outputLimitLine(id, pipelineRequest(model), payload, response)
                    assertTrue(line.startsWith("provider_output_limit "))
                    assertFalse(line.contains("Private reasoning"))
                    val record = JSONObject(line.substringAfter(' '))
                    assertEquals("generate_normalized_ddl", record.getString("action"))
                    assertEquals(id, record.getString("provider"))
                    assertEquals("gpt-oss:20b", record.getString("model"))
                    assertEquals(10240, record.getInt("max_tokens"))
                    assertEquals("length", record.getString("finish_reason"))
                    assertEquals(10240, record.getInt("output_tokens"))
                    assertTrue(record.isNull("reasoning_tokens"))
                    assertTrue(record.getBoolean("has_reasoning"))
                    assertFalse(record.getBoolean("has_text"))
                    assertFalse(record.getBoolean("has_tool_call"))
                }
            } else {
                assertEquals("normalized_ddl_generated", result.getString("tag"))
                assertEquals("circle", JSONObject(result.getString("response")).getString("normalized_ddl"))
                assertTrue(details.isEmpty())
            }
        }
    }

    /**
     * The server's `openai_sampling()`: OpenAI's own API takes the length as
     * `max_completion_tokens`, refuses a temperature on the reasoning families,
     * and refuses a forced call from gpt-5.1 and later unless they do not reason.
     */
    @Test
    fun openAiItselfGetsItsOwnLengthTemperatureAndReasoningFields() {
        fun body(model: String) = OpenAiCompatibleProvider.requestBody("openai", pipelineRequest("openai:$model"), OPENAI_URL)

        val luna = body("gpt-5.6-luna")
        assertEquals(2048, luna.getInt("max_completion_tokens"))
        assertFalse(luna.has("max_tokens"))
        assertFalse(luna.has("temperature"))
        assertEquals("none", luna.getString("reasoning_effort"))
        assertEquals(1, luna.getJSONArray("tools").length())

        val gpt5 = body("gpt-5")
        assertFalse(gpt5.has("temperature"))
        assertFalse(gpt5.has("reasoning_effort"))

        val o4 = body("o4-mini")
        assertFalse(o4.has("temperature"))
        assertFalse(o4.has("reasoning_effort"))

        val gpt41 = body("gpt-4.1")
        assertEquals(2048, gpt41.getInt("max_completion_tokens"))
        assertEquals(0.3, gpt41.getDouble("temperature"), 0.0)
        assertFalse(gpt41.has("reasoning_effort"))

        // The rule follows the host, not the connection's name.
        val elsewhere = OpenAiCompatibleProvider.requestBody("openai", pipelineRequest("openai:gpt-5.6-luna"), NVIDIA_URL)
        assertEquals(2048, elsewhere.getInt("max_tokens"))
        assertFalse(elsewhere.has("max_completion_tokens"))
        assertEquals(0.3, elsewhere.getDouble("temperature"), 0.0)
        assertFalse(elsewhere.has("reasoning_effort"))
    }

    /** Server `_STAGE1_SAMPLED_ACTIONS`: the composition reading is sampled as Stage 1 is. */
    @Test
    fun compositionReadingIsSampledLikeStageOne() {
        fun body(providerId: String, url: String, model: String, action: String) =
            OpenAiCompatibleProvider.requestBody(providerId, pipelineRequest("$providerId:$model").copy(pipelineAction = action), url)

        assertEquals(0.3, body("nvidia", NVIDIA_URL, "gemma", "read_composition").getDouble("temperature"), 0.0)
        assertEquals(0.0, body("nvidia", NVIDIA_URL, "gemma", "complete_visible_ddl_holes").getDouble("temperature"), 0.0)
        assertEquals(0.0, body("nvidia", NVIDIA_URL, "gemma", "generate_sketch").getDouble("temperature"), 0.0)
        assertEquals(0.3, body("openai", OPENAI_URL, "gpt-4.1", "read_composition").getDouble("temperature"), 0.0)
        assertFalse(body("openai", OPENAI_URL, "gpt-5.6-luna", "read_composition").has("temperature"))
    }

    /** Server `pipeline_provider.py`: `"Bearer " + (key or "none")` on every OpenAI-compatible call. */
    @Test
    fun aConnectionWithoutAKeyStillSendsBearerNone() = kotlinx.coroutines.runBlocking {
        val connections = mutableListOf<RecordingConnection>()
        for (key in listOf(null, "")) {
            OpenAiCompatibleProvider("ollama", OLLAMA_URL, key) { url -> RecordingConnection(url).also { connections += it } }
                .generate(pipelineRequest("ollama:gemma"))
        }
        OpenAiCompatibleProvider("nvidia", NVIDIA_URL, "test-key") { url -> RecordingConnection(url).also { connections += it } }
            .generate(pipelineRequest("nvidia:gemma"))
        assertEquals(
            listOf("Bearer none", "Bearer none", "Bearer test-key"),
            connections.map { it.getRequestProperty("Authorization") },
        )
    }

    private companion object {
        const val OPENAI_URL = "https://api.openai.com/v1"
        const val NVIDIA_URL = "https://integrate.api.nvidia.com/v1"
        const val OLLAMA_URL = "http://127.0.0.1:11434/v1"
        const val OLLAMA_CLOUD_URL = "https://ollama.com/v1"
    }
}

private class RecordingConnection(url: java.net.URL,
    private val response: String = """{"choices":[{"message":{"content":"{\"normalized_ddl\":\"circle\"}"}}]}""",
) : java.net.HttpURLConnection(url) {
    val sent = java.io.ByteArrayOutputStream()
    override fun getOutputStream() = sent
    override fun getResponseCode() = 200
    override fun getInputStream() = response.byteInputStream()
    override fun connect() = Unit
    override fun disconnect() = Unit
    override fun usingProxy() = false
}
