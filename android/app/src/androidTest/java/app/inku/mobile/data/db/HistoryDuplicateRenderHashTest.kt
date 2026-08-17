package app.inku.mobile.data.db

import android.database.sqlite.SQLiteConstraintException
import androidx.room.Room
import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

private const val TEST_DB = "history-duplicate-render-hash-test"
private const val RENDER_HASH_INDEX = "index_history_items_render_hash"

/**
 * The same drawing reached twice is two works, because that is what the server
 * says it is.
 *
 * `history.render_hash` carries no unique constraint there -- the column is
 * declared `index=True` and nothing more (`db.py:178`), the index is created
 * with a plain `CREATE INDEX` (`db.py:653`), and the only duplicate the save
 * path drops is the one the caller names with an explicit `idempotency_key`
 * (`db.py:2965`). A colliding primary key is re-raised rather than absorbed
 * (`db.py:2990-2993`).
 *
 * These open real databases. Room does not run on the JVM here (there is no
 * Robolectric in this project), and the subject is a SQLite index either way:
 * a test that read the annotation off the entity would never touch the index
 * the annotation is supposed to produce.
 */
@RunWith(AndroidJUnit4::class)
class HistoryDuplicateRenderHashTest {

    @get:Rule
    val helper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        InkuDatabase::class.java,
    )

    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private var database: InkuDatabase? = null

    @After
    fun tearDown() {
        database?.close()
    }

    /** A version 9 database, made from the entity rather than migrated into. */
    private fun openFresh(): InkuDatabase =
        Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .build()
            .also { database = it }

    private fun item(id: String, renderHash: String, input: String) = HistoryItemEntity(
        id = id,
        createdAt = 1L,
        updatedAt = 1L,
        originalInput = input,
        normalizedDdl = input,
        expandedDdl = null,
        scoreJson = "{}",
        displaySvg = "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
        stage1Model = "test-stage1",
        stage2Model = "test-stage2",
        renderMetadataJson = "{}",
        renderHash = renderHash,
        renderHashShort = renderHash.takeLast(8),
        colorCatalogId = "sumi",
        canvasAspect = "1:1",
        starred = false,
        trashed = false,
        elapsedMs = 0L,
        tokenMetadataJson = null,
    )

    /** The columns a version 8 row needs, written the way the neighbouring migration tests write them. */
    private fun insertRow(db: SupportSQLiteDatabase, id: String, renderHash: String) {
        db.execSQL(
            """
            INSERT INTO history_items (
                id, created_at, updated_at, original_input, normalized_ddl,
                score_json, display_svg, render_metadata_json, render_hash,
                render_hash_short, color_catalog_id, canvas_aspect, starred, trashed
            ) VALUES (?, 1, 1, '青い円', '青い円', '{}', '<svg/>', '{}', ?, 'abc', 'sumi', '1:1', 0, 0)
            """.trimIndent(),
            arrayOf<Any>(id, renderHash),
        )
    }

    private fun renderHashIndexIsUnique(db: SupportSQLiteDatabase): Boolean {
        db.query("PRAGMA index_list('history_items')").use { cursor ->
            val nameColumn = cursor.getColumnIndexOrThrow("name")
            val uniqueColumn = cursor.getColumnIndexOrThrow("unique")
            while (cursor.moveToNext()) {
                if (cursor.getString(nameColumn) == RENDER_HASH_INDEX) {
                    return cursor.getInt(uniqueColumn) != 0
                }
            }
            throw AssertionError("$RENDER_HASH_INDEX is not on the table at all")
        }
    }

    // ── T-266 ──────────────────────────────────────────────

    /**
     * Two works that reached the same drawing are two rows, the way two rows is
     * what the server's table holds.
     *
     * The count alone would pass on one row read twice, so the ids are read back
     * one at a time as well.
     */
    @Test
    fun t266_twoWorksWithTheSameRenderHashBothStay() = runBlocking {
        val dao = openFresh().historyDao()
        val hash = "rh3:the-same-drawing-twice"

        dao.insert(item("h-1", hash, "赤い円を5個、横に並べる"))
        dao.insert(item("h-2", hash, "赤い円を5個、横に並べる"))

        val rows = dao.listActive(20, 0).first()
        assertEquals("both works are in history", 2, rows.size)
        assertEquals(
            "and they are two rows, not one row counted twice",
            setOf("h-1", "h-2"),
            rows.map { it.id }.toSet(),
        )
        assertNotNull("the first work reads back on its own id", dao.getById("h-1"))
        assertNotNull("the second work reads back on its own id", dao.getById("h-2"))
        assertEquals("and both carry the hash they arrived at", hash, dao.getById("h-2")!!.renderHash)
    }

    // ── T-267 ──────────────────────────────────────────────

    /**
     * The same id twice is refused, and the row already written stays.
     *
     * This is `db.py:2993`: the server catches the IntegrityError a colliding
     * primary key produces and re-raises it when the caller named no
     * idempotency key. Absorbing it silently would report a save that never
     * happened.
     */
    @Test
    fun t267_theSameIdTwiceIsRefusedAndTheFirstRowSurvives() = runBlocking {
        val dao = openFresh().historyDao()
        val first = item("h-1", "rh3:first", "最初の記述")

        dao.insert(first)
        val failure = runCatching {
            dao.insert(item("h-1", "rh3:second", "あとから来た別の記述"))
        }.exceptionOrNull()

        assertTrue(
            "a colliding primary key must be refused with SQLiteConstraintException, got $failure",
            failure is SQLiteConstraintException,
        )
        val stored = dao.getById("h-1")
        assertNotNull("the row written first is still there", stored)
        assertEquals("and it was not overwritten", "最初の記述", stored!!.originalInput)
        assertEquals("nor was its hash", "rh3:first", stored.renderHash)
        assertEquals("and no second row appeared", 1, dao.listActive(20, 0).first().size)
    }

    // ── T-268 ──────────────────────────────────────────────

    /**
     * The migration exchanges the index and loses no work.
     *
     * The rows here carry different hashes, because version 8 is where the
     * unique index still stands and would refuse two of a kind. What the
     * migration has to prove is that it did not rebuild the table underneath
     * works the author already saved.
     */
    @Test
    fun t268_migration8to9KeepsEveryRowAndLeavesTheIndexNonUnique() {
        helper.createDatabase(TEST_DB, 8).use { db ->
            insertRow(db, "h-1", "rh3:first")
            insertRow(db, "h-2", "rh3:second")
        }

        val db = helper.runMigrationsAndValidate(TEST_DB, 9, true, InkuDatabase.MIGRATION_8_9)

        db.query("SELECT id FROM history_items ORDER BY id").use { cursor ->
            assertEquals("both works survived the migration", 2, cursor.count)
            cursor.moveToFirst()
            assertEquals("h-1", cursor.getString(0))
            cursor.moveToNext()
            assertEquals("h-2", cursor.getString(0))
        }
        assertTrue(
            "$RENDER_HASH_INDEX must be non-unique after the migration",
            !renderHashIndexIsUnique(db),
        )
    }

    // ── T-269 ──────────────────────────────────────────────

    /**
     * A database that was unique before the migration takes a second work after
     * it.
     *
     * The starting point is what separates this from T-266: that one is a
     * version 9 database built from the entity, this one is a version 8
     * database carried across. A migration that declared the new shape without
     * touching the index would pass the first and fail here.
     */
    @Test
    fun t269_aMigratedDatabaseAcceptsASecondWorkWithTheSameHash() {
        helper.createDatabase(TEST_DB, 8).use { db ->
            insertRow(db, "h-1", "rh3:the-same-drawing-twice")
        }

        val db = helper.runMigrationsAndValidate(TEST_DB, 9, true, InkuDatabase.MIGRATION_8_9)
        insertRow(db, "h-2", "rh3:the-same-drawing-twice")

        db.query("SELECT id FROM history_items ORDER BY id").use { cursor ->
            assertEquals("the second arrival at the same drawing is a second work", 2, cursor.count)
            cursor.moveToFirst()
            assertEquals("h-1", cursor.getString(0))
            cursor.moveToNext()
            assertEquals("h-2", cursor.getString(0))
        }
    }
}
