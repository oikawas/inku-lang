package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.PaintResult

/** The exact preview that may be kept as a replay child, including its save identity. */
data class ReplayComparison(
    val parentHistoryId: String,
    val parentLineageNodeId: String,
    val originalSvg: String,
    val replayedSvg: String,
    val recordedVersion: String?,
    val currentVersion: String?,
    val provisionalSeed: Boolean,
    val originalSvgBytes: Int,
    val replayedSvgBytes: Int,
    val renderHash: String,
    val svgSha256: String,
    val elapsedMs: Long,
    val result: PaintResult,
    val catalogId: String,
    val canvasAspect: String,
    val stage1ModelId: String,
    val stage2ModelId: String,
    val sourceText: String,
    val saveId: String,
)
