package app.inku.mobile.pipeline

import org.json.JSONObject

/** Score-shape semantics used before the request crosses the Rust render boundary. */
internal object ScoreGeometryPolicy {
    val closedShapes: Set<String> = setOf(
        "circle",
        "ellipse",
        "square",
        "triangle",
        "polygon",
        "cloudform",
    )

    fun fillIsAskedFor(instruction: JSONObject): Boolean {
        if (instruction.optBoolean("filled", false)) return true
        return instruction.optJSONObject("surface")
            ?.optString("texture", "none") == "solid"
    }
}
