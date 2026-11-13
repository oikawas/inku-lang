package app.inku.mobile.ui

/** Conditions are frozen before the first line, including a later failed-line retry. */
internal data class BatchConditions(
    val catalogId: String,
    val canvasAspect: String,
    val modelId: String,
    val stage2ModelId: String,
    val languageCode: String,
    val renderWild: Boolean,
    val readAndDraw: Boolean = false,
    val composition: Boolean = false,
    val sketch: Boolean = false,
    val review: Boolean = false,
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
