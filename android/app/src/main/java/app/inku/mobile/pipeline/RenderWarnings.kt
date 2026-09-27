package app.inku.mobile.pipeline

import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

/**
 * Something the render core drew around without stopping, from the drawing's
 * `render_warnings`: today a color table value that is not `#rrggbb`, drawn in
 * its default. Kinds and names only; the core never records the values.
 */
data class RenderWarning(val kind: String, val name: String?) {
    companion object {
        /** Reads a drawing's metadata; absent when the core raised none, and on older works. */
        fun listFrom(metadata: JSONObject?): List<RenderWarning> {
            val array = metadata?.optJSONArray("render_warnings") ?: return emptyList()
            return (0 until array.length()).mapNotNull { index ->
                val item = array.optJSONObject(index) ?: return@mapNotNull null
                RenderWarning(
                    kind = item.optString("kind").takeIf { it.isNotEmpty() } ?: return@mapNotNull null,
                    name = item.optString("name").takeIf { it.isNotEmpty() },
                )
            }
        }
    }
}

/** The drawing's warnings, logged; null when there were none, so callers keep them only if any. */
internal fun loggedRenderWarnings(metadata: JSONObject, during: String): JSONArray? {
    val warnings = metadata.optJSONArray("render_warnings")?.takeIf { it.length() > 0 } ?: return null
    Log.w(RENDER_LOG_TAG, "render warnings during $during: $warnings")
    return warnings
}

internal const val RENDER_LOG_TAG = "InkuRender"
