package app.inku.mobile.pipeline

/** Thin byte transport implemented by the Android JNI bridge. */
interface SharedPipelineBinding {
    fun versionReport(): String
    fun stage1SystemProjection(languageCode: String): String =
        throw UnsupportedOperationException("stage1_system_projection_unavailable")
    fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray): ByteArray
    fun canvasRegistry(): String
    fun resolvePalette(inputBytes: ByteArray): ByteArray
    fun resolveMacroCatalog(inputBytes: ByteArray): ByteArray
    fun renderSaved(inputBytes: ByteArray): ByteArray
}
