package app.inku.mobile.data.refinement

import app.inku.mobile.data.refinementColorSnapshot
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.WorkColorSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RefinementColorContractTest {
    private val snapshot = WorkColorSnapshot(
        "default",
        ColorCatalogs.get("default").renderMap,
    )

    private fun parent(held: WorkColorSnapshot? = snapshot) = RefinementParent(
        historyId = "parent",
        lineageNodeId = null,
        description = "red line",
        ddl = "中央に赤い線を一本引く。",
        scoreJson = """{"instructions":[]}""",
        catalogId = "default",
        canvasAspect = "square",
        stage1Model = "stage1",
        stage2Model = "stage2",
        seeds = PaintSeeds(renderSeed = 4242L),
        workColorSnapshot = held,
    )

    @Test
    fun colorRefinementUsesTheRequestedCatalogNotTheSnapshot() {
        val parent = parent()
        val plan = RefinementPlanner.plan(
            RefinementElement.Color,
            parent,
            newCatalogId = "vivid_material",
        )

        assertNull(refinementColorSnapshot(parent, plan))
    }

    // A replay of the saved Score in the parent's catalogue, the shape of the
    // tool change (`InkuRepository.toolChangePlan`). The touch refinement that
    // used to stand here was retired on 2026-10-14; a layout composes a new
    // Score from the DDL, so it is not one of these.
    private fun scoreOnlyPlan(parent: RefinementParent) = RefinementPlan(
        element = null,
        route = RefinementRoute.RenderFromScore,
        catalogId = parent.catalogId,
        canvasAspect = parent.canvasAspect,
        seeds = parent.seeds,
        derivationKind = "tool_change",
        derivationMetadata = emptyMap(),
    )

    @Test
    fun scoreOnlyRefinementKeepsTheParentSnapshot() {
        val parent = parent()

        assertEquals(snapshot, refinementColorSnapshot(parent, scoreOnlyPlan(parent)))
    }

    @Test
    fun missingParentSnapshotStaysMissing() {
        val parent = parent(null)

        assertNull(refinementColorSnapshot(parent, scoreOnlyPlan(parent)))
    }
}
