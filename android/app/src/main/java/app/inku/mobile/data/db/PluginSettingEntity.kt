package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "plugin_settings")
data class PluginSettingEntity(
    @PrimaryKey
    val key: String,
    @ColumnInfo(name = "plugin_id")
    val pluginId: String,
    @ColumnInfo(name = "value_json")
    val valueJson: String,
    @ColumnInfo(name = "updated_at")
    val updatedAt: Long,
)
