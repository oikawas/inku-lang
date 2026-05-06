package app.inku.mobile.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ModelAssetDao {
    @Query(
        """
        SELECT * FROM model_assets
        ORDER BY
            CASE quality_tier
                WHEN 'standard' THEN 0
                WHEN 'high' THEN 1
                ELSE 2
            END,
            display_name
        """,
    )
    fun observeAll(): Flow<List<ModelAssetEntity>>

    @Query("SELECT * FROM model_assets WHERE model_id = :modelId LIMIT 1")
    suspend fun getByModelId(modelId: String): ModelAssetEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(asset: ModelAssetEntity)

    @Query(
        """
        UPDATE model_assets
        SET license_accepted_at = :acceptedAt,
            download_state = :downloadState,
            updated_at = :updatedAt
        WHERE model_id = :modelId
        """,
    )
    suspend fun acceptLicense(modelId: String, acceptedAt: Long, downloadState: String, updatedAt: Long)

    @Query(
        """
        UPDATE model_assets
        SET download_state = :downloadState,
            bytes_downloaded = :bytesDownloaded,
            bytes_total = :bytesTotal,
            local_path = :localPath,
            updated_at = :updatedAt
        WHERE model_id = :modelId
        """,
    )
    suspend fun updateDownload(
        modelId: String,
        downloadState: String,
        bytesDownloaded: Long,
        bytesTotal: Long?,
        localPath: String?,
        updatedAt: Long,
    )
}
