package app.inku.mobile.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ExportTemplateDao {
    @Query("SELECT * FROM export_templates ORDER BY sort_order, height_px")
    fun observeAll(): Flow<List<ExportTemplateEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(template: ExportTemplateEntity)

    @Query("DELETE FROM export_templates WHERE id = :id")
    suspend fun delete(id: String)
}
