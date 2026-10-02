package app.inku.mobile.data.db

import android.os.SystemClock
import android.util.Log
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

/** Rebuilds the v12 table without changing any work except an absent DDL. */
internal object HistoryDdlNullableMigration : Migration(12, 13) {
    override fun migrate(db: SupportSQLiteDatabase) {
        val startedAt = SystemClock.elapsedRealtime()
        val beforeBytes = allocatedBytes(db)
        val indexes = mutableListOf<String>()
        db.query("SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'history_items' AND sql IS NOT NULL").use { cursor ->
            while (cursor.moveToNext()) indexes += cursor.getString(0)
        }
        db.execSQL(
            """
            CREATE TABLE `history_items_nullable` (
                `id` TEXT NOT NULL,
                `created_at` INTEGER NOT NULL,
                `updated_at` INTEGER NOT NULL,
                `original_input` TEXT NOT NULL,
                `normalized_ddl` TEXT,
                `expanded_ddl` TEXT,
                `score_json` TEXT NOT NULL,
                `display_svg` TEXT NOT NULL,
                `stage1_model` TEXT,
                `stage2_model` TEXT,
                `render_metadata_json` TEXT NOT NULL,
                `render_hash` TEXT NOT NULL,
                `render_hash_short` TEXT NOT NULL,
                `color_catalog_id` TEXT NOT NULL,
                `catalog_mode` TEXT,
                `canvas_aspect` TEXT NOT NULL,
                `starred` INTEGER NOT NULL,
                `trashed` INTEGER NOT NULL,
                `elapsed_ms` INTEGER,
                `token_metadata_json` TEXT,
                `thumbnail_path` TEXT,
                `thumbnail_width` INTEGER,
                `thumbnail_height` INTEGER,
                `render_wild` INTEGER,
                `lineage_node_id` TEXT,
                `render_seed` TEXT,
                `composition_seed` TEXT,
                `interpretation_seed` TEXT,
                `variation_amplitude` TEXT,
                `variation_seed` TEXT,
                `seed_text` TEXT,
                `instruction_lang_requested` TEXT,
                `instruction_lang_resolved` TEXT,
                `source_text` TEXT,
                `sketch_text` TEXT,
                `sketch_grain` TEXT,
                `sketch_state` TEXT,
                PRIMARY KEY(`id`)
            )
            """.trimIndent(),
        )
        // Use the existing column order explicitly: catalog_mode was appended
        // in v12, so SELECT * would put it into the wrong destination column.
        val columns = db.query("PRAGMA table_info(`history_items`)").use { cursor ->
            buildList {
                while (cursor.moveToNext()) add(cursor.getString(1))
            }
        }
        val names = columns.joinToString(", ") { "`$it`" }
        val values = columns.joinToString(", ") {
            if (it == "normalized_ddl") "NULLIF(`normalized_ddl`, '')" else "`$it`"
        }
        db.execSQL("INSERT INTO `history_items_nullable` ($names) SELECT $values FROM `history_items`")
        val copiedBytes = allocatedBytes(db)
        db.execSQL("DROP TABLE `history_items`")
        db.execSQL("ALTER TABLE `history_items_nullable` RENAME TO `history_items`")
        indexes.forEach(db::execSQL)
        // Logical allocation includes free pages; it measures the temporary
        // table cost, while journal/WAL files need additional disk space.
        Log.i(
            "InkuMigration",
            "Room 12->13 elapsed_ms=${SystemClock.elapsedRealtime() - startedAt} " +
                "allocated_before_bytes=$beforeBytes allocated_copy_bytes=$copiedBytes " +
                "allocated_after_bytes=${allocatedBytes(db)}",
        )
    }

    private fun allocatedBytes(db: SupportSQLiteDatabase): Long {
        fun pragma(name: String): Long = db.query("PRAGMA $name").use { cursor ->
            check(cursor.moveToFirst())
            cursor.getLong(0)
        }
        return pragma("page_count") * pragma("page_size")
    }
}
