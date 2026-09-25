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
        VariationAuthorityEntity::class,
        VariationAuthorityActionEntity::class,
        PipelineExecutionEntity::class,
        PipelineHistoryLinkEntity::class,
    ],
    version = InkuDatabase.SCHEMA_VERSION,
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
    abstract fun sharedPipelineDao(): SharedPipelineDao

    companion object {
        const val SCHEMA_VERSION = 12
        private const val DB_NAME = "inku.sqlite"

        val MIGRATION_11_12 = object : Migration(11, 12) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE `history_items` ADD COLUMN `catalog_mode` TEXT")
            }
        }

        val MIGRATION_10_11 = object : Migration(10, 11) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `variation_authority` (
                        `owner_id` TEXT NOT NULL,
                        `variation_id` TEXT NOT NULL,
                        `protocol_version` TEXT NOT NULL,
                        `revision` TEXT NOT NULL,
                        `origin` TEXT NOT NULL,
                        `authority` TEXT NOT NULL,
                        `source` TEXT NOT NULL,
                        `document_json` TEXT NOT NULL,
                        `ddl_digest` TEXT NOT NULL,
                        `authority_digest` TEXT NOT NULL,
                        `description` TEXT NOT NULL,
                        `derivation_kind` TEXT NOT NULL,
                        `parent_legacy_history_id` TEXT,
                        `parent_variation_id` TEXT,
                        `updated_at` INTEGER NOT NULL,
                        PRIMARY KEY(`owner_id`, `variation_id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_variation_authority_owner_id_parent_legacy_history_id` ON `variation_authority` (`owner_id`, `parent_legacy_history_id`)")
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_variation_authority_owner_id_parent_variation_id` ON `variation_authority` (`owner_id`, `parent_variation_id`)")
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `variation_authority_actions` (
                        `owner_id` TEXT NOT NULL,
                        `action_id` TEXT NOT NULL,
                        `variation_id` TEXT NOT NULL,
                        `request_digest` TEXT NOT NULL,
                        `action_fingerprint` TEXT NOT NULL,
                        `context_fingerprint` TEXT NOT NULL,
                        `ddl_digest` TEXT NOT NULL,
                        `revision` TEXT NOT NULL,
                        `authority_digest` TEXT NOT NULL,
                        `committed_at` INTEGER NOT NULL,
                        PRIMARY KEY(`owner_id`, `action_id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_variation_authority_actions_owner_id_variation_id_revision_ddl_digest` ON `variation_authority_actions` (`owner_id`, `variation_id`, `revision`, `ddl_digest`)")
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `pipeline_candidate_executions` (
                        `owner_id` TEXT NOT NULL,
                        `execution_id` TEXT NOT NULL,
                        `variation_id` TEXT NOT NULL,
                        `sequence` TEXT NOT NULL,
                        `state_bytes` BLOB NOT NULL,
                        `state_digest` TEXT NOT NULL,
                        `created_at` INTEGER NOT NULL,
                        `updated_at` INTEGER NOT NULL,
                        PRIMARY KEY(`owner_id`, `execution_id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_pipeline_candidate_executions_owner_id_variation_id_updated_at` ON `pipeline_candidate_executions` (`owner_id`, `variation_id`, `updated_at`)")
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `pipeline_history_links` (
                        `owner_id` TEXT NOT NULL,
                        `history_id` TEXT NOT NULL,
                        `variation_id` TEXT NOT NULL,
                        `revision` TEXT NOT NULL,
                        `ddl_digest` TEXT NOT NULL,
                        `fork_context_bytes` BLOB NOT NULL,
                        `fork_context_digest` TEXT NOT NULL,
                        PRIMARY KEY(`owner_id`, `history_id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS `index_pipeline_history_links_history_id` ON `pipeline_history_links` (`history_id`)")
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_pipeline_history_links_owner_id_variation_id` ON `pipeline_history_links` (`owner_id`, `variation_id`)")
            }
        }

        val FRESH_SCHEMA_CALLBACK = object : RoomDatabase.Callback() {
            override fun onCreate(db: SupportSQLiteDatabase) {
                super.onCreate(db)
                db.execSQL(
                    """
                    CREATE TRIGGER IF NOT EXISTS `ck_lineage_no_self_edge_insert`
                    BEFORE INSERT ON `lineage_edges`
                    WHEN NEW.`parent_node_id` = NEW.`child_node_id`
                    BEGIN
                        SELECT RAISE(ABORT, 'lineage edge cannot reference itself');
                    END
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TRIGGER IF NOT EXISTS `ck_lineage_no_self_edge_update`
                    BEFORE UPDATE ON `lineage_edges`
                    WHEN NEW.`parent_node_id` = NEW.`child_node_id`
                    BEGIN
                        SELECT RAISE(ABORT, 'lineage edge cannot reference itself');
                    END
                    """.trimIndent(),
                )
            }
        }

        fun open(context: Context): InkuDatabase {
            return when (val result = RoomV10ResetCoordinator.prepare(context)) {
                is RoomV10ResetCoordinator.Result.Ready -> openPrepared(context)
                is RoomV10ResetCoordinator.Result.Refused -> {
                    error("Database startup refused: ${result.reason}")
                }
            }
        }

        internal fun openPrepared(
            context: Context,
            databaseName: String = DB_NAME,
        ): InkuDatabase {
            return Room.databaseBuilder(
                context.applicationContext,
                InkuDatabase::class.java,
                databaseName,
            ).openHelperFactory(LargeRowOpenHelperFactory())
                .addMigrations(MIGRATION_10_11, MIGRATION_11_12).addCallback(FRESH_SCHEMA_CALLBACK).build()
        }
    }
}
