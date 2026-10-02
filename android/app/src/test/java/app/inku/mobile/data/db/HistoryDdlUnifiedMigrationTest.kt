package app.inku.mobile.data.db

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class HistoryDdlUnifiedMigrationTest {
    @Test
    fun actualV13MigrationKeepsProtectedValuesAndConstraintsAndAdmitsV13WithoutReset() {
        assertTrue(RoomV10ResetCoordinator.isNonDestructiveVersion(13))
        assertTrue(RoomV10ResetCoordinator.isNonDestructiveVersion(14))
        assertFalse(RoomV10ResetCoordinator.isNonDestructiveVersion(15))
        HostSqlite().use { host ->
            val entities = host.createSchema(13)
            val history = entities.single { it.getString("tableName") == "history_items" }
            val fields = history.getJSONArray("fields")
            val fixtures = JSONArray(productFile("persistence/fixtures/ddl-selection.json").readText())
            val before = mutableListOf<Map<String, Any?>>()
            for (i in 0 until fixtures.length()) {
                val fixture = fixtures.getJSONObject(i)
                val row = (0 until fields.length()).associate { index ->
                    val field = fields.getJSONObject(index)
                    val name = field.getString("columnName")
                    name to when (name) {
                        "id" -> fixture.getString("id")
                        "normalized_ddl" -> fixture.opt("ddl").takeUnless { it == JSONObject.NULL }
                        "expanded_ddl" -> fixture.opt("expanded_ddl").takeUnless { it == JSONObject.NULL }
                        "render_hash" -> "same-render-hash"
                        "starred" -> 1
                        "trashed" -> 0
                        else -> if (field.getString("affinity") == "INTEGER") 100 + index else "$i:$name: \n"
                    }
                }
                before += row
                host.db.execSQL(
                    "INSERT INTO history_items (${row.keys.joinToString(",")}) VALUES (${row.keys.joinToString(",") { "?" }})",
                    row.values.toTypedArray(),
                )
            }
            host.db.execSQL("INSERT INTO lineage_nodes(id, history_id, state, at) VALUES ('root', 'null-transfer', 'active', 7)")
            host.db.execSQL("INSERT INTO app_settings(key, value_json, updated_at) VALUES (?, '{\"kept\":true}', 8)", arrayOf(SaijikiV1Migration.DONE_SETTING))
            val objectsBefore = host.rows("SELECT type, name, sql FROM sqlite_master WHERE type IN ('index', 'trigger') AND sql IS NOT NULL ORDER BY name")
            val otherTables = entities.filter { it != history }.associate { entity ->
                val table = entity.getString("tableName")
                table to host.rows("SELECT * FROM `$table` ORDER BY rowid")
            }
            host.db.beginTransaction()
            try {
                InkuDatabase.MIGRATION_13_14.migrate(host.db)
                host.db.setTransactionSuccessful()
            } finally { host.db.endTransaction() }
            val columns = host.request("PRAGMA table_info(history_items)").getJSONArray("rows")
            val names = (0 until columns.length()).map { columns.getJSONArray(it).getString(1) }
            assertFalse(names.contains("expanded_ddl"))
            assertTrue(names.contains("ddl_source_origin"))
            for ((i, old) in before.withIndex()) {
                val fixture = fixtures.getJSONObject(i)
                val expected = old.toMutableMap().apply {
                    remove("expanded_ddl")
                    put("normalized_ddl", fixture.opt("selected").takeUnless { it == JSONObject.NULL })
                    put("ddl_source_origin", fixture.opt("ddl_source_origin").takeUnless { it == JSONObject.NULL })
                }
                val actual = host.request("SELECT * FROM history_items WHERE id = ?", arrayOf(old.getValue("id")))
                val keys = actual.getJSONArray("columns")
                val values = actual.getJSONArray("rows").getJSONArray(0)
                assertEquals(expected, (0 until keys.length()).associate { index ->
                    keys.getString(index) to values.opt(index).takeUnless { it == JSONObject.NULL }
                })
            }
            assertEquals(objectsBefore, host.rows("SELECT type, name, sql FROM sqlite_master WHERE type IN ('index', 'trigger') AND sql IS NOT NULL ORDER BY name"))
            for ((table, rows) in otherTables) assertEquals(table, rows, host.rows("SELECT * FROM `$table` ORDER BY rowid"))
            assertThrows(IllegalStateException::class.java) {
                host.db.execSQL("INSERT INTO history_items SELECT * FROM history_items LIMIT 1")
            }
            // A copied work may share a render hash, but never a lineage node.
            assertThrows(IllegalStateException::class.java) {
                host.db.execSQL("UPDATE history_items SET lineage_node_id = 'shared-node'")
            }
            // Match the generated current Room table's types, nullability and PK.
            val current = JSONObject(productFile("android/app/schemas/app.inku.mobile.data.db.InkuDatabase/14.json").readText())
                .getJSONObject("database").getJSONArray("entities").getJSONObject(0)
            HostSqlite().use { fresh ->
                fresh.db.execSQL(current.getString("createSql").replace("\u0024{TABLE_NAME}", "history_items"))
                fun signature(sqlite: HostSqlite): Map<String, List<Any?>> {
                    val info = sqlite.request("PRAGMA table_info(history_items)").getJSONArray("rows")
                    return (0 until info.length()).associate { index ->
                        val row = info.getJSONArray(index)
                        row.getString(1) to (2 until row.length()).map { row.opt(it).takeUnless { value -> value == JSONObject.NULL } }
                    }
                }
                assertEquals(signature(host), signature(fresh))
            }
            // Already-completed Saijiki migration must keep its marker and every work.
            val alreadyMoved = SaijikiV1Migration({ error("already migrated") }, discardExecutions = true)
            assertNull(alreadyMoved.runOnce(host.db))
        }
    }

    @Test
    fun saijikiPostRoomStartupUsesOnlyTheUnifiedDdlAndKeepsSavedDrawingsAndOrigin() {
        HostSqlite().use { host ->
            host.createSchema(13)
            host.db.execSQL(
                "INSERT INTO history_items(id, created_at, updated_at, original_input, normalized_ddl, expanded_ddl, " +
                    "score_json, display_svg, render_metadata_json, render_hash, render_hash_short, color_catalog_id, canvas_aspect, starred, trashed) " +
                    "VALUES ('old-work', 1, 2, 'description', NULL, 'old word', 'saved-score', 'saved-svg', '{}', 'hash', '0000', 'default', 'square', 1, 0)",
            )
            InkuDatabase.MIGRATION_13_14.migrate(host.db)
            val calls = mutableListOf<String>()
            val migration = SaijikiV1Migration({ bytes ->
                val source = JSONObject(bytes.toString(Charsets.UTF_8)).getJSONObject("document").getString("source")
                calls += source
                JSONObject().put("document", JSONObject().put("document", JSONObject().put("source", "current word")))
                    .toString().toByteArray(Charsets.UTF_8)
            }, discardExecutions = true)
            val protectedBefore = host.rows("SELECT original_input, score_json, display_svg, starred, trashed, ddl_source_origin FROM history_items")
            assertTrue(checkNotNull(migration.runOnce(host.db)).getInt("statements") > 0)
            assertEquals(listOf("old word"), calls)
            assertEquals("[[\"current word\"]]", host.rows("SELECT normalized_ddl FROM history_items"))
            assertEquals(protectedBefore, host.rows("SELECT original_input, score_json, display_svg, starred, trashed, ddl_source_origin FROM history_items"))
            assertNull(migration.runOnce(host.db))
            assertEquals(1, calls.size)
        }
    }
}
