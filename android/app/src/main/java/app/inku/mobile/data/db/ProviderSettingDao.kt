package app.inku.mobile.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ProviderSettingDao {
    @Query("SELECT * FROM provider_settings ORDER BY is_default_local DESC, display_name")
    fun observeAll(): Flow<List<ProviderSettingEntity>>

    @Query("SELECT * FROM provider_settings ORDER BY is_default_local DESC, display_name")
    suspend fun listAll(): List<ProviderSettingEntity>

    @Query("SELECT * FROM provider_settings WHERE provider_id = :providerId LIMIT 1")
    suspend fun get(providerId: String): ProviderSettingEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(setting: ProviderSettingEntity)

    @Query("DELETE FROM provider_settings WHERE provider_id = :providerId AND is_default_local = 0")
    suspend fun deleteCustom(providerId: String)
}
