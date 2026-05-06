package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "history_items",
    indices = [
        Index("created_at"),
        Index("render_hash", unique = true),
        Index("render_hash_short"),
        Index("starred"),
        Index("trashed"),
    ],
)
data class HistoryItemEntity(
    @PrimaryKey
    val id: String,
    @ColumnInfo(name = "created_at")
    val createdAt: Long,
    @ColumnInfo(name = "updated_at")
    val updatedAt: Long,
    @ColumnInfo(name = "original_input")
    val originalInput: String,
    @ColumnInfo(name = "normalized_ddl")
    val normalizedDdl: String,
    @ColumnInfo(name = "expanded_ddl")
    val expandedDdl: String?,
    @ColumnInfo(name = "score_json")
    val scoreJson: String,
    @ColumnInfo(name = "display_svg")
    val displaySvg: String,
    @ColumnInfo(name = "stage1_model")
    val stage1Model: String?,
    @ColumnInfo(name = "stage2_model")
    val stage2Model: String?,
    @ColumnInfo(name = "render_metadata_json")
    val renderMetadataJson: String,
    @ColumnInfo(name = "render_hash")
    val renderHash: String,
    @ColumnInfo(name = "render_hash_short")
    val renderHashShort: String,
    @ColumnInfo(name = "color_catalog_id")
    val colorCatalogId: String,
    @ColumnInfo(name = "canvas_aspect")
    val canvasAspect: String,
    val starred: Boolean,
    val trashed: Boolean,
    @ColumnInfo(name = "elapsed_ms")
    val elapsedMs: Long?,
    @ColumnInfo(name = "token_metadata_json")
    val tokenMetadataJson: String?,
)
