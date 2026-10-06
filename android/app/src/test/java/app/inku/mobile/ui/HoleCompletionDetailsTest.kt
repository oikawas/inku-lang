package app.inku.mobile.ui

import app.inku.mobile.pipeline.HoleCompletionResult
import app.inku.mobile.pipeline.PipelineView
import app.inku.mobile.ui.i18n.InkuStringsEn
import app.inku.mobile.ui.i18n.InkuStringsJa
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HoleCompletionDetailsTest {
    @Test
    fun approvalAndStoppedCompletionExplainOnlyIncompleteHolesInTheAuthorsWords() {
        val checked = listOf(
            HoleCompletionResult("h1", "通った文", "validated", null),
            HoleCompletionResult("h2", "右下に赤い円", "rejected", "numeric_range_outside_words"),
            HoleCompletionResult("h3", "その周りに青い点", "unresolved", "unsupported"),
            HoleCompletionResult("h4", "もう一つの原文", "rejected", "future_check_code"),
        )
        val approval = PipelineView(
            executionId = "run", variationId = "variation", sequence = "1", revision = "1",
            origin = "user_committed", authority = "ddl_authoritative", phaseTag = "awaiting_patch_approval",
            visibleDdl = "all the original instructions", scoreJson = null, deliveryJson = null,
            renderedJson = null, patchProposal = null, busy = false, terminal = false, eventsJson = "[]",
            holeCompletionResults = checked,
        )
        val details = holeCompletionDetails(approval)
        assertEquals(listOf("右下に赤い円", "その周りに青い点", "もう一つの原文"), details.map { it.source })
        assertEquals(
            listOf("数の範囲が、括弧の前の位置の語の範囲から外れた", "今の文法では書けないと答えた", "検査で断られた（future_check_code）"),
            details.map { InkuStringsJa.pipelineHoleCompletionReason(it.reason.orEmpty()) },
        )
        assertEquals(
            listOf("The numeric range fell outside the place word before the parenthesis.",
                "The model answered that the current grammar cannot write it.", "Refused by the check (future_check_code)."),
            details.map { InkuStringsEn.pipelineHoleCompletionReason(it.reason.orEmpty()) },
        )
        assertEquals(details, holeCompletionDetails(approval.copy(phaseTag = "needs_user_edit", phaseReason = "hole_completion_failed")))
        val context = approval.copy(
            phaseTag = "needs_user_edit", phaseReason = "hole_completion_context_limit",
            holeCompletionResults = listOf(HoleCompletionResult("h2", "右下に赤い円", "unresolved", "context_limit")),
        )
        assertEquals("右下に赤い円", holeCompletionDetails(context).single().source)
        assertEquals("文脈が長すぎて補えなかった", InkuStringsJa.pipelineHoleCompletionReason("context_limit"))
        assertEquals("The context was too long to complete.", InkuStringsEn.pipelineHoleCompletionReason("context_limit"))
        assertEquals("理由: 文脈が長すぎて補えなかった", InkuStringsJa.pipelineAttentionReason("hole_completion_context_limit"))
        assertEquals("Reason: The context was too long to complete.", InkuStringsEn.pipelineAttentionReason("hole_completion_context_limit"))
        assertTrue(holeCompletionDetails(approval.copy(phaseTag = "awaiting_llm")).isEmpty())
        assertTrue(holeCompletionDetails(approval.copy(phaseTag = "failed", phaseReason = "stage1_failed")).isEmpty())
        assertTrue(holeCompletionDetails(approval.copy(holeCompletionResults = checked.take(1))).isEmpty())
    }
}
