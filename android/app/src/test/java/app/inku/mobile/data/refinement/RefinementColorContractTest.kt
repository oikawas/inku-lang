package app.inku.mobile.data.refinement

import app.inku.mobile.data.refinementColorSnapshot
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.WorkColorSnapshot
import app.inku.mobile.pipeline.LocalFallbackPipeline
import app.inku.mobile.pipeline.PaintRequest
import app.inku.mobile.render.DefaultSvgRenderer
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RefinementColorContractTest {
    private val score = """
        {"version":"0.1.0","canvas":"square","background":"white","instructions":[
          {"primitive":"line","from":[0.2,0.5],"to":[0.8,0.5],"color":"red","weight":"rotring"}
        ]}
    """.trimIndent()

    private fun parent(snapshot: WorkColorSnapshot?) = RefinementParent(
        historyId = "parent",
        lineageNodeId = null,
        description = "red line",
        ddl = "中央に赤い線を一本引く。",
        scoreJson = score,
        catalogId = "default",
        canvasAspect = "square",
        stage1Model = "stage1",
        stage2Model = "stage2",
        seeds = PaintSeeds(renderSeed = 4242L),
        workColorSnapshot = snapshot,
    )

    private fun request(catalogId: String, snapshot: WorkColorSnapshot?) = PaintRequest(
        description = "red line",
        stage1Model = "stage1",
        stage2Model = "stage2",
        colorCatalogId = catalogId,
        canvasAspect = "square",
        autoRepair = false,
        renderSeed = 4242L,
        workColorSnapshot = snapshot,
    )

    @Test
    fun t1_colourRefinementUsesTheRequestedCatalogInsteadOfTheSnapshot() = runBlocking {
        val snapshot = WorkColorSnapshot("default", ColorCatalogs.get("default").renderMap)
        val parent = parent(snapshot)
        val plan = RefinementPlanner.plan(RefinementElement.Color, parent, newCatalogId = "vivid_material")
        val selected = refinementColorSnapshot(parent, plan)
        val pipeline = LocalFallbackPipeline(DefaultSvgRenderer())
        val candidate = pipeline.renderFromScore(score, request(plan.catalogId, selected))
        val requestedCatalog = pipeline.renderFromScore(score, request("vivid_material", null))
        val parentDrawing = pipeline.renderFromScore(score, request("default", snapshot))

        assertNull(selected)
        assertEquals(requestedCatalog.displaySvg, candidate.displaySvg)
        assertNotEquals(parentDrawing.displaySvg, candidate.displaySvg)
    }

    @Test
    fun t2_touchRefinementKeepsDrawingFromTheSnapshot() = runBlocking {
        val changedMap = ColorCatalogs.get("default").renderMap.mapValues { "#00aa00" }
        val snapshot = WorkColorSnapshot("default", changedMap)
        val parent = parent(snapshot)
        val plan = RefinementPlanner.plan(RefinementElement.Touch, parent, seedText = "quiet")
        val selected = refinementColorSnapshot(parent, plan)
        val pipeline = LocalFallbackPipeline(DefaultSvgRenderer())
        val candidate = pipeline.renderFromScore(score, request(plan.catalogId, selected).copy(renderSeed = plan.seeds.renderSeed))
        val replay = pipeline.renderFromScore(score, request("default", snapshot).copy(renderSeed = plan.seeds.renderSeed))
        val currentCatalog = pipeline.renderFromScore(score, request("default", null).copy(renderSeed = plan.seeds.renderSeed))

        assertEquals(snapshot, selected)
        assertEquals(replay.displaySvg, candidate.displaySvg)
        assertNotEquals(currentCatalog.displaySvg, candidate.displaySvg)
    }

    @Test
    fun t3_colourRefinementWithoutASnapshotStillUsesTheRequestedCatalog() = runBlocking {
        val parent = parent(null)
        val plan = RefinementPlanner.plan(RefinementElement.Color, parent, newCatalogId = "vivid_material")
        val selected = refinementColorSnapshot(parent, plan)
        val pipeline = LocalFallbackPipeline(DefaultSvgRenderer())
        val candidate = pipeline.renderFromScore(score, request(plan.catalogId, selected))
        val requestedCatalog = pipeline.renderFromScore(score, request("vivid_material", null))

        assertNull(selected)
        assertEquals(requestedCatalog.displaySvg, candidate.displaySvg)
    }
}
