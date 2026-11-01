package app.inku.mobile.data.db

import app.inku.mobile.pipeline.*
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions

/** The app's direct-DDL start and host drive, with only authority/execution writes kept in memory. */
internal fun compileMigratedRecords(host: HostSqlite, folder: File) = runBlocking {
    val binding = NativePipelineBridge
    val builder = SharedPipelineConfigBuilder(binding)
    val records = JSONArray()
    val diagnostics = linkedMapOf<String, Int>()
    val progress = folder.resolve("compile-progress.jsonl")
    progress.createNewFile()
    Files.setPosixFilePermissions(progress.toPath(), PosixFilePermissions.fromString("rw-------"))
    progress.writeText("")
    val configs = linkedMapOf<String, JSONObject>()
    val variationConfigs = linkedMapOf<String, JSONObject>()
    val historyLocks = linkedMapOf<String, JSONArray>()
    host.db.query("SELECT history_id, variation_id, fork_context_bytes FROM pipeline_history_links").use { c ->
        while (c.moveToNext()) {
            val context = JSONObject(c.getBlob(2).decodeToString())
            val config = context.getJSONObject("config")
            historyLocks[c.getString(0)] = SaijikiV3Migration.documentLocks(context.optJSONObject("macro_catalog")?.optJSONArray("definition_locks"))
            configs[c.getString(0)] = config
            variationConfigs.putIfAbsent(c.getString(1), config)
        }
    }
    suspend fun compile(kind: String, id: String, source: String, language: String, saved: JSONObject?, locks: JSONArray?, canvas: String = "square", catalog: String = "default") {
        val record = JSONObject().put("kind", kind).put("id", id).put("config_source", if (saved == null) "current_catalog" else "saved_fork_context")
        val codes = linkedSetOf<String>()
        fun scan(value: Any?) {
            when (value) {
                is JSONObject -> value.keys().forEach { key ->
                    val child = value.opt(key)
                    if ((key == "code" || key == "detail") && child is String) codes += child
                    scan(child)
                }
                is JSONArray -> (0 until value.length()).forEach { scan(value.opt(it)) }
            }
        }
        try {
            val prepared = if (saved == null) builder.build(SharedPipelineConfigRequest(
                resolvedLanguage = language, canvasFormatId = canvas, catalogSelectionId = catalog,
            )) else null
            val config = saved?.toString() ?: requireNotNull(prepared).configJson
            val configObject = JSONObject(config)
            val editorInput = JSONObject().put("source", source).put("language", language)
                .put("definitions", configObject.optJSONArray("definitions") ?: JSONArray())
                .put("locks", locks ?: SaijikiV3Migration.documentLocks(JSONArray(prepared?.macroLocksJson ?: "[]")))
                .put("compiler", configObject.getJSONObject("compiler"))
            val editor = JSONObject(binding.pluginCalls(editorInput.toString().toByteArray()).decodeToString())
            record.put("editor_resolution", editor)
            val calls = editor.optJSONArray("calls") ?: JSONArray()
            for (i in 0 until calls.length()) {
                val status = calls.getJSONObject(i).optString("status")
                if (status != "resolved") codes += status
            }
            if (editor.has("error")) codes += "editor_error:${editor.optString("error")}"
            val states = linkedMapOf<String, ByteArray>()
            val store = object : PipelineExecutionStore {
                override suspend fun create(ownerId: String, executionId: String, variationId: String, sequence: String, stateBytes: ByteArray) { states[executionId] = stateBytes }
                override suspend fun compareAndSet(ownerId: String, executionId: String, expectedSequence: String, nextSequence: String, stateBytes: ByteArray): Boolean { states[executionId] = stateBytes; return true }
                override suspend fun load(ownerId: String, executionId: String): ByteArray? = states[executionId]
            }
            val commits = object : PipelineCommitStore {
                override suspend fun commit(ownerId: String, actionJson: String, createIfMissing: Boolean, context: AuthoringContext): String {
                    val action = JSONObject(actionJson)
                    return JSONObject().put("tag", "visible_normalized_ddl_committed").put("identity", action.getJSONObject("identity"))
                        .put("ddl_digest", action.getJSONObject("payload").getString("ddl_digest"))
                        .put("revision", action.getJSONObject("payload").getJSONObject("authority").getJSONObject("next_state").getString("revision"))
                        .put("authority_digest", action.getJSONObject("payload").getString("authority_digest")).toString()
                }
            }
            val pipeline = SharedPipelineHost(binding, PipelineProviderEffect { _, _ -> error("provider_not_allowed_in_compile_rehearsal") }, commits, store)
            val view = pipeline.start(PipelineStartRequest("rehearsal", config,
                PipelineAuthoring.DirectDdl(source), PipelineModelSelection("none", "none"), AuthoringContext("")))
            record.put("phase", view.phaseTag).put("phase_reason", view.phaseReason)
                .put("events", JSONArray(view.eventsJson)).put("delivery", view.deliveryJson?.let(::JSONObject))
            scan(record)
            for (state in states.values) {
                val wrapper = JSONObject(state.decodeToString())
                val snapshot = wrapper.optJSONObject("snapshot") ?: wrapper.optString("snapshot_base64").takeIf { it.isNotEmpty() }?.let {
                    JSONObject(java.util.Base64.getDecoder().decode(it).decodeToString())
                }
                scan(snapshot?.optJSONObject("delivery"))
            }
        } catch (e: Exception) {
            record.put("exception", e.toString()); codes += "exception:${e.message}"
        }
        record.put("diagnostic_codes", JSONArray(codes.toList()))
        for (code in codes) diagnostics[code] = (diagnostics[code] ?: 0) + 1
        records.put(record)
        progress.appendText(JSONObject().put("kind", kind).put("id", id).put("phase", record.opt("phase"))
            .put("exception", record.opt("exception")).put("diagnostic_codes", JSONArray(codes.toList())).toString() + "\n")
    }
    host.db.query("SELECT variation_id, document_json FROM variation_authority").use { c ->
        while (c.moveToNext()) {
            val doc = JSONObject(c.getString(1))
            compile("variation", c.getString(0), doc.getString("source"), doc.optString("language", "ja"), variationConfigs[c.getString(0)], doc.optJSONArray("macro_locks"))
        }
    }
    host.db.query("SELECT id, normalized_ddl, instruction_lang_resolved, canvas_aspect, color_catalog_id FROM history_items").use { c ->
        while (c.moveToNext()) {
            if (c.isNull(1)) continue
            compile("history", c.getString(0), c.getString(1), c.getString(2) ?: "ja", configs[c.getString(0)], historyLocks[c.getString(0)], c.getString(3), c.getString(4))
        }
    }
    val report = JSONObject().put("records", records).put("diagnostic_records", JSONObject(diagnostics as Map<*, *>))
    val file = folder.resolve("compile-report.json"); file.createNewFile()
    Files.setPosixFilePermissions(file.toPath(), PosixFilePermissions.fromString("rw-------"))
    file.writeText(report.toString(2))
}

/** A variation without a surviving context can only see the current bundled catalog. */
internal fun inspectOrphanLocks(host: HostSqlite, folder: File) {
    val records = JSONArray()
    val builder = SharedPipelineConfigBuilder(NativePipelineBridge)
    fun key(lock: JSONObject) = listOf(lock.optString("qualified_name"), lock.optString("version"), lock.optString("digest").removePrefix("sha256:"))
    val catalogs = mutableMapOf<String, Set<List<String>>>()
    host.db.query("SELECT variation_id, document_json FROM variation_authority WHERE NOT EXISTS (SELECT 1 FROM pipeline_history_links l WHERE l.owner_id = variation_authority.owner_id AND l.variation_id = variation_authority.variation_id)").use { c ->
        while (c.moveToNext()) {
            val document = JSONObject(c.getString(1))
            val language = document.optString("language", "ja")
            val available = catalogs.getOrPut(language) {
                val prepared = builder.build(SharedPipelineConfigRequest(language, "square", "default"))
                val locks = JSONArray(prepared.macroLocksJson)
                (0 until locks.length()).map { key(locks.getJSONObject(it)) }.toSet()
            }
            val locks = document.optJSONArray("macro_locks") ?: JSONArray()
            val missing = JSONArray()
            for (i in 0 until locks.length()) if (key(locks.getJSONObject(i)) !in available) missing.put(locks.getJSONObject(i))
            records.put(JSONObject().put("id", c.getString(0)).put("locks", locks.length()).put("unavailable_locks", missing))
        }
    }
    val file = folder.resolve("orphan-locks.json"); file.createNewFile()
    Files.setPosixFilePermissions(file.toPath(), PosixFilePermissions.fromString("rw-------"))
    file.writeText(JSONObject().put("records", records).toString(2))
}
