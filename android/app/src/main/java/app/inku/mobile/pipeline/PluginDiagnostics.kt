package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject

/** The plugin package shipped with the app; its document is the enable/disable handle. */
const val BUNDLED_PLUGIN_PACKAGE = "Nature.leaves"

internal data class PluginWord(val qualifiedName: String, val ja: List<String>, val en: List<String>)

internal fun pluginWord(definition: JSONObject, qualifiedName: String): PluginWord {
    val names = definition.optJSONObject("names")
    fun values(language: String): List<String> {
        val array = names?.optJSONArray(language) ?: return emptyList()
        return (0 until array.length()).mapNotNull { array.opt(it) as? String }
    }
    return PluginWord(qualifiedName, values("ja"), values("en"))
}

internal fun pluginNameEntries(words: List<PluginWord>, enabled: Boolean): List<JSONObject> = words.flatMap { word ->
    (word.ja + word.en).map { name ->
        val normalized = java.text.Normalizer.normalize(name, java.text.Normalizer.Form.NFKC)
            .lowercase(java.util.Locale.ROOT).trim().replace(Regex("(?U)\\s+"), " ")
        JSONObject().put("name", normalized).put("qualified_name", word.qualifiedName).put("enabled", enabled)
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
