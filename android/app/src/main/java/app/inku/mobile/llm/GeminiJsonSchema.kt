package app.inku.mobile.llm

import org.json.JSONObject

/** Compatibility inspection seam; projection itself is performed by the shared core. */
internal object GeminiJsonSchema {
    fun project(schema: JSONObject, compactHoleEdits: Boolean = false): JSONObject {
        val request = ModelRequest("gemini:gemini-3-flash-preview", "", 0.0, 128,
            tool = ModelTool("submit_pipeline_response", "", schema.toString()),
            pipelineAction = if (compactHoleEdits) "complete_visible_ddl_holes" else "generate_normalized_ddl")
        val built = ProviderWireTransport.build("gemini", "gemini", "https://generativelanguage.googleapis.com", request)
        return JSONObject(built.getString("body")).getJSONArray("tools").getJSONObject(0)
            .getJSONArray("functionDeclarations").getJSONObject(0).getJSONObject("parametersJsonSchema")
    }

    /** ChatGPT's ordered schema writer still needs to inspect declared names. */
    internal fun orderedPropertyNames(schema: JSONObject): List<String> {
        val properties = schema.optJSONObject("properties") ?: return emptyList()
        val named = schema.optJSONArray("propertyOrdering")?.let { order ->
            (0 until order.length()).mapNotNull { index ->
                (order.opt(index) as? String)?.takeIf(properties::has)
            }
        }.orEmpty()
        return (named + properties.keys().asSequence().toList()).distinct()
    }
}
