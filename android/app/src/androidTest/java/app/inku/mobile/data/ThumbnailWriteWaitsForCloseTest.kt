package app.inku.mobile.data

import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.refinement.PaintSeeds
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * T-1: `close()` waits for the scheduled thumbnail write (I-150).
 *
 * The row is inserted with a null thumbnail and filled in later by a coroutine
 * the save does not wait for. Every caller then closes the database next, and
 * for five instrumentation runs out of twelve the close landed on top of a
 * write still in flight. That throws on the background coroutine rather than on
 * the caller, so it took the whole process down and the remaining tests were
 * never recorded -- the failure arrived as a short XML, not as a red test.
 *
 * Asserting "no crash" cannot be written: the race is a race. What can be
 * written is the property that removes it. If `close()` returns only once the
 * scheduled write has finished, the path is on the row by then, and nothing is
 * left holding the database. So the thumbnail column is the observable stand-in
 * for the guarantee, and a `close()` that only cancels leaves it null.
 */
@RunWith(AndroidJUnit4::class)
class ThumbnailWriteWaitsForCloseTest {

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository

    private val score = """
        {"version":"0.1.0","canvas":"square","background":"white","instructions":[
          {"primitive":"line","from":[0.2,0.5],"to":[0.8,0.5],"color":"red","weight":"brush_thick"}
        ]}
    """.trimIndent()

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        database = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        repository = InkuRepository(context, database)
    }

    @After
    fun tearDown() = runBlocking {
        repository.close()
        database.close()
    }

    private suspend fun paint(description: String): HistoryItemEntity =
        repository.renderFromScore(
            description = description,
            scoreJson = score,
            catalogId = "ink_season",
            canvasAspect = "square",
            stage1ModelId = "test-stage1",
            stage2ModelId = "test-stage2",
            seeds = PaintSeeds(renderSeed = 4242L, compositionSeed = 77L, interpretationSeed = "thumbnail-close"),
        )

    @Test
    fun theSaveReturnsBeforeTheThumbnailIsWritten() = runBlocking {
        val saved = paint("閉じる前の下地")

        // The contrast the assertion below needs: the write really is still
        // outstanding when the save returns, so a `close()` that waits is doing
        // something a `close()` that cancels would not.
        assertNull("the save should not have written the thumbnail yet", saved.thumbnailPath)
    }

    @Test
    fun closeReturnsOnlyAfterTheScheduledThumbnailIsOnTheRow() = runBlocking {
        val saved = paint("閉じたあとに読む")

        repository.close()

        val row = requireNotNull(repository.getHistoryById(saved.id))
        assertNotNull(
            "close() returned while the thumbnail write was still outstanding;" +
                " the database close after it can land on top of that write (I-150)",
            row.thumbnailPath,
        )
    }
}
