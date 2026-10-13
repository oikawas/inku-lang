package app.inku.mobile.llm

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue

/** Alphabetical core input, including keywords that must survive without Gemini projection. */
internal object SchemaOrderFixtures {
    val reading = """{
        "additionalProperties":false,"description":"構図の読み","properties":{
            "joints":{"items":{"properties":{"jointTarget":{"type":"string"}},"type":"object"},"type":"array"},
            "relations":{"items":{"properties":{
                "entryKind":{"const":"overlap","examples":["overlap"]},
                "layers":{"items":{"type":"string"},"type":"array"},
                "side":{"default":null,"type":"string"},
                "toward":{"enum":["left","right"],"type":"string"},
                "zExtra":{"x-note":"keep every word","type":"string"}},
                "propertyOrdering":["toward","entryKind","layers"],"required":["entryKind"],"type":"object"},"type":"array"},
            "thesis":{"description":"先に書く","type":"string"}},
        "propertyOrdering":["thesis","relations","joints"],"required":["thesis","relations","joints"],"type":"object"
    }""".trimIndent()

    val plain = listOf(
        "generate_normalized_ddl" to """{"additionalProperties":false,"properties":{"normalized_ddl":{"type":"string"}},"required":["normalized_ddl"],"type":"object"}""",
        "complete_visible_ddl_holes" to """{"properties":{"edits":{"items":{"oneOf":[{"properties":{"replacement":{"type":"string"}},"type":"object"},{"properties":{"reason":{"enum":["missing"]}},"type":"object"}]},"type":"array"}},"required":["edits"],"type":"object"}""",
    )

    fun request(modelId: String, action: String, schema: String) = ModelRequest(
        modelId, "Read the composition.\nKeep \"words\".", 0.0, 2048,
        systemInstruction = "Submit the requested JSON.",
        tool = ModelTool("submit_pipeline_response", "Submit JSON", schema), pipelineAction = action,
    )

    fun assertOrdered(wire: String, sentSchema: JSONObject) {
        fun inOrder(names: List<String>) {
            val positions = names.map { wire.indexOf(JSONObject.quote(it) + ":") }
            assertTrue("Missing properties in $names", positions.all { it >= 0 })
            assertTrue("Wrong properties order for $names", positions.zipWithNext().all { (a, b) -> a < b })
        }
        inOrder(listOf("thesis", "relations", "joints"))
        inOrder(listOf("toward", "entryKind", "layers"))
        val original = JSONObject(reading)
        val unlisted = original.getJSONObject("properties").getJSONObject("relations").getJSONObject("items")
            .getJSONObject("properties").keys().asSequence().filter { it == "side" || it == "zExtra" }.toList()
        inOrder(listOf("layers") + unlisted)
        assertEquals(plainValue(original), plainValue(sentSchema))
    }

    fun assertBytes(before: String, after: String) = assertArrayEquals(before.toByteArray(Charsets.UTF_8), after.toByteArray(Charsets.UTF_8))

    private fun plainValue(value: Any?): Any? = when (value) {
        is JSONObject -> value.keys().asSequence().associateWith { plainValue(value.get(it)) }
        is JSONArray -> (0 until value.length()).map { plainValue(value.get(it)) }
        is Number -> value.toDouble()
        JSONObject.NULL -> null
        else -> value
    }
}
