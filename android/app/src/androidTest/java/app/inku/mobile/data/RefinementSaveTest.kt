package app.inku.mobile.data

import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.refinement.PaintSeeds
import app.inku.mobile.data.refinement.RefinementElement
import app.inku.mobile.data.refinement.RefinementParent
import app.inku.mobile.data.refinement.RefinementPlanner
import app.inku.mobile.data.refinement.VariationAmplitude
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * T-6 to T-9: what a refinement writes.
 *
 * A real Room database on the device, saved through `InkuRepository`, because
 * the rows are the only place the answer is. The JVM tests beside these read the
 * decision; these read the table.
 */
@RunWith(AndroidJUnit4::class)
class RefinementSaveTest {

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

    private fun countRows(table: String): Int {
        database.openHelper.readableDatabase.query("SELECT COUNT(*) FROM $table").use { cursor ->
            cursor.moveToFirst()
            return cursor.getInt(0)
        }
    }

    /** A work to refine, saved the ordinary way so it has a lineage node. */
    private suspend fun paintParent(description: String = "赤い線を引く"): HistoryItemEntity =
        repository.renderFromScore(
            description = description,
            scoreJson = score,
            catalogId = "ink_season",
            canvasAspect = "square",
            stage1ModelId = "test-stage1",
            stage2ModelId = "test-stage2",
            seeds = PaintSeeds(renderSeed = 4242L, compositionSeed = 77L, interpretationSeed = "parent-reading"),
        )

    private fun parentOf(item: HistoryItemEntity) = RefinementParent.of(item, item.originalInput)

    /** Draws and saves one candidate the way the view model does. */
    private suspend fun refineAndSave(
        parentItem: HistoryItemEntity,
        element: RefinementElement,
        newCatalogId: String? = null,
        seedText: String? = null,
        historyVisibility: String? = null,
    ): HistoryItemEntity {
        val parent = parentOf(parentItem)
        val plan = RefinementPlanner.plan(
            element = element,
            parent = parent,
            amplitude = VariationAmplitude.Large,
            newCatalogId = newCatalogId,
            seedText = seedText,
        )
        val result = repository.renderRefinementCandidate(parent, plan)
        return repository.saveRefinementCandidate(
            result = result,
            plan = plan,
            parentNodeId = parentItem.lineageNodeId,
            elapsedMs = 1L,
            historyVisibility = historyVisibility,
            stage1ModelId = parentItem.stage1Model ?: "",
            stage2ModelId = parentItem.stage2Model ?: "",
        )
    }

    // ── T-6 ────────────────────────────────────────────────

    /**
     * 「保存済み候補は再保存できない」, and this is the layer that does NOT enforce it.
     *
     * The repository writes what it is asked to write: it mints a fresh id for
     * every save (`newHistoryId()`), so a second call writes a second work.
     * Until the render hash stopped being unique it looked otherwise -- the
     * index replaced the first row and the count stayed at two -- so this test
     * passed for a reason it did not name, and it named a guard it never
     * reached. The guard lives in the view model, where `RefinementScreenTest`
     * measures it.
     */
    @Test
    fun t6_asecondSaveThroughTheRepositoryIsASecondWork() = runBlocking {
        val parent = paintParent()
        assertEquals(1, countRows("history_items"))

        val parentRef = parentOf(parent)
        val plan = RefinementPlanner.plan(RefinementElement.Color, parentRef, newCatalogId = "vivid_material")
        val result = repository.renderRefinementCandidate(parentRef, plan)

        repository.saveRefinementCandidate(
            result = result, plan = plan, parentNodeId = parent.lineageNodeId, elapsedMs = 1L,
            stage1ModelId = "s1", stage2ModelId = "s2",
        )
        assertEquals("the candidate is in history", 2, countRows("history_items"))

        // The same drawing again, reaching the same render hash. The server
        // keeps both (`db.py:178`, `:653`, `:2965`) and so does this table now.
        repository.saveRefinementCandidate(
            result = result, plan = plan, parentNodeId = parent.lineageNodeId, elapsedMs = 1L,
            stage1ModelId = "s1", stage2ModelId = "s2",
        )
        assertEquals("a second save is a second work", 3, countRows("history_items"))
    }

    // ── T-7 ────────────────────────────────────────────────

    /**
     * 「保存だけではスターを付けない」-- and the star still works, so an implementation
     * that broke starring outright does not pass by never setting it.
     */
    @Test
    fun t7_savingACandidateDoesNotStarItAndStarringStillWorks() = runBlocking {
        val parent = paintParent()
        val saved = refineAndSave(parent, RefinementElement.Color, newCatalogId = "vivid_material")

        assertFalse("the save left the star alone", saved.starred)
        assertFalse("and so it is in the table", database.historyDao().getById(saved.id)!!.starred)

        repository.setStarred(saved.id, true)
        assertTrue("the ordinary star operation still stars it", database.historyDao().getById(saved.id)!!.starred)
    }

    // ── T-8 ────────────────────────────────────────────────

    /**
     * Each of the five elements writes one edge, and the edge says which
     * intervention it was. The metadata is read back from the row, not from the
     * plan, so a declaration dropped between the two is visible here.
     */
    @Test
    fun t8_eachElementWritesOneEdgeOfItsOwnKind() = runBlocking {
        val cases = listOf(
            Triple(RefinementElement.Touch, "touch_change", "しずかに"),
            Triple(RefinementElement.Color, "catalog_change", null),
            Triple(RefinementElement.Layout, "layout_change", null),
            Triple(RefinementElement.Reading, "reinterpretation", null),
            Triple(RefinementElement.Variation, "variation", null),
        )

        cases.forEachIndexed { index, (element, expectedKind, words) ->
            val parent = paintParent("親$index")
            val edgesBefore = countRows("lineage_edges")
            val child = refineAndSave(
                parent,
                element,
                newCatalogId = if (element == RefinementElement.Color) "vivid_material" else null,
                seedText = words,
            )

            assertEquals("$element wrote exactly one edge", edgesBefore + 1, countRows("lineage_edges"))
            val edge = database.lineageDao().getEdgeByChildId(child.lineageNodeId!!)
            assertNotNull("$element: the edge is there", edge)
            assertEquals("$element", expectedKind, edge!!.derivationKind)
            assertEquals("$element: it hangs off the work refined", parent.lineageNodeId, edge.parentNodeId)

            val metadata = JSONObject(edge.metadataJson)
            when (element) {
                RefinementElement.Touch -> {
                    assertTrue(metadata.has("render_seed_from"))
                    assertTrue(metadata.has("render_seed_to"))
                    assertEquals("4242", metadata.getString("render_seed_from"))
                }
                RefinementElement.Color -> {
                    // SPEC :678 -- the edge records both catalogue ids.
                    assertEquals("ink_season", metadata.getString("catalog_id_from"))
                    assertEquals("vivid_material", metadata.getString("catalog_id_to"))
                }
                RefinementElement.Layout -> assertTrue(metadata.has("composition_seed"))
                RefinementElement.Reading -> assertTrue(metadata.has("interpretation_seed"))
                RefinementElement.Variation -> {
                    assertEquals("large", metadata.getString("variation_amplitude"))
                    assertTrue(metadata.has("variation_seed"))
                }
            }
        }
    }

    /** The seeds a candidate was made with are on its row, for the next refinement to inherit. */
    @Test
    fun t8_theSavedRowRecordsWhatItWasMadeWith() = runBlocking {
        val parent = paintParent()
        val child = refineAndSave(parent, RefinementElement.Color, newCatalogId = "vivid_material")

        val stored = database.historyDao().getById(child.id)!!
        assertEquals("the colour refinement held the parent's touch", "4242", stored.renderSeed)
        assertEquals("and its layout", "77", stored.compositionSeed)
        assertEquals("and its reading", "parent-reading", stored.interpretationSeed)
        assertEquals("only the catalogue moved", "vivid_material", stored.colorCatalogId)
        assertEquals("the canvas is the parent's", parent.canvasAspect, stored.canvasAspect)
    }

    // ── T-9 ────────────────────────────────────────────────

    /**
     * SPEC `:2105`: drawing on from a candidate that was never saved records the
     * candidate as a `lineage_only` node, so the branch keeps the step that was
     * really taken instead of showing the new work hanging off its grandparent.
     */
    @Test
    fun t9_anUnsavedCandidateBecomesALineageOnlyAncestor() = runBlocking {
        val grandparent = paintParent()
        val candidate = refineAndSave(
            grandparent,
            RefinementElement.Color,
            newCatalogId = "vivid_material",
            historyVisibility = "lineage_only",
        )

        val node = database.lineageDao().getNodeById(candidate.lineageNodeId!!)!!
        assertEquals("the candidate is in the lineage but not in the ordinary history", "lineage_only", node.state)

        // The next work comes from the candidate, not from what it was refined from.
        val next = repository.renderFromScore(
            description = "候補から描き継ぐ",
            scoreJson = score,
            catalogId = "vivid_material",
            canvasAspect = "square",
            stage1ModelId = "s1",
            stage2ModelId = "s2",
            lineage = app.inku.mobile.data.lineage.LineageDeclaration(
                parentNodeId = candidate.lineageNodeId,
                derivationKind = "replay",
            ),
            seeds = PaintSeeds(renderSeed = 555L),
        )

        val edge = database.lineageDao().getEdgeByChildId(next.lineageNodeId!!)!!
        assertEquals("the candidate is the direct ancestor", candidate.lineageNodeId, edge.parentNodeId)
        assertEquals("and the root still comes from the top", grandparent.lineageNodeId, database.lineageDao().getNodeById(next.lineageNodeId!!)!!.rootNodeId)
    }

    /** A candidate that is only drawn writes nothing at all. */
    @Test
    fun aCandidateThatIsNotSavedReachesNoTable() = runBlocking {
        val parent = parentOf(paintParent())
        val rowsBefore = countRows("history_items")

        val plan = RefinementPlanner.plan(RefinementElement.Color, parent, newCatalogId = "vivid_material")
        val result = repository.renderRefinementCandidate(parent, plan)

        assertTrue("something was drawn", result.displaySvg.isNotEmpty())
        assertEquals("and none of it was saved", rowsBefore, countRows("history_items"))
        assertEquals(1, countRows("lineage_nodes"))
        assertEquals(0, countRows("lineage_edges"))
    }

    /**
     * T-11, on the wiring rather than on the layer.
     *
     * The JVM test beside this one calls `WebDdlExpander` directly and would
     * stay green if nothing on the request ever reached it -- which is exactly
     * the shape of [I-142]. This goes in through `PaintRequest`, so the two
     * variation fields have to survive the whole way to Stage 1.5.
     *
     * `composeFromDdl` is the entry that carries them, and it logs, so it can
     * only be run on a device.
     */
    @Test
    fun t11_theVariationPairReachesStage1_5ThroughTheRequest() = runBlocking {
        val ddl = "画面の中央に太い墨の線を一本引く。右上に小さな円を三つ散らす。"

        suspend fun expandedOf(amplitude: String?, seed: Long?): String = repository.composeFromDdl(
            description = "変奏 $amplitude $seed",
            ddl = ddl,
            catalogId = "default",
            canvasAspect = "square",
            stage1ModelId = "s1",
            stage2ModelId = "s2",
            autoRepair = true,
            seeds = PaintSeeds(variationAmplitude = amplitude, variationSeed = seed),
        ).expandedDdl!!

        val none = expandedOf(null, null)
        val small7 = expandedOf("small", 7L)
        val small7Again = expandedOf("small", 7L)
        val medium7 = expandedOf("medium", 7L)
        val small8 = expandedOf("small", 8L)

        assertEquals("the same pair expands the same way", small7, small7Again)
        assertTrue("a variation is not the unvaried expansion", small7 != none)
        assertTrue("the amplitude alone moves it", small7 != medium7)
        assertTrue("the seed alone moves it", small7 != small8)
    }

    /** The touch seed reaches the renderer through the request, not only the Score. */
    @Test
    fun t11_theRenderSeedReachesTheRendererThroughTheRequest() = runBlocking {
        val a = repository.renderFromScore(
            description = "タッチ a", scoreJson = score, catalogId = "default", canvasAspect = "square",
            stage1ModelId = "s1", stage2ModelId = "s2", seeds = PaintSeeds(renderSeed = 4242L),
        )
        val b = repository.renderFromScore(
            description = "タッチ b", scoreJson = score, catalogId = "default", canvasAspect = "square",
            stage1ModelId = "s1", stage2ModelId = "s2", seeds = PaintSeeds(renderSeed = 9999L),
        )

        assertTrue("the performance differs", a.displaySvg != b.displaySvg)
        assertEquals("4242", database.historyDao().getById(a.id)!!.renderSeed)
        assertEquals("9999", database.historyDao().getById(b.id)!!.renderSeed)
    }

    /** The migration this contract adds carries a work across without losing it. */
    @Test
    fun theSeedColumnsAreNullForAWorkThatNeverHadThem() = runBlocking {
        val item = repository.renderFromScore(
            description = "seed を持たない作品",
            scoreJson = score,
            catalogId = "default",
            canvasAspect = "square",
            stage1ModelId = "s1",
            stage2ModelId = "s2",
        )

        val stored = database.historyDao().getById(item.id)!!
        // A drawing always gets a touch now, so this one is not null...
        assertNotNull("every drawing is performed with a seed", stored.renderSeed)
        // ...but nothing asked for the other four, so they stay unsaid.
        assertNull(stored.compositionSeed)
        assertNull(stored.interpretationSeed)
        assertNull(stored.variationAmplitude)
        assertNull(stored.variationSeed)
    }
}
