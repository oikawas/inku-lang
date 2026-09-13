package app.inku.mobile.pipeline

/** Thin byte transport implemented by the Android JNI bridge. */
interface SharedPipelineBinding {
    fun versionReport(): String
    fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray): ByteArray
    fun canvasRegistry(): String
    fun resolvePalette(inputBytes: ByteArray): ByteArray
    fun resolveMacroCatalog(inputBytes: ByteArray): ByteArray
    fun renderSaved(inputBytes: ByteArray): ByteArray
}
