package app.inku.mobile.data.db

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/** Schema 14 -> 15 moves the large columns, keeps every value and ends at Room's schema 15. */
class HistoryPayloadsMigrationTest {
    @Test
    fun theLargeColumnsMoveUnchangedAndTheTablesMatchSchema15() {
        HostSqlite().use { host ->
            val entities = host.createSchema(14)
            val history = entities.single { it.getString("tableName") == "history_items" }
            val fields = history.getJSONArray("fields")
            val before = (0 until 3).map { work ->
                val row: Map<String, Any?> = (0 until fields.length()).associate { index ->
                    val field = fields.getJSONObject(index)
                    val name = field.getString("columnName")
                    val value: Any? = when (name) {
                        "id" -> "work-$work"
                        "lineage_node_id" -> "node-$work"
                        "starred", "trashed" -> work % 2
                        else -> if (field.getString("affinity") == "INTEGER") 100 + index else "$work:$name:写\n"
                    }
                    name to value
                }
                host.db.execSQL(
                    "INSERT INTO history_items (${row.keys.joinToString(",")}) VALUES (${row.keys.joinToString(",") { "?" }})",
                    row.values.toTypedArray(),
                )
                row
            }
            host.db.execSQL("INSERT INTO lineage_nodes(id, history_id, state, at) VALUES ('node-0', 'work-0', 'active', 7)")
            val untouched = listOf("lineage_nodes", "app_settings", "pipeline_history_links", "pipeline_candidate_executions")
                .associateWith { host.rows("SELECT * FROM `$it` ORDER BY rowid") }

            host.db.beginTransaction()
            try {
                InkuDatabase.MIGRATION_14_15.migrate(host.db)
                host.db.setTransactionSuccessful()
            } finally { host.db.endTransaction() }

            val large = listOf("score_json", "display_svg", "render_metadata_json")
            for (old in before) {
                val payload = host.request("SELECT score_json, display_svg, render_metadata_json FROM history_payloads WHERE id = ?",
                    arrayOf<Any?>(old["id"])).getJSONArray("rows").getJSONArray(0)
                assertEquals(large.map { old[it] }, (0 until 3).map<Int, Any?> { payload.get(it) })
                val actual = host.request("SELECT * FROM history_items WHERE id = ?", arrayOf<Any?>(old["id"]))
                val keys = actual.getJSONArray("columns")
                val values = actual.getJSONArray("rows").getJSONArray(0)
                val kept: Map<String, Any?> = (0 until keys.length()).associate { keys.getString(it) to values.get(it) }
                assertEquals(old - large.toSet(), kept)
            }
            for ((table, rows) in untouched) assertEquals(table, rows, host.rows("SELECT * FROM `$table` ORDER BY rowid"))
            val tables = host.rows("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
            assertFalse(tables.contains("color_catalogs"))

            // The migrated tables are the ones Room creates for schema 15.
            val target = JSONObject(productFile("android/app/schemas/app.inku.mobile.data.db.InkuDatabase/15.json").readText())
                .getJSONObject("database").getJSONArray("entities")
            HostSqlite().use { fresh ->
                fresh.createSchema(15)
                for (table in listOf("history_items", "history_payloads", "lineage_edges", "variation_authority")) {
                    fun signature(sqlite: HostSqlite): Pair<Map<String, List<Any?>>, String> {
                        val info = sqlite.request("PRAGMA table_info($table)").getJSONArray("rows")
                        val columns = (0 until info.length()).associate { index ->
                            val row = info.getJSONArray(index)
                            row.getString(1) to (2 until row.length()).map { row.opt(it).takeUnless { value -> value == JSONObject.NULL } }
                        }
                        val indexes = sqlite.rows("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = '$table' AND sql IS NOT NULL ORDER BY name")
                        return columns to indexes
                    }
                    assertEquals(table, signature(fresh), signature(host))
                }
            }
            assertEquals((0 until target.length()).map { target.getJSONObject(it).getString("tableName") }.sorted().toString(),
                JSONArray(tables).let { rows -> (0 until rows.length()).map { rows.getJSONArray(it).getString(0) } }
                    .filterNot { it in setOf("room_master_table", "android_metadata", "sqlite_sequence") }.sorted().toString())
        }
    }
}
