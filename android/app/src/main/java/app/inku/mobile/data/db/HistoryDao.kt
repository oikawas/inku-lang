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

    @Query("SELECT * FROM history_items WHERE trashed = 1 ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    fun listTrashed(limit: Int, offset: Int): Flow<List<HistoryItemEntity>>

    @Query("SELECT * FROM history_items WHERE starred = 1 AND trashed = 0 ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    fun listStarred(limit: Int, offset: Int): Flow<List<HistoryItemEntity>>

    @Query("SELECT * FROM history_items WHERE id = :id LIMIT 1")
    suspend fun getById(id: String): HistoryItemEntity?

    @Query("SELECT * FROM history_items WHERE render_hash = :hash OR render_hash_short = :hash LIMIT 1")
    suspend fun getByHash(hash: String): HistoryItemEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: HistoryItemEntity)

    @Query("UPDATE history_items SET starred = :starred, updated_at = :updatedAt WHERE id = :id")
    suspend fun setStarred(id: String, starred: Boolean, updatedAt: Long)

    @Query("UPDATE history_items SET trashed = :trashed, updated_at = :updatedAt WHERE id = :id")
    suspend fun setTrashed(id: String, trashed: Boolean, updatedAt: Long)

    @Query("DELETE FROM history_items WHERE id = :id")
    suspend fun deletePermanently(id: String)
}
