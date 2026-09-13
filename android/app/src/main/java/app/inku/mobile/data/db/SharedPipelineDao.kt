package app.inku.mobile.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface SharedPipelineDao {
    @Query("SELECT * FROM variation_authority WHERE owner_id = :ownerId AND variation_id = :variationId")
    suspend fun getAuthority(ownerId: String, variationId: String): VariationAuthorityEntity?

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertAuthority(entity: VariationAuthorityEntity)

    @Query(
        """
        UPDATE variation_authority SET
            protocol_version = :protocolVersion,
            revision = :nextRevision,
            authority = :authority,
            source = :source,
            document_json = :documentJson,
            ddl_digest = :ddlDigest,
            authority_digest = :authorityDigest,
            description = :description,
            updated_at = :updatedAt
        WHERE owner_id = :ownerId
          AND variation_id = :variationId
          AND revision = :expectedRevision
        """,
    )
    suspend fun updateAuthorityCas(
        ownerId: String,
        variationId: String,
        expectedRevision: String,
        protocolVersion: String,
        nextRevision: String,
        authority: String,
        source: String,
        documentJson: String,
        ddlDigest: String,
        authorityDigest: String,
        description: String,
        updatedAt: Long,
    ): Int

    @Query("SELECT * FROM variation_authority_actions WHERE owner_id = :ownerId AND action_id = :actionId")
    suspend fun getAction(ownerId: String, actionId: String): VariationAuthorityActionEntity?

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertAction(entity: VariationAuthorityActionEntity)

    @Query(
        """
        SELECT action_id FROM variation_authority_actions
        WHERE owner_id = :ownerId
          AND variation_id = :variationId
          AND revision = :revision
          AND ddl_digest = :ddlDigest
        LIMIT 1
        """,
    )
    suspend fun findCommittedAction(
        ownerId: String,
        variationId: String,
        revision: String,
        ddlDigest: String,
    ): String?

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertExecution(entity: PipelineExecutionEntity)

    @Query("SELECT * FROM pipeline_candidate_executions WHERE owner_id = :ownerId AND execution_id = :executionId")
    suspend fun getExecution(ownerId: String, executionId: String): PipelineExecutionEntity?

    @Query(
        """
        SELECT * FROM pipeline_candidate_executions
        WHERE owner_id = :ownerId AND variation_id = :variationId
        ORDER BY updated_at DESC, execution_id DESC
        LIMIT 1
        """,
    )
    suspend fun getLatestExecution(ownerId: String, variationId: String): PipelineExecutionEntity?

    @Query(
        """
        SELECT * FROM pipeline_candidate_executions
        WHERE owner_id = :ownerId
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
    )
    suspend fun latestExecution(ownerId: String): PipelineExecutionEntity?

    @Query(
        """
        UPDATE pipeline_candidate_executions SET
            sequence = :nextSequence,
            state_bytes = :stateBytes,
            state_digest = :stateDigest,
            updated_at = :updatedAt
        WHERE owner_id = :ownerId
          AND execution_id = :executionId
          AND sequence = :expectedSequence
        """,
    )
    suspend fun updateExecutionCas(
        ownerId: String,
        executionId: String,
        expectedSequence: String,
        nextSequence: String,
        stateBytes: ByteArray,
        stateDigest: String,
        updatedAt: Long,
    ): Int

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertHistoryLink(entity: PipelineHistoryLinkEntity)

    @Query("SELECT * FROM pipeline_history_links WHERE owner_id = :ownerId AND history_id = :historyId")
    suspend fun getHistoryLink(ownerId: String, historyId: String): PipelineHistoryLinkEntity?

    @Query("SELECT * FROM pipeline_history_links WHERE history_id = :historyId LIMIT 1")
    suspend fun getAnyHistoryLink(historyId: String): PipelineHistoryLinkEntity?
}
