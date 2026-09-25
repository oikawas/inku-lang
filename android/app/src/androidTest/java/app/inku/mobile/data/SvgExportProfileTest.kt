package app.inku.mobile.data

import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.db.InkuDatabase
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The editable and compat SVG files are drawn again from the saved Score, as
 * the server's `GET /api/history/{id}/svg?profile=` draws them. They used to be
 * the display SVG under a new title, which a check of the title alone would
 * still pass; the profile is read from what the renderer wrote.
 */
@RunWith(AndroidJUnit4::class)
class SvgExportProfileTest {
    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository

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

    @Test
    fun editableAndCompatAreDrawnInTheirOwnProfile() = runBlocking {
        val item = repository.renderFromScore(
            description = "書き出しの形",
            scoreJson = """{"version":"0.1.0","canvas":"square","background":"white","instructions":[]}""",
            catalogId = "default",
            canvasAspect = "square",
            stage1ModelId = "test-stage1",
            stage2ModelId = "test-stage2",
        )

        assertEquals(item.displaySvg, repository.exportSvg(item, "display"))
        val editable = repository.exportSvg(item, "editable")
        val compat = repository.exportSvg(item, "compat")
        assertTrue(editable.startsWith("<svg"))
        assertTrue("the renderer names the profile it drew", editable.contains("\"svg_profile\":\"editable\""))
        assertTrue(compat.contains("\"svg_profile\":\"compat\""))
        assertFalse(item.displaySvg.contains("\"svg_profile\":\"editable\""))
    }
}
