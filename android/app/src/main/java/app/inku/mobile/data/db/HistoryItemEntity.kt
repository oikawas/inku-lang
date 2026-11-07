package app.inku.mobile.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import org.json.JSONObject

/**
 * One saved work, read whole: the small columns of `history_items` joined with
 * its large ones in `history_payloads` (schema 15). Every reader keeps this
 * shape; only the tables under it are two.
 *
 * The large columns live apart so that the list, star, trash and thumbnail
 * queries read small rows: in one row the columns after the SVG were reached
 * through its overflow pages (the author's library read 4x faster split, a
 * copy of the device database, 2026-11-07).
 */
data class HistoryItemEntity(
    val id: String,
    @ColumnInfo(name = "created_at")
    val createdAt: Long,
    @ColumnInfo(name = "updated_at")
    val updatedAt: Long,
    @ColumnInfo(name = "original_input")
    val originalInput: String,
    @ColumnInfo(name = "normalized_ddl")
    val normalizedDdl: String?,
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
    @ColumnInfo(name = "catalog_mode")
    val catalogMode: String? = null,
    @ColumnInfo(name = "canvas_aspect")
    val canvasAspect: String,
    val starred: Boolean,
    val trashed: Boolean,
    @ColumnInfo(name = "elapsed_ms")
    val elapsedMs: Long?,
    @ColumnInfo(name = "token_metadata_json")
    val tokenMetadataJson: String?,
    @ColumnInfo(name = "thumbnail_path")
    val thumbnailPath: String? = null,
    @ColumnInfo(name = "thumbnail_width")
    val thumbnailWidth: Int? = null,
    @ColumnInfo(name = "thumbnail_height")
    val thumbnailHeight: Int? = null,
    @ColumnInfo(name = "render_wild")
    val renderWild: Boolean? = null,
    @ColumnInfo(name = "lineage_node_id")
    val lineageNodeId: String? = null,
    // The seeds a work was made with, one column each, with the server's names
    // and the server's type: `history.render_seed` and its neighbours are all
    // VARCHAR there (`db.py:132-142`), including the numeric ones, and the
    // number is parsed on the way out rather than stored as one. NULL is "the
    // work does not say" -- an ordinary drawing asks for no reading and no
    // variation, so four of these five stay empty on most rows.
    // `moved_axes` has no column on either side: it is recomputed from the
    // amplitude and the seed.
    @ColumnInfo(name = "render_seed")
    val renderSeed: String? = null,
    @ColumnInfo(name = "composition_seed")
    val compositionSeed: String? = null,
    @ColumnInfo(name = "interpretation_seed")
    val interpretationSeed: String? = null,
    @ColumnInfo(name = "variation_amplitude")
    val variationAmplitude: String? = null,
    @ColumnInfo(name = "variation_seed")
    val variationSeed: String? = null,
    @ColumnInfo(name = "seed_text")
    val seedText: String? = null,
    // What the author asked the instruction language to be and what it resolved
    // to, with the server's names and its nullable type (`db.py:129-130`). They
    // are two quantities: a work asked for with `auto` keeps `auto` on the left
    // and the language it was actually drawn in on the right, and a work drawn
    // on a path that ran no prompt has neither.
    @ColumnInfo(name = "instruction_lang_requested")
    val instructionLangRequested: String? = null,
    @ColumnInfo(name = "instruction_lang_resolved")
    val instructionLangResolved: String? = null,
    // The prose alone, without the bookkeeping `original_input` carries in front
    // of it on a batch or demo line (`db.py:170`). NULL means the row never had
    // a separate one, and every reader falls back to `original_input` for those
    // -- `row.source_text if row.source_text is not None else row.input`
    // (`db.py:1835`).
    @ColumnInfo(name = "source_text")
    val sourceText: String? = null,
    // 写生 (Stage 0.5). Three nullable Text columns, the server's names and its
    // types (`db.py`), and the state is the one that is always written: a work
    // whose layer fell back records `fallback` here with no prose beside it.
    //
    // NULL in these three is a sixth state and it is NOT `off`: `off` is a
    // choice the author made, and a row written before the columns existed made
    // no such choice. Only the migration may produce it.
    @ColumnInfo(name = "sketch_text")
    val sketchText: String? = null,
    @ColumnInfo(name = "sketch_grain")
    val sketchGrain: String? = null,
    @ColumnInfo(name = "sketch_state")
    val sketchState: String? = null,
    /** A retired-text transfer marker, never an authoring authority. */
    @ColumnInfo(name = "ddl_source_origin")
    val ddlSourceOrigin: String? = null,
) {
    /** The small columns, as `history_items` stores them. */
    fun row(): HistoryRowEntity = HistoryRowEntity(
        id = id, createdAt = createdAt, updatedAt = updatedAt, originalInput = originalInput,
        normalizedDdl = normalizedDdl, stage1Model = stage1Model, stage2Model = stage2Model,
        renderHash = renderHash, renderHashShort = renderHashShort, colorCatalogId = colorCatalogId,
        catalogMode = catalogMode, canvasAspect = canvasAspect, starred = starred, trashed = trashed,
        elapsedMs = elapsedMs, tokenMetadataJson = tokenMetadataJson, thumbnailPath = thumbnailPath,
        thumbnailWidth = thumbnailWidth, thumbnailHeight = thumbnailHeight, renderWild = renderWild,
        lineageNodeId = lineageNodeId, renderSeed = renderSeed, compositionSeed = compositionSeed,
        interpretationSeed = interpretationSeed, variationAmplitude = variationAmplitude,
        variationSeed = variationSeed, seedText = seedText, instructionLangRequested = instructionLangRequested,
        instructionLangResolved = instructionLangResolved, sourceText = sourceText, sketchText = sketchText,
        sketchGrain = sketchGrain, sketchState = sketchState, ddlSourceOrigin = ddlSourceOrigin,
    )

    /** The large columns, as `history_payloads` stores them. */
    fun payload(): HistoryPayloadEntity = HistoryPayloadEntity(id, scoreJson, displaySvg, renderMetadataJson)
}

/** The small columns of a saved work (schema 15); the large ones are in [HistoryPayloadEntity]. */
@Entity(
    tableName = "history_items",
    indices = [
        Index("created_at"),
        Index(value = ["trashed", "created_at"]),
        Index(value = ["starred", "trashed", "created_at"]),
        Index(value = ["lineage_node_id"], unique = true),
        // A permanent delete counts the rows sharing a thumbnail file.
        Index("thumbnail_path"),
    ],
)
data class HistoryRowEntity(
    @PrimaryKey
    val id: String,
    @ColumnInfo(name = "created_at") val createdAt: Long,
    @ColumnInfo(name = "updated_at") val updatedAt: Long,
    @ColumnInfo(name = "original_input") val originalInput: String,
    @ColumnInfo(name = "normalized_ddl") val normalizedDdl: String?,
    @ColumnInfo(name = "stage1_model") val stage1Model: String?,
    @ColumnInfo(name = "stage2_model") val stage2Model: String?,
    @ColumnInfo(name = "render_hash") val renderHash: String,
    @ColumnInfo(name = "render_hash_short") val renderHashShort: String,
    @ColumnInfo(name = "color_catalog_id") val colorCatalogId: String,
    @ColumnInfo(name = "catalog_mode") val catalogMode: String?,
    @ColumnInfo(name = "canvas_aspect") val canvasAspect: String,
    val starred: Boolean,
    val trashed: Boolean,
    @ColumnInfo(name = "elapsed_ms") val elapsedMs: Long?,
    @ColumnInfo(name = "token_metadata_json") val tokenMetadataJson: String?,
    @ColumnInfo(name = "thumbnail_path") val thumbnailPath: String?,
    @ColumnInfo(name = "thumbnail_width") val thumbnailWidth: Int?,
    @ColumnInfo(name = "thumbnail_height") val thumbnailHeight: Int?,
    @ColumnInfo(name = "render_wild") val renderWild: Boolean?,
    @ColumnInfo(name = "lineage_node_id") val lineageNodeId: String?,
    @ColumnInfo(name = "render_seed") val renderSeed: String?,
    @ColumnInfo(name = "composition_seed") val compositionSeed: String?,
    @ColumnInfo(name = "interpretation_seed") val interpretationSeed: String?,
    @ColumnInfo(name = "variation_amplitude") val variationAmplitude: String?,
    @ColumnInfo(name = "variation_seed") val variationSeed: String?,
    @ColumnInfo(name = "seed_text") val seedText: String?,
    @ColumnInfo(name = "instruction_lang_requested") val instructionLangRequested: String?,
    @ColumnInfo(name = "instruction_lang_resolved") val instructionLangResolved: String?,
    @ColumnInfo(name = "source_text") val sourceText: String?,
    @ColumnInfo(name = "sketch_text") val sketchText: String?,
    @ColumnInfo(name = "sketch_grain") val sketchGrain: String?,
    @ColumnInfo(name = "sketch_state") val sketchState: String?,
    @ColumnInfo(name = "ddl_source_origin") val ddlSourceOrigin: String?,
)

/** The large columns of a saved work, one row per `history_items` row with the same id. */
@Entity(tableName = "history_payloads")
data class HistoryPayloadEntity(
    @PrimaryKey
    val id: String,
    @ColumnInfo(name = "score_json") val scoreJson: String,
    @ColumnInfo(name = "display_svg") val displaySvg: String,
    @ColumnInfo(name = "render_metadata_json") val renderMetadataJson: String,
)

/**
 * Whether the work was drawn with Wild. Works saved through the shared core
 * record it only in their render metadata (`render_wild`); the column is
 * filled by older paths alone.
 */
val HistoryItemEntity.drawnWild: Boolean
    get() = renderWild ?: runCatching { JSONObject(renderMetadataJson).optBoolean("render_wild", false) }.getOrDefault(false)
