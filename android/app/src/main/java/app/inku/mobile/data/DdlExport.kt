package app.inku.mobile.data

import app.inku.mobile.pipeline.ImportedPluginDefinition
import app.inku.mobile.pipeline.pluginVisibleNames
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/**
 * Portable DDL: the visible DDL with the plugin definitions it names
 * (`inku.ddl-export.v1`). Mirrors the server's `ddl_export.build_ddl_export`
 * and the web's `parseDdlImport`. Definitions are data-only and are validated
 * again by the shared Rust boundary when a new work resolves them.
 */
object DdlExport {
    const val SCHEMA = "inku.ddl-export.v1"
    private const val MAX_IMPORTED_PLUGINS = 64

    /** Keeps only the definitions whose canonical name or an alias the DDL writes. */
    fun build(
        source: String,
        language: String,
        definitions: JSONArray?,
        summaries: JSONArray?,
        exportedFrom: JSONObject,
    ): JSONObject {
        val plugins = JSONArray()
        val seen = mutableSetOf<String>()
        for (index in 0 until (definitions?.length() ?: 0)) {
            val definition = definitions?.optJSONObject(index) ?: continue
            val names = pluginVisibleNames(JSONArray().put(definition))
            val name = names.firstOrNull() ?: continue
            if (name in seen || names.none { source.contains(it) }) continue
            seen += name
            plugins.put(
                JSONObject()
                    .put("definition", definition)
                    .put("summary", summaries?.opt(index) as? String ?: ""),
            )
        }
        return JSONObject()
            .put("schema", SCHEMA)
            .put("language", language)
            .put("ddl", source)
            .put("plugins", plugins)
            .put("exported_from", exportedFrom)
    }

    data class Import(
        val ddl: String,
        val plugins: List<ImportedPluginDefinition>,
        /** Canonical names of the carried plugins, for the author-facing notice. */
        val names: List<String>,
    )

    /** Any text that is not an export -- JSON or not -- is the author's DDL as written. */
    fun parse(text: String): Import {
        val file = try {
            JSONObject(text)
        } catch (_: JSONException) {
            return Import(text, emptyList(), emptyList())
        }
        if (file.optString("schema") != SCHEMA) return Import(text, emptyList(), emptyList())
        val ddl = file.opt("ddl") as? String ?: throw IllegalArgumentException("ddl_export_without_ddl")
        val items = file.optJSONArray("plugins") ?: JSONArray()
        require(items.length() <= MAX_IMPORTED_PLUGINS) { "ddl_export_too_many_plugins" }
        val plugins = (0 until items.length()).map { index ->
            val definition = items.optJSONObject(index)?.optJSONObject("definition")
                ?: throw IllegalArgumentException("ddl_export_invalid_plugin")
            val summary = (items.optJSONObject(index)?.opt("summary") as? String)?.trim().orEmpty()
            ImportedPluginDefinition(
                definitionJson = definition.toString(),
                // Stage 1 requires a summary; an export without one still names the plugin.
                summary = summary.ifEmpty { "${definition.optString("namespace")}.${definition.optString("heading")}" },
            )
        }
        val names = plugins.map { plugin ->
            JSONObject(plugin.definitionJson).let { "${it.optString("namespace")}.${it.optString("heading")}" }
        }
        return Import(ddl, plugins, names)
    }
}
