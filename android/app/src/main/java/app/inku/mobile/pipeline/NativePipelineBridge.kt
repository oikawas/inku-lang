package app.inku.mobile.pipeline

/** SVG is detached so JSON escaping cannot consume the protocol's byte allowance. */
data class NativeSvgOutput(val jsonBytes: ByteArray, val svg: String?)

/** Synchronous owned-byte transport; the host owns scheduling and all effects. */
object NativePipelineBridge : SharedPipelineBinding {
    init {
        System.loadLibrary("inku_render_android")
    }

    external override fun versionReport(): String
    external override fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray): ByteArray
    external override fun canvasRegistry(): String
    external override fun compositionRanges(): String
    external override fun resolvePalette(inputBytes: ByteArray): ByteArray
    external override fun resolveMacroCatalog(inputBytes: ByteArray): ByteArray
    external override fun renderSaved(inputBytes: ByteArray): ByteArray
    external override fun stepSvgLimited(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray, maxSvgBytes: Long): NativeSvgOutput
    external override fun renderSavedSvgLimited(inputBytes: ByteArray, maxSvgBytes: Long): NativeSvgOutput
    external override fun explainPluginDiagnostics(inputBytes: ByteArray): ByteArray
    external override fun recompose(inputBytes: ByteArray): ByteArray
    external override fun retouch(inputBytes: ByteArray): ByteArray
    external override fun completionRangeStates(inputBytes: ByteArray): ByteArray
    external override fun providerAttempt(snapshotBytes: ByteArray): ByteArray
    external override fun pipelineDescription(text: String): String
    external override fun renderSeedFromText(seedText: String): String?

    /** One saved Saijiki v1 unit in, the same unit in the current edition out (SPEC §3.3). */
    external fun migrateSaijikiV1(inputBytes: ByteArray): ByteArray
}
