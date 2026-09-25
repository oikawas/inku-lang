package app.inku.mobile.pipeline

/** Synchronous owned-byte transport; the host owns scheduling and all effects. */
object NativePipelineBridge : SharedPipelineBinding {
    init {
        System.loadLibrary("inku_render_android")
    }

    external override fun versionReport(): String
    external override fun stage1SystemProjection(languageCode: String): String
    external override fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray): ByteArray
    external override fun canvasRegistry(): String
    external override fun resolvePalette(inputBytes: ByteArray): ByteArray
    external override fun resolveMacroCatalog(inputBytes: ByteArray): ByteArray
    external override fun renderSaved(inputBytes: ByteArray): ByteArray
    external override fun explainPluginDiagnostics(inputBytes: ByteArray): ByteArray
}
