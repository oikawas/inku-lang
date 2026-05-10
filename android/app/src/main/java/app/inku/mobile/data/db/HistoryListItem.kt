package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Ignore

data class HistoryListItem(
    val id: String,
    @ColumnInfo(name = "created_at")
    val createdAt: Long,
    @ColumnInfo(name = "updated_at")
    val updatedAt: Long,
    @ColumnInfo(name = "original_input")
    val originalInput: String,
    @ColumnInfo(name = "normalized_ddl")
    val normalizedDdl: String,
    @ColumnInfo(name = "stage1_model")
    val stage1Model: String?,
    @ColumnInfo(name = "stage2_model")
    val stage2Model: String?,
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
    @ColumnInfo(name = "thumbnail_path")
    val thumbnailPath: String?,
    @ColumnInfo(name = "thumbnail_width")
    val thumbnailWidth: Int?,
    @ColumnInfo(name = "thumbnail_height")
    val thumbnailHeight: Int?,
) {
    @Ignore
    val searchText: String = listOf(
        originalInput,
        normalizedDdl,
        renderHash,
        renderHashShort,
        stage1Model.orEmpty(),
        stage2Model.orEmpty(),
        colorCatalogId,
        canvasAspect,
    ).joinToString("\n").lowercase()
}
