package app.inku.mobile.ui

import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.pipeline.PipelinePatchProposal
import app.inku.mobile.pipeline.PipelineView
import app.inku.mobile.ui.i18n.InkuStringsJa
import org.junit.Assert.*
import org.junit.Test

class PipelineStatusPlacementTest {
    @Test
    fun aSafePerformanceKeepsApprovalAndStoppedRunAnswersOutsideTheEditor() {
        val proposal = PipelinePatchProposal("exact-proposal", "1", "{}", "左下（横0〜1/3、縦2/3〜1）に円。")
        val view = PipelineView("run", "variation", "1", "1", "user_committed", "ddl_authoritative",
            "awaiting_patch_approval", "左下に円。", null, null, null, proposal, false, false, "[]")
        val work = HistoryItemEntity(id = "safe", createdAt = 0, updatedAt = 0, originalInput = "",
            normalizedDdl = view.visibleDdl, scoreJson = "{}", displaySvg = "<svg/>",
            stage1Model = null, stage2Model = null,
            renderMetadataJson = """{"pipeline_execution_id":"run","pipeline_revision":"1"}""",
            renderHash = "hash", renderHashShort = "hash", colorCatalogId = "default", canvasAspect = "square",
            starred = false, trashed = false, elapsedMs = null, tokenMetadataJson = null)
        val showingWork = InkuUiState(selectedHistory = work, pipelineView = view)
        assertTrue(composeScreenLayout(showingWork).showEditor)
        assertTrue(composeScreenLayout(showingWork).showPipelineStatus)
        assertFalse(composeScreenLayout(showingWork.copy(canvasPresentationMode = true)).presentationOnly)
        assertSame(proposal, showingWork.pipelineView!!.patchProposal)
        assertEquals("左下に円。", showingWork.pipelineView.visibleDdl)
        assertFalse(pipelineStatusPresentation(showingWork, InkuStringsJa).canResume)
        assertTrue(composeScreenLayout(showingWork.copy(descriptionEditing = true)).showEditor)
        assertTrue(composeScreenLayout(showingWork.copy(composeMode = ComposeMode.Batch)).showEditor)
        assertTrue(composeScreenLayout(showingWork.copy(selectedHistory = null)).showEditor)

        val stopped = showingWork.copy(pipelineView = view.copy(phaseTag = "needs_user_edit",
            patchProposal = null, phaseReason = "hole_completion_context_limit"), message = null)
        assertTrue(composeScreenLayout(stopped).showEditor)
        assertTrue(composeScreenLayout(stopped).showPipelineStatus)
        assertFalse(composeScreenLayout(stopped.copy(canvasPresentationMode = true)).presentationOnly)
        assertEquals("${InkuStringsJa.pipelineNeedsAttention} ${InkuStringsJa.pipelineAttentionReason("hole_completion_context_limit")}",
            pipelineStatusPresentation(stopped, InkuStringsJa).attentionText)
        assertFalse(pipelineStatusPresentation(stopped, InkuStringsJa).canResume)
        assertTrue(composeScreenLayout(stopped.copy(pipelineView = stopped.pipelineView!!.copy(
            phaseTag = "failed", phaseReason = "stage1_failed"))).showPipelineStatus)
        val ready = showingWork.copy(pipelineView = view.copy(phaseTag = "score_ready", patchProposal = null))
        assertTrue(pipelineStatusPresentation(ready, InkuStringsJa).canResume)
        assertFalse(composeScreenLayout(ready.copy(canvasPresentationMode = true)).presentationOnly)
        val completed = ready.copy(pipelineView = ready.pipelineView!!.copy(phaseTag = "completed"))
        assertFalse(pipelineStatusPresentation(completed, InkuStringsJa).canResume)
        assertFalse(composeScreenLayout(completed).showPipelineStatus)
        assertFalse(composeScreenLayout(showingWork.copy(pipelineView = null)).showPipelineStatus)
        assertTrue(composeScreenLayout(completed.copy(canvasPresentationMode = true)).presentationOnly)
        assertTrue(pipelineStatusPresentation(completed.copy(selectedHistory = null), InkuStringsJa).canResume)
    }
}
