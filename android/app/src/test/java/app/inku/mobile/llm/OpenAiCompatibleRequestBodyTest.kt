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
        val ollama = OpenAiCompatibleProvider.requestBody("ollama", pipelineRequest("ollama:gemma4:31b"))
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

        val cloud = OpenAiCompatibleProvider.requestBody("ollama-cloud", pipelineRequest("ollama-cloud:gpt-oss:120b"))
        assertEquals("submit_pipeline_response", cloud.getJSONObject("tool_choice").getJSONObject("function").getString("name"))
        assertEquals("none", cloud.getString("reasoning_effort"))

        val openAi = OpenAiCompatibleProvider.requestBody("openai", pipelineRequest("openai:gpt-5.4-mini"))
        assertEquals(1, openAi.getJSONArray("tools").length())
        assertFalse(openAi.has("response_format"))
        assertFalse(openAi.has("reasoning_effort"))

        // Outside the pipeline nothing of this is added.
        val plain = OpenAiCompatibleProvider.requestBody(
            "ollama",
            ModelRequest(modelId = "ollama:gemma4:31b", prompt = "Describe", temperature = 0.2, maxTokens = 256),
        )
        assertFalse(plain.has("response_format"))
        assertFalse(plain.has("reasoning_effort"))
        assertEquals(0.2, plain.getDouble("temperature"), 0.0)
    }
}
