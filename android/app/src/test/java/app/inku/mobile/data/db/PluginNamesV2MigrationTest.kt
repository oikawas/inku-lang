package app.inku.mobile.data.db

import app.inku.mobile.data.lineage.LineagePlanner
import app.inku.mobile.pipeline.NativePipelineBridge
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** A JVM SQLite database exercises the same transaction and JNI core as the host. */
class PluginNamesV2MigrationTest {
    private fun digest(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    @Test fun unchangedAndRefusedUnitsAreLeftAsTheyWere() {
        HostSqlite().use { host ->
            val db = host.db
            listOf(
                "CREATE TABLE app_settings(key TEXT, value_json TEXT, updated_at INTEGER)",
                "CREATE TABLE history_items(id TEXT, normalized_ddl TEXT, instruction_lang_resolved TEXT)",
                "CREATE TABLE pipeline_history_links(owner_id TEXT, history_id TEXT, variation_id TEXT, fork_context_bytes BLOB, fork_context_digest TEXT, ddl_digest TEXT)",
                "CREATE TABLE variation_authority(owner_id TEXT, variation_id TEXT, revision TEXT, source TEXT, document_json TEXT, ddl_digest TEXT)",
                "CREATE TABLE variation_authority_actions(owner_id TEXT, variation_id TEXT, revision TEXT, ddl_digest TEXT)",
            ).forEach(db::execSQL)
            db.execSQL("INSERT INTO history_items VALUES (?, ?, ?)", arrayOf<Any>("unchanged", "赤い円。", "ja"))
            val source = "Garden.薔薇。"; val oldDigest = digest(source.toByteArray())
            val context = JSONObject().put("ddl_digest", oldDigest).put("config", JSONObject().put("definitions", JSONArray().put(JSONObject())))
                .put("macro_catalog", JSONObject().put("definition_locks", JSONArray()))
            val bytes = LineagePlanner.canonicalJson(context).toByteArray()
            db.execSQL("INSERT INTO history_items VALUES (?, ?, ?)", arrayOf<Any>("refused", source, "ja"))
            db.execSQL("INSERT INTO pipeline_history_links VALUES (?, ?, ?, ?, ?, ?)", arrayOf<Any>("u", "refused", "v", bytes, digest(bytes), oldDigest))
            val partialSource = "Garden.Flower。"; val partialDigest = digest(partialSource.toByteArray())
            val missing = JSONObject().put("qualified_name", "Garden.Flower").put("version", "1.0.0").put("digest", "0".repeat(64))
            val partialContext = JSONObject().put("ddl_digest", partialDigest).put("config", JSONObject().put("definitions", JSONArray()))
                .put("macro_catalog", JSONObject().put("definition_locks", JSONArray().put(missing)))
            val partialBytes = LineagePlanner.canonicalJson(partialContext).toByteArray()
            db.execSQL("INSERT INTO history_items VALUES (?, ?, ?)", arrayOf<Any>("partial", partialSource, "ja"))
            db.execSQL("INSERT INTO pipeline_history_links VALUES (?, ?, ?, ?, ?, ?)", arrayOf<Any>("u", "partial", "v2", partialBytes, digest(partialBytes), partialDigest))
            val report = PluginNamesV2Migration(NativePipelineBridge::migratePluginNames).runOnce(db)!!
            assertEquals(0, report.getInt("history_changed"))
            assertEquals("invalid_plugin_migration_input", report.getJSONArray("refused_records").getJSONObject(0).getString("code"))
            assertEquals("partial", report.getJSONArray("refused_records").getJSONObject(1).getString("code"))
            db.query("SELECT normalized_ddl FROM history_items WHERE id = 'refused'").use { assertTrue(it.moveToFirst()); assertEquals(source, it.getString(0)) }
            db.query("SELECT normalized_ddl FROM history_items WHERE id = 'unchanged'").use { assertTrue(it.moveToFirst()); assertEquals("赤い円。", it.getString(0)) }
        }
    }

    @Test fun migrationRewritesLinkedSourcesOnceAndRollsBackFailures() {
        val host = HostSqlite()
        val db = host.db
        fun query(sql: String) = db.query(sql)
        listOf(
                "CREATE TABLE app_settings(key TEXT, value_json TEXT, updated_at INTEGER)",
                "CREATE TABLE history_items(id TEXT, normalized_ddl TEXT, instruction_lang_resolved TEXT, score TEXT, svg TEXT)",
                "CREATE TABLE pipeline_history_links(owner_id TEXT, history_id TEXT, variation_id TEXT, fork_context_bytes BLOB, fork_context_digest TEXT, ddl_digest TEXT)",
                "CREATE TABLE variation_authority(owner_id TEXT, variation_id TEXT, revision TEXT, source TEXT, document_json TEXT, ddl_digest TEXT)",
                "CREATE TABLE variation_authority_actions(owner_id TEXT, variation_id TEXT, revision TEXT, ddl_digest TEXT)",
            ).forEach(db::execSQL)
        val definition = JSONObject(productFile("core/crates/inku-ddl/tests/fixtures/nature-leaves-2.1-v1.json").readText())
            .getJSONArray("entries").getJSONObject(0).getJSONObject("definition")
        val catalogInput = JSONObject().put("maximum_entries", 1).put("canonical", JSONArray().put(JSONObject()
            .put("source_id", "test").put("definition_json", definition.toString()).put("summary", "leaves")))
        val entry = JSONObject(NativePipelineBridge.resolveMacroCatalog(catalogInput.toString().toByteArray()).decodeToString())
            .getJSONArray("entries").getJSONObject(0)
        val lock = JSONObject().put("qualified_name", entry.getString("qualified_name")).put("version", entry.getString("version")).put("digest", entry.getString("digest"))
        val source = "Nature.若葉。"; val oldDigest = digest(source.toByteArray())
        val context = JSONObject().put("ddl_digest", oldDigest).put("config", JSONObject().put("definitions", JSONArray().put(definition)))
            .put("macro_catalog", JSONObject().put("definition_locks", JSONArray().put(lock)))
        val contextBytes = LineagePlanner.canonicalJson(context).toByteArray()
        val document = JSONObject().put("source", source).put("language", "ja")
            .put("macro_locks", SaijikiV1Migration.documentLocks(JSONArray().put(lock)))
        db.execSQL("INSERT INTO history_items VALUES (?, ?, ?, ?, ?)", arrayOf<Any>("h", source, "ja", "score", "svg"))
        db.execSQL("INSERT INTO pipeline_history_links VALUES (?, ?, ?, ?, ?, ?)", arrayOf<Any>("u", "h", "v", contextBytes, digest(contextBytes), oldDigest))
        db.execSQL("INSERT INTO variation_authority VALUES (?, ?, ?, ?, ?, ?)", arrayOf<Any>("u", "v", "1", source, LineagePlanner.canonicalJson(document), oldDigest))
        db.execSQL("INSERT INTO variation_authority_actions VALUES (?, ?, ?, ?)", arrayOf<Any>("u", "v", "1", oldDigest))
        try {
            val invalidLocks = PluginNamesV2Migration({ input ->
                val answer = JSONObject(NativePipelineBridge.migratePluginNames(input).decodeToString())
                answer.getJSONObject("document").put("macro_locks", JSONArray())
                answer.toString().toByteArray()
            }).runOnce(db)!!
            assertEquals(2, invalidLocks.getJSONArray("refused_records").length())
            query("SELECT normalized_ddl FROM history_items").use { assertTrue(it.moveToFirst()); assertEquals(source, it.getString(0)) }
            db.execSQL("DELETE FROM app_settings")
            var calls = 0
            try { PluginNamesV2Migration({ input -> if (++calls == 2) error("fixture failure") else NativePipelineBridge.migratePluginNames(input) }).runOnce(db); fail() }
            catch (_: IllegalStateException) { }
            query("SELECT normalized_ddl FROM history_items").use { assertTrue(it.moveToFirst()); assertEquals(source, it.getString(0)) }
            query("SELECT key FROM app_settings").use { assertFalse(it.moveToFirst()) }
            val report = PluginNamesV2Migration(NativePipelineBridge::migratePluginNames).runOnce(db)!!
            assertEquals(1, report.getInt("history_changed")); assertEquals(1, report.getInt("variation_changed"))
            val newSource = "｛若葉｝。"; val newDigest = digest(newSource.toByteArray())
            query("SELECT normalized_ddl, score, svg FROM history_items").use { assertTrue(it.moveToFirst()); assertEquals(newSource, it.getString(0)); assertEquals("score", it.getString(1)); assertEquals("svg", it.getString(2)) }
            query("SELECT source, document_json, ddl_digest FROM variation_authority").use { assertTrue(it.moveToFirst()); assertEquals(newSource, it.getString(0)); assertEquals(newSource, JSONObject(it.getString(1)).getString("source")); assertEquals(newDigest, it.getString(2)) }
            query("SELECT ddl_digest, fork_context_bytes, fork_context_digest FROM pipeline_history_links").use { assertTrue(it.moveToFirst()); assertEquals(newDigest, it.getString(0)); assertEquals(newDigest, JSONObject(it.getBlob(1).decodeToString()).getString("ddl_digest")); assertEquals(digest(it.getBlob(1)), it.getString(2)) }
            query("SELECT ddl_digest FROM variation_authority_actions").use { assertTrue(it.moveToFirst()); assertEquals(newDigest, it.getString(0)) }
            assertNull(PluginNamesV2Migration(NativePipelineBridge::migratePluginNames).runOnce(db))
        } finally { host.close() }
    }
}
