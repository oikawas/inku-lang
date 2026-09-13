package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index

@Entity(
    tableName = "variation_authority",
    primaryKeys = ["owner_id", "variation_id"],
    indices = [
        Index(value = ["owner_id", "parent_legacy_history_id"]),
        Index(value = ["owner_id", "parent_variation_id"]),
    ],
)
data class VariationAuthorityEntity(
    @ColumnInfo(name = "owner_id") val ownerId: String,
    @ColumnInfo(name = "variation_id") val variationId: String,
    @ColumnInfo(name = "protocol_version") val protocolVersion: String,
    val revision: String,
    val origin: String,
    val authority: String,
    val source: String,
    @ColumnInfo(name = "document_json") val documentJson: String,
    @ColumnInfo(name = "ddl_digest") val ddlDigest: String,
    @ColumnInfo(name = "authority_digest") val authorityDigest: String,
    val description: String,
    @ColumnInfo(name = "derivation_kind") val derivationKind: String,
    @ColumnInfo(name = "parent_legacy_history_id") val parentLegacyHistoryId: String?,
    @ColumnInfo(name = "parent_variation_id") val parentVariationId: String?,
    @ColumnInfo(name = "updated_at") val updatedAt: Long,
)

@Entity(
    tableName = "variation_authority_actions",
    primaryKeys = ["owner_id", "action_id"],
    indices = [Index(value = ["owner_id", "variation_id", "revision", "ddl_digest"])],
)
data class VariationAuthorityActionEntity(
    @ColumnInfo(name = "owner_id") val ownerId: String,
    @ColumnInfo(name = "action_id") val actionId: String,
    @ColumnInfo(name = "variation_id") val variationId: String,
    @ColumnInfo(name = "request_digest") val requestDigest: String,
    @ColumnInfo(name = "action_fingerprint") val actionFingerprint: String,
    @ColumnInfo(name = "context_fingerprint") val contextFingerprint: String,
    @ColumnInfo(name = "ddl_digest") val ddlDigest: String,
    val revision: String,
    @ColumnInfo(name = "authority_digest") val authorityDigest: String,
    @ColumnInfo(name = "committed_at") val committedAt: Long,
)

@Entity(
    tableName = "pipeline_candidate_executions",
    primaryKeys = ["owner_id", "execution_id"],
    indices = [Index(value = ["owner_id", "variation_id", "updated_at"])],
)
data class PipelineExecutionEntity(
    @ColumnInfo(name = "owner_id") val ownerId: String,
    @ColumnInfo(name = "execution_id") val executionId: String,
    @ColumnInfo(name = "variation_id") val variationId: String,
    val sequence: String,
    @ColumnInfo(name = "state_bytes", typeAffinity = ColumnInfo.BLOB) val stateBytes: ByteArray,
    @ColumnInfo(name = "state_digest") val stateDigest: String,
    @ColumnInfo(name = "created_at") val createdAt: Long,
    @ColumnInfo(name = "updated_at") val updatedAt: Long,
)

@Entity(
    tableName = "pipeline_history_links",
    primaryKeys = ["owner_id", "history_id"],
    indices = [
        Index(value = ["history_id"], unique = true),
        Index(value = ["owner_id", "variation_id"]),
    ],
)
data class PipelineHistoryLinkEntity(
    @ColumnInfo(name = "owner_id") val ownerId: String,
    @ColumnInfo(name = "history_id") val historyId: String,
    @ColumnInfo(name = "variation_id") val variationId: String,
    val revision: String,
    @ColumnInfo(name = "ddl_digest") val ddlDigest: String,
    @ColumnInfo(name = "fork_context_bytes", typeAffinity = ColumnInfo.BLOB) val forkContextBytes: ByteArray,
    @ColumnInfo(name = "fork_context_digest") val forkContextDigest: String,
)
