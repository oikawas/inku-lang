package app.inku.mobile.ui

import app.inku.mobile.pipeline.PipelineProviderFailure
import app.inku.mobile.pipeline.HoleCompletionResult
import app.inku.mobile.pipeline.PipelineView
import app.inku.mobile.ui.i18n.InkuStrings
import org.json.JSONObject

internal data class ComposeScreenLayout(
    val showEditor: Boolean,
    val showPipelineStatus: Boolean,
    val presentationOnly: Boolean,
)

/** Answering a run is independent of whether its safe performance is already on screen. */
internal fun composeScreenLayout(state: InkuUiState): ComposeScreenLayout {
    val view = state.pipelineView
    val needsAnswer = view?.patchProposal != null || view?.phaseReason != null ||
        view?.phaseTag == "score_ready" || (view?.phaseTag == "completed" && !savedPipelineRevision(state))
    val showEditor = state.selectedHistory == null || state.descriptionEditing || state.composeMode == ComposeMode.Batch
    return ComposeScreenLayout(
        showEditor = showEditor,
        showPipelineStatus = showEditor || needsAnswer,
        presentationOnly = state.canvasPresentationMode && !needsAnswer,
    )
}

internal data class PipelineStatusPresentation(val attentionText: String?, val canResume: Boolean)

internal fun pipelineStatusPresentation(state: InkuUiState, strings: InkuStrings): PipelineStatusPresentation {
    val view = state.pipelineView
    return PipelineStatusPresentation(
        attentionText = view?.phaseReason?.let { pipelineAttentionText(it, view.providerFailure, strings) },
        canResume = view?.patchProposal == null && (view?.phaseTag == "score_ready" ||
            (view?.phaseTag == "completed" && !savedPipelineRevision(state))),
    )
}

internal fun savedPipelineRevision(state: InkuUiState): Boolean = runCatching {
    val metadata = JSONObject(state.selectedHistory?.renderMetadataJson ?: "{}")
    metadata.optString("pipeline_execution_id") == state.pipelineView?.executionId &&
        metadata.optString("pipeline_revision") == state.pipelineView?.revision
}.getOrDefault(false)

/** The stage a stopped phase belongs to, as [PipelineProviderFailure.stage] names it (web `attention.ts`). */
private val STAGE_OF_REASON = mapOf(
    "stage1_failed" to "stage1",
    "hole_completion_failed" to "stage2",
)

/**
 * Web's `pipelineAttentionText`: why a run stopped, and what happened to the
 * model when the stage that stopped was its call. An earlier stage's retry
 * that later succeeded explains nothing and is left out.
 */
fun pipelineAttentionText(reason: String, failure: PipelineProviderFailure?, strings: InkuStrings): String {
    val base = "${strings.pipelineNeedsAttention} ${strings.pipelineAttentionReason(reason)}"
    if (failure == null || failure.stage != STAGE_OF_REASON[reason]) return base
    return base + strings.pipelineFailureCause(failure.failure, failure.attempt, failure.detail)
}

/** Explain incomplete holes only when completion stops or asks for approval. */
internal fun holeCompletionDetails(view: PipelineView?): List<HoleCompletionResult> {
    if (view == null || (view.phaseTag != "awaiting_patch_approval" &&
            view.phaseReason !in setOf("hole_completion_failed", "hole_completion_context_limit"))) return emptyList()
    return view.holeCompletionResults.filter { it.status == "rejected" || it.status == "unresolved" }
}
