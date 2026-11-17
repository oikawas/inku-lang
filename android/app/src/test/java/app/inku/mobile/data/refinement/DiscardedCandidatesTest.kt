package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.PaintResult
import app.inku.mobile.pipeline.PipelineView
import app.inku.mobile.ui.RefinementCandidate
import app.inku.mobile.ui.RefinementSaveState
import app.inku.mobile.ui.unsavedCandidateDrafts
import org.junit.Assert.assertEquals
import org.junit.Test

class DiscardedCandidatesTest {
    @Test fun onlyUnsavedCandidatesWithPipelineDocumentsAreDiscarded() {
        fun view(id: String) = PipelineView(id, id, "1", "1", "user_authored_ddl", "ddl_authoritative",
            "completed", "", null, null, null, null, false, true, "[]")
        val plan = RefinementPlan(null, RefinementRoute.Paint, "default", "square", PaintSeeds(), "new", emptyMap())
        fun candidate(id: String, state: RefinementSaveState, document: PipelineView?) = RefinementCandidate(
            id = id, label = id, plan = plan, displaySvg = "", scoreJson = "{}", normalizedDdl = "",
            renderHash = "", renderHashShort = "", renderMetadataJson = "{}", elapsedMs = 0,
            stage1Model = "", stage2Model = "", saveState = state,
            pipelineResult = PaintResult("", "", "{}", "", "{}", "", "", pipelineView = document),
        )
        val drafts = unsavedCandidateDrafts(listOf(
            candidate("unsaved", RefinementSaveState.Unsaved, view("unsaved")),
            candidate("saved", RefinementSaveState.Saved, view("saved")),
            candidate("saving", RefinementSaveState.Saving, view("saving")),
            candidate("tool", RefinementSaveState.Unsaved, null),
        ))
        assertEquals(listOf("unsaved"), drafts.map { it.variationId })
    }
}
