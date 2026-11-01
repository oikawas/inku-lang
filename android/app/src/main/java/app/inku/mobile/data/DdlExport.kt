package app.inku.mobile.data

import app.inku.mobile.pipeline.ImportedPluginDefinition
import app.inku.mobile.pipeline.InstructionLanguages
import app.inku.mobile.pipeline.NativePipelineBridge
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/**
 * Portable DDL: the visible DDL with the plugin definitions it names
 * (`inku.ddl-export.v2`). Mirrors the server's `ddl_export.build_ddl_export`
 * and the web's `parseDdlImport`. Definitions are data-only and are validated
 * again by the shared Rust boundary when a new work resolves them.
 */
object DdlExport {
    const val SCHEMA = "inku.ddl-export.v2"
    private const val MAX_IMPORTED_PLUGINS = 64

    /** Keeps the definitions selected by the work's saved locks. */
    fun build(
        source: String?,
        language: String,
        definitions: JSONArray?,
        summaries: JSONArray?,
        exportedFrom: JSONObject,
        ddlSourceOrigin: String? = null,
        locks: JSONArray? = null,
    ): JSONObject {
        val plugins = JSONArray()
        val seen = mutableSetOf<Pair<String, String>>()
        val locked = (0 until (locks?.length() ?: 0)).mapNotNull { locks?.optJSONObject(it) }
            .map { it.optString("qualified_name") to it.optString("version") }.toSet()
        for (index in 0 until (definitions?.length() ?: 0)) {
            val definition = definitions?.optJSONObject(index) ?: continue
            val namespace = definition.optString("namespace")
            val id = definition.optString("id").ifEmpty { definition.optString("heading") }
            if (namespace.isEmpty() || id.isEmpty()) continue
            val key = "$namespace.$id" to definition.optString("version")
            if (key !in locked || !seen.add(key)) continue
            plugins.put(
                JSONObject()
                    .put("definition", definition)
                    .put("note", summaries?.opt(index) as? String ?: ""),
            )
        }
        return DdlSource.putJson(JSONObject(), source, ddlSourceOrigin)
            .put("schema", SCHEMA)
            .put("saijiki", "inku.saijiki.v3")
            .put("language", language)
            .put("plugins", plugins)
            .put("exported_from", exportedFrom)
    }

    data class Import(
        val ddl: String?,
        val plugins: List<ImportedPluginDefinition>,
        /** Canonical names of the carried plugins, for the author-facing notice. */
        val names: List<String>,
        val ddlSourceOrigin: String? = null,
        val migratedChanges: Int = 0,
    )

    /** Any text that is not an export -- JSON or not -- is the author's DDL as written. */
    fun parse(text: String, fallbackLanguage: String = "ja"): Import {
        val file = try {
            JSONObject(text)
        } catch (_: JSONException) {
            return Import(text, emptyList(), emptyList())
        }
        val schema = file.optString("schema")
        require(schema != "inku.ddl-export.v1") { "ddl_export_requires_v2" }
        if (schema != SCHEMA && schema != "inku.history_item") return Import(text, emptyList(), emptyList())
        require(file.has("ddl") || file.has("normalized_ddl") || file.has("expanded_ddl")) {
            "ddl_export_without_ddl"
        }
        var selected = DdlSource.fromJson(file)
        var migratedChanges = 0
        val edition = file.optString("saijiki")
        require(edition.isEmpty() || edition == "inku.saijiki.v2" || edition == "inku.saijiki.v3") { "other_edition" }
        if (edition != "inku.saijiki.v3") {
            val items = file.optJSONArray("plugins") ?: JSONArray()
            require(items.length() <= MAX_IMPORTED_PLUGINS) { "ddl_export_too_many_plugins" }
            val definitions = JSONArray()
            for (index in 0 until items.length()) definitions.put(items.getJSONObject(index).getJSONObject("definition"))
            fun ask(input: JSONObject): JSONObject = JSONObject(NativePipelineBridge.migrateSaijikiV2(input.toString().toByteArray(Charsets.UTF_8)).toString(Charsets.UTF_8))
            val first = ask(JSONObject().put("definitions", definitions))
            require(!first.has("error")) { "invalid_export_definitions" }
            val entries = first.getJSONArray("definitions")
            require(entries.length() == definitions.length()) { "invalid_export_definitions" }
            val locks = JSONArray()
            for (index in 0 until entries.length()) {
                val entry = entries.getJSONObject(index)
                require(!entry.has("error")) { "invalid_export_definitions" }
                locks.put(JSONObject().put("qualified_name", entry.getString("qualified_name")).put("version", entry.getString("version")).put("digest", entry.getString("old_digest")))
            }
            val migrationLanguage = file.optString("language").takeIf { it == "ja" || it == "en" }
                ?: InstructionLanguages.ofDdl(selected.ddl.orEmpty(), null, null, fallbackLanguage)
            val answer = ask(JSONObject().put("definitions", definitions).put("document", JSONObject()
                .put("source", selected.ddl.orEmpty()).put("language", migrationLanguage)
                .put("saijiki", "inku.saijiki.v2").put("macro_locks", locks)))
            require(!answer.has("error")) { "saijiki_export_migration_refused" }
            val document = answer.getJSONObject("document")
            require(!document.has("error")) { "saijiki_export_migration_refused" }
            val migrated = answer.getJSONArray("definitions")
            require(migrated.length() == items.length()) { "saijiki_export_migration_refused" }
            for (index in 0 until migrated.length()) {
                val entry = migrated.getJSONObject(index)
                require(!entry.has("error")) { "saijiki_export_migration_refused" }
                items.getJSONObject(index).put("definition", entry.getJSONObject("definition"))
            }
            file.put("plugins", items)
            selected = selected.copy(ddl = selected.ddl?.let { document.getJSONObject("document").getString("source") })
            migratedChanges = document.optJSONArray("edits")?.length() ?: 0
        }
        val language = InstructionLanguages.ofDdl(selected.ddl.orEmpty(), null, null, fallbackLanguage)
        fun primary(definition: JSONObject): String =
            definition.optJSONObject("names")?.optJSONArray(language)?.optString(0).orEmpty()
                .ifEmpty { definition.optString("heading").ifEmpty { definition.optString("id") } }
        fun name(definition: JSONObject): String {
            if (schema == "inku.history_item") return "${definition.optString("namespace")}.${definition.optString("heading")}"
            val value = primary(definition)
            return if (language == "en") "{$value}" else "｛$value｝"
        }
        val items = file.optJSONArray("plugins") ?: JSONArray()
        require(items.length() <= MAX_IMPORTED_PLUGINS) { "ddl_export_too_many_plugins" }
        val plugins = (0 until items.length()).map { index ->
            val definition = items.optJSONObject(index)?.optJSONObject("definition")
                ?: throw IllegalArgumentException("ddl_export_invalid_plugin")
            val summary = (items.optJSONObject(index)?.opt(if (schema == SCHEMA) "note" else "summary") as? String)?.trim().orEmpty()
            ImportedPluginDefinition(
                definitionJson = definition.toString(),
                // Stage 1 requires a summary; an export without one still names the plugin.
                summary = summary.ifEmpty { if (schema == "inku.history_item") name(definition) else primary(definition) },
            )
        }
        val names = plugins.map { plugin ->
            name(JSONObject(plugin.definitionJson))
        }
        return Import(selected.ddl, plugins, names, selected.origin, migratedChanges)
    }
}
