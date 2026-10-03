package app.inku.mobile.llm

import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.ResponseFormat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalLiteRtLmGenerationConfigTest {
    @Test
    fun structuredRequestEnablesItsExactSchemaAndPlainRequestRemainsUnconstrained() {
        val schema = """{"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":60}},"required":["count"]}"""
        val request = ModelRequest(
            modelId = "local-litert-lm:gemma-4-e2b",
            prompt = "Draw a circle",
            temperature = 0.0,
            maxTokens = 2048,
            systemInstruction = "Submit the work plan",
            tool = ModelTool("submit_pipeline_response", "Submit", schema),
            pipelineAction = "generate_normalized_ddl",
        )

        val structured = localLiteRtLmGenerationConfig(request)
        assertTrue(structured.conversationConfig.enableResponseFormat)
        assertEquals(ResponseFormat.Type.JSON_OBJECT, structured.responseFormat?.type)
        assertEquals(schema, structured.responseFormat?.schemaOrPattern)
        assertEquals(listOf(Content.Text("Submit the work plan")), structured.conversationConfig.systemInstruction?.contents)
        assertEquals(0.0, structured.conversationConfig.samplerConfig!!.temperature, 0.0)
        assertEquals(10, structured.conversationConfig.samplerConfig!!.topK)
        assertEquals(0.95, structured.conversationConfig.samplerConfig!!.topP, 0.0)

        val plain = localLiteRtLmGenerationConfig(request.copy(tool = null))
        assertFalse(plain.conversationConfig.enableResponseFormat)
        assertNull(plain.responseFormat)
        assertEquals(structured.conversationConfig.samplerConfig, plain.conversationConfig.samplerConfig)
        assertEquals(structured.conversationConfig.systemInstruction?.contents, plain.conversationConfig.systemInstruction?.contents)
    }
}
