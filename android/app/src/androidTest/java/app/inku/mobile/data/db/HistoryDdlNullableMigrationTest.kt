package app.inku.mobile.data.db

import android.content.Context
import android.database.Cursor
import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.refinement.RefinementParent
import java.io.File
import java.util.UUID
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class HistoryDdlNullableMigrationTest {
    private val context: Context = InstrumentationRegistry.getInstrumentation().targetContext
    private val databaseName = "i376-test-nullable-ddl-${UUID.randomUUID()}.sqlite"
    private var database: InkuDatabase? = null

    @get:Rule
    val migrationHelper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        InkuDatabase::class.java.canonicalName,
        FrameworkSQLiteOpenHelperFactory(),
    )

    @After
    fun tearDown() {
        database?.close()
        context.deleteDatabase(databaseName)
    }

    @Test
    fun v12WorksKeepEveryColumnAndEmptyDdlBecomesNullableAtV13() = runBlocking {
        lateinit var before: List<Map<String, Any?>>
        migrationHelper.createDatabase(databaseName, 12).use { db ->
            val columns = db.query("PRAGMA table_info(history_items)").use { cursor ->
                buildList {
                    while (cursor.moveToNext()) add(cursor.getString(1) to cursor.getString(2))
                }
            }
            for ((id, ddl) in listOf("with-ddl" to "赤い円を描く。", "without-ddl" to "")) {
                val values = columns.mapIndexed { index, (name, type) ->
                    when (name) {
                        "id" -> id
                        "normalized_ddl" -> ddl
                        "original_input" -> "保存した記述"
                        "score_json", "render_metadata_json", "token_metadata_json" -> "{}"
                        "display_svg" -> "<svg>${" ".repeat(256 * 1024)}</svg>"
                        "starred" -> 1L
                        "trashed" -> 0L
                        else -> if (type == "INTEGER") index.toLong() else "$id-$name"
                    }
                }.toTypedArray<Any>()
                db.execSQL(
                    "INSERT INTO history_items (${columns.joinToString(",") { "`${it.first}`" }}) " +
                        "VALUES (${columns.joinToString(",") { "?" }})",
                    values,
                )
            }
            db.execSQL("INSERT INTO lineage_nodes (id, history_id, state, at) VALUES ('node', 'without-ddl', 'active', 1)")
            before = rows(db)
        }

        // The shipped application classifies the schema before Room opens it.
        // v12 must be admitted for this migration without resetting any data.
        assertEquals(
            RoomV10ResetCoordinator.Result.Ready(resetPerformed = false),
            RoomV10ResetCoordinator.prepare(
                context,
                databaseName,
                File(context.filesDir, "$databaseName-thumbnails"),
            ),
        )
        migrationHelper.runMigrationsAndValidate(
            databaseName,
            13,
            true,
            InkuDatabase.MIGRATION_12_13,
        ).use { db ->
            assertEquals(before.map { row ->
                row.mapValues { (name, value) ->
                    if (name == "normalized_ddl" && value == "") null else value
                }
            }, rows(db))
            db.query("SELECT history_id FROM lineage_nodes WHERE id = 'node'").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("without-ddl", cursor.getString(0))
            }
        }

    }

    @Test
    fun v13ExpandedOnlyTransfersAndBothAbsentStaysNullableThroughRoom() = runBlocking {
        migrationHelper.createDatabase(databaseName, 13).use { db ->
            for ((id, expanded) in listOf("expanded-only" to "\n赤い円を描く。 \n", "without-ddl" to null)) {
                db.execSQL(
                    "INSERT INTO history_items (id, created_at, updated_at, original_input, normalized_ddl, expanded_ddl, " +
                        "score_json, display_svg, render_metadata_json, render_hash, render_hash_short, " +
                        "color_catalog_id, canvas_aspect, starred, trashed) " +
                        "VALUES (?, 1, 1, '保存した記述', NULL, ?, '{}', '<svg/>', '{}', ?, '0000', 'default', 'square', 0, 0)",
                    arrayOf<Any?>(id, expanded, id),
                )
            }
        }
        assertEquals(
            RoomV10ResetCoordinator.Result.Ready(resetPerformed = false),
            RoomV10ResetCoordinator.prepare(context, databaseName, File(context.filesDir, "$databaseName-thumbnails")),
        )
        migrationHelper.runMigrationsAndValidate(databaseName, 14, true, InkuDatabase.MIGRATION_13_14).close()
        val opened = InkuDatabase.openPrepared(context, databaseName).also { database = it }
        val transferred = checkNotNull(opened.historyDao().getById("expanded-only"))
        assertEquals("\n赤い円を描く。 \n", transferred.normalizedDdl)
        assertEquals("legacy_expanded", transferred.ddlSourceOrigin)
        val absent = checkNotNull(opened.historyDao().getById("without-ddl"))
        assertNull(absent.normalizedDdl)
        assertEquals("", RefinementParent.of(absent, absent.originalInput).ddl)
        val summary = opened.historyDao().listActiveSummaries(10, 0).first().single { it.id == absent.id }
        assertNull(summary.normalizedDdl)
        assertFalse(summary.searchText.contains("null"))
        assertTrue(summary.searchText.contains(absent.originalInput))
        opened.historyDao().insert(absent.copy(id = "null-roundtrip", lineageNodeId = null))
        assertNull(checkNotNull(opened.historyDao().getById("null-roundtrip")).normalizedDdl)
    }

    private fun rows(db: SupportSQLiteDatabase): List<Map<String, Any?>> =
        db.query("SELECT * FROM history_items ORDER BY id").use { cursor ->
            buildList {
                while (cursor.moveToNext()) add(cursor.columnNames.indices.associate { index ->
                    cursor.getColumnName(index) to when (cursor.getType(index)) {
                        Cursor.FIELD_TYPE_NULL -> null
                        Cursor.FIELD_TYPE_INTEGER -> cursor.getLong(index)
                        else -> cursor.getString(index)
                    }
                })
            }
        }
}
