package app.inku.mobile.data.db

import androidx.sqlite.db.SupportSQLiteDatabase
import app.inku.mobile.data.lineage.LineagePlanner
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject

/** Migrate saved source and its linked digests together, once, before reading works. */
internal class PluginNamesV2Migration(
    private val migrate: (ByteArray) -> ByteArray,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private data class Link(val owner: String, val variation: String, val context: JSONObject, val digest: String)

    fun runOnce(db: SupportSQLiteDatabase): JSONObject? {
        fun done() = db.query("SELECT 1 FROM app_settings WHERE key = ?", arrayOf<Any>(DONE_SETTING)).use { it.moveToFirst() }
        if (done()) return null
        db.beginTransaction()
        try {
            if (done()) return null
            val started = System.nanoTime()
            val refused = JSONArray()
            val links = mutableMapOf<String, Link>()
            val invalidLinks = mutableSetOf<String>()
            val byVariation = mutableMapOf<Pair<String, String>, MutableList<Any>>()
            db.query("SELECT owner_id, history_id, variation_id, fork_context_bytes, fork_context_digest, ddl_digest FROM pipeline_history_links").use { cursor ->
                while (cursor.moveToNext()) {
                    val owner = cursor.getString(0); val id = cursor.getString(1); val variation = cursor.getString(2)
                    val bytes = cursor.getBlob(3)
                    val context = runCatching { JSONObject(bytes.toString(Charsets.UTF_8)) }.getOrNull()
                    if (sha(bytes) != cursor.getString(4) || context == null || context.optString("ddl_digest") != cursor.getString(5)) {
                        invalidLinks.add(id); refused.put(problem("link", id, "unreadable_context")); continue
                    }
                    links[id] = Link(owner, variation, context, context.optString("ddl_digest"))
                    byVariation.getOrPut(owner to variation) { mutableListOf() }.addAll(definitions(context))
                }
            }
            var changedHistory = 0; var changedVariation = 0
            fun ask(kind: String, id: String, source: String, language: String, locks: JSONArray, definitions: List<Any>): String? {
                val document = JSONObject().put("source", source).put("language", language).put("macro_locks", locks)
                val unit = JSONObject().put("document", document).put("definitions", JSONArray(definitions))
                val answer = JSONObject(migrate(LineagePlanner.canonicalJson(unit).toByteArray()).toString(Charsets.UTF_8))
                val result = answer.optJSONObject("document")
                if (answer.optString("schema") != "inku.plugin-name-migration.v1" || result == null) {
                    refused.put(problem(kind, id, answer.optString("error", "core_refused"))); return null
                }
                if (LineagePlanner.canonicalJson(result.optJSONArray("macro_locks")) != LineagePlanner.canonicalJson(locks) || result.opt("source") !is String) {
                    refused.put(problem(kind, id, "invalid_core_answer")); return null
                }
                answer.optJSONArray("problems")?.takeIf { it.length() > 0 }?.let {
                    refused.put(problem(kind, id, "partial").put("problems", it))
                }
                return result.getString("source")
            }
            db.query("SELECT id, normalized_ddl, instruction_lang_resolved FROM history_items").use { cursor ->
                while (cursor.moveToNext()) {
                    val id = cursor.getString(0)
                    if (cursor.isNull(1) || id in invalidLinks) continue
                    val source = cursor.getString(1); if (source.isEmpty()) continue
                    val link = links[id]
                    if (link != null && link.digest != sha(source.toByteArray())) {
                        refused.put(problem("history", id, "link_digest_mismatch")); continue
                    }
                    val locks = SaijikiV1Migration.documentLocks(link?.context?.optJSONObject("macro_catalog")?.optJSONArray("definition_locks"))
                    val language = cursor.getString(2).takeIf { it == "ja" || it == "en" } ?: "ja"
                    val new = ask("history", id, source, language, locks, link?.let { definitions(it.context) }.orEmpty()) ?: continue
                    if (new == source) continue
                    val digest = sha(new.toByteArray())
                    if (link != null) {
                        val context = JSONObject(link.context.toString()).put("ddl_digest", digest)
                        val bytes = LineagePlanner.canonicalJson(context).toByteArray()
                        db.execSQL("UPDATE pipeline_history_links SET ddl_digest = ?, fork_context_bytes = ?, fork_context_digest = ? WHERE owner_id = ? AND history_id = ?", arrayOf<Any?>(digest, bytes, sha(bytes), link.owner, id))
                    }
                    db.execSQL("UPDATE history_items SET normalized_ddl = ? WHERE id = ?", arrayOf<Any?>(new, id))
                    changedHistory++
                }
            }
            db.query("SELECT owner_id, variation_id, revision, source, document_json, ddl_digest FROM variation_authority").use { cursor ->
                while (cursor.moveToNext()) {
                    val owner = cursor.getString(0); val id = cursor.getString(1); val revision = cursor.getString(2)
                    val source = cursor.getString(3); val oldDigest = cursor.getString(5)
                    val doc = runCatching { JSONObject(cursor.getString(4)) }.getOrNull()
                    if (doc == null || doc.optString("source") != source || sha(source.toByteArray()) != oldDigest) {
                        refused.put(problem("variation", "$owner/$id", "unreadable_document")); continue
                    }
                    val defs = byVariation[owner to id].orEmpty().associateBy { LineagePlanner.canonicalJson(it) }.values.toList()
                    val language = doc.optString("language").takeIf { it == "ja" || it == "en" } ?: "ja"
                    val locks = doc.optJSONArray("macro_locks") ?: JSONArray()
                    val new = ask("variation", "$owner/$id", source, language, locks, defs) ?: continue
                    if (new == source) continue
                    val digest = sha(new.toByteArray())
                    db.execSQL("UPDATE variation_authority SET source = ?, document_json = ?, ddl_digest = ? WHERE owner_id = ? AND variation_id = ?", arrayOf<Any?>(new, LineagePlanner.canonicalJson(doc.put("source", new)), digest, owner, id))
                    db.execSQL("UPDATE variation_authority_actions SET ddl_digest = ? WHERE owner_id = ? AND variation_id = ? AND revision = ? AND ddl_digest = ?", arrayOf<Any?>(digest, owner, id, revision, oldDigest))
                    changedVariation++
                }
            }
            val report = JSONObject().put("history_changed", changedHistory).put("variation_changed", changedVariation)
                .put("refused_records", refused).put("total_ms", (System.nanoTime() - started) / 1_000_000)
            db.execSQL("INSERT INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?)", arrayOf<Any>(DONE_SETTING, LineagePlanner.canonicalJson(report), now()))
            db.setTransactionSuccessful()
            return report
        } finally { db.endTransaction() }
    }

    companion object {
        const val DONE_SETTING = "plugin_names_v2_saved_records"
        private fun definitions(context: JSONObject): List<Any> {
            val items = context.optJSONObject("config")?.optJSONArray("definitions") ?: return emptyList()
            return (0 until items.length()).map { items.get(it) }
        }
        private fun problem(kind: String, id: String, code: String) = JSONObject().put("kind", kind).put("id", id).put("code", code)
        private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    }
}
