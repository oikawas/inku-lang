package app.inku.mobile.pipeline

/** Thin byte transport implemented by the Android JNI bridge. */
interface SharedPipelineBinding {
    fun versionReport(): String
    fun step(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray): ByteArray
    fun canvasRegistry(): String
    /** Range names and exact bounds; an older binding leaves the DDL display unfolded. */
    fun compositionRanges(): String =
        """{"schema":"inku.composition-ranges.v1","ranges":[]}"""
    fun resolvePalette(inputBytes: ByteArray): ByteArray
    fun resolveMacroCatalog(inputBytes: ByteArray): ByteArray
    fun renderSaved(inputBytes: ByteArray): ByteArray

    /** Selects other composition ranges without a model; an older binding leaves them alone. */
    fun recompose(inputBytes: ByteArray): ByteArray =
        """{"error":"unavailable"}""".encodeToByteArray()

    /** Author-facing reasons for withheld plugin sentences; a host without it has none. */
    fun explainPluginDiagnostics(inputBytes: ByteArray): ByteArray =
        """{"schema":"inku.plugin-diagnostics.v1","plugins":[]}""".encodeToByteArray()

    /**
     * The provider attempt in flight for a stored snapshot, as
     * `{"provider_attempt": {...} | null}`; a host without the call reports none.
     */
    fun providerAttempt(snapshotBytes: ByteArray): ByteArray =
        """{"provider_attempt":null}""".encodeToByteArray()

    /**
     * The description every layer reads, with the author's leading numbers and
     * bracketed comments cut by the one shared rule. A binding without it
     * refuses rather than passing the labels through to the core.
     */
    fun pipelineDescription(text: String): String =
        throw PipelineHostException("binding_description_labels_unavailable")

    /**
     * A word-touch seed as `{"render_seed": "<decimal>", "seed_text": "<normalized>"}`,
     * or null when the words carry no seed. A binding without it refuses rather
     * than deriving a different seed in Kotlin.
     */
    fun renderSeedFromText(seedText: String): String? =
        throw PipelineHostException("binding_text_seed_unavailable")
}
