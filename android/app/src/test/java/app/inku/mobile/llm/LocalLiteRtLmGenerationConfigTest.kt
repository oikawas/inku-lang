package app.inku.mobile.llm

import app.inku.mobile.data.db.productFile
import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.ResponseFormat
import org.json.JSONObject
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
            pipelineAction = "read_composition",
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

    @Test
    fun stageOneLayerLimitMatchesCoreWithoutChangingSharedOrOtherSchemas() {
        val coreSource = productFile("core/crates/inku-ddl/src/work_plan.rs").readText()
        val coreLimit = Regex("""(?m)^\s*pub\s+const\s+MAX_WORK_PLAN_LAYERS\s*:\s*usize\s*=\s*(\d+)\s*;""")
            .findAll(coreSource).single().groupValues[1].toInt()
        assertEquals(coreLimit, LITERT_STAGE1_MAX_LAYERS)
        val schema = """{"type":"object","properties":{"layers":{"type":"array","items":{"type":"object","properties":{"plugins":{"type":"array","items":{"type":"string"}}}}}},"required":["layers"]}"""
        val request = ModelRequest(modelId = "local-litert-lm:gemma-4-e2b", prompt = "Draw a circle",
            temperature = 0.0, maxTokens = 2048, tool = ModelTool("submit_pipeline_response", "Submit", schema),
            pipelineAction = "generate_normalized_ddl")
        val bounded = JSONObject(checkNotNull(localLiteRtLmGenerationConfig(request).responseFormat).schemaOrPattern)
        val layers = bounded.getJSONObject("properties").getJSONObject("layers")
        assertEquals(coreLimit, layers.getInt("maxItems"))
        assertFalse(layers.getJSONObject("items").getJSONObject("properties").getJSONObject("plugins").has("maxItems"))
        layers.remove("maxItems")
        assertEquals(JSONObject(schema).toString(), bounded.toString())
        assertEquals(schema, checkNotNull(request.tool).parametersJson)
        assertEquals(schema, localLiteRtLmGenerationConfig(request.copy(pipelineAction = "read_composition")).responseFormat?.schemaOrPattern)
        assertEquals(schema, localLiteRtLmGenerationConfig(request.copy(pipelineAction = null)).responseFormat?.schemaOrPattern)
    }
}
