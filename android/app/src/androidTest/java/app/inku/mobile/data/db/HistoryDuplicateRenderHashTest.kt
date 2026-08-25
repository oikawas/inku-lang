package app.inku.mobile.data.db

import android.database.sqlite.SQLiteConstraintException
import androidx.room.Room
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

    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private var database: InkuDatabase? = null

    @After
    fun tearDown() {
        database?.close()
    }

    /** A version 10 database, made from the entity rather than migrated into. */
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

}
