package app.inku.mobile.data.db

import androidx.room.testing.MigrationTestHelper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

private const val TEST_DB = "sketch-migration-test"

/**
 * 写生 (Stage 0.5) arrives, and the works that predate it say so.
 *
 * This opens a real database, for the reason `LineageMigrationTest` states next
 * door: a migration test that reads `startVersion` / `endVersion` off the
 * Migration object never touches the SQL it is named after.
 *
 * What is under test is one thing: a row written before the columns existed
 * reads back with all three empty. That absence is the sixth state, and it is
 * NOT `off` -- `off` is a choice the author made, and a work drawn before there
 * was a layer to switch off made no such choice. Backfilling anything here
 * would undo the whole point of having a state column.
 */
@RunWith(AndroidJUnit4::class)
class SketchMigrationTest {

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
    fun migration7to8_leavesTheThreeColumnsEmptyOnAWorkThatPredatesThem() {
        helper.createDatabase(TEST_DB, 7).use { db ->
            insertHistoryRow(db, "h-1")
        }

        val db = helper.runMigrationsAndValidate(TEST_DB, 8, true, InkuDatabase.MIGRATION_7_8)

        db.query("SELECT id, sketch_text, sketch_grain, sketch_state FROM history_items").use { cursor ->
            assertEquals("the row survived the migration", 1, cursor.count)
            cursor.moveToFirst()
            assertEquals("h-1", cursor.getString(0))
            assertTrue("the prose column starts empty", cursor.isNull(1))
            assertTrue("the grain column starts empty", cursor.isNull(2))
            assertTrue("the state column starts empty", cursor.isNull(3))
            // Said the other way round as well, because this is the distinction
            // the column exists to hold: an empty state is not the word `off`.
            assertNotEquals("off", cursor.getString(3))
        }
    }

    /** The new columns are writable, so a work drawn after the migration records. */
    @Test
    fun migration7to8_letsAWorkRecordWhatTheLayerDid() {
        helper.createDatabase(TEST_DB, 7).use { db ->
            insertHistoryRow(db, "h-1")
        }

        val db = helper.runMigrationsAndValidate(TEST_DB, 8, true, InkuDatabase.MIGRATION_7_8)
        db.execSQL(
            "UPDATE history_items SET sketch_text = ?, sketch_grain = 'coarse', sketch_state = 'coarse' WHERE id = 'h-1'",
            arrayOf<Any>("円がある。円は青い。"),
        )

        db.query("SELECT sketch_text, sketch_grain, sketch_state FROM history_items").use { cursor ->
            cursor.moveToFirst()
            assertEquals("円がある。円は青い。", cursor.getString(0))
            assertEquals("coarse", cursor.getString(1))
            assertEquals("coarse", cursor.getString(2))
        }
    }
}
