package app.inku.mobile.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface HistoryDao {
    @Query("SELECT * FROM history_items WHERE trashed = 0 ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    fun listActive(limit: Int, offset: Int): Flow<List<HistoryItemEntity>>

    @Query(
        "SELECT id, created_at, updated_at, original_input, normalized_ddl, stage1_model, stage2_model, " +
            "render_hash, render_hash_short, color_catalog_id, canvas_aspect, starred, trashed, " +
            "thumbnail_path, thumbnail_width, thumbnail_height " +
            "FROM history_items WHERE trashed = 0 ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
    )
    fun listActiveSummaries(limit: Int, offset: Int): Flow<List<HistoryListItem>>

    @Query("SELECT * FROM history_items WHERE trashed = 1 ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    fun listTrashed(limit: Int, offset: Int): Flow<List<HistoryItemEntity>>

    @Query("SELECT * FROM history_items WHERE starred = 1 AND trashed = 0 ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    fun listStarred(limit: Int, offset: Int): Flow<List<HistoryItemEntity>>

    @Query("SELECT * FROM history_items WHERE id = :id LIMIT 1")
    suspend fun getById(id: String): HistoryItemEntity?

    @Query("SELECT * FROM history_items WHERE render_hash = :hash OR render_hash_short = :hash LIMIT 1")
    suspend fun getByHash(hash: String): HistoryItemEntity?

    @Query("SELECT * FROM history_items WHERE thumbnail_path IS NULL ORDER BY created_at DESC LIMIT :limit")
    suspend fun listMissingThumbnails(limit: Int): List<HistoryItemEntity>

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

    @Query("UPDATE history_items SET thumbnail_path = :path, thumbnail_width = :width, thumbnail_height = :height, updated_at = :updatedAt WHERE id = :id")
    suspend fun updateThumbnail(id: String, path: String, width: Int, height: Int, updatedAt: Long)

    @Query("DELETE FROM history_items WHERE id = :id")
    suspend fun deletePermanently(id: String)
}
