package app.inku.mobile.ui

import app.inku.mobile.data.db.HistoryItemEntity
import org.junit.Assert.*
import org.junit.Test

class DescriptionWorkspaceStateTest {
    private val work = HistoryItemEntity(
        id = "work", createdAt = 0, updatedAt = 0, originalInput = "赤い円。",
        normalizedDdl = "赤い円を置く。", scoreJson = "{}", displaySvg = "<svg/>",
        stage1Model = null, stage2Model = null, renderMetadataJson = "{}",
        renderHash = "hash", renderHashShort = "hash", colorCatalogId = "default", canvasAspect = "square",
        starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null,
        lineageNodeId = "parent-node",
    )

    @Test fun returningToStudioKeepsTheEditedDescriptionItsWorkAndItsParent() {
        val editing = InkuUiState(
            tab = AppTab.Lineage, selectedHistory = work, workContextId = work.id,
            prompt = "赤い円を小さく。", ddl = "作者が編集中の指示書。", ddlEditedAfterGeneration = true,
            lineageDetached = false, descriptionEditing = true, descriptionForkRequested = true,
            selectedCatalogId = "catalog-for-next-work", selectedCanvasAspect = "portrait",
        )
        val studio = editing.returnToDescriptionWorkspace()
        assertEquals(AppTab.Compose, studio.tab)
        assertEquals(editing.prompt, studio.prompt)
        assertEquals(editing.ddl, studio.ddl)
        assertTrue(studio.ddlEditedAfterGeneration)
        assertSame(work, studio.selectedHistory)
        assertEquals(work.id, studio.workContextId)
        assertFalse(studio.lineageDetached)
        assertTrue(studio.descriptionForkRequested)
        assertEquals(editing.selectedCatalogId, studio.selectedCatalogId)
        assertEquals(editing.selectedCanvasAspect, studio.selectedCanvasAspect)
    }

    @Test fun aFinishedOrHeldWorkStillOffersItsDescriptionWithoutUnlockingIt() {
        val held = InkuUiState(selectedHistory = work, prompt = work.originalInput,
            historyDescriptionLocked = true, descriptionEditing = false)
        assertTrue(composeScreenLayout(held).showEditor)
        val returned = held.copy(tab = AppTab.Settings).returnToDescriptionWorkspace()
        assertSame(work, returned.selectedHistory)
        assertTrue(returned.descriptionLocked)
        assertFalse(returned.descriptionForkRequested)
        assertTrue(composeScreenLayout(returned).showEditor)
    }
}
