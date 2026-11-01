package app.inku.mobile.data.db

import app.inku.mobile.pipeline.NativePipelineBridge
import java.io.File
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SaijikiV3MigrationTest {
    private fun migration(v1: (ByteArray) -> ByteArray = NativePipelineBridge::migrateSaijikiV1) =
        SaijikiV3Migration(v1, NativePipelineBridge::migrateSaijikiV2, true)

    private fun schema(host: HostSqlite) {
        listOf(
            "CREATE TABLE app_settings(key TEXT, value_json TEXT, updated_at INTEGER)",
            "CREATE TABLE history_items(id TEXT, normalized_ddl TEXT, instruction_lang_resolved TEXT)",
            "CREATE TABLE pipeline_history_links(owner_id TEXT, history_id TEXT, variation_id TEXT, fork_context_bytes BLOB, fork_context_digest TEXT, ddl_digest TEXT)",
            "CREATE TABLE variation_authority(owner_id TEXT, variation_id TEXT, revision TEXT, source TEXT, document_json TEXT, ddl_digest TEXT)",
            "CREATE TABLE variation_authority_actions(owner_id TEXT, variation_id TEXT, revision TEXT, ddl_digest TEXT)",
            "CREATE TABLE pipeline_candidate_executions(owner_id TEXT, variation_id TEXT, state_bytes BLOB)",
        ).forEach(host.db::execSQL)
    }

    @Test fun editionsAndIdempotenceUseRealCore() {
        HostSqlite().use { host ->
            schema(host)
            for ((id, edition) in listOf("v1" to null, "v2" to "inku.saijiki.v2", "v3" to "inku.saijiki.v3", "other" to "inku.saijiki.v4")) {
                val doc = JSONObject().put("source", "青の細筆の線を3個引く。").put("language", "ja").put("macro_locks", org.json.JSONArray())
                if (edition != null) doc.put("saijiki", edition)
                host.db.execSQL("INSERT INTO variation_authority VALUES (?, ?, ?, ?, ?, ?)", arrayOf<Any>("u", id, "1", doc.getString("source"), doc.toString(), "old"))
            }
            val report = migration().runOnce(host.db)!!
            assertEquals(1, report.getJSONArray("refused_records").length())
            assertEquals("other_edition", report.getJSONArray("refused_records").getJSONObject(0).getJSONObject("error").getString("code"))
            assertEquals(2, report.getJSONObject("variation_documents").getInt("written"))
            host.db.query("SELECT document_json FROM variation_authority WHERE variation_id = 'v2'").use {
                assertTrue(it.moveToFirst()); val doc = JSONObject(it.getString(0))
                assertEquals("inku.saijiki.v3", doc.getString("saijiki")); assertTrue(doc.getString("source").contains("ガッシュ"))
            }
            assertNull(migration().runOnce(host.db))
        }
    }

    @Test fun failureRollsBackAndAllowsRetry() {
        HostSqlite().use { host ->
            schema(host)
            host.db.execSQL("INSERT INTO history_items VALUES ('h', '黒い太筆の線。', 'ja')")
            try { migration { error("injected core failure") }.runOnce(host.db); fail() } catch (_: IllegalStateException) { }
            assertEquals("[[\"黒い太筆の線。\"]]", host.rows("SELECT normalized_ddl FROM history_items"))
            assertFalse(SaijikiV3Migration.alreadyWritten(host.db))
            assertNotNull(migration().runOnce(host.db))
        }
    }

    @Test fun missingHistoryLanguageUsesSavedConfigOrDdlDetection() {
        HostSqlite().use { host ->
            schema(host)
            host.db.execSQL("INSERT INTO app_settings VALUES ('saijiki_v2_saved_records', '{}', 0)")
            val source = "Draw a blue fine-brush line."
            val context = JSONObject().put("ddl_digest", "old").put("config", JSONObject().put("language", "en"))
                .put("macro_catalog", JSONObject().put("definition_locks", org.json.JSONArray()))
            val bytes = app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(context).toByteArray()
            val digest = java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            host.db.execSQL("INSERT INTO pipeline_history_links VALUES ('u', 'linked', 'v', ?, ?, 'old')", arrayOf<Any>(bytes, digest))
            for (id in listOf("linked", "unlinked")) host.db.execSQL("INSERT INTO history_items VALUES (?, ?, NULL)", arrayOf<Any>(id, source))
            val report = migration().runOnce(host.db)!!
            assertEquals(0, report.getJSONArray("refused_records").length())
            host.db.query("SELECT normalized_ddl FROM history_items").use {
                var count = 0
                while (it.moveToNext()) { assertEquals("Draw a blue gouache line.", it.getString(0)); count++ }
                assertEquals(2, count)
            }
        }
    }

    @Test fun boundDefinitionsRecoverAcrossVariationsAndOnlyMatchingDigestsMove() {
        HostSqlite().use { host ->
            schema(host)
            val definitions = JSONObject(productFile("core/crates/inku-ddl/tests/fixtures/nature-leaves-1.0-package.json").readText()).getJSONArray("entries")
            val definition = (0 until definitions.length()).map { definitions.getJSONObject(it).getJSONObject("definition") }.first { it.getString("heading") == "下草" }
            val answer = JSONObject(NativePipelineBridge.migrateSaijikiV2(JSONObject().put("definitions", org.json.JSONArray().put(definition)).toString().toByteArray()).decodeToString()).getJSONArray("definitions").getJSONObject(0)
            assertFalse(answer.has("error"))
            val lock = JSONObject().put("qualified_name", answer.getString("qualified_name")).put("version", answer.getString("version")).put("digest", answer.getString("old_digest"))
            val wrong = JSONObject(lock.toString()).put("digest", "sha256:" + "0".repeat(64))
            val locks = org.json.JSONArray().put(lock).put(wrong)
            val context = JSONObject().put("ddl_digest", "old").put("config", JSONObject().put("definitions", org.json.JSONArray().put(definition)))
                .put("macro_catalog", JSONObject().put("definition_locks", locks))
            val bytes = app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(context).toByteArray()
            val digest = java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            host.db.execSQL("INSERT INTO pipeline_history_links VALUES (?, ?, ?, ?, ?, ?)", arrayOf<Any>("u", "orphan", "local", bytes, digest, "old"))
            for ((id, item) in listOf("local" to lock, "foreign" to lock, "wrong" to wrong)) {
                val doc = JSONObject().put("source", "赤い円。").put("language", "ja").put("saijiki", "inku.saijiki.v2").put("macro_locks", org.json.JSONArray().put(item))
                host.db.execSQL("INSERT INTO variation_authority VALUES (?, ?, '1', ?, ?, 'old')", arrayOf<Any>("u", id, "赤い円。", doc.toString()))
            }
            val report = migration().runOnce(host.db)!!
            assertEquals(2, report.getJSONObject("variation_documents").getInt("written"))
            assertEquals(1, report.getJSONArray("refused_records").length())
            host.db.query("SELECT fork_context_bytes FROM pipeline_history_links").use {
                assertTrue(it.moveToFirst())
                val moved = JSONObject(it.getBlob(0).decodeToString()).getJSONObject("macro_catalog").getJSONArray("definition_locks")
                assertEquals(answer.getString("digest").removePrefix("sha256:"), moved.getJSONObject(0).getString("digest"))
                assertEquals(wrong.getString("digest"), moved.getJSONObject(1).getString("digest"))
            }
        }
    }

    /** Explicit opt-in, on a separately copied database only. No device access. */
    @Test fun coreHistoricalFallbackRecoversAnOtherwiseMissingDefinition() {
        HostSqlite().use { host ->
            schema(host)
            val lock = JSONObject().put("qualified_name", "Nature.下草").put("version", "1.0.0")
                .put("digest", "sha256:88046b24987a2600eeb8b985f36bc15222202a5758a0f4a7638e514dd6af2aea")
            val doc = JSONObject().put("source", "黒い太筆の線を引く。").put("language", "ja").put("saijiki", "inku.saijiki.v2")
                .put("macro_locks", org.json.JSONArray().put(lock))
            host.db.execSQL("INSERT INTO variation_authority VALUES ('u', 'fallback', '1', ?, ?, 'old')", arrayOf<Any>(doc.getString("source"), doc.toString()))
            val context = JSONObject().put("ddl_digest", "old").put("config", JSONObject().put("definitions", org.json.JSONArray()))
                .put("macro_catalog", JSONObject().put("definition_locks", org.json.JSONArray().put(lock)))
            val bytes = app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(context).toByteArray()
            val digest = java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            host.db.execSQL("INSERT INTO history_items VALUES ('recovered', ?, 'ja')", arrayOf<Any>(doc.getString("source")))
            host.db.execSQL("INSERT INTO pipeline_history_links VALUES ('u', 'recovered', 'fallback', ?, ?, 'old')", arrayOf<Any>(bytes, digest))
            val packageEntries = JSONObject(productFile("core/crates/inku-ddl/tests/fixtures/nature-leaves-1.0-package.json").readText()).getJSONArray("entries")
            val wrongDefinition = (0 until packageEntries.length()).map { packageEntries.getJSONObject(it).getJSONObject("definition") }.first { it.getString("heading") == "下草" }
            fun edit(value: Any?): Boolean {
                if (value is JSONObject) {
                    if (value.optString("expr") == "exact_decimal") { value.put("value", "0.123"); return true }
                    return value.keys().asSequence().any { edit(value.opt(it)) }
                }
                if (value is org.json.JSONArray) return (0 until value.length()).any { edit(value.opt(it)) }
                return false
            }
            assertTrue(edit(wrongDefinition))
            val wrongContext = JSONObject(context.toString()).put("config", JSONObject()
                .put("definitions", org.json.JSONArray().put(wrongDefinition)).put("macro_summaries", org.json.JSONArray().put("下草")))
            val wrongBytes = app.inku.mobile.data.lineage.LineagePlanner.canonicalJson(wrongContext).toByteArray()
            val wrongDigest = java.security.MessageDigest.getInstance("SHA-256").digest(wrongBytes).joinToString("") { "%02x".format(it) }
            host.db.execSQL("INSERT INTO history_items VALUES ('wrong-copy', ?, 'ja')", arrayOf<Any>(doc.getString("source")))
            host.db.execSQL("INSERT INTO pipeline_history_links VALUES ('u', 'wrong-copy', 'fallback', ?, ?, 'old')", arrayOf<Any>(wrongBytes, wrongDigest))
            val report = migration().runOnce(host.db)!!
            assertEquals(0, report.getJSONArray("refused_records").length())
            assertEquals(1, report.getJSONObject("variation_documents").getInt("written"))
            host.db.query("SELECT fork_context_bytes FROM pipeline_history_links WHERE history_id = 'recovered'").use {
                assertTrue(it.moveToFirst())
                val saved = JSONObject(it.getBlob(0).decodeToString())
                assertEquals(1, saved.getJSONObject("config").getJSONArray("definitions").length())
                assertEquals(1, saved.getJSONObject("config").getJSONArray("macro_summaries").length())
                assertNotEquals(lock.getString("digest").removePrefix("sha256:"), saved.getJSONObject("macro_catalog").getJSONArray("definition_locks").getJSONObject(0).getString("digest"))
            }
            host.db.query("SELECT fork_context_bytes FROM pipeline_history_links WHERE history_id = 'wrong-copy'").use {
                assertTrue(it.moveToFirst())
                val saved = JSONObject(it.getBlob(0).decodeToString()).getJSONObject("config")
                assertEquals(1, saved.getJSONArray("definitions").length())
                assertEquals(1, saved.getJSONArray("macro_summaries").length())
            }
        }
    }

    /** Explicit opt-in, on a separately copied database only. No device access. */
    @Test fun copiedDatabaseRehearsal() {
        val path = System.getenv("INKU_SAIJIKI_REHEARSAL_DB") ?: return
        require(path.contains("/local/evidence/android/tools-v3-step5-20261101/"))
        val folder = requireNotNull(File(path).parentFile)
        val journal = folder.resolve("journal.jsonl")
        journal.createNewFile()
        Files.setPosixFilePermissions(journal.toPath(), PosixFilePermissions.fromString("rw-------"))
        fun call(version: Int, input: ByteArray): ByteArray {
            val answer = if (version == 1) NativePipelineBridge.migrateSaijikiV1(input) else NativePipelineBridge.migrateSaijikiV2(input)
            journal.appendText(JSONObject().put("version", version).put("input", JSONObject(input.decodeToString())).put("answer", JSONObject(answer.decodeToString())).toString() + "\n")
            return answer
        }
        HostSqlite(path).use { host ->
            if (System.getenv("INKU_SAIJIKI_ORPHAN_ONLY") == "1") {
                check(SaijikiV3Migration.alreadyWritten(host.db))
                inspectOrphanLocks(host, folder)
                return
            }
            if (System.getenv("INKU_SAIJIKI_COMPILE_ONLY") == "1") {
                check(SaijikiV3Migration.alreadyWritten(host.db))
                compileMigratedRecords(host, folder)
                inspectOrphanLocks(host, folder)
                return
            }
            val report = SaijikiV3Migration({ call(1, it) }, { call(2, it) }, true).runOnce(host.db)!!
            val file = folder.resolve("report.json")
            file.createNewFile()
            Files.setPosixFilePermissions(file.toPath(), PosixFilePermissions.fromString("rw-------"))
            file.writeText(report.toString(2))
            assertNull(migration().runOnce(host.db))
            compileMigratedRecords(host, folder)
            inspectOrphanLocks(host, folder)
        }
    }
}
