package app.inku.mobile.data.db

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import app.inku.mobile.data.DdlSource

/** Room supplies the transaction; no compilation, rendering or authority rewrite occurs. */
internal object HistoryDdlUnifiedMigration : Migration(13, 14) {
    override fun migrate(db: SupportSQLiteDatabase) {
        val indexes = db.query(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'history_items' AND sql IS NOT NULL",
        ).use { cursor ->
            buildList { while (cursor.moveToNext()) add(cursor.getString(0)) }
        }
        statements(indexes).forEach(db::execSQL)
    }

    private fun statements(indexes: List<String>): List<String> {
        val ddlHasBody = DdlSource.sqlHasBody("normalized_ddl")
        val expandedHasBody = DdlSource.sqlHasBody("expanded_ddl")
        val columns = listOf(
            "id", "created_at", "updated_at", "original_input", "normalized_ddl", "ddl_source_origin",
            "score_json", "display_svg", "stage1_model", "stage2_model", "render_metadata_json",
            "render_hash", "render_hash_short", "color_catalog_id", "catalog_mode", "canvas_aspect",
            "starred", "trashed", "elapsed_ms", "token_metadata_json", "thumbnail_path",
            "thumbnail_width", "thumbnail_height", "render_wild", "lineage_node_id", "render_seed",
            "composition_seed", "interpretation_seed", "variation_amplitude", "variation_seed", "seed_text",
            "instruction_lang_requested", "instruction_lang_resolved", "source_text", "sketch_text",
            "sketch_grain", "sketch_state",
        )
        val names = columns.joinToString(", ") { "`$it`" }
        val values = columns.joinToString(", ") { column ->
            when (column) {
                "normalized_ddl" -> "CASE WHEN $ddlHasBody THEN `normalized_ddl` " +
                    "WHEN $expandedHasBody THEN `expanded_ddl` ELSE `normalized_ddl` END"
                "ddl_source_origin" -> "CASE WHEN NOT ($ddlHasBody) AND ($expandedHasBody) " +
                    "THEN '${DdlSource.LEGACY_EXPANDED}' ELSE NULL END"
                else -> "`$column`"
            }
        }
        return listOf(
            """
            CREATE TABLE `history_items_single_ddl` (
                `id` TEXT NOT NULL, `created_at` INTEGER NOT NULL, `updated_at` INTEGER NOT NULL,
                `original_input` TEXT NOT NULL, `normalized_ddl` TEXT, `ddl_source_origin` TEXT,
                `score_json` TEXT NOT NULL, `display_svg` TEXT NOT NULL,
                `stage1_model` TEXT, `stage2_model` TEXT, `render_metadata_json` TEXT NOT NULL,
                `render_hash` TEXT NOT NULL, `render_hash_short` TEXT NOT NULL,
                `color_catalog_id` TEXT NOT NULL, `catalog_mode` TEXT, `canvas_aspect` TEXT NOT NULL,
                `starred` INTEGER NOT NULL, `trashed` INTEGER NOT NULL, `elapsed_ms` INTEGER,
                `token_metadata_json` TEXT, `thumbnail_path` TEXT, `thumbnail_width` INTEGER,
                `thumbnail_height` INTEGER, `render_wild` INTEGER, `lineage_node_id` TEXT,
                `render_seed` TEXT, `composition_seed` TEXT, `interpretation_seed` TEXT,
                `variation_amplitude` TEXT, `variation_seed` TEXT, `seed_text` TEXT,
                `instruction_lang_requested` TEXT, `instruction_lang_resolved` TEXT,
                `source_text` TEXT, `sketch_text` TEXT, `sketch_grain` TEXT, `sketch_state` TEXT,
                PRIMARY KEY(`id`)
            )
            """.trimIndent(),
            "INSERT INTO `history_items_single_ddl` ($names) SELECT $values FROM `history_items`",
            "DROP TABLE `history_items`",
            "ALTER TABLE `history_items_single_ddl` RENAME TO `history_items`",
        ) + indexes
    }
}
