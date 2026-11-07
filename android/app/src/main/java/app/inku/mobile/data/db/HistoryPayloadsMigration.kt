package app.inku.mobile.data.db

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

/**
 * Schema 14 -> 15 (Android source review step 4, 2026-11-07, the author's
 * choice). Room runs it in one transaction: a failure leaves schema 14 as it was.
 *
 * - A work's large columns (`score_json`, `display_svg`, `render_metadata_json`)
 *   move to `history_payloads`, so the list, star, trash and thumbnail queries
 *   read small rows. The values are copied unchanged.
 * - Indexes: the single `starred` and `trashed` indexes repeat the head of the
 *   composite ones, and the `render_hash` pair served a lookup nothing called;
 *   the thumbnail, lineage-parent and variation lookups gain one each.
 * - `color_catalogs` had no reader and no row.
 *
 * The statements are listed here so that a rehearsal on a copy of the author's
 * database runs exactly these (`internal/main/topics/android-task/
 * android-source-review-20261107/`).
 */
object HistoryPayloadsMigration : Migration(14, 15) {
    val STATEMENTS: List<String> = listOf(
        "CREATE TABLE IF NOT EXISTS `history_payloads` (`id` TEXT NOT NULL, `score_json` TEXT NOT NULL, " +
            "`display_svg` TEXT NOT NULL, `render_metadata_json` TEXT NOT NULL, PRIMARY KEY(`id`))",
        "INSERT INTO `history_payloads` (`id`, `score_json`, `display_svg`, `render_metadata_json`) " +
            "SELECT `id`, `score_json`, `display_svg`, `render_metadata_json` FROM `history_items`",
        "DROP INDEX IF EXISTS `index_history_items_render_hash`",
        "DROP INDEX IF EXISTS `index_history_items_render_hash_short`",
        "DROP INDEX IF EXISTS `index_history_items_starred`",
        "DROP INDEX IF EXISTS `index_history_items_trashed`",
        "ALTER TABLE `history_items` DROP COLUMN `score_json`",
        "ALTER TABLE `history_items` DROP COLUMN `display_svg`",
        "ALTER TABLE `history_items` DROP COLUMN `render_metadata_json`",
        "CREATE INDEX IF NOT EXISTS `index_history_items_thumbnail_path` ON `history_items` (`thumbnail_path`)",
        "CREATE INDEX IF NOT EXISTS `index_lineage_edges_parent_node_id` ON `lineage_edges` (`parent_node_id`)",
        "CREATE INDEX IF NOT EXISTS `index_variation_authority_variation_id` ON `variation_authority` (`variation_id`)",
        "DROP TABLE IF EXISTS `color_catalogs`",
    )

    override fun migrate(db: SupportSQLiteDatabase) {
        STATEMENTS.forEach(db::execSQL)
    }
}
