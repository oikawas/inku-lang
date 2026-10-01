package app.inku.mobile.data.db

import androidx.sqlite.db.SupportSQLiteDatabase
import app.inku.mobile.data.lineage.LineagePlanner
import java.security.MessageDigest
import java.util.Base64
import org.json.JSONArray
import org.json.JSONObject

/**
 * The one-time move of the saved records from Saijiki v1 to the current edition.
 *
 * Saijiki v2 (DDL 16) names its edition on every visible document; a saved
 * document without the field was written with v1, and the core refuses it, and
 * a saved Macro definition that only a migration makes valid, with
 * `saijiki_migration_required` (SPEC §3.3). The core owns the migration itself
 * (`migrate_saijiki_v1`): given one saved unit -- a v1 document and the
 * definitions its locks name, or definitions alone -- it returns the unit in
 * the current edition.
 *
 * This is the Server's `persistence/saijiki_migration.py` (product `99a23771`)
 * on the same tables, run once at startup before anything reads a work:
 *
 * - the committed document of each variation (`variation_authority`): its
 *   source, its document with the edition and the moved locks, and its digest;
 *   the acknowledgment of its current revision follows the new digest;
 * - the definitions and locks frozen with each performance
 *   (`pipeline_history_links.fork_context_bytes`), with the digests that bind
 *   them to the work's instructions;
 * - the instructions of each saved work (`history_items.normalized_ddl` and
 *   `expanded_ddl`); its description, Score and SVG are never touched;
 * - the execution snapshots (`pipeline_candidate_executions`) are discarded
 *   when [discardExecutions] says so, not migrated.
 *
 * A record the core refuses is left as it was and listed; it need not be
 * perfect (the author, 2026-09-30). Everything is written in one transaction,
 * with the setting [DONE_SETTING], so a failure writes nothing and the next
 * start tries again, and a second run after success does nothing.
 */
internal class SaijikiV1Migration(
    private val migrate: (ByteArray) -> ByteArray,
    private val discardExecutions: Boolean,
    private val now: () -> Long = System::currentTimeMillis,
    private val elapsedMillis: () -> Long = { System.nanoTime() / 1_000_000 },
) {
    private val answers = HashMap<String, JSONObject>()
    private var coreCalls = 0
    private var coreMillis = 0L

    /** Writes the migration once; null when it was already written. */
    fun runOnce(db: SupportSQLiteDatabase): JSONObject? {
        if (alreadyWritten(db)) return null
        val started = elapsedMillis()
        db.beginTransaction()
        try {
            if (alreadyWritten(db)) return null
            val plan = plan(db)
            for ((sql, args) in plan.statements) db.execSQL(sql, args)
            if (discardExecutions) db.execSQL("DELETE FROM $DISCARDED_TABLE")
            val report = plan.report
                .put("discarded_executions", if (discardExecutions) plan.executions else 0)
                .put("statements", plan.statements.size)
                .put("core_calls", coreCalls)
                .put("core_ms", coreMillis)
                .put("total_ms", elapsedMillis() - started)
            val summary = JSONObject()
                .put("refused_records", report.getJSONArray("refused_records").length())
                .put("statements", plan.statements.size)
            db.execSQL(
                "INSERT INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?)",
                arrayOf<Any>(DONE_SETTING, LineagePlanner.canonicalJson(summary), now()),
            )
            db.setTransactionSuccessful()
            return report
        } finally {
            db.endTransaction()
        }
    }

    private class Plan(
        val statements: List<Pair<String, Array<Any?>>>,
        val executions: Int,
        val report: JSONObject,
    )

    private class Link(
        val ownerId: String,
        val historyId: String,
        val context: JSONObject,
        val definitions: List<Any>,
        val catalogLocks: JSONArray,
    )

    private fun plan(db: SupportSQLiteDatabase): Plan {
        val statements = mutableListOf<Pair<String, Array<Any?>>>()
        val counts = linkedMapOf<String, LinkedHashMap<String, Int>>()
        fun count(kind: String, name: String) {
            val tally = counts.getOrPut(kind) { linkedMapOf() }
            tally[name] = (tally[name] ?: 0) + 1
        }
        val edits = linkedMapOf<String, Int>()
        val refused = JSONArray()
        val sweeps = JSONArray()

        // The frozen catalogs of the performances, and the definitions each variation saved.
        val links = linkedMapOf<String, Link>()
        val savedByVariation = linkedMapOf<Pair<String, String>, MutableList<Any>>()
        db.query(
            "SELECT owner_id, history_id, variation_id, fork_context_bytes, fork_context_digest" +
                " FROM pipeline_history_links",
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val ownerId = cursor.getString(0)
                val historyId = cursor.getString(1)
                val bytes = cursor.getBlob(3)
                count("history_links", "rows")
                val context = runCatching { JSONObject(bytes.toString(Charsets.UTF_8)) }.getOrNull()
                if (sha256(bytes) != cursor.getString(4) || context == null) {
                    count("history_links", "unreadable")
                    refused.put(refusal("history_links", "$ownerId/$historyId", JSONObject().put("code", "unreadable_context")))
                    continue
                }
                val definitions = definitionsOf(context.optJSONObject("config"))
                val locks = context.optJSONObject("macro_catalog")?.optJSONArray("definition_locks") ?: JSONArray()
                links[historyId] = Link(ownerId, historyId, context, definitions, locks)
                savedByVariation.getOrPut(ownerId to cursor.getString(2)) { mutableListOf() }.addAll(definitions)
            }
        }
        var executions = 0
        db.query("SELECT owner_id, variation_id, state_bytes FROM $DISCARDED_TABLE").use { cursor ->
            while (cursor.moveToNext()) {
                executions += 1
                val snapshot = runCatching {
                    val wrapper = JSONObject(cursor.getBlob(2).toString(Charsets.UTF_8))
                    JSONObject(Base64.getDecoder().decode(wrapper.getString("snapshot_base64")).toString(Charsets.UTF_8))
                }.getOrNull() ?: continue
                savedByVariation.getOrPut(cursor.getString(0) to cursor.getString(1)) { mutableListOf() }
                    .addAll(definitionsOf(snapshot.optJSONObject("config")))
            }
        }
        counts.getOrPut("executions") { linkedMapOf() }["rows"] = executions

        // Every distinct definition once; a document's unit carries the ones its locks name.
        for (definition in distinct(savedByVariation.values.flatten())) {
            val answer = definitionAnswer(definition)
            if (answer.has("error")) {
                count("definitions", "refused:${answer.optJSONObject("error")?.optString("code")}")
            } else {
                count("definitions", if (answer.optBoolean("changed")) "changed" else "unchanged")
            }
        }

        fun locked(definitions: List<Any>, locks: JSONArray): List<Any> {
            val names = locks.objects().map { it.opt("qualified_name") to it.opt("version") }.toSet()
            return definitions.filter { definition ->
                val answer = definitionAnswer(definition)
                (answer.opt("qualified_name") to answer.opt("version")) in names
            }
        }

        // The migrated document, or null after listing the refusal.
        fun documentAnswer(kind: String, recordId: String, unit: String, source: String, locks: Int): JSONObject? {
            val answer = ask(unit)
            val migrated = if (answer.has("error")) answer else answer.optJSONObject("document")
            if (migrated == null || migrated.has("error") || migrated.optJSONObject("document") == null) {
                count(kind, "refused")
                refused.put(
                    refusal(kind, recordId, migrated?.optJSONObject("error") ?: JSONObject().put("code", "unknown"))
                        .put("source", source)
                        .put("locks", locks),
                )
                return null
            }
            val documentEdits = migrated.optJSONArray("edits") ?: JSONArray()
            for (edit in documentEdits.objects()) {
                val key = "${edit.opt("original")} -> ${edit.opt("replacement")}"
                edits[key] = (edits[key] ?: 0) + 1
            }
            val unassociated = migrated.optJSONArray("unassociated_sweeps") ?: JSONArray()
            if (unassociated.length() > 0) {
                count(kind, "with_unassociated_sweeps")
                sweeps.put(JSONObject().put("kind", kind).put("id", recordId).put("unassociated_sweeps", unassociated))
            }
            count(kind, if (documentEdits.length() > 0) "changed" else "unchanged")
            return migrated
        }

        // Each variation's committed document.
        db.query(
            "SELECT owner_id, variation_id, revision, document_json, ddl_digest FROM variation_authority",
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val ownerId = cursor.getString(0)
                val variationId = cursor.getString(1)
                val revision = cursor.getString(2)
                val ddlDigest = cursor.getString(4)
                count("variation_documents", "rows")
                val document = runCatching { JSONObject(cursor.getString(3)) }.getOrNull()
                if (document == null) {
                    count("variation_documents", "unreadable")
                    refused.put(refusal("variation_documents", "$ownerId/$variationId", JSONObject().put("code", "unreadable_document")))
                    continue
                }
                if (document.has("saijiki")) {
                    count("variation_documents", "current")
                    continue
                }
                count("variation_documents", "v1")
                val locks = documentLocks(document.optJSONArray("macro_locks"))
                val definitions = locked(distinct(savedByVariation[ownerId to variationId].orEmpty()), locks)
                val source = document.optString("source")
                val unit = documentUnit(source, document.optString("language"), locks, definitions)
                val migrated = documentAnswer(
                    "variation_documents", "$ownerId/$variationId", unit, source,
                    document.optJSONArray("macro_locks")?.length() ?: 0,
                ) ?: continue
                val newDocument = migrated.getJSONObject("document")
                val newSource = newDocument.getString("source")
                val newDigest = sha256(newSource.toByteArray(Charsets.UTF_8))
                statements += "UPDATE variation_authority SET source = ?, document_json = ?, ddl_digest = ?" +
                    " WHERE owner_id = ? AND variation_id = ?" to
                    arrayOf<Any?>(newSource, LineagePlanner.canonicalJson(newDocument), newDigest, ownerId, variationId)
                count("variation_documents", "written")
                if (newDigest != ddlDigest) {
                    statements += "UPDATE variation_authority_actions SET ddl_digest = ?" +
                        " WHERE owner_id = ? AND variation_id = ? AND revision = ? AND ddl_digest = ?" to
                        arrayOf<Any?>(newDigest, ownerId, variationId, revision, ddlDigest)
                }
            }
        }

        // Each work's instructions, one unit with its performance's link.
        val present = mutableSetOf<String>()
        db.query(
            "SELECT id, normalized_ddl, expanded_ddl, instruction_lang_resolved FROM history_items",
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val historyId = cursor.getString(0)
                val ddl = cursor.getString(1)
                val expandedDdl = if (cursor.isNull(2)) null else cursor.getString(2)
                val language = cursor.getString(3)?.takeIf { it == "ja" || it == "en" } ?: "ja"
                present += historyId
                count("history", "rows")
                val link = links[historyId]
                if (link != null) count("history", "linked")
                val locks = link?.let { documentLocks(it.catalogLocks) } ?: JSONArray()
                val definitions = link?.let { locked(it.definitions, locks) }.orEmpty()
                val migratedTexts = linkedMapOf<String, String>()
                var refusedWork = false
                for ((column, source) in listOf("ddl" to ddl, "expanded_ddl" to expandedDdl)) {
                    if (source.isNullOrEmpty()) continue
                    count("history", "${column}_present")
                    val answer = documentAnswer(
                        "history", "$historyId:$column", documentUnit(source, language, locks, definitions),
                        source, link?.catalogLocks?.length() ?: 0,
                    )
                    if (answer == null) {
                        refusedWork = true
                    } else {
                        val migratedSource = answer.getJSONObject("document").getString("source")
                        if (migratedSource != source) migratedTexts[column] = migratedSource
                    }
                }
                val newDdl = migratedTexts["ddl"] ?: ddl

                val linkDefinitions = mutableListOf<Any>()
                if (link != null && !refusedWork) {
                    for (definition in link.definitions) {
                        val answer = definitionAnswer(definition)
                        if (answer.has("error")) {
                            refusedWork = true
                            count("history_links", "refused")
                            refused.put(refusal("history_links", "${link.ownerId}/$historyId", answer.getJSONObject("error")))
                            break
                        }
                        linkDefinitions += answer.get("definition")
                    }
                }
                if (refusedWork) {
                    // A work is one unit with its link: the link's digest binds it to the instructions.
                    count("history", "rows_left")
                    continue
                }
                if (migratedTexts.isNotEmpty()) {
                    statements += "UPDATE history_items SET normalized_ddl = ?, expanded_ddl = ? WHERE id = ?" to
                        arrayOf<Any?>(newDdl, migratedTexts["expanded_ddl"] ?: expandedDdl, historyId)
                    count("history", "rows_written")
                }
                if (link != null) {
                    linkStatement(link, linkDefinitions, newDdl)?.let {
                        statements += it
                        count("history_links", "written")
                    }
                }
            }
        }

        // A link whose work is gone still moves its definitions and locks.
        for ((historyId, link) in links) {
            if (historyId in present) continue
            count("history_links", "without_history")
            val linkAnswers = link.definitions.map(::definitionAnswer)
            val failed = linkAnswers.firstOrNull { it.has("error") }
            if (failed != null) {
                count("history_links", "refused")
                refused.put(refusal("history_links", "${link.ownerId}/$historyId", failed.getJSONObject("error")))
                continue
            }
            linkStatement(link, linkAnswers.map { it.get("definition") }, null)?.let {
                statements += it
                count("history_links", "written")
            }
        }

        val report = JSONObject()
        for ((kind, tally) in counts) report.put(kind, JSONObject(tally as Map<*, *>))
        return Plan(
            statements = statements,
            executions = executions,
            report = report
                .put("edits", JSONObject(edits as Map<*, *>))
                .put("refused_records", refused)
                .put("unassociated_sweep_records", sweeps),
        )
    }

    /** Rewrite one frozen fork context: its definitions, its locks, and the work's digest. */
    private fun linkStatement(link: Link, definitions: List<Any>, ddl: String?): Pair<String, Array<Any?>>? {
        val moved = link.definitions.associate { definition ->
            val answer = definitionAnswer(definition)
            (answer.opt("qualified_name") to answer.opt("version")) to answer.optString("digest")
        }
        val locks = JSONArray()
        for (lock in link.catalogLocks.objects()) {
            val digest = moved[lock.opt("qualified_name") to lock.opt("version")]
            // The catalog keeps bare hex; sha256: is the document's form.
            locks.put(
                if (digest.isNullOrEmpty()) lock else JSONObject(lock.toString()).put("digest", digest.removePrefix("sha256:")),
            )
        }
        // Changed in place: a copy through its text would respell numbers (1.0 as 1)
        // and rewrite a context that did not change. Each link is rewritten once.
        val original = LineagePlanner.canonicalJson(link.context)
        val context = link.context
        val config = context.optJSONObject("config") ?: JSONObject()
        if (definitions.isNotEmpty() || config.has("definitions")) {
            config.put("definitions", JSONArray(definitions))
        }
        context.put("config", config)
        context.put("macro_catalog", (context.optJSONObject("macro_catalog") ?: JSONObject()).put("definition_locks", locks))
        if (ddl != null) context.put("ddl_digest", sha256(ddl.toByteArray(Charsets.UTF_8)))
        val encoded = LineagePlanner.canonicalJson(context)
        if (encoded == original) return null
        val bytes = encoded.toByteArray(Charsets.UTF_8)
        return "UPDATE pipeline_history_links SET ddl_digest = ?, fork_context_bytes = ?, fork_context_digest = ?" +
            " WHERE owner_id = ? AND history_id = ?" to
            arrayOf<Any?>(context.getString("ddl_digest"), bytes, sha256(bytes), link.ownerId, link.historyId)
    }

    /** The core's answer for one unit, asked once per distinct unit. */
    private fun ask(unit: String): JSONObject = answers.getOrPut(unit) {
        val started = elapsedMillis()
        val output = migrate(unit.toByteArray(Charsets.UTF_8))
        coreCalls += 1
        coreMillis += elapsedMillis() - started
        runCatching { JSONObject(output.toString(Charsets.UTF_8)) }
            .getOrElse { JSONObject().put("error", JSONObject().put("code", "unreadable_answer")) }
            .let { answer ->
                // An input the core could not read at all comes back as a bare code.
                val error = answer.opt("error")
                if (error is String) answer.put("error", JSONObject().put("code", error)) else answer
            }
    }

    private fun definitionAnswer(definition: Any): JSONObject {
        val answer = ask(LineagePlanner.canonicalJson(JSONObject().put("definitions", JSONArray().put(definition))))
        return answer.optJSONArray("definitions")?.optJSONObject(0)
            ?: JSONObject().put("error", answer.optJSONObject("error") ?: JSONObject().put("code", "unknown"))
    }

    companion object {
        /** The table whose rows the migration discards instead of moving. */
        const val DISCARDED_TABLE = "pipeline_candidate_executions"

        /** The app setting that records the migration was written; the Server's name. */
        const val DONE_SETTING = "saijiki_v2_saved_records"

        private val LOCK_FIELDS = listOf("qualified_name", "version", "digest", "aliases")

        fun alreadyWritten(db: SupportSQLiteDatabase): Boolean =
            db.query("SELECT 1 FROM app_settings WHERE key = ?", arrayOf<Any>(DONE_SETTING)).use { it.moveToFirst() }

        /**
         * The locks as a document holds them. A macro catalog freezes each lock's
         * digest as bare hex; a document's lock carries it as `sha256:<hex>`, and
         * the core reads only that form.
         */
        fun documentLocks(locks: JSONArray?): JSONArray {
            val moved = JSONArray()
            for (index in 0 until (locks?.length() ?: 0)) {
                val lock = locks!!.get(index)
                if (lock !is JSONObject) {
                    moved.put(lock)
                    continue
                }
                val entry = JSONObject()
                for (key in LOCK_FIELDS) if (lock.has(key)) entry.put(key, lock.get(key))
                val digest = entry.opt("digest")
                if (digest is String && !digest.startsWith("sha256:")) entry.put("digest", "sha256:$digest")
                moved.put(entry)
            }
            return moved
        }

        private fun documentUnit(source: String, language: String, locks: JSONArray, definitions: List<Any>): String =
            LineagePlanner.canonicalJson(
                JSONObject()
                    .put("document", JSONObject().put("source", source).put("language", language).put("macro_locks", locks))
                    .put("definitions", JSONArray(distinct(definitions))),
            )

        private fun definitionsOf(config: JSONObject?): List<Any> {
            val definitions = config?.optJSONArray("definitions") ?: return emptyList()
            return (0 until definitions.length()).map { definitions.get(it) }
        }

        /** Each saved definition once: many performances freeze the same catalog. */
        private fun distinct(definitions: List<Any>): List<Any> =
            definitions.associateBy { LineagePlanner.canonicalJson(it) }.values.toList()

        private fun refusal(kind: String, id: String, error: JSONObject): JSONObject =
            JSONObject().put("kind", kind).put("id", id).put("error", error)

        private fun JSONArray.objects(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }

        private fun sha256(bytes: ByteArray): String =
            MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    }
}
