package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "app_settings")
data class AppSettingEntity(
    @PrimaryKey
    val key: String,
    @ColumnInfo(name = "value_json")
    val valueJson: String,
    @ColumnInfo(name = "updated_at")
    val updatedAt: Long,
)
