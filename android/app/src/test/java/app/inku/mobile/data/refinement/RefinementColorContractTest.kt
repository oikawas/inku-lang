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

    @Test
    fun scoreOnlyRefinementKeepsTheParentSnapshot() {
        val parent = parent()
        val plan = RefinementPlanner.plan(RefinementElement.Touch, parent, seedText = "quiet")

        assertEquals(snapshot, refinementColorSnapshot(parent, plan))
    }

    @Test
    fun missingParentSnapshotStaysMissing() {
        val parent = parent(null)
        val plan = RefinementPlanner.plan(RefinementElement.Touch, parent, seedText = "quiet")

        assertNull(refinementColorSnapshot(parent, plan))
    }
}
