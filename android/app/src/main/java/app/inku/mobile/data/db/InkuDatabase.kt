package app.inku.mobile.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        HistoryItemEntity::class,
        AppSettingEntity::class,
        ModelAssetEntity::class,
        ProviderSettingEntity::class,
        ColorCatalogEntity::class,
        PluginSettingEntity::class,
        ExportTemplateEntity::class,
        LineageNodeEntity::class,
        LineageEdgeEntity::class,
    ],
    version = 9,
    exportSchema = true,
)
abstract class InkuDatabase : RoomDatabase() {
    abstract fun historyDao(): HistoryDao
    abstract fun settingsDao(): SettingsDao
    abstract fun modelAssetDao(): ModelAssetDao
    abstract fun providerSettingDao(): ProviderSettingDao
    abstract fun colorCatalogDao(): ColorCatalogDao
    abstract fun pluginSettingDao(): PluginSettingDao
    abstract fun exportTemplateDao(): ExportTemplateDao
    abstract fun lineageDao(): LineageDao

    companion object {
        private const val DB_NAME = "inku.sqlite"

        fun open(context: Context): InkuDatabase {
            return Room.databaseBuilder(
                context.applicationContext,
                InkuDatabase::class.java,
                DB_NAME,
            ).addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6, MIGRATION_6_7, MIGRATION_7_8, MIGRATION_8_9).build()
        }

        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE history_items ADD COLUMN thumbnail_path TEXT")
                db.execSQL("ALTER TABLE history_items ADD COLUMN thumbnail_width INTEGER")
                db.execSQL("ALTER TABLE history_items ADD COLUMN thumbnail_height INTEGER")
            }
        }

        private val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_history_items_trashed_created_at` ON `history_items` (`trashed`, `created_at`)")
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_history_items_starred_trashed_created_at` ON `history_items` (`starred`, `trashed`, `created_at`)")
            }
        }

        private val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE history_items ADD COLUMN render_wild INTEGER")
            }
        }

        val MIGRATION_4_5 = object : Migration(4, 5) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE history_items ADD COLUMN lineage_node_id TEXT")
                db.execSQL("""
                    CREATE TABLE IF NOT EXISTS `lineage_nodes` (
                        `id` TEXT NOT NULL PRIMARY KEY,
                        `history_id` TEXT,
                        `state` TEXT NOT NULL,
                        `description_hash` TEXT,
                        `render_hash` TEXT,
                        `at` INTEGER NOT NULL,
                        `deleted_at` INTEGER,
                        `root_node_id` TEXT
                    )
                """.trimIndent())
                db.execSQL("""
                    CREATE TABLE IF NOT EXISTS `lineage_edges` (
                        `id` TEXT NOT NULL PRIMARY KEY,
                        `parent_node_id` TEXT NOT NULL,
                        `child_node_id` TEXT NOT NULL,
                        `derivation_kind` TEXT NOT NULL,
                        `metadata_json` TEXT NOT NULL DEFAULT '{}',
                        `at` INTEGER NOT NULL
                    )
                """.trimIndent())
                db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS `uq_lineage_primary_parent` ON `lineage_edges` (`child_node_id`)")
            }
        }

        /**
         * The six columns a refinement needs to record what a work was made
         * with. The server added the same six to `history` one at a time
         * (`_HISTORY_COLUMN_MIGRATIONS`, `db.py:341-350`), all VARCHAR, all
         * nullable; this does it in one step because the client has no rows
         * between the two states.
         */
        val MIGRATION_5_6 = object : Migration(5, 6) {
            override fun migrate(db: SupportSQLiteDatabase) {
                listOf(
                    "render_seed",
                    "composition_seed",
                    "interpretation_seed",
                    "variation_amplitude",
                    "variation_seed",
                    "seed_text",
                ).forEach { column ->
                    db.execSQL("ALTER TABLE history_items ADD COLUMN $column TEXT")
                }
            }
        }

        /**
         * The language a work was asked for and drawn in, and the prose it was
         * drawn from. All three are nullable Text on the server too
         * (`db.py:129-130`, `:170`), and NULL is what a row that predates them
         * holds -- readers fall back to `original_input` for the third and treat
         * the first two as "this work does not say".
         */
        val MIGRATION_6_7 = object : Migration(6, 7) {
            override fun migrate(db: SupportSQLiteDatabase) {
                listOf(
                    "instruction_lang_requested",
                    "instruction_lang_resolved",
                    "source_text",
                ).forEach { column ->
                    db.execSQL("ALTER TABLE history_items ADD COLUMN $column TEXT")
                }
            }
        }

        /**
         * 写生 (Stage 0.5): the prose the work was painted from, the grain it
         * was cut at, and what the layer did. All three are nullable Text on the
         * server too, and every row that exists before this runs keeps NULL in
         * all three.
         *
         * That NULL is the point. It is the sixth state -- "this work was drawn
         * before the layer was recorded" -- and it reads differently from every
         * recorded state, `off` included. Backfilling `off` here would say the
         * author switched the layer off on works drawn before there was a
         * layer to switch off.
         */
        val MIGRATION_7_8 = object : Migration(7, 8) {
            override fun migrate(db: SupportSQLiteDatabase) {
                listOf(
                    "sketch_text",
                    "sketch_grain",
                    "sketch_state",
                ).forEach { column ->
                    db.execSQL("ALTER TABLE history_items ADD COLUMN $column TEXT")
                }
            }
        }

        /**
         * The same drawing reached twice is two works, as it is on the server.
         *
         * `history.render_hash` carries no unique constraint there: the column
         * is declared `index=True` and nothing more (`db.py:178`), the index is
         * created as a plain `CREATE INDEX` (`db.py:653`), and the one place
         * that drops a duplicate on the save path keys off the caller's explicit
         * `idempotency_key` (`db.py:2965`), never off the hash. A primary-key
         * collision is re-raised rather than absorbed (`db.py:2993`).
         *
         * The port had a unique index here instead, so a second arrival at the
         * same score replaced the first row: the save reported success and the
         * count never moved. This drops that index and rebuilds it non-unique.
         *
         * ⚠ The table is not rebuilt. Only the index is exchanged, so every work
         * already saved survives the migration -- a `CREATE TABLE ... SELECT`
         * round trip would put the author's existing rows at risk for a change
         * that touches no column.
         */
        val MIGRATION_8_9 = object : Migration(8, 9) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("DROP INDEX IF EXISTS `index_history_items_render_hash`")
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_history_items_render_hash` ON `history_items` (`render_hash`)")
            }
        }
    }
}
