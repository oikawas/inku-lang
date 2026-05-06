package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "provider_settings")
data class ProviderSettingEntity(
    @PrimaryKey
    @ColumnInfo(name = "provider_id")
    val providerId: String,
    @ColumnInfo(name = "display_name")
    val displayName: String,
    val kind: String,
    @ColumnInfo(name = "base_url")
    val baseUrl: String?,
    @ColumnInfo(name = "encrypted_api_key")
    val encryptedApiKey: String?,
    @ColumnInfo(name = "published_models_json")
    val publishedModelsJson: String,
    @ColumnInfo(name = "is_enabled")
    val isEnabled: Boolean,
    @ColumnInfo(name = "is_default_local")
    val isDefaultLocal: Boolean,
    @ColumnInfo(name = "updated_at")
    val updatedAt: Long,
)
