package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject

/** The plugin package shipped with the app; its document is the enable/disable handle. */
const val BUNDLED_PLUGIN_PACKAGE = "Nature.leaves"

/**
 * Every name a set of definitions answers to: `Namespace.Heading` and each
 * `Namespace.Alias` (DDL Spec 14). Hosts pass both so a sentence written with
 * either name is explained the same way.
 */
internal fun pluginVisibleNames(definitions: JSONArray?): List<String> {
    if (definitions == null) return emptyList()
    return (0 until definitions.length()).flatMap { index ->
        val definition = definitions.optJSONObject(index) ?: return@flatMap emptyList()
        val namespace = definition.optString("namespace").takeIf { it.isNotEmpty() } ?: return@flatMap emptyList()
        val heading = definition.optString("heading").takeIf { it.isNotEmpty() } ?: return@flatMap emptyList()
        val aliases = definition.optJSONArray("aliases")
            ?.let { array -> (0 until array.length()).mapNotNull { array.opt(it) as? String } }
            .orEmpty()
        (listOf(heading) + aliases).map { "$namespace.$it" }
    }
}

/** One author-facing reason for a plugin sentence the compiler withheld. */
data class PluginDiagnostic(
    val name: String,
    val reason: String,
    val suggestion: String?,
    val startByte: Int,
    val endByte: Int,
) {
    companion object {
        /** Reads `pipeline_diagnostics.plugin_diagnostics`; absent on works saved before it existed. */
        fun listFrom(pipelineDiagnostics: JSONObject?): List<PluginDiagnostic> {
            val array = pipelineDiagnostics?.optJSONArray("plugin_diagnostics") ?: return emptyList()
            return (0 until array.length()).mapNotNull { index ->
                val item = array.optJSONObject(index) ?: return@mapNotNull null
                PluginDiagnostic(
                    name = item.optString("name").takeIf { it.isNotEmpty() } ?: return@mapNotNull null,
                    reason = item.optString("reason").takeIf { it.isNotEmpty() } ?: return@mapNotNull null,
                    suggestion = item.optString("suggestion").takeIf { it.isNotEmpty() },
                    startByte = item.optInt("start_byte", -1),
                    endByte = item.optInt("end_byte", -1),
                )
            }
        }
    }
}
