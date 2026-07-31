package app.inku.mobile.data.db

import android.database.sqlite.SQLiteConstraintException
import androidx.room.testing.MigrationTestHelper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

private const val TEST_DB = "lineage-migration-test"

// These open a real database. A migration test that only reads startVersion /
// endVersion off the Migration object never touches the SQL it is named after.
@RunWith(AndroidJUnit4::class)
class LineageMigrationTest {

    @get:Rule
    val helper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        InkuDatabase::class.java,
    )

    private fun insertHistoryRow(db: androidx.sqlite.db.SupportSQLiteDatabase, id: String) {
        db.execSQL(
            """
            INSERT INTO history_items (
                id, created_at, updated_at, original_input, normalized_ddl,
                score_json, display_svg, render_metadata_json, render_hash,
                render_hash_short, color_catalog_id, canvas_aspect, starred, trashed
            ) VALUES (?, 1, 1, '青い円', '青い円', '{}', '<svg/>', '{}', 'rh3:abc', 'abc', 'sumi', '1:1', 0, 0)
            """.trimIndent(),
            arrayOf<Any>(id),
        )
    }

    @Test
    fun migration4to5_keepsExistingHistoryRows() {
        helper.createDatabase(TEST_DB, 4).use { db ->
            insertHistoryRow(db, "h-1")
        }

        val db = helper.runMigrationsAndValidate(TEST_DB, 5, true, InkuDatabase.MIGRATION_4_5)

        db.query("SELECT id, lineage_node_id FROM history_items").use { cursor ->
            assertEquals(1, cursor.count)
            cursor.moveToFirst()
            assertEquals("h-1", cursor.getString(0))
            assertTrue("the new column starts empty", cursor.isNull(1))
        }
    }

    @Test
    fun migration4to5_letsALineageNodePointAtAHistoryRow() {
        helper.createDatabase(TEST_DB, 4).use { db ->
            insertHistoryRow(db, "h-1")
        }

        val db = helper.runMigrationsAndValidate(TEST_DB, 5, true, InkuDatabase.MIGRATION_4_5)
        db.execSQL(
            "INSERT INTO lineage_nodes (id, history_id, state, at) VALUES ('n-1', 'h-1', 'active', 1)",
        )

        // history_items.id is TEXT, so the join only lands if history_id is TEXT too.
        db.query(
            "SELECT h.id FROM lineage_nodes n JOIN history_items h ON h.id = n.history_id",
        ).use { cursor ->
            assertEquals(1, cursor.count)
            cursor.moveToFirst()
            assertEquals("h-1", cursor.getString(0))
        }
    }

    @Test
    fun migration4to5_rejectsASecondParentForTheSameChild() {
        helper.createDatabase(TEST_DB, 4).close()
        val db = helper.runMigrationsAndValidate(TEST_DB, 5, true, InkuDatabase.MIGRATION_4_5)

        db.execSQL(
            "INSERT INTO lineage_edges (id, parent_node_id, child_node_id, derivation_kind, metadata_json, at) " +
                "VALUES ('e-1', 'p-1', 'c-1', 'touch_change', '{}', 1)",
        )

        var rejected = false
        try {
            db.execSQL(
                "INSERT INTO lineage_edges (id, parent_node_id, child_node_id, derivation_kind, metadata_json, at) " +
                    "VALUES ('e-2', 'p-2', 'c-1', 'layout_change', '{}', 2)",
            )
        } catch (e: SQLiteConstraintException) {
            rejected = true
        }

        assertTrue("uq_lineage_primary_parent must reject a second parent for c-1", rejected)
    }
}
