package app.inku.mobile.llm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
        assertEquals("none", cloud.getString("reasoning_effort"))

        val nvidia = OpenAiCompatibleProvider.requestBody("nvidia", pipelineRequest("nvidia:google/gemma-4-31b-it"), NVIDIA_URL)
        assertEquals(1, nvidia.getJSONArray("tools").length())
        assertFalse(nvidia.has("response_format"))
        assertFalse(nvidia.has("reasoning_effort"))

        // Outside the pipeline nothing of this is added.
        val plain = OpenAiCompatibleProvider.requestBody(
            "ollama",
            ModelRequest(modelId = "ollama:gemma4:31b", prompt = "Describe", temperature = 0.2, maxTokens = 256),
            OLLAMA_URL,
        )
        assertFalse(plain.has("response_format"))
        assertFalse(plain.has("reasoning_effort"))
        assertEquals(0.2, plain.getDouble("temperature"), 0.0)
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

    private companion object {
        const val OPENAI_URL = "https://api.openai.com/v1"
        const val NVIDIA_URL = "https://integrate.api.nvidia.com/v1"
        const val OLLAMA_URL = "http://127.0.0.1:11434/v1"
        const val OLLAMA_CLOUD_URL = "https://ollama.com/v1"
    }
}
