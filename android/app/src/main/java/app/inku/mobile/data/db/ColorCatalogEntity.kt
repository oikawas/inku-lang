package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "color_catalogs")
data class ColorCatalogEntity(
    @PrimaryKey
    @ColumnInfo(name = "catalog_id")
    val catalogId: String,
    val name: String,
    @ColumnInfo(name = "name_ja")
    val nameJa: String?,
    val sub: String,
    @ColumnInfo(name = "sub_ja")
    val subJa: String?,
    @ColumnInfo(name = "catalog_json")
    val catalogJson: String,
    @ColumnInfo(name = "is_builtin")
    val isBuiltin: Boolean,
    @ColumnInfo(name = "updated_at")
    val updatedAt: Long,
)
