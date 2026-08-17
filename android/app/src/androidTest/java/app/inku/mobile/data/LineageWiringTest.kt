package app.inku.mobile.data

import android.database.sqlite.SQLiteConstraintException
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.db.LineageEdgeEntity
import app.inku.mobile.data.lineage.LineageDeclaration
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * T-2 to T-5. These open a real Room database on the device and save through
 * `InkuRepository`, because that is the only way to see whether the save path
 * calls the lineage DAO at all. `LineageWiringReferenceTest` on the JVM checks
 * the same decisions against the server fixture and stays green whether or not
 * anything is wired -- a whole contract once shipped in exactly that state.
 *
 * `renderFromScore` is the entry point used here: it is the one save path that
 * needs no language model, and it reaches the same `saveResult` the other two
 * do.
 */
@RunWith(AndroidJUnit4::class)
class LineageWiringTest {

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository

    private val score = """{"version":"0.1.0","canvas":"square","background":"white","instructions":[]}"""

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
        // Cancels the thumbnail coroutine before the database goes away.
        repository.close()
        database.close()
    }

    /** Each save needs its own text, so the rows a test reads can be told apart. */
    private suspend fun save(
        description: String,
        repo: InkuRepository = repository,
        lineage: LineageDeclaration = LineageDeclaration(),
    ) = repo.renderFromScore(
        description = description,
        scoreJson = score,
        catalogId = "sumi",
        canvasAspect = "1:1",
        stage1ModelId = "test-stage1",
        stage2ModelId = "test-stage2",
        lineage = lineage,
    )

    private fun countRows(table: String): Int {
        database.openHelper.readableDatabase.query("SELECT COUNT(*) FROM $table").use { cursor ->
            cursor.moveToFirst()
            return cursor.getInt(0)
        }
    }

    @Test
    fun t2_savingThroughTheRepositoryWritesALineageNodeRow() = runBlocking {
        val item = save("系譜の節を書く")

        assertNotNull("the history row points at a node", item.lineageNodeId)
        val node = database.lineageDao().getNodeById(item.lineageNodeId!!)
        assertNotNull("the node is really in lineage_nodes", node)
        assertEquals(item.id, node!!.historyId)
        assertEquals("active", node.state)
        assertEquals(node.id, node.rootNodeId)
        assertEquals(item.createdAt, node.at)
        assertEquals(item.renderHash, node.renderHash)
        assertTrue("the description hash was computed", node.descriptionHash!!.startsWith("dh1:"))
        assertEquals(1, countRows("lineage_nodes"))
    }

    @Test
    fun t3_aDeclaredDerivationWritesExactlyOneEdge() = runBlocking {
        val parent = save("親")
        val parentNodeId = parent.lineageNodeId!!

        val child = save(
            "子",
            lineage = LineageDeclaration(
                parentNodeId = parentNodeId,
                derivationKind = "touch_change",
                derivationMetadata = mapOf("b" to 1, "a" to 2),
            ),
        )

        assertEquals(1, countRows("lineage_edges"))
        val edge = database.lineageDao().getEdgeByChildId(child.lineageNodeId!!)
        assertNotNull(edge)
        assertEquals(parentNodeId, edge!!.parentNodeId)
        assertEquals("touch_change", edge.derivationKind)
        assertEquals("""{"a":2,"b":1}""", edge.metadataJson)
        assertEquals(child.createdAt, edge.at)
    }

    /**
     * The other direction. "Always writes an edge" passes the test above just
     * as well as the correct behaviour does; only this one tells them apart.
     */
    @Test
    fun t3_aSaveWithNoDeclaredParentWritesNoEdge() = runBlocking {
        val first = save("起点その一")
        val second = save("起点その二")

        assertEquals(2, countRows("lineage_nodes"))
        assertEquals(0, countRows("lineage_edges"))
        assertNull(database.lineageDao().getEdgeByChildId(first.lineageNodeId!!))
        assertNull(database.lineageDao().getEdgeByChildId(second.lineageNodeId!!))
    }

    @Test
    fun t4_theRootPropagatesThroughTwoGenerations() = runBlocking {
        val a = save("祖")
        val b = save(
            "親",
            lineage = LineageDeclaration(parentNodeId = a.lineageNodeId, derivationKind = "variation"),
        )
        val c = save(
            "子",
            lineage = LineageDeclaration(parentNodeId = b.lineageNodeId, derivationKind = "replay"),
        )

        val stored = database.lineageDao().getNodeById(c.lineageNodeId!!)!!
        assertEquals("the root is the first work", a.lineageNodeId, stored.rootNodeId)
        assertTrue("the root is not the parent", stored.rootNodeId != b.lineageNodeId)
        assertEquals(a.lineageNodeId, database.lineageDao().getNodeById(b.lineageNodeId!!)!!.rootNodeId)
    }

    @Test
    fun t5_theNodeAndTheEdgeAreOneTransaction() = runBlocking {
        val parent = save("親")
        val parentNodeId = parent.lineageNodeId!!

        // Take the child node id the next save will use, and give its edge slot
        // away first: uq_lineage_primary_parent allows one parent per child.
        val takenNodeId = "node-whose-edge-slot-is-taken"
        database.lineageDao().insertEdge(
            LineageEdgeEntity(
                id = "edge-already-here",
                parentNodeId = parentNodeId,
                childNodeId = takenNodeId,
                derivationKind = "replay",
            ),
        )
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val ids = ArrayDeque(listOf(takenNodeId, "edge-that-cannot-be-written"))
        val scripted = InkuRepository(context, database) { ids.removeFirst() }

        assertThrows(SQLiteConstraintException::class.java) {
            runBlocking {
                save(
                    "書けないはずの子",
                    repo = scripted,
                    lineage = LineageDeclaration(
                        parentNodeId = parentNodeId,
                        derivationKind = "replay",
                    ),
                )
            }
        }

        assertNull("no orphan node survives the failed edge", database.lineageDao().getNodeById(takenNodeId))
        assertEquals("only the parent's node is left", 1, countRows("lineage_nodes"))
        assertEquals("only the parent's history row is left", 1, countRows("history_items"))
        assertEquals("the edge that was already there is untouched", 1, countRows("lineage_edges"))
        scripted.close()
    }

    /** A rejected declaration writes nothing at all, history row included. */
    @Test
    fun aRejectedDerivationLeavesNoRows() = runBlocking {
        assertThrows(IllegalArgumentException::class.java) {
            runBlocking {
                save("親のいない派生", lineage = LineageDeclaration(derivationKind = "touch_change"))
            }
        }

        assertEquals(0, countRows("history_items"))
        assertEquals(0, countRows("lineage_nodes"))
        assertEquals(0, countRows("lineage_edges"))
    }
}
