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

/**
 * Vision is the only method: the random one, which drew each generation's
 * element by chance, was removed (the author, 2026-10-18). Generations made
 * with it keep `autonomous_refine_mode: random` and stay readable.
 */
data class AutonomousRefinementSettings(
    val generations: Int = 3,
    val changeColor: Boolean = true,
    val changeLayout: Boolean = true,
    val modelId: String = "",
    val direction: String = "",
    val wildOverride: Boolean? = null,
) {
    val allowedKinds: List<String>
        get() = buildList {
            if (changeColor) add("catalog_change")
            if (changeLayout) add("layout_change")
        }
}

data class AutonomousRefinementStatus(
    val busy: Boolean = false,
    val step: Int = 0,
    val total: Int = 0,
    val observation: String? = null,
    val nextDirection: String? = null,
    val message: String? = null,
    val error: String? = null,
)

data class ParityModelChoice(val id: String, val label: String, val provider: String)
