package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelTool
import org.json.JSONObject

internal object WebScoreTool {
    val submitScore = ModelTool(
        name = "submit_score",
        description = "正規化DDLから導出した JSON Score を提出する。",
        parametersJson = ServerScoreSchemaJson.parameters,
    )

    fun extractJsonObject(text: String): JSONObject {
        val trimmed = text.trim()
        runCatching { return unwrapScoreJson(JSONObject(trimmed)) }
        val start = trimmed.indexOf('{')
        val end = trimmed.lastIndexOf('}')
        if (start >= 0 && end > start) {
            return unwrapScoreJson(JSONObject(trimmed.substring(start, end + 1)))
        }
        error("Stage2 did not return a JSON object.")
    }

    fun unwrapScoreJson(json: JSONObject): JSONObject {
        json.optJSONArray("tool_calls")?.let { calls ->
            for (i in 0 until calls.length()) {
                val call = calls.optJSONObject(i) ?: continue
                val arguments = call.optJSONObject("arguments")
                    ?: call.optJSONObject("parameters")
                    ?: call.optJSONObject("function")?.let { function ->
                        function.optJSONObject("arguments")
                            ?: function.optString("arguments").takeIf { it.isNotBlank() }?.let(::JSONObject)
                    }
                if (arguments != null) return arguments
            }
        }
        json.optJSONObject("arguments")?.let { return it }
        return json
    }

    fun hasRenderableInstructions(json: JSONObject): Boolean {
        val instructions = json.optJSONArray("instructions") ?: return false
        for (i in 0 until instructions.length()) {
            if (instructions.optJSONObject(i) != null) return true
        }
        return false
    }
}
