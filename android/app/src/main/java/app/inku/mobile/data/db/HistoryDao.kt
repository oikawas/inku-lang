package app.inku.mobile.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import app.inku.mobile.data.lineage.DescriptionLock
import kotlinx.coroutines.flow.Flow

@Dao
interface HistoryDao {
    @Query("SELECT * FROM history_items WHERE trashed = 0 ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    fun listActive(limit: Int, offset: Int): Flow<List<HistoryItemEntity>>

    @Query(
        "SELECT id, created_at, updated_at, original_input, normalized_ddl, ddl_source_origin, stage1_model, stage2_model, " +
            "render_hash, render_hash_short, color_catalog_id, canvas_aspect, starred, trashed, " +
            "thumbnail_path, thumbnail_width, thumbnail_height " +
            "FROM history_items WHERE trashed = 0 ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
    )
    fun listActiveSummaries(limit: Int, offset: Int): Flow<List<HistoryListItem>>

    @Query("SELECT * FROM history_items WHERE trashed = 1 ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    fun listTrashed(limit: Int, offset: Int): Flow<List<HistoryItemEntity>>

    @Query(
        "SELECT id, created_at, updated_at, original_input, normalized_ddl, ddl_source_origin, stage1_model, stage2_model, " +
            "render_hash, render_hash_short, color_catalog_id, canvas_aspect, starred, trashed, " +
            "thumbnail_path, thumbnail_width, thumbnail_height " +
            "FROM history_items WHERE trashed = 1 ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
    )
    fun listTrashedSummaries(limit: Int, offset: Int): Flow<List<HistoryListItem>>

    @Query("SELECT * FROM history_items WHERE starred = 1 AND trashed = 0 ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    fun listStarred(limit: Int, offset: Int): Flow<List<HistoryItemEntity>>

    @Query("SELECT * FROM history_items WHERE id = :id LIMIT 1")
    suspend fun getById(id: String): HistoryItemEntity?

    @Query("SELECT * FROM history_items WHERE render_hash = :hash OR render_hash_short = :hash LIMIT 1")
    suspend fun getByHash(hash: String): HistoryItemEntity?

    @Query(
        "SELECT * FROM history_items WHERE thumbnail_path IS NULL OR thumbnail_path NOT LIKE :currentVersionPattern " +
            "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset",
    )
    suspend fun listMissingThumbnails(currentVersionPattern: String, limit: Int, offset: Int): List<HistoryItemEntity>

    // A history row is written once and never overwritten by a second insert.
    // The server re-raises the IntegrityError a colliding primary key produces
    // (`db.py:2990-2993`) unless the caller passed an idempotency_key, so a
    // silent REPLACE here would be a judgement the server does not make.
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(item: HistoryItemEntity)

    @Query("UPDATE history_items SET starred = :starred, updated_at = :updatedAt WHERE id = :id")
    suspend fun setStarred(id: String, starred: Boolean, updatedAt: Long)

    @Query("UPDATE history_items SET trashed = :trashed, updated_at = :updatedAt WHERE id = :id")
    suspend fun setTrashed(id: String, trashed: Boolean, updatedAt: Long)

    /** Returns the rows updated: 0 when the work was deleted while its thumbnail was drawn. */
    @Query("UPDATE history_items SET thumbnail_path = :path, thumbnail_width = :width, thumbnail_height = :height, updated_at = :updatedAt WHERE id = :id")
    suspend fun updateThumbnail(id: String, path: String, width: Int, height: Int, updatedAt: Long): Int

    // The two columns a permanent delete needs, without loading the SVG.
    @Query("SELECT lineage_node_id FROM history_items WHERE id = :id")
    suspend fun lineageNodeIdOf(id: String): String?

    @Query("SELECT thumbnail_path FROM history_items WHERE id = :id")
    suspend fun thumbnailPathOf(id: String): String?

    @Query("SELECT DISTINCT thumbnail_path FROM history_items WHERE thumbnail_path IS NOT NULL")
    suspend fun thumbnailPaths(): List<String>

    /** Thumbnails are named by render hash, so two rows can share one file. */
    @Query("SELECT COUNT(*) FROM history_items WHERE thumbnail_path = :path")
    suspend fun countWithThumbnail(path: String): Int

    @Query("DELETE FROM history_items WHERE id = :id")
    suspend fun deletePermanently(id: String)

    /** Each work's DDL and its origin, for the description lock's replay test. */
    @Query("SELECT id AS historyId, normalized_ddl AS ddl, ddl_source_origin AS ddlSourceOrigin FROM history_items WHERE id IN (:ids)")
    suspend fun lockDdlOfHistories(ids: Collection<String>): List<DescriptionLock.HistoryDdl>
}
