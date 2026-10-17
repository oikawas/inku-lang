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
        assertFalse(payload.has("stream"))
    }

    @Test
    fun onlyRefinementVisionAdviceAddsAnImageToOfficialOpenAiResponses() {
        val request = ModelRequest(
            modelId = "openai:gpt-4.1",
            prompt = "Observe this generation",
            temperature = 0.35,
            maxTokens = 320,
            systemInstruction = "Return bounded advice",
            tool = ModelTool(REFINEMENT_ADVICE_TOOL, "Submit", """{"type":"object"}"""),
            pipelineAction = REFINEMENT_VISION_ACTION,
            imageJpeg = byteArrayOf(1, 2, 3),
        )
        val body = OpenAiCompatibleProvider.requestBody("openai", request, OPENAI_URL)
        val content = body.getJSONArray("input").getJSONObject(0).getJSONArray("content")
        assertEquals("input_text", content.getJSONObject(0).getString("type"))
        assertEquals(request.prompt, content.getJSONObject(0).getString("text"))
        assertEquals("input_image", content.getJSONObject(1).getString("type"))
        assertEquals("data:image/jpeg;base64,AQID", content.getJSONObject(1).getString("image_url"))
        assertEquals(0.35, body.getDouble("temperature"), 0.0)
        assertEquals(320, body.getInt("max_output_tokens"))
        assertEquals(REFINEMENT_ADVICE_TOOL, body.getJSONArray("tools").getJSONObject(0).getString("name"))
        assertEquals("Draw a circle", OpenAiCompatibleProvider.requestBody("openai", pipelineRequest("openai:gpt-4.1"), OPENAI_URL)
            .getJSONArray("input").getJSONObject(0).getString("content"))
        assertThrows(IllegalArgumentException::class.java) {
            OpenAiCompatibleProvider.requestBody("openai", request.copy(imageJpeg = null), OPENAI_URL)
        }
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

    /** Server's model table, with sampling fields translated for Responses drawing requests. */
    @Test
    fun openAiItselfGetsItsOwnLengthTemperatureAndReasoningFields() {
        val cases = listOf("gpt-4.1" to null, "gpt-5.1" to "none", "gpt-5.6-luna" to "none",
            "gpt-6-luna" to "none", "gpt-6-sol" to "none", "gpt-6.1-sol" to "low",
            "gpt-6-astra" to "low", "gpt-5" to "low", "o3" to "low")
        for ((model, effort) in cases) {
            val request = pipelineRequest("openai:$model")
            val body = OpenAiCompatibleProvider.requestBody("openai", request, OPENAI_URL)
            val limit = 2048 + if (effort == "low") 25000 else 0
            assertEquals(limit, body.getInt("max_output_tokens"))
            assertFalse(body.has("max_completion_tokens")); assertFalse(body.has("max_tokens"))
            assertFalse(body.has("reasoning_effort")); assertFalse(body.has("messages")); assertFalse(body.has("stream"))
            assertFalse(body.getBoolean("store")); assertFalse(body.getBoolean("parallel_tool_calls"))
            assertEquals("required", body.getString("tool_choice"))
            assertEquals("Submit JSON", body.getString("instructions"))
            val input = body.getJSONArray("input").getJSONObject(0)
            assertEquals("user", input.getString("role")); assertEquals("Draw a circle", input.getString("content"))
            val tool = body.getJSONArray("tools").getJSONObject(0)
            assertEquals(1, body.getJSONArray("tools").length())
            assertEquals("function", tool.getString("type")); assertEquals("submit_pipeline_response", tool.getString("name"))
            assertEquals("Submit", tool.getString("description")); assertFalse(tool.getBoolean("strict"))
            assertEquals(JSONObject(schema).toString(), tool.getJSONObject("parameters").toString())
            if (effort == null) {
                assertFalse(body.has("reasoning")); assertEquals(0.3, body.getDouble("temperature"), 0.0)
            } else {
                assertEquals(effort, body.getJSONObject("reasoning").getString("effort")); assertFalse(body.has("temperature"))
            }
            val plain = OpenAiCompatibleProvider.requestBody("openai", request.copy(pipelineAction = null, tool = null), OPENAI_URL)
            assertEquals(limit, plain.getInt("max_completion_tokens")); assertFalse(plain.has("max_output_tokens"))
            assertTrue(plain.has("messages")); assertFalse(plain.has("tools"))
            if (effort == null) {
                assertFalse(plain.has("reasoning_effort")); assertEquals(0.7, plain.getDouble("temperature"), 0.0)
            } else {
                assertEquals(effort, plain.getString("reasoning_effort")); assertFalse(plain.has("temperature"))
            }
        }

        // The rule follows the host, not the connection's name.
        val elsewhere = OpenAiCompatibleProvider.requestBody("openai", pipelineRequest("openai:gpt-5.6-luna"), NVIDIA_URL)
        assertEquals(2048, elsewhere.getInt("max_tokens"))
        assertFalse(elsewhere.has("max_completion_tokens"))
        assertEquals(0.3, elsewhere.getDouble("temperature"), 0.0)
        assertFalse(elsewhere.has("reasoning_effort"))
        assertTrue(elsewhere.has("messages")); assertFalse(elsewhere.has("input"))
        val renamed = OpenAiCompatibleProvider.requestBody("custom", pipelineRequest("custom:gpt-6-sol-fast"), OPENAI_URL)
        assertEquals("none", renamed.getJSONObject("reasoning").getString("effort"))
    }

    @Test
    fun openAiAuxiliaryCallsKeepChatCompletionsWithLowReasoningAndRoom() = runBlocking {
        val sent = mutableListOf<RecordingConnection>()
        val provider = OpenAiCompatibleProvider("openai", OPENAI_URL, "test-only") { url ->
            RecordingConnection(url, """{"choices":[{"finish_reason":"stop","message":{"content":"A red circle."}}]}""")
                .also { sent += it }
        }
        val model = "openai:gpt-6.1-sol"
        RemoteVisionAnalyzer(provider).analyze(VisionAnalysisRequest(byteArrayOf(1, 2, 3), 1, 1, "en", model))
        CameraDescriptionWriter(provider).write(CameraDescriptionRequest("A red circle", model, "en"))
        assertEquals("A red circle.", DemoInstructionWriter(provider).write("circle", model))
        assertTrue(sent.all { it.url.path == "/v1/chat/completions" })
        val bodies = sent.map { JSONObject(it.sent.toString(Charsets.UTF_8.name())) }
        assertEquals(listOf(27048, 27048, 25256), bodies.map { it.getInt("max_completion_tokens") })
        for (body in bodies) {
            assertEquals("low", body.getString("reasoning_effort"))
            assertFalse(body.has("temperature")); assertFalse(body.has("top_p"))
            assertFalse(body.has("tools")); assertFalse(body.has("max_output_tokens"))
        }
        val image = bodies.first().getJSONArray("messages").getJSONObject(0).getJSONArray("content")
        assertEquals("data:image/jpeg;base64,AQID", image.getJSONObject(1).getJSONObject("image_url").getString("url"))
    }

    @Test
    fun responsesNeedCompletionAndExactlyTheOfferedFunctionOrOnlyOutputText() {
        fun call() = JSONObject().put("type", "function_call").put("name", "submit_pipeline_response").put("arguments", "{\"normalized_ddl\":\"circle\"}")
        fun response(output: JSONArray) = JSONObject().put("status", "completed").put("output", output)
        fun answer(value: JSONObject) = OpenAiCompatibleProvider.responsesAnswerText(value, "submit_pipeline_response")
        assertEquals("circle", JSONObject(answer(response(JSONArray().put(JSONObject().put("type", "reasoning")).put(call())))).getString("normalized_ddl"))
        for (status in listOf("incomplete", "failed", "in_progress")) {
            assertThrows(MalformedProviderResponseException::class.java) { answer(response(JSONArray().put(call())).put("status", status)) }
        }
        for (calls in listOf(JSONArray().put(call()).put(call()), JSONArray().put(call().put("name", "other")),
            JSONArray().put(call().put("arguments", JSONObject())), JSONArray().put(call().put("arguments", JSONObject.NULL)))) {
            assertThrows(MalformedProviderResponseException::class.java) { answer(response(calls)) }
        }
        val message = JSONObject().put("type", "message").put("content", JSONArray()
            .put(JSONObject().put("type", "refusal").put("refusal", "Do not use"))
            .put(JSONObject().put("type", "output_text").put("text", "{\"normalized_ddl\":")))
        val tail = JSONObject().put("type", "message").put("content", JSONArray().put(JSONObject().put("type", "output_text").put("text", "\"circle\"}")))
        assertEquals("circle", JSONObject(answer(response(JSONArray().put("ignore").put(message).put(tail)))).getString("normalized_ddl"))
        assertThrows(MalformedProviderResponseException::class.java) { answer(response(JSONArray().put(JSONObject().put("type", "reasoning")))) }
        assertThrows(MalformedProviderResponseException::class.java) { answer(JSONObject().put("status", "completed")) }
    }

    @Test
    fun openAiPipelineUsesResponsesAndKeepsUsageAndHttpRefusalDetails() = runBlocking {
        val action = """{"tag":"generate_normalized_ddl","identity":{"action_id":"draw"},"timeout_ms":"1000",
            "payload":{"prompt":{"action_name":"generate_normalized_ddl","message":"draw","system":"submit",
            "response_schema":{"type":"object"}}}}"""
        val sent = mutableListOf<RecordingConnection>()
        val provider = OpenAiCompatibleProvider("custom-openai", OPENAI_URL, "test-only") { url ->
            val success = sent.isEmpty()
            RecordingConnection(url, if (success) """{"status":"completed","output":[{"type":"function_call",
                "name":"submit_pipeline_response","arguments":"{\"normalized_ddl\":\"circle\"}"}],
                "usage":{"input_tokens":12,"output_tokens":7}}""" else """{"error":{"code":"unsupported_parameter","param":"max_output_tokens","type":"invalid_request_error"}}""",
                if (success) 200 else 400).also { sent += it }
        }
        val received = mutableListOf<ModelResponse>()
        val observing = object : ModelProvider {
            override val providerId = provider.providerId
            override suspend fun generate(request: ModelRequest) = provider.generate(request).also { received += it }
        }
        val failures = mutableListOf<Throwable>()
        val effect = SingleAttemptModelEffectProvider(observing) { _, _, _, cause -> failures += cause }
        val models = PipelineModelSelection("custom-openai:gpt-6-sol", "custom-openai:gpt-6-sol")
        val result = JSONObject(effect.perform(action, models))
        assertEquals("normalized_ddl_generated", result.getString("tag"))
        assertEquals("circle", JSONObject(result.getString("response")).getString("normalized_ddl"))
        assertEquals(12, received.single().promptTokens); assertEquals(7, received.single().completionTokens)
        assertFalse(received.single().outputTruncated)
        val rejected = JSONObject(effect.perform(action, models))
        assertEquals("provider_rejected", rejected.getString("failure"))
        val cause = failures.single() as ModelProviderHttpException
        assertEquals(400, cause.statusCode); assertEquals("unsupported_parameter", cause.refusal.getString("code"))
        assertEquals("max_output_tokens", cause.refusal.getString("param"))
        for (connection in sent) {
            assertEquals("/v1/responses", connection.url.path); assertEquals("POST", connection.requestMethod)
            assertEquals("Bearer test-only", connection.getRequestProperty("Authorization"))
            assertEquals(1000, connection.readTimeout); assertFalse(connection.instanceFollowRedirects)
            val body = JSONObject(connection.sent.toString(Charsets.UTF_8.name()))
            assertFalse(body.getBoolean("store")); assertEquals(2048, body.getInt("max_output_tokens"))
            assertEquals("none", body.getJSONObject("reasoning").getString("effort"))
        }
    }

    @Test
    fun incompleteResponsesNeverBecomeAnswersAndOutputLimitsKeepTheirDetail() = runBlocking {
        val action = """{"tag":"generate_normalized_ddl","identity":{"action_id":"draw"},"timeout_ms":"1000",
            "payload":{"prompt":{"action_name":"generate_normalized_ddl","message":"draw","system":"submit",
            "response_schema":{"type":"object"}}}}"""
        val function = JSONObject().put("type", "function_call").put("name", "submit_pipeline_response").put("arguments", "{}")
        val cases = listOf("max_output_tokens" to JSONArray().put(JSONObject().put("type", "reasoning")),
            "max_output_tokens" to JSONArray().put(function).put(JSONObject().put("type", "message")),
            "content_filter" to JSONArray().put(function))
        for ((reason, output) in cases) {
            val response = JSONObject().put("status", "incomplete").put("incomplete_details", JSONObject().put("reason", reason))
                .put("output", output).put("usage", JSONObject().put("input_tokens", 12).put("output_tokens", 27048)
                    .put("output_tokens_details", JSONObject().put("reasoning_tokens", 26000)))
            lateinit var connection: RecordingConnection
            val provider = OpenAiCompatibleProvider("openai", OPENAI_URL, "test-only") { url ->
                RecordingConnection(url, response.toString()).also { connection = it }
            }
            val details = mutableListOf<String?>()
            val effect = SingleAttemptModelEffectProvider(provider) { _, _, detail, _ -> details += detail }
            val model = "openai:gpt-6.1-sol"
            val result = JSONObject(effect.perform(action, PipelineModelSelection(model, model)))
            assertEquals("malformed_payload", result.getString("failure")); assertFalse(result.has("response"))
            assertEquals(listOf(if (reason == "max_output_tokens") "output_limit_reached" else null), details)
            if (reason == "max_output_tokens") {
                val payload = JSONObject(connection.sent.toString(Charsets.UTF_8.name()))
                val line = OpenAiCompatibleProvider.outputLimitLine("openai", pipelineRequest(model), payload, response)
                assertTrue(line.startsWith("provider_output_limit "))
                val record = JSONObject(line.substringAfter(' '))
                assertEquals("generate_normalized_ddl", record.getString("action")); assertEquals("openai", record.getString("provider"))
                assertEquals("gpt-6.1-sol", record.getString("model")); assertEquals(27048, record.getInt("max_tokens"))
                assertEquals("max_output_tokens", record.getString("incomplete_reason"))
                assertEquals(27048, record.getInt("output_tokens")); assertEquals(26000, record.getInt("reasoning_tokens"))
                assertEquals(output.length() == 2, record.getBoolean("has_text"))
                assertEquals(output.length() == 2, record.getBoolean("has_function_call"))
                assertFalse(record.has("finish_reason")); assertFalse(record.has("has_reasoning"))
            }
        }
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
    private val status: Int = 200,
) : java.net.HttpURLConnection(url) {
    val sent = java.io.ByteArrayOutputStream()
    override fun getOutputStream() = sent
    override fun getResponseCode() = status
    override fun getInputStream() = response.byteInputStream()
    override fun getErrorStream() = response.byteInputStream()
    override fun connect() = Unit
    override fun disconnect() = Unit
    override fun usingProxy() = false
}
