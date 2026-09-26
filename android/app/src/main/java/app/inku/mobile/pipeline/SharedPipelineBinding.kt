package app.inku.mobile.pipeline

/** Thin byte transport implemented by the Android JNI bridge. */
interface SharedPipelineBinding {
    fun versionReport(): String
    fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray): ByteArray
    fun canvasRegistry(): String
    fun resolvePalette(inputBytes: ByteArray): ByteArray
    fun resolveMacroCatalog(inputBytes: ByteArray): ByteArray
    fun renderSaved(inputBytes: ByteArray): ByteArray

    /** Author-facing reasons for withheld plugin sentences; a host without it has none. */
    fun explainPluginDiagnostics(inputBytes: ByteArray): ByteArray =
        """{"schema":"inku.plugin-diagnostics.v1","plugins":[]}""".encodeToByteArray()

    /**
     * The provider attempt in flight for a stored snapshot, as
     * `{"provider_attempt": {...} | null}`; a host without the call reports none.
     */
    fun providerAttempt(snapshotBytes: ByteArray): ByteArray =
        """{"provider_attempt":null}""".encodeToByteArray()
}
