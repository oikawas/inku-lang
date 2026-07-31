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
    version = 5,
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
            ).addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5).build()
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
                        `history_id` INTEGER,
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
    }
}
