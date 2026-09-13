package app.inku.mobile.pipeline

/** Host provenance needed by the atomic visible-DDL commit. */
data class AuthoringContext(
    val description: String,
    val derivationKind: String = "new",
    val parentLegacyHistoryId: String? = null,
    val parentVariationId: String? = null,
)

/** Room-owned implementation of the core-requested authority transition. */
interface PipelineCommitStore {
    suspend fun commit(
        ownerId: String,
        actionJson: String,
        createIfMissing: Boolean,
        context: AuthoringContext,
    ): String
}

/** Opaque durable execution storage. Only the host decodes [stateBytes]. */
interface PipelineExecutionStore {
    suspend fun create(
        ownerId: String,
        executionId: String,
        variationId: String,
        sequence: String,
        stateBytes: ByteArray,
    )

    suspend fun compareAndSet(
        ownerId: String,
        executionId: String,
        expectedSequence: String,
        nextSequence: String,
        stateBytes: ByteArray,
    ): Boolean

    suspend fun load(ownerId: String, executionId: String): ByteArray?
}
