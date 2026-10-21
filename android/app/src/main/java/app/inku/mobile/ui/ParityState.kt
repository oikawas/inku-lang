package app.inku.mobile.ui

/** Conditions are frozen before the first line, including a later failed-line retry. */
internal data class BatchConditions(
    val catalogId: String,
    val canvasAspect: String,
    val modelId: String,
    val stage2ModelId: String,
    val languageCode: String,
    val renderWild: Boolean,
)

internal data class NumberedBatchLine(val number: Int, val input: String)

internal data class BatchSnapshot(
    val text: String,
    val lines: List<NumberedBatchLine>,
    val conditions: BatchConditions,
)

internal fun failedBatchLines(snapshot: BatchSnapshot, failures: List<BatchFailure>): List<NumberedBatchLine> {
    val failed = failures.associateBy { it.line }
    return snapshot.lines.filter { failed[it.number]?.input == it.input }
}

internal fun batchRetryAllowed(failures: List<BatchFailure>, completedRounds: Int, limit: Int, interrupted: Boolean): Boolean =
    !interrupted && failures.isNotEmpty() && completedRounds < limit.coerceIn(0, 5)

/** Settings for the shared core's laws and juxtaposition moves. */
typealias AutonomousRefinementSettings = app.inku.mobile.data.refinement.AutonomousSettings

data class AutonomousRefinementAttempt(
    val turn: Int, val kind: String, val outcome: String, val share: Double?,
    val historyId: String?, val detail: String?, val reason: String?,
)

data class AutonomousRefinementStatus(
    val busy: Boolean = false,
    val stopping: Boolean = false,
    val runId: String? = null,
    val step: Int = 0,
    val kind: String? = null,
    val stopReason: String? = null,
    val attempts: List<AutonomousRefinementAttempt> = emptyList(),
    val lastKeptHistoryId: String? = null,
    val error: String? = null,
) {
    companion object {
        fun fromRun(run: org.json.JSONObject): AutonomousRefinementStatus {
            val turns = run.getJSONArray("turns")
            val attempts = buildList {
                for (turn in 0 until turns.length()) {
                    val rows = turns.getJSONObject(turn).getJSONArray("attempts")
                    for (index in 0 until rows.length()) {
                        val row = rows.getJSONObject(index)
                        add(AutonomousRefinementAttempt(turn + 1, row.getString("kind"), row.getString("outcome"),
                            (row.opt("share") as? Number)?.toDouble(), row.opt("history_id") as? String,
                            row.opt("sentence") as? String ?: row.opt("main_law") as? String, row.opt("reason") as? String))
                    }
                }
            }
            val current = run.optJSONObject("current")
            return AutonomousRefinementStatus(run.getString("state") == "running", run.optBoolean("stopping"),
                run.getString("id"), current?.optInt("turn") ?: 0, current?.optString("kind"),
                run.opt("stop_reason") as? String, attempts, run.opt("last_kept_history_id") as? String,
                run.opt("error") as? String)
        }
    }
}

/**
 * The 取り合わせ dialog for one work. [shown] holds every sentence offered so
 * far, so that 選び直す leaves them out; [chosen] indexes [result]'s choices.
 */
data class JuxtapositionDialogState(
    val target: app.inku.mobile.data.db.HistoryItemEntity,
    val busy: Boolean = false,
    val startedAtMs: Long = 0L,
    val result: app.inku.mobile.data.refinement.JuxtapositionResult? = null,
    val shown: List<String> = emptyList(),
    val chosen: Int? = null,
    val error: String? = null,
) {
    val choice: app.inku.mobile.data.refinement.JuxtapositionChoice?
        get() = chosen?.let { result?.choices?.getOrNull(it) }
}
