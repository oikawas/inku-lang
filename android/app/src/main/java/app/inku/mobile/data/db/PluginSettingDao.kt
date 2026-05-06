package app.inku.mobile.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface PluginSettingDao {
    @Query("SELECT * FROM plugin_settings WHERE plugin_id = :pluginId ORDER BY key")
    fun observeForPlugin(pluginId: String): Flow<List<PluginSettingEntity>>

    @Query("SELECT * FROM plugin_settings WHERE key = :key LIMIT 1")
    suspend fun get(key: String): PluginSettingEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(setting: PluginSettingEntity)
}
