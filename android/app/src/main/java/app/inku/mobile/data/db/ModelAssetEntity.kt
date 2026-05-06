package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "model_assets",
    indices = [
        Index("provider_id"),
        Index("model_id", unique = true),
    ],
)
data class ModelAssetEntity(
    @PrimaryKey
    val id: String,
    @ColumnInfo(name = "provider_id")
    val providerId: String,
    @ColumnInfo(name = "model_id")
    val modelId: String,
    @ColumnInfo(name = "display_name")
    val displayName: String,
    @ColumnInfo(name = "quality_tier")
    val qualityTier: String,
    @ColumnInfo(name = "download_url")
    val downloadUrl: String?,
    @ColumnInfo(name = "license_url")
    val licenseUrl: String?,
    @ColumnInfo(name = "license_accepted_at")
    val licenseAcceptedAt: Long?,
    @ColumnInfo(name = "local_path")
    val localPath: String?,
    @ColumnInfo(name = "expected_sha256")
    val expectedSha256: String?,
    @ColumnInfo(name = "download_state")
    val downloadState: String,
    @ColumnInfo(name = "bytes_downloaded")
    val bytesDownloaded: Long,
    @ColumnInfo(name = "bytes_total")
    val bytesTotal: Long?,
    @ColumnInfo(name = "updated_at")
    val updatedAt: Long,
)
